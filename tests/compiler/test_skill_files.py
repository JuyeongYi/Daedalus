# tests/compiler/test_skill_files.py
"""스킬별 동봉 파일 (skill-files/) — 복사 + 경고 + 충돌 게이트 (WP-SF)."""
from __future__ import annotations

from pathlib import Path

from daedalus.compiler import compile_project
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


def _project(skill_name: str = "alpha", **kwargs) -> PluginProject:
    return PluginProject(
        name="p", skills=[make_procedural(name=skill_name)], **kwargs,
    )


def _make_skill_files(tmp_path, skill_name: str = "alpha") -> Path:
    root = tmp_path / "skill-files"
    sub = root / skill_name
    (sub / "scripts").mkdir(parents=True)
    (sub / "reference.md").write_bytes(b"ref-doc")
    (sub / "scripts" / "run.sh").write_bytes(b"#!/bin/sh")
    return root


# --- 하위 호환 ---


def test_omitted_skill_files_dir_is_backward_compatible(tmp_path):
    out = tmp_path / "out"
    result = compile_project(_project(), out)
    assert result.ok
    assert result.copied_files == []


def test_nonexistent_skill_files_dir_is_noop(tmp_path):
    out = tmp_path / "out"
    result = compile_project(
        _project(), out, skill_files_dir=tmp_path / "no-such-dir",
    )
    assert result.ok
    assert result.copied_files == []
    assert result.warnings == []


# --- 복사 ---


def test_files_copied_next_to_skill_md_marketplace(tmp_path):
    root = _make_skill_files(tmp_path)
    out = tmp_path / "out"
    result = compile_project(_project(), out, skill_files_dir=root)
    assert result.ok
    skill_dir = out / "skills" / "alpha"
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "reference.md").read_bytes() == b"ref-doc"
    assert (skill_dir / "scripts" / "run.sh").read_bytes() == b"#!/bin/sh"
    assert set(result.copied_files) == {
        skill_dir / "reference.md", skill_dir / "scripts" / "run.sh",
    }


def test_files_copied_under_dot_claude_in_local_build(tmp_path):
    """LOCAL은 컴파일이 곧 설치 — .claude/skills/ 밑으로 함께 간다."""
    root = _make_skill_files(tmp_path)
    out = tmp_path / "work"
    result = compile_project(
        _project(build_target=BuildTarget.LOCAL), out, skill_files_dir=root,
    )
    assert result.ok
    skill_dir = out / ".claude" / "skills" / "alpha"
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "reference.md").read_bytes() == b"ref-doc"


def test_local_skill_dir_name_matches(tmp_path):
    """legacy 로컬 스킬은 '<agent>--<skill>' 폴더명으로 매칭된다."""
    agent = make_agent(name="worker")
    agent.skills = [make_procedural(name="helper")]
    project = PluginProject(name="p", agents=[agent])
    root = tmp_path / "skill-files"
    (root / "worker--helper").mkdir(parents=True)
    (root / "worker--helper" / "data.txt").write_bytes(b"x")

    out = tmp_path / "out"
    result = compile_project(project, out, skill_files_dir=root)
    assert result.ok
    assert result.warnings == []
    assert (out / "skills" / "worker--helper" / "data.txt").read_bytes() == b"x"


# --- 경고 ---


def test_unknown_subdir_warns_and_skips(tmp_path):
    root = _make_skill_files(tmp_path)
    (root / "ghost").mkdir()
    (root / "ghost" / "orphan.md").write_text("x", encoding="utf-8")

    out = tmp_path / "out"
    result = compile_project(_project(), out, skill_files_dir=root)
    assert result.ok
    rules = [w.rule for w in result.warnings]
    assert rules.count("unknown_skill_files_dir") == 1
    assert not (out / "skills" / "ghost").exists()


def test_loose_file_under_root_warns(tmp_path):
    root = _make_skill_files(tmp_path)
    (root / "stray.txt").write_text("x", encoding="utf-8")

    result = compile_project(_project(), tmp_path / "out", skill_files_dir=root)
    assert result.ok
    assert any(
        w.rule == "unknown_skill_files_dir" and "stray.txt" in w.message
        for w in result.warnings
    )


# --- 충돌 게이트 ---


def test_skill_md_collision_is_rejected(tmp_path):
    """동봉 파일 이름이 SKILL.md면 산출 경로 충돌 에러로 컴파일 거부."""
    root = tmp_path / "skill-files"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "SKILL.md").write_text("evil", encoding="utf-8")

    out = tmp_path / "out"
    result = compile_project(_project(), out, skill_files_dir=root)
    assert not result.ok
    assert any(e.rule == "compile_output_path_conflict" for e in result.errors)
    assert not (out / "skills").exists()  # 게이트 거부 — 아무것도 안 쓴다


# --- dangling_skill_file_ref ---


def test_existing_ref_no_warning(tmp_path):
    root = _make_skill_files(tmp_path)
    skill = make_procedural(name="alpha")
    skill.body = "참고: ${CLAUDE_SKILL_DIR}/reference.md 를 읽어라."
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path / "out", skill_files_dir=root)
    assert result.ok
    assert [w for w in result.warnings if w.rule == "dangling_skill_file_ref"] == []


def test_missing_ref_warns(tmp_path):
    root = _make_skill_files(tmp_path)
    skill = make_procedural(name="alpha")
    skill.body = "참고: ${CLAUDE_SKILL_DIR}/missing.md"
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path / "out", skill_files_dir=root)
    assert result.ok
    warns = [w for w in result.warnings if w.rule == "dangling_skill_file_ref"]
    assert len(warns) == 1
    assert "missing.md" in warns[0].message


def test_cross_skill_ref_warns(tmp_path):
    """다른 스킬의 파일을 참조 — 런타임 SKILL_DIR에는 없으므로 경고."""
    root = _make_skill_files(tmp_path, skill_name="alpha")
    other = make_procedural(name="beta")
    other.body = "참고: ${CLAUDE_SKILL_DIR}/reference.md"  # alpha의 파일
    project = PluginProject(
        name="p", skills=[make_procedural(name="alpha"), other],
    )

    result = compile_project(project, tmp_path / "out", skill_files_dir=root)
    assert result.ok
    warns = [w for w in result.warnings if w.rule == "dangling_skill_file_ref"]
    assert len(warns) == 1
    assert warns[0].subject is other


def test_angle_wrapped_ref_with_spaces(tmp_path):
    root = tmp_path / "skill-files"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "my doc.md").write_text("x", encoding="utf-8")
    skill = make_procedural(name="alpha")
    skill.body = "참고: <${CLAUDE_SKILL_DIR}/my doc.md>"
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path / "out", skill_files_dir=root)
    assert result.ok
    assert [w for w in result.warnings if w.rule == "dangling_skill_file_ref"] == []
