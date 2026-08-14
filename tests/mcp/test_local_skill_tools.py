"""로컬 스킬(에이전트 소속 스킬)을 다루는 MCP 도구의 agent 인자.

실제로 에이전트 내부 워크플로를 만들다 드러난 구멍이다: create_skill(agent=...)로
로컬 스킬을 만들 수는 있는데, 포트를 선언하거나 본문을 쓰려 하면 "컴포넌트를 찾을
수 없습니다"가 났다. 로컬 스킬은 project.skills에 없고 agent.skills에만 있다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
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
    t.create_skill("step-one", kind="procedural", agent="worker")
    return t


def _local(tools, name="step-one"):
    return tools._find_component(name, agent="worker")


def test_set_transfer_on_reaches_local_skill(tools):
    tools.set_transfer_on(
        "step-one", [{"name": "ok"}, {"name": "retry"}], agent="worker"
    )
    assert [e.name for e in _local(tools).transfer_on] == ["ok", "retry"]


def test_set_entry_paths_reaches_local_skill(tools):
    tools.set_entry_paths("step-one", [{"name": "fresh"}], agent="worker")
    assert [e.name for e in _local(tools).entry_paths] == ["fresh"]


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
