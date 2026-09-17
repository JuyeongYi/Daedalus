"""fork 스킬 MCP 패리티 (2026-09-13/2026-09-17) — 생성·3-way 전환·fork 에이전트 검증."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ForkSkill,
    ProceduralSkill,
    SyncForkSkill,
)
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


@pytest.mark.parametrize(
    ("kind", "cls"), [("sync_fork", SyncForkSkill), ("async_fork", AsyncForkSkill)]
)
def test_create_fork_skill_with_agent_and_undo(tools, window, kind, cls):
    out = tools.create_skill("scout", kind=kind, fork_agent="Explore")
    assert out["fork_agent"] == "Explore"
    skill = _skill(window, "scout")
    assert type(skill) is cls
    assert skill.config.agent == "Explore"
    # background는 종류가 정하는 FIXED 값이라 config에 없다(MCP도 못 쓴다).
    assert not hasattr(skill.config, "background")
    tools.undo()
    assert not any(s.name == "scout" for s in window._project.skills)


def test_create_fork_default_agent(tools, window):
    tools.create_skill("scout", kind="async_fork")
    assert _skill(window, "scout").config.agent == "general-purpose"


def test_create_fork_rejects_unknown_agent(tools):
    with pytest.raises(ValueError, match="general-purpose"):
        tools.create_skill("scout", kind="sync_fork", fork_agent="explore")


def test_background_is_not_a_settable_field(tools, window):
    """background는 매트릭스 전용 FIXED다 — 목록에도 없고 설정도 거절된다."""
    tools.convert_skill("init", "async_fork")
    fields = [f["field"] for f in tools.list_component_fields("init")["fields"]]
    assert "background" not in fields
    with pytest.raises(ValueError, match="background"):
        tools.set_component_field("init", "background", True)


def test_fork_agent_rejected_for_other_kinds(tools):
    with pytest.raises(ValueError, match="fork"):
        tools.create_skill("x", kind="procedural", fork_agent="Explore")


def test_convert_keeps_identity_reports_dropped_and_undoes(tools, window):
    skill = _skill(window, "init")
    skill.config.allowed_tools = ["Read"]
    out = tools.convert_skill("init", "sync_fork")
    assert out["changed"] is True
    assert out["dropped"] == {"allowed_tools": ["Read"]}
    assert _skill(window, "init") is skill
    assert isinstance(skill, ForkSkill)
    assert skill.config.agent == "general-purpose"
    tools.undo()
    assert type(skill) is ProceduralSkill
    assert skill.config.allowed_tools == ["Read"]


def test_sync_to_async_keeps_agent_and_drops_nothing(tools, window):
    """sync ↔ async는 같은 fork다 — fork 에이전트를 잃으면 안 된다."""
    tools.convert_skill("init", "sync_fork")
    tools.set_component_field("init", "agent", "Plan")
    out = tools.convert_skill("init", "async_fork")
    assert out["changed"] is True
    assert out["dropped"] == {}
    skill = _skill(window, "init")
    assert type(skill) is AsyncForkSkill
    assert skill.config.agent == "Plan"


def test_sync_to_async_keeps_allowed_tools(tools, window):
    """sync ↔ async는 드롭이 없다 — `allowed_tools`는 fork config의 실필드다.

    드롭 집합을 대상 종류만 보고 정하면 빈 기본값에 가려 눈에 띄지 않는 채
    사용자가 적어 둔 도구 목록이 사라진다.
    """
    tools.convert_skill("init", "sync_fork")
    _skill(window, "init").config.allowed_tools = ["Read", "Grep"]
    out = tools.convert_skill("init", "async_fork")
    assert out["dropped"] == {}
    assert _skill(window, "init").config.allowed_tools == ["Read", "Grep"]


def test_convert_back_to_procedural_drops_agent_attribute(tools, window):
    tools.convert_skill("init", "async_fork")
    out = tools.convert_skill("init", "procedural")
    assert out["dropped"] == {"agent": "general-purpose"}
    skill = _skill(window, "init")
    assert type(skill) is ProceduralSkill
    # 유령 속성이 남으면 MCP의 hasattr 게이트가 무력해진다.
    assert not hasattr(skill.config, "agent")


def test_convert_rejects_unknown_target(tools):
    with pytest.raises(ValueError, match="사용 가능"):
        tools.convert_skill("init", "fork")


def test_convert_same_kind_is_noop(tools):
    assert tools.convert_skill("init", "procedural")["changed"] is False


def test_convert_rejects_non_procedural(tools):
    with pytest.raises(ValueError, match="절차형"):
        tools.convert_skill("rules", "sync_fork")


def test_set_agent_field_is_validated(tools, window):
    tools.convert_skill("init", "sync_fork")
    tools.set_component_field("init", "agent", "Plan")
    assert _skill(window, "init").config.agent == "Plan"
    with pytest.raises(ValueError, match="사용 가능"):
        tools.set_component_field("init", "agent", "nope")


def test_agent_field_absent_on_procedural(tools):
    with pytest.raises(ValueError, match="agent"):
        tools.set_component_field("init", "agent", "Plan")
