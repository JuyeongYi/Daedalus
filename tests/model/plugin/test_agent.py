from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy


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


def test_agent_output_events_from_exit_points():
    """output_events는 FSM의 ExitPoint 이름에서 파생."""
    entry = EntryPoint(name="entry")
    exit_ok = ExitPoint(name="success")
    exit_err = ExitPoint(name="error")
    fsm = StateMachine(
        name="f",
        states=[entry, exit_ok, exit_err],
        initial_state=entry,
        final_states=[exit_ok, exit_err],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert set(agent.output_events) == {"success", "error"}


def test_agent_exit_points_property():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done", color="#44aa44")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert len(agent.exit_points) == 1
    assert agent.exit_points[0].name == "done"
    assert agent.exit_points[0].color == "#44aa44"


def test_agent_output_event_defs():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done", color="#44aa44")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    defs = agent.output_event_defs
    assert len(defs) == 1
    assert defs[0].name == "done"
    assert defs[0].color == "#44aa44"


def test_agent_skills_default():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.skills == []


def test_agent_execution_policy_default():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert isinstance(agent.execution_policy, ExecutionPolicy)


def test_agent_execution_policy_parallel():
    fsm = _make_agent_fsm()
    policy = ExecutionPolicy(join=JoinStrategy.ANY)
    agent = AgentDefinition(fsm=fsm, name="A", description="d", execution_policy=policy)
    assert agent.execution_policy.join == JoinStrategy.ANY
