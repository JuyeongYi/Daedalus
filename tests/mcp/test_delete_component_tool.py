"""MCP `delete_component` — 컴포넌트 삭제의 노출과 undo (A2).

GUI에서는 되는데 AI는 못 하는 편집이 남아 있으면 협업이 한쪽에서만 성립한다.
삭제는 정리 범위가 넓어 오래 미노출이었고, 여기서 확인하는 것은 **노출되었고
사용자의 undo 스택으로 되돌아오는가**다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


def _proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}-fsm", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    alpha, beta = _proc("alpha"), _proc("beta")
    entry = EntryPoint(name="entry")
    agent = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=entry, states=[entry]),
        name="worker", description="d", transfer_on=[EventDef(name="done")],
    )
    project = PluginProject(name="p", skills=[alpha, beta], agents=[agent])
    na = SimpleState(name="alpha", skill_ref=alpha)
    nb = SimpleState(name="beta", skill_ref=beta)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(Transition(source=na, target=nb))

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def test_tool_is_exposed():
    """TOOL_NAMES에 올라 있어야 CC가 부를 수 있다."""
    from daedalus.mcp.service import TOOL_NAMES
    from daedalus.mcp.tools import DaedalusTools

    assert "delete_component" in TOOL_NAMES
    assert hasattr(DaedalusTools, "delete_component")


def test_delete_skill_then_undo(tools, window):
    result = tools.delete_component("alpha")
    assert result["deleted"] == "alpha"
    assert [s.name for s in window._project.skills] == ["beta"]
    assert window._project.graph.transitions == []

    tools.undo()
    assert [s.name for s in window._project.skills] == ["alpha", "beta"]
    assert len(window._project.graph.transitions) == 1


def test_delete_agent(tools, window):
    tools.delete_component("worker")
    assert window._project.agents == []
    tools.undo()
    assert [a.name for a in window._project.agents] == ["worker"]


def test_unknown_name_is_rejected(tools):
    """오타는 그 자리에서 거절한다 — 조용히 아무것도 안 하면 왜 안 됐는지 모른다."""
    with pytest.raises(ValueError, match="찾을 수 없"):
        tools.delete_component("nope")


def test_still_referenced_by_is_reported(tools, window):
    """이름 참조는 정리하지 않고 **보고**한다.

    되돌렸을 때 참조가 돌아오지 않는 비대칭을 만들지 않기 위해 그대로 두고,
    남은 참조를 결과로 알려 dangling 경고를 예고한다.
    """
    agent = window._project.agents[0]
    agent.config.skills = ["alpha"]

    result = tools.delete_component("alpha")
    assert result["still_referenced_by"] == ["agent:worker.skills"]
    assert agent.config.skills == ["alpha"]  # 건드리지 않았다


def test_delete_appears_in_history(tools, window):
    """사람 편집과 같은 형식으로 히스토리에 남는다."""
    tools.delete_component("alpha")
    history = tools.get_history()
    assert history["can_undo"] is True
    entries = history["entries"]
    assert any("alpha" in entry["description"] for entry in entries)
    assert any('delete_component("alpha")' in entry["script"] for entry in entries)
