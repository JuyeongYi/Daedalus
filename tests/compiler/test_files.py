# tests/compiler/test_files.py
"""컴파일 files/ 복사 + dangling_file_ref 경고 (WP-FR Part C)."""
from __future__ import annotations

import pytest

from daedalus.compiler import compile_project
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_procedural


def test_files_dir_omitted_is_backward_compatible(tmp_path):
    """files_dir 생략 — 기존 산출 파일/문자열 불변, files/ 생성 안 함."""
    out_dir = tmp_path / "out"
    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, out_dir)
    assert result.ok
    assert result.copied_files == []
    assert not (out_dir / "files").exists()


def test_files_dir_none_explicit_matches_omitted(tmp_path):
    """files_dir=None을 명시해도 생략과 동일한 산출(하위 호환)."""
    skill = make_procedural(name="clean-skill")

    out1 = tmp_path / "out1"
    result1 = compile_project(PluginProject(name="p", skills=[skill]), out1)
    out2 = tmp_path / "out2"
    result2 = compile_project(PluginProject(name="p", skills=[skill]), out2, files_dir=None)

    text1 = (out1 / "skills" / "clean-skill" / "SKILL.md").read_text(encoding="utf-8")
    text2 = (out2 / "skills" / "clean-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert text1 == text2
    assert result1.copied_files == result2.copied_files == []


def test_files_tree_copied_with_nested_structure(tmp_path):
    """중첩 구조가 그대로 <out>/files/에 바이트 동일하게 복사된다."""
    src = tmp_path / "src_files"
    (src / "A").mkdir(parents=True)
    (src / "A" / "c.txt").write_bytes(b"hello-bytes")
    (src / "top.txt").write_bytes(b"top-level")

    out_dir = tmp_path / "out"
    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, out_dir, files_dir=src)
    assert result.ok

    copied_top = out_dir / "files" / "top.txt"
    copied_nested = out_dir / "files" / "A" / "c.txt"
    assert copied_top.read_bytes() == b"top-level"
    assert copied_nested.read_bytes() == b"hello-bytes"
    assert set(result.copied_files) == {copied_top, copied_nested}


def test_stale_out_files_cleared_before_copy(tmp_path):
    """기존 <out>/files/ 잔존 파일은 복사 전에 삭제된다(out 전체가 아니라 files/만)."""
    src = tmp_path / "src_files"
    src.mkdir()
    (src / "new.txt").write_text("new", encoding="utf-8")

    out_dir = tmp_path / "out"
    (out_dir / "files").mkdir(parents=True)
    (out_dir / "files" / "stale.txt").write_text("stale", encoding="utf-8")
    # out 하위 다른 산출물은 보존되어야 하므로 마커 파일도 둔다
    (out_dir / "marker.txt").write_text("keep", encoding="utf-8")

    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, out_dir, files_dir=src)

    assert result.ok
    assert not (out_dir / "files" / "stale.txt").exists()
    assert (out_dir / "files" / "new.txt").exists()
    assert (out_dir / "marker.txt").exists()  # files/ 밖은 안 건드림


def test_files_dir_nonexistent_skips_copy_but_still_scans(tmp_path):
    """files_dir가 실존하지 않으면 복사는 생략하지만 dangling 스캔은 수행한다."""
    out_dir = tmp_path / "out"
    body = "참조: ${CLAUDE_PLUGIN_ROOT}/files/missing.txt"
    skill = make_procedural(name="clean-skill", body=body)
    project = PluginProject(name="p", skills=[skill])

    missing_src = tmp_path / "does-not-exist"
    result = compile_project(project, out_dir, files_dir=missing_src)

    assert result.ok
    assert result.copied_files == []
    dangling = [w for w in result.warnings if w.rule == "dangling_file_ref"]
    assert len(dangling) == 1
    assert "missing.txt" in dangling[0].message


def test_dangling_file_ref_warning_when_referenced_file_absent(tmp_path):
    src = tmp_path / "src_files"
    src.mkdir()
    body = "See ${CLAUDE_PLUGIN_ROOT}/files/ghost.txt for details."
    skill = make_procedural(name="ref-skill", body=body)
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path / "out", files_dir=src)
    assert result.ok
    dangling = [w for w in result.warnings if w.rule == "dangling_file_ref"]
    assert len(dangling) == 1
    assert dangling[0].subject is skill
    assert dangling[0].is_warning  # WARNING_RULES에 등록됨(view 표시 일관성)


def test_no_dangling_warning_when_referenced_file_exists(tmp_path):
    src = tmp_path / "src_files"
    (src / "A").mkdir(parents=True)
    (src / "A" / "c.txt").write_text("x", encoding="utf-8")
    body = "See ${CLAUDE_PLUGIN_ROOT}/files/A/c.txt for details."
    skill = make_procedural(name="ref-skill", body=body)
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path / "out", files_dir=src)
    assert result.ok
    dangling = [w for w in result.warnings if w.rule == "dangling_file_ref"]
    assert dangling == []


def test_dangling_scan_covers_agent_and_local_skill_bodies(tmp_path):
    from tests.compiler.builders import make_agent

    src = tmp_path / "src_files"
    src.mkdir()

    agent = make_agent("worker")
    agent.body = "Agent needs ${CLAUDE_PLUGIN_ROOT}/files/agent-missing.txt"
    local_skill = make_procedural(
        name="local-helper", body="Local ${CLAUDE_PLUGIN_ROOT}/files/local-missing.txt",
    )
    agent.skills = [local_skill]
    project = PluginProject(name="p", agents=[agent])

    result = compile_project(project, tmp_path / "out", files_dir=src)
    assert result.ok
    refs = {w.source for w in result.warnings if w.rule == "dangling_file_ref"}
    assert refs == {"agent-missing.txt", "local-missing.txt"}


def test_symlinks_are_not_followed(tmp_path):
    """심볼릭 링크는 따라가지 않는다 — 파일/디렉토리 심볼릭 링크 모두 스킵.

    Windows에서는 개발자 모드/관리자 권한 없이 심볼릭 링크 생성이 거부될 수
    있다 — 그 경우 이 플랫폼 제약과 무관하므로 테스트를 스킵한다.
    """
    src = tmp_path / "src_files"
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    (real_dir / "inner.txt").write_text("inner", encoding="utf-8")
    src.mkdir()
    (src / "kept.txt").write_text("kept", encoding="utf-8")

    try:
        (src / "link_dir").symlink_to(real_dir, target_is_directory=True)
        (src / "link_file.txt").symlink_to(src / "kept.txt")
    except OSError:
        pytest.skip("symlink 생성 권한 없음 (Windows 개발자 모드 필요)")

    out_dir = tmp_path / "out"
    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, out_dir, files_dir=src)

    assert result.ok
    assert (out_dir / "files" / "kept.txt").exists()
    assert not (out_dir / "files" / "link_file.txt").exists()
    assert not (out_dir / "files" / "link_dir" / "inner.txt").exists()


def test_gate_rejection_skips_copy_and_scan(tmp_path):
    """검증 게이트 에러로 거부되면 files/ 복사·스캔도 수행하지 않는다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState

    src = tmp_path / "src_files"
    src.mkdir()
    (src / "a.txt").write_text("a", encoding="utf-8")

    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad_fsm = StateMachine(name="bad", initial_state=orphan, states=[real])
    skill = make_procedural(name="bad-skill", fsm=bad_fsm)
    project = PluginProject(name="p", skills=[skill])

    out_dir = tmp_path / "out"
    result = compile_project(project, out_dir, files_dir=src)
    assert not result.ok
    assert result.copied_files == []
    assert not (out_dir / "files").exists()


# ── 리뷰 반영 회귀 (자기모순·정션·구두점) ──


def _proj_with_body(body: str):
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.model.project import PluginProject

    s = SimpleState(name="s")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name="alpha", description="d", body=body)
    return PluginProject(name="p", skills=[skill])


def test_angle_wrapped_space_path_not_flagged(tmp_path):
    """드롭이 만드는 <...> 감싼 공백 경로 토큰을 스캐너가 오탐하지 않는다
    (리뷰: Part B/C 자기모순)."""
    files = tmp_path / "files"
    files.mkdir()
    (files / "with space.txt").write_text("x", encoding="utf-8")
    project = _proj_with_body(
        "참조: <${CLAUDE_PLUGIN_ROOT}/files/with space.txt>\n"
    )
    result = compile_project(project, tmp_path / "out", files_dir=files)
    assert not [w for w in result.warnings if w.rule == "dangling_file_ref"]


def test_angle_wrapped_missing_path_still_flagged(tmp_path):
    files = tmp_path / "files"
    files.mkdir()
    project = _proj_with_body("참조: <${CLAUDE_PLUGIN_ROOT}/files/no such.txt>\n")
    result = compile_project(project, tmp_path / "out", files_dir=files)
    assert [w for w in result.warnings if w.rule == "dangling_file_ref"]


def test_trailing_punctuation_not_part_of_path(tmp_path):
    """쉼표·세미콜론·마침표 종결이 경로에 딸려 들어가 오탐하지 않는다."""
    files = tmp_path / "files"
    files.mkdir()
    (files / "top.txt").write_text("x", encoding="utf-8")
    project = _proj_with_body(
        "A: ${CLAUDE_PLUGIN_ROOT}/files/top.txt, "
        "B: ${CLAUDE_PLUGIN_ROOT}/files/top.txt; "
        "C: ${CLAUDE_PLUGIN_ROOT}/files/top.txt.\n"
    )
    result = compile_project(project, tmp_path / "out", files_dir=files)
    assert not [w for w in result.warnings if w.rule == "dangling_file_ref"]


def test_junction_like_dirs_excluded_from_copy(tmp_path, monkeypatch):
    """Windows 정션(is_symlink()=False)도 복사에서 제외된다 — files/ 밖 유출·
    폭주 재귀 방지 (리뷰 실측). isjunction을 몽키패치해 플랫폼 무관 검증."""
    import os as _os

    from daedalus.compiler import project_compiler as pc

    files = tmp_path / "files"
    (files / "normal").mkdir(parents=True)
    (files / "normal" / "ok.txt").write_text("ok", encoding="utf-8")
    fake_junction = files / "junction_dir"
    fake_junction.mkdir()
    (fake_junction / "secret.txt").write_text("SECRET", encoding="utf-8")

    monkeypatch.setattr(
        _os.path, "isjunction", lambda p: str(p).endswith("junction_dir"),
        raising=False,
    )
    project = _proj_with_body("본문\n")
    out = tmp_path / "out"
    compile_project(project, out, files_dir=files)
    assert (out / "files" / "normal" / "ok.txt").exists()
    assert not (out / "files" / "junction_dir").exists()
