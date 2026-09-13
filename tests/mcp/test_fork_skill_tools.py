"""fork 스킬 MCP 패리티 (2026-09-13) — 생성·전환·몸 에이전트 검증."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import DeclarativeSkill, ForkSkill, ProceduralSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    doc = DeclarativeSkill(name="rules", description="규칙", body="원본 본문")
    win = MainWindow()
    win.set_project(PluginProject(name="p", skills=[skill, doc]))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def _skill(window, name: str):
    return next(s for s in window._project.skills if s.name == name)


def test_create_fork_skill_with_agent_and_undo(tools, window):
    out = tools.create_skill("scout", kind="fork", fork_agent="Explore")
    assert out["fork_agent"] == "Explore"
    skill = _skill(window, "scout")
    assert isinstance(skill, ForkSkill)
    assert skill.config.agent == "Explore"
    tools.undo()
    assert not any(s.name == "scout" for s in window._project.skills)


def test_create_fork_default_agent(tools, window):
    tools.create_skill("scout", kind="fork")
    assert _skill(window, "scout").config.agent == "general-purpose"


def test_create_fork_rejects_unknown_agent(tools):
    with pytest.raises(ValueError, match="general-purpose"):
        tools.create_skill("scout", kind="fork", fork_agent="explore")


def test_fork_agent_rejected_for_other_kinds(tools):
    with pytest.raises(ValueError, match="fork"):
        tools.create_skill("x", kind="procedural", fork_agent="Explore")


def test_convert_keeps_identity_reports_dropped_and_undoes(tools, window):
    skill = _skill(window, "init")
    skill.config.allowed_tools = ["Read"]
    out = tools.convert_skill("init", "fork")
    assert out["changed"] is True
    assert out["dropped"] == {"allowed_tools": ["Read"]}
    assert _skill(window, "init") is skill
    assert isinstance(skill, ForkSkill)
    assert skill.config.agent == "general-purpose"
    tools.undo()
    assert type(skill) is ProceduralSkill
    assert skill.config.allowed_tools == ["Read"]


def test_convert_same_kind_is_noop(tools):
    assert tools.convert_skill("init", "procedural")["changed"] is False


def test_convert_rejects_non_procedural(tools):
    with pytest.raises(ValueError, match="절차형"):
        tools.convert_skill("rules", "fork")


def test_set_agent_field_is_validated(tools, window):
    tools.convert_skill("init", "fork")
    tools.set_component_field("init", "agent", "Plan")
    assert _skill(window, "init").config.agent == "Plan"
    with pytest.raises(ValueError, match="사용 가능"):
        tools.set_component_field("init", "agent", "nope")


def test_agent_field_absent_on_procedural(tools):
    with pytest.raises(ValueError, match="agent"):
        tools.set_component_field("init", "agent", "Plan")
