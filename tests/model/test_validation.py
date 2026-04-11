from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable, VariableScope


def _make_sm(states, transitions):
    return StateMachine(
        name="test",
        states=states,
        transitions=transitions,
        initial_state=states[0],
    )


def _make_agent(name, child_names):
    """헬퍼: SimpleState 자식을 가진 CompositeState 생성."""
    children = [SimpleState(name=n) for n in child_names]
    sub = StateMachine(
        name=f"{name}_flow",
        states=children,
        initial_state=children[0],
    )
    return CompositeState(name=name, sub_machine=sub)


def test_no_agent_inside_agent():
    """CompositeState 내부에 CompositeState 불가."""
    inner_agent = _make_agent("inner_agent", ["x"])
    outer_sub = StateMachine(
        name="outer_flow",
        states=[inner_agent],
        initial_state=inner_agent,
    )
    outer_agent = CompositeState(name="outer_agent", sub_machine=outer_sub)
    sm = _make_sm([outer_agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_nested_agent" for e in errors)


def test_no_agent_to_agent_direct():
    """Agent→Agent 직접 엣지 불가."""
    a1 = _make_agent("agent1", ["x"])
    a2 = _make_agent("agent2", ["y"])
    t = Transition(source=a1, target=a2)
    sm = _make_sm([a1, a2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_agent_to_agent" for e in errors)


def test_valid_skill_to_agent():
    """Skill→Agent 엣지는 허용."""
    skill = SimpleState(name="skill_a")
    agent = _make_agent("agent_x", ["s1"])
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
