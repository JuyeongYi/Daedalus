# tests/compiler/test_gate.py
"""컴파일 게이트 — 에러는 거부, 경고만은 통과."""
from __future__ import annotations

from daedalus.compiler import compile_project
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agora_dispatch, make_delegation_skill, make_procedural


def test_error_project_rejected_no_files(tmp_path):
    # initial_state가 states에 없으면 initial_state_in_states 에러
    real = SimpleState(name="real")
    orphan = SimpleState(name="orphan")
    bad_fsm = StateMachine(name="bad", initial_state=orphan, states=[real])
    skill = make_procedural(name="bad-skill", fsm=bad_fsm)
    project = PluginProject(name="p", skills=[skill])

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.errors
    assert result.written == []
    # 출력 폴더에 파일이 없어야
    assert not list(tmp_path.rglob("*.md"))
    assert result.skipped


def test_warning_only_project_compiles_and_includes_warnings(tmp_path):
    # AgoraDispatch with msgtype empty → empty_delegation 경고. msgtype 채워 다른 경고만 유도.
    # 간단히: 정상 procedural 스킬 1개 + 경고 유발 위임 노드(미등록 delegation)
    from daedalus.model.plugin.delegation import AgoraDispatchDef

    deleg = AgoraDispatchDef(name="orphan-send", description="d", msgtype="")  # msgtype 빈값 = 경고
    skill = make_delegation_skill(deleg, name="warn-skill")
    project = PluginProject(name="p", skills=[skill], delegations=[deleg])

    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert result.warnings  # empty_delegation 경고 동봉
    assert result.written
    assert (tmp_path / "skills" / "warn-skill" / "SKILL.md").exists()


def test_clean_project_no_warnings(tmp_path):
    skill = make_procedural(name="clean-skill")
    project = PluginProject(name="p", skills=[skill])
    result = compile_project(project, tmp_path)
    assert result.ok
    assert result.warnings == []
    assert (tmp_path / "skills" / "clean-skill" / "SKILL.md").exists()
