"""컴파일 dry-run — 파일을 하나도 쓰지 않는 예행 (G3).

컴파일러가 emit하는 경고 7종(dangling_file_ref / unknown_skill_files_dir /
dangling_skill_file_ref / missing_mcp_server_def / unmergeable_settings_json /
unmergeable_claude_md / rule_body_frontmatter)은 `Validator.validate_project`에
나오지 않아 **실제 컴파일에서만** 드러났다. dry-run은 텍스트 생성·계획·스캔·
LOCAL 병합 판정을 전부 돌리고 쓰기/복사/병합만 생략해 그것을 미리 보여준다.

게이트: ① dry-run 후 디스크가 바이트 단위로 불변일 것 ② 판정(errors/warnings/
계획 경로/토큰)이 실제 컴파일과 일치할 것. 둘 중 하나만 지키면 쓸모가 없다 —
불변이 아니면 검사가 아니고, 일치하지 않으면 "검사는 통과했는데 컴파일하면
경고가 뜬다"가 된다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.compiler import compile_project
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import BuildTarget, ModelType
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


def _snapshot(root) -> dict[str, bytes]:
    """트리의 모든 파일 내용 스냅샷 — dry-run 불변 판정용."""
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _findings(result) -> list[tuple[str, str]]:
    return [(e.rule, e.source or "") for e in (*result.errors, *result.warnings)]


# ─────────────────────── 디스크 불변 ───────────────────────


def test_dry_run_writes_nothing_marketplace(tmp_path):
    out = tmp_path / "out"
    project = PluginProject(name="p", skills=[make_procedural()])

    result = compile_project(project, out, dry_run=True)

    assert result.ok
    assert result.dry_run is True
    assert not out.exists()          # 디렉토리조차 만들지 않는다
    assert result.written            # 그러나 "쓰였을" 경로는 보고한다
    assert all(not p.exists() for p in result.written)


def test_dry_run_leaves_existing_output_untouched(tmp_path):
    """이미 컴파일한 폴더에 dry-run을 돌려도 한 바이트도 바뀌지 않는다."""
    out = tmp_path / "out"
    project = PluginProject(name="p", skills=[make_procedural()])
    compile_project(project, out)
    before = _snapshot(out)

    # 산출이 달라질 편집을 한 뒤 dry-run — 그래도 디스크는 그대로다.
    project.skills[0].body = "# Instructions\n\nSomething entirely different."
    compile_project(project, out, dry_run=True)

    assert _snapshot(out) == before


def test_dry_run_does_not_clear_stale_files_dir(tmp_path):
    """실제 컴파일은 <out>/files/를 지우고 다시 복사한다 — dry-run은 지우지 않는다."""
    out = tmp_path / "out"
    files = tmp_path / "files"
    files.mkdir()
    (files / "a.txt").write_bytes(b"A")
    project = PluginProject(name="p", skills=[make_procedural()])
    compile_project(project, out, files_dir=files)
    (out / "files" / "stale.txt").write_bytes(b"STALE")

    result = compile_project(project, out, files_dir=files, dry_run=True)

    assert (out / "files" / "stale.txt").read_bytes() == b"STALE"
    assert result.copied_files == [out / "files" / "a.txt"]


# ─────────────────────── 실제 컴파일과의 일치 ───────────────────────


def test_dry_run_matches_real_compile(tmp_path):
    """판정·계획 경로·토큰이 실제 컴파일과 같다."""
    files = tmp_path / "files"
    files.mkdir()
    (files / "kept.txt").write_bytes(b"K")
    skill_files = tmp_path / "skill-files"
    (skill_files / "orphan-dir").mkdir(parents=True)
    (skill_files / "orphan-dir" / "x.md").write_bytes(b"x")

    skill = make_procedural(
        body="See ${ROOT}/files/missing.txt and ${CLAUDE_SKILL_DIR}/nope.md",
    )
    project = PluginProject(name="p", skills=[skill])

    dry = compile_project(
        project, tmp_path / "dry", files_dir=files, skill_files_dir=skill_files,
        dry_run=True,
    )
    real = compile_project(
        project, tmp_path / "real", files_dir=files, skill_files_dir=skill_files,
    )

    assert _findings(dry) == _findings(real)
    assert {"dangling_file_ref", "dangling_skill_file_ref", "unknown_skill_files_dir"} <= {
        rule for rule, _ in _findings(dry)
    }
    assert [p.relative_to(tmp_path / "dry") for p in dry.written] == [
        p.relative_to(tmp_path / "real") for p in real.written
    ]
    assert [p.relative_to(tmp_path / "dry") for p in dry.copied_files] == [
        p.relative_to(tmp_path / "real") for p in real.copied_files
    ]
    assert dry.token_report.total_tokens == real.token_report.total_tokens
    assert dry.token_report.total_chars == real.token_report.total_chars


def test_dry_run_reports_gate_errors_like_real_compile(tmp_path):
    """게이트에 막히면 실제 컴파일과 같은 에러 + skipped를 낸다."""
    project = PluginProject(name="p", skills=[make_procedural(name="Bad Name")])

    dry = compile_project(project, tmp_path / "dry", dry_run=True)
    real = compile_project(project, tmp_path / "real", dry_run=False)

    assert not dry.ok and not real.ok
    assert _findings(dry) == _findings(real)
    assert dry.skipped == real.skipped
    assert dry.written == [] and real.written == []
    assert not (tmp_path / "real").exists()


# ─────────────────────── out_dir 생략 ───────────────────────


def test_out_dir_required_without_dry_run(tmp_path):
    project = PluginProject(name="p", skills=[make_procedural()])
    with pytest.raises(ValueError, match="dry_run"):
        compile_project(project, None)


def test_dry_run_without_out_dir_uses_relative_paths(tmp_path):
    project = PluginProject(name="p", skills=[make_procedural()])

    result = compile_project(project, None, dry_run=True)

    assert result.ok
    assert "skills/my-skill/SKILL.md" in [p.as_posix() for p in result.written]
    # 상대 경로라도 아무것도 만들어지지 않는다.
    assert not (tmp_path / "skills").exists()


def test_dry_run_without_out_dir_still_reports_path_independent_warnings(tmp_path):
    """`missing_mcp_server_def`는 대상 폴더와 무관하므로 out_dir 없이도 나온다."""
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.SONNET, tools=["mcp__github__search"])
    project = PluginProject(name="p", skills=[make_procedural()], agents=[agent])
    project.build_target = BuildTarget.LOCAL

    result = compile_project(project, None, dry_run=True)

    assert ("missing_mcp_server_def", "github") in _findings(result)


# ─────────────────────── LOCAL 병합 (읽기만) ───────────────────────


def _local_project() -> PluginProject:
    project = PluginProject(name="p", skills=[make_procedural()])
    project.build_target = BuildTarget.LOCAL
    project.claude_md = WorkspaceDoc(name="p", body="Follow the plan.")
    return project


def test_dry_run_does_not_merge_local_settings(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".claude").mkdir()
    (work / ".claude" / "CLAUDE.md").write_text("# Team\n\nkeep me\n", encoding="utf-8")
    (work / ".claude" / "settings.local.json").write_text(
        json.dumps({"env": {"A": "1"}}), encoding="utf-8",
    )
    project = _local_project()
    project.mcp_server_defs = {"github": {"type": "http", "url": "http://x/mcp"}}
    project.agents.append(make_agent())
    project.agents[0].config = AgentConfig(
        model=ModelType.SONNET, tools=["mcp__github__search"],
    )
    before = _snapshot(work)

    result = compile_project(project, work, dry_run=True)

    assert result.ok
    assert _snapshot(work) == before
    # 병합됐을 파일은 "쓰였을" 목록에 그대로 보고된다.
    written = {p.name for p in result.written}
    assert {".mcp.json", "settings.local.json", "CLAUDE.md"} <= written


def test_dry_run_detects_broken_settings_json(tmp_path):
    """깨진 JSON은 읽어서 판정만 한다 — 고치지도, 덮어쓰지도 않는다."""
    work = tmp_path / "work"
    (work / ".claude").mkdir(parents=True)
    broken = work / ".claude" / "settings.local.json"
    broken.write_text("{not json", encoding="utf-8")
    project = _local_project()
    project.mcp_server_defs = {"github": {"type": "http", "url": "http://x/mcp"}}
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.SONNET, tools=["mcp__github__search"])
    project.agents.append(agent)

    result = compile_project(project, work, dry_run=True)

    assert "unmergeable_settings_json" in {rule for rule, _ in _findings(result)}
    assert broken.read_text(encoding="utf-8") == "{not json"


def test_dry_run_detects_unmergeable_claude_md(tmp_path):
    """손상된 표식은 경고만 — 파일은 건드리지 않는다."""
    work = tmp_path / "work"
    (work / ".claude").mkdir(parents=True)
    md = work / ".claude" / "CLAUDE.md"
    md.write_text("<!-- daedalus:p open -->\nno close marker\n", encoding="utf-8")
    before = md.read_text(encoding="utf-8")

    result = compile_project(_local_project(), work, dry_run=True)

    assert "unmergeable_claude_md" in {rule for rule, _ in _findings(result)}
    assert md.read_text(encoding="utf-8") == before


def test_dry_run_without_out_dir_skips_merge_judgement(tmp_path):
    """out_dir 없이는 대상 폴더를 읽을 수 없어 병합 경고 판정을 건너뛴다."""
    result = compile_project(_local_project(), None, dry_run=True)

    rules = {rule for rule, _ in _findings(result)}
    assert "unmergeable_claude_md" not in rules
    assert "unmergeable_settings_json" not in rules
    # 그래도 CLAUDE.md 구역의 토큰 비용은 계상한다.
    assert any(e.kind == "claude_md" for e in result.token_report.entries)


def test_dry_run_reports_rule_body_frontmatter(tmp_path):
    project = _local_project()
    project.rules = [
        WorkspaceDoc(name="r", body="---\npaths: [x]\n---\nbody", paths=["src/**"])
    ]

    result = compile_project(project, tmp_path / "work", dry_run=True)

    assert "rule_body_frontmatter" in {rule for rule, _ in _findings(result)}
    assert not (tmp_path / "work").exists()


# ─────────────────────── copied_files 합류 ───────────────────────


def test_copied_files_includes_both_trees(tmp_path):
    """files/와 skill-files/를 함께 주면 둘 다 보고된다 (대입이면 앞의 것이 사라진다)."""
    files = tmp_path / "files"
    files.mkdir()
    (files / "shared.txt").write_bytes(b"S")
    skill_files = tmp_path / "skill-files" / "my-skill"
    skill_files.mkdir(parents=True)
    (skill_files / "ref.md").write_bytes(b"R")
    out = tmp_path / "out"
    project = PluginProject(name="p", skills=[make_procedural()])

    result = compile_project(
        project, out, files_dir=files, skill_files_dir=tmp_path / "skill-files",
    )

    assert result.ok
    assert set(result.copied_files) == {
        out / "skills" / "my-skill" / "ref.md",
        out / "files" / "shared.txt",
    }
