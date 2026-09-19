from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition


def _make_agent_fsm():
    """에이전트 기본 FSM — EntryPoint + ExitPoint."""
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm",
        states=[entry, exit_done],
        initial_state=entry,
        final_states=[exit_done],
    )


def test_agent_definition():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.name == "A"
    assert agent.description == "d"
    assert agent.kind == "agent"


def test_agent_body_default():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.body == ""


def test_agent_has_transfer_on_output_ports():
    """WP-AF — 에이전트의 결과 분기는 transfer_on(출력 포트)이 담는다
    (ExitPoint 승계, 스킬과 동일 필드)."""
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.transfer_on == []


def test_agent_output_ports_from_transfer_on():
    """RF-1b — 출력 포트는 transfer_on이 단일 진실 (ExitPoint 폴백 없음)."""
    from daedalus.model.fsm.section import EventDef

    fsm = _make_agent_fsm()
    agent = AgentDefinition(
        fsm=fsm, name="A", description="d",
        transfer_on=[EventDef("success"), EventDef("error")],
    )
    assert [e.name for e in agent.output_ports()] == ["success", "error"]


def test_agent_output_ports_ignore_fsm_exit_points():
    """FSM에 ExitPoint가 있어도 transfer_on이 비어 있으면 출력 포트도 없다 —
    v1 파일의 ExitPoint 승계는 로드 마이그레이션(serialize._migrate_v1) 소관."""
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done", color="#44aa44")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.output_ports() == []


def test_agent_output_ports_carry_event_defs():
    from daedalus.model.fsm.section import EventDef

    fsm = _make_agent_fsm()
    agent = AgentDefinition(
        fsm=fsm, name="A", description="d",
        transfer_on=[EventDef("done", color="#44aa44")],
    )
    defs = agent.output_ports()
    assert len(defs) == 1
    assert defs[0].name == "done"
    assert defs[0].color == "#44aa44"


def test_agent_does_not_own_the_graph():
    """그래프 소유 필드 4종은 퇴역했다 (2026-09-19) — 에이전트는 노드다.

    `execution_policy`/`reference_placements`/`graph_layout`/`edge_layout`은
    편집 표면 0에 직렬화 왕복만 하던 잔재였다. 실체는 `PluginProject`의
    동명 필드다(원칙 7 — 퇴역 개념은 흔적 없이).
    """
    import dataclasses

    agent = AgentDefinition(fsm=_make_agent_fsm(), name="A", description="d")
    names = {f.name for f in dataclasses.fields(agent)}
    for retired in (
        "execution_policy", "reference_placements", "graph_layout", "edge_layout",
    ):
        assert retired not in names, retired
        assert not hasattr(agent, retired), retired
