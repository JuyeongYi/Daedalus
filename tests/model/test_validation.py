from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState, ParallelState, Region
from daedalus.model.fsm.pseudo import ChoiceState, HistoryState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable, VariableScope
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution
from daedalus.model.fsm.event import CompletionEvent


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


# -- initial_state_in_states --

def test_initial_state_not_in_states():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    sm = StateMachine(name="test", states=[s1], initial_state=s2)
    errors = Validator.validate(sm)
    assert any(e.rule == "initial_state_in_states" for e in errors)


def test_initial_state_in_states_ok():
    s1 = SimpleState(name="A")
    sm = StateMachine(name="test", states=[s1], initial_state=s1)
    errors = Validator.validate(sm)
    assert not any(e.rule == "initial_state_in_states" for e in errors)


# -- final_states_in_states --

def test_final_state_not_in_states():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    sm = StateMachine(name="test", states=[s1], initial_state=s1, final_states=[s2])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)


# -- pseudo_state_hooks --

def test_choice_state_with_hooks_warns():
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    choice = ChoiceState(name="c", on_entry=[action])
    sm = StateMachine(name="test", states=[choice], initial_state=choice)
    errors = Validator.validate(sm)
    assert any(e.rule == "pseudo_state_hooks" for e in errors)


def test_history_state_with_hooks_no_warning():
    """HistoryState는 on_entry 훅 허용."""
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    h = HistoryState(name="H", on_entry=[action])
    sm = StateMachine(name="test", states=[h], initial_state=h)
    errors = Validator.validate(sm)
    assert not any(e.rule == "pseudo_state_hooks" for e in errors)


def test_terminate_state_with_hooks_warns():
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    t = TerminateState(name="t", on_exit=[action])
    sm = StateMachine(name="test", states=[t], initial_state=t)
    errors = Validator.validate(sm)
    assert any(e.rule == "pseudo_state_hooks" for e in errors)


# -- completion_event_on_composite --

def test_composite_without_completion_trigger_warns():
    agent = _make_agent("agent1", ["s1"])
    s2 = SimpleState(name="next")
    t = Transition(source=agent, target=s2)  # trigger=None
    sm = _make_sm([agent, s2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "completion_event_on_composite" for e in errors)


def test_composite_with_completion_trigger_ok():
    agent = _make_agent("agent1", ["s1"])
    s2 = SimpleState(name="next")
    t = Transition(source=agent, target=s2, trigger=CompletionEvent(name="done"))
    sm = _make_sm([agent, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "completion_event_on_composite" for e in errors)


# -- 재귀 검증 --

def test_recursive_validation_in_composite():
    """CompositeState 내부의 sub_machine도 검증."""
    inner_s1 = SimpleState(name="inner1")
    inner_s2 = SimpleState(name="inner2")
    inner_sm = StateMachine(
        name="inner",
        states=[inner_s1],
        initial_state=inner_s1,
        final_states=[inner_s2],  # inner_s2가 states에 없음
    )
    agent = CompositeState(name="agent", sub_machine=inner_sm)
    sm = _make_sm([agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)


def test_recursive_validation_in_region():
    """Region 내부의 sub_machine도 검증."""
    s1 = SimpleState(name="r_s1")
    s2 = SimpleState(name="r_s2")
    region_sm = StateMachine(
        name="region_flow",
        states=[s1],
        initial_state=s1,
        final_states=[s2],  # s2가 states에 없음
    )
    r = Region(name="r1", sub_machine=region_sm)
    ps = ParallelState(name="par", regions=[r])
    sm = _make_sm([ps], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)
