from __future__ import annotations

import pytest
from daedalus.model.fsm.state import (
    State,
    SimpleState,
    CompositeState,
    ParallelState,
    Region,
)
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution
from daedalus.model.fsm.variable import Variable, VariableScope
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.blackboard import Blackboard


def test_state_is_abstract():
    with pytest.raises(TypeError):
        State(name="s")


def test_simple_state():
    s = SimpleState(name="idle")
    assert s.name == "idle"
    assert s.on_entry == []
    assert s.on_exit == []
    assert s.inputs == []
    assert s.outputs == []
    assert s.custom_events == {}


def test_simple_state_with_actions():
    action = Action(name="greet", execution=LLMExecution(prompt="인사"))
    s = SimpleState(
        name="greeting",
        on_entry=[action],
    )
    assert len(s.on_entry) == 1
    assert s.on_entry[0].name == "greet"


def test_simple_state_with_io():
    inp = Variable(name="data", description="입력")
    out = Variable(name="result", description="출력", scope=VariableScope.BLACKBOARD)
    s = SimpleState(name="process", inputs=[inp], outputs=[out])
    assert len(s.inputs) == 1
    assert len(s.outputs) == 1
    assert s.outputs[0].scope == VariableScope.BLACKBOARD


def test_composite_state():
    s1 = SimpleState(name="s1")
    s2 = SimpleState(name="s2")
    t = Transition(source=s1, target=s2)
    sub = StateMachine(
        name="inner",
        states=[s1, s2],
        transitions=[t],
        initial_state=s1,
        final_states=[s2],
    )
    cs = CompositeState(name="agent_x", sub_machine=sub)
    assert cs.name == "agent_x"
    assert cs.sub_machine is sub
    assert len(cs.sub_machine.states) == 2
    assert len(cs.sub_machine.transitions) == 1
    assert cs.sub_machine.initial_state is s1
    assert cs.sub_machine.final_states == [s2]


def test_composite_state_blackboard_scoping():
    parent_bb = Blackboard()
    child_bb = Blackboard(parent=parent_bb)
    s1 = SimpleState(name="s1")
    sub = StateMachine(name="inner", initial_state=s1, states=[s1], blackboard=child_bb)
    cs = CompositeState(name="scoped", sub_machine=sub)
    assert cs.sub_machine.blackboard.parent is parent_bb


def test_region():
    s1 = SimpleState(name="r1_s1")
    sub = StateMachine(name="r1_flow", initial_state=s1, states=[s1])
    r = Region(name="region_1", sub_machine=sub)
    assert r.name == "region_1"
    assert r.sub_machine is sub
    assert r.sub_machine.initial_state is s1


def test_parallel_state():
    s1 = SimpleState(name="a")
    s2 = SimpleState(name="b")
    sub1 = StateMachine(name="r1_flow", initial_state=s1, states=[s1])
    sub2 = StateMachine(name="r2_flow", initial_state=s2, states=[s2])
    r1 = Region(name="r1", sub_machine=sub1)
    r2 = Region(name="r2", sub_machine=sub2)
    ps = ParallelState(name="parallel", regions=[r1, r2])
    assert len(ps.regions) == 2
    assert ps.regions[0].sub_machine.initial_state is s1
    assert ps.regions[1].sub_machine.initial_state is s2
