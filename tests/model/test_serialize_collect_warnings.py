"""deserialize_project collect_warnings 파라미터 테스트 (WP-J)."""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import DeclarativeSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import FORMAT_VERSION, deserialize_project, serialize_project


def _minimal_project_data() -> dict:
    """최소 직렬화 데이터 (위반 없음)."""
    project = PluginProject(name="p", skills=[DeclarativeSkill(name="x", description="d")])
    return serialize_project(project)


def _dangling_initial_state_data() -> dict:
    """initial_state가 존재하지 않는 ID를 가리키는 데이터 (dangling id 경고 유발)."""
    data = _minimal_project_data()
    # DeclarativeSkill은 FSM 없음 → 에이전트로 dangling 심기
    # 직접 FSM 데이터에 유령 initial_state id 삽입
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(name="af", states=[entry, done], initial_state=entry, final_states=[done])
    from daedalus.model.plugin.agent import AgentDefinition
    agent = AgentDefinition(fsm=fsm, name="my-agent", description="d")
    project = PluginProject(name="p", agents=[agent])
    agent_data = serialize_project(project)
    # agent_data의 agents[0].fsm.initial_state를 유령 id로 교체
    agent_data["agents"][0]["fsm"]["initial_state"] = "ghost-id-000"
    return agent_data


# ---------------------------------------------------------------------------
# 기존 시그니처 호환
# ---------------------------------------------------------------------------

def test_deserialize_without_collect_warnings_still_works():
    """collect_warnings 없이 호출해도 정상 동작한다 (기존 시그니처 호환)."""
    data = _minimal_project_data()
    project = deserialize_project(data)
    assert project.name == "p"


# ---------------------------------------------------------------------------
# collect_warnings 동작
# ---------------------------------------------------------------------------

def test_collect_warnings_empty_when_no_dangling():
    """dangling id 없으면 collect_warnings 리스트가 비어 있다."""
    data = _minimal_project_data()
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert project is not None
    assert warnings == []


def test_collect_warnings_filled_on_dangling_id():
    """dangling state id가 있으면 collect_warnings에 경고 문자열이 추가된다."""
    data = _dangling_initial_state_data()
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert project is not None
    assert len(warnings) >= 1
    assert any("ghost-id-000" in w for w in warnings)


def test_collect_warnings_none_does_not_raise():
    """collect_warnings=None (기본)이면 경고를 버리고 에러 없이 반환한다."""
    data = _dangling_initial_state_data()
    project = deserialize_project(data, collect_warnings=None)
    assert project is not None
