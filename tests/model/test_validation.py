from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable, VariableScope, VariableType


def _make_sm(states, transitions):
    return StateMachine(
        name="test",
        states=states,
        transitions=transitions,
        initial_state=states[0],
    )


def test_no_agent_inside_agent():
    """CompositeState 내부에 CompositeState 불가."""
    inner_agent = CompositeState(name="inner_agent", children=[SimpleState(name="x")])
    outer_agent = CompositeState(
        name="outer_agent",
        children=[inner_agent],
        initial_state=inner_agent,
    )
    sm = _make_sm([outer_agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_nested_agent" for e in errors)


def test_no_agent_to_agent_direct():
    """Agent→Agent 직접 엣지 불가."""
    a1 = CompositeState(name="agent1", children=[SimpleState(name="x")])
    a2 = CompositeState(name="agent2", children=[SimpleState(name="y")])
    t = Transition(source=a1, target=a2)
    sm = _make_sm([a1, a2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_agent_to_agent" for e in errors)


def test_valid_skill_to_agent():
    """Skill→Agent 엣지는 허용."""
    skill = SimpleState(name="skill_a")
    agent = CompositeState(name="agent_x", children=[SimpleState(name="s1")])
    t = Transition(source=skill, target=agent)
    sm = _make_sm([skill, agent], [t])
    errors = Validator.validate(sm)
    agent_errors = [e for e in errors if e.rule in ("no_agent_to_agent", "no_nested_agent")]
    assert agent_errors == []


def test_missing_required_input():
    """타겟의 필수 input이 data_map에 없으면 경고."""
    s1 = SimpleState(name="A", outputs=[Variable(name="result", description="r")])
    s2 = SimpleState(
        name="B",
        inputs=[Variable(name="data", description="d", required=True)],
    )
    t = Transition(source=s1, target=s2, data_map={})
    sm = _make_sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "missing_required_input" for e in errors)


def test_required_input_satisfied():
    """필수 input이 data_map에 있으면 에러 없음."""
    s1 = SimpleState(name="A", outputs=[Variable(name="result", description="r")])
    s2 = SimpleState(
        name="B",
        inputs=[Variable(name="data", description="d", required=True)],
    )
    t = Transition(source=s1, target=s2, data_map={"result": "data"})
    sm = _make_sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "missing_required_input" for e in errors)
