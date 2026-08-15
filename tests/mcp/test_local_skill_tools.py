"""legacy 로컬 스킬을 다루는 MCP 도구의 agent 인자 (WP-AF 이후).

로컬 스킬 **생성**은 내부 FSM과 함께 퇴역했지만, 기존 파일의 로컬 스킬은 계속
읽히고 컴파일된다 — 포트/본문/프론트매터 도구가 agent 인자로 여전히 닿아야 한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    project = PluginProject(name="p", skills=[skill])

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    t = DaedalusTools(window)
    t.create_agent("worker")
    # WP-AF — 로컬 스킬 생성 도구는 퇴역했다. 기존 파일에서 온 로컬 스킬을
    # 도구들이 여전히 다룰 수 있는지가 이 파일의 관심사이므로, legacy 상태를
    # 모델에 직접 구성한다.
    agent = t._find_component("worker")
    start = SimpleState(name="start")
    local_fsm = StateMachine(name="lf", states=[start], initial_state=start)
    agent.skills.append(
        ProceduralSkill(fsm=local_fsm, name="step-one", description="")
    )
    return t


def _local(tools, name="step-one"):
    return tools._find_component(name, agent="worker")


def test_set_transfer_on_reaches_local_skill(tools):
    tools.set_transfer_on(
        "step-one", [{"name": "ok"}, {"name": "retry"}], agent="worker"
    )
    assert [e.name for e in _local(tools).transfer_on] == ["ok", "retry"]


def test_legacy_entry_paths_are_inert(tools):
    """WP-IP — legacy 선언이 남아 있어도 산출·검증 어디에도 영향이 없다."""
    _local(tools).entry_paths.append(EventDef(name="stale"))
    out = tools.get_component("step-one", agent="worker")
    assert "entry_paths" not in out  # 조회 표면에서도 사라졌다


def test_set_component_body_reaches_local_skill(tools):
    tools.set_component_body("step-one", "# 본문", agent="worker")
    assert _local(tools).body == "# 본문"


def test_compile_preview_reaches_local_skill(tools):
    out = tools.compile_preview("step-one", agent="worker")
    assert out["name"] == "step-one"
    assert "step-one" in out["text"]


def test_without_agent_still_rejects_unknown_name(tools):
    """agent를 빠뜨리면 전역에서 찾다 실패한다 — 조용히 엉뚱한 걸 고치면 안 된다."""
    with pytest.raises(ValueError, match="step-one"):
        tools.set_transfer_on("step-one", [{"name": "ok"}])


def test_global_component_unaffected_by_agent_arg(tools):
    """agent를 줘도 전역 컴포넌트는 여전히 찾힌다(로컬을 먼저 볼 뿐)."""
    tools.set_transfer_on("init", [{"name": "done"}], agent="worker")
    assert [e.name for e in tools._find_component("init").transfer_on] == ["done"]


def test_local_skill_body_is_undoable_through_its_own_document(tools):
    tools.set_component_body("step-one", "첫 판", agent="worker")
    tools.set_component_body("step-one", "둘째 판", agent="worker")
    assert _local(tools).body == "둘째 판"
