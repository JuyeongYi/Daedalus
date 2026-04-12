from __future__ import annotations

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import ModelType, AgentColor
from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def _make_fsm():
    s = SimpleState(name="s")
    return StateMachine(name="f", states=[s], initial_state=s)


def test_agent_definition():
    s1 = SimpleState(name="analyze")
    s2 = SimpleState(name="report")
    sm = StateMachine(name="review_flow", initial_state=s1, states=[s1, s2])
    agent = AgentDefinition(
        name="code-reviewer",
        description="코드 리뷰 에이전트",
        fsm=sm,
        config=AgentConfig(
            tools=["Read", "Grep"],
            model=ModelType.SONNET,
            color=AgentColor.BLUE,
        ),
    )
    assert agent.name == "code-reviewer"
    assert agent.fsm is sm
    assert agent.config.tools == ["Read", "Grep"]
    assert isinstance(agent, PluginComponent)
    assert isinstance(agent, WorkflowComponent)


def test_agent_execution_policy_default():
    s1 = SimpleState(name="s")
    sm = StateMachine(name="f", initial_state=s1)
    agent = AgentDefinition(
        name="worker",
        description="작업자",
        fsm=sm,
        config=AgentConfig(),
    )
    assert agent.execution_policy.mode == "fixed"
    assert agent.execution_policy.count == 1


def test_agent_execution_policy_parallel():
    s1 = SimpleState(name="s")
    sm = StateMachine(name="f", initial_state=s1)
    agent = AgentDefinition(
        name="researcher",
        description="연구 에이전트",
        fsm=sm,
        config=AgentConfig(),
        execution_policy=ExecutionPolicy(
            mode="fixed",
            count=3,
            join=JoinStrategy.ANY,
        ),
    )
    assert agent.execution_policy.count == 3
    assert agent.execution_policy.join == JoinStrategy.ANY


def test_agent_sections_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.sections == []


def test_agent_transfer_on_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert len(agent.transfer_on) == 1
    assert agent.transfer_on[0].name == "done"


def test_agent_output_events_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.output_events == ["done"]


def test_agent_output_events_via_property():
    """output_events는 transfer_on에서 파생된 읽기 전용 프로퍼티."""
    fsm = _make_fsm()
    agent = AgentDefinition(
        fsm=fsm, name="A", description="d",
        transfer_on=[EventDef("done"), EventDef("failed")],
    )
    assert agent.output_events == ["done", "failed"]
