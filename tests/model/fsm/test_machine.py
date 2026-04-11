from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.blackboard import Blackboard


def test_state_machine_basic():
    s1 = SimpleState(name="start")
    s2 = SimpleState(name="end")
    t = Transition(source=s1, target=s2)
    bb = Blackboard()
    sm = StateMachine(
        name="workflow",
        states=[s1, s2],
        transitions=[t],
        initial_state=s1,
        final_states=[s2],
        blackboard=bb,
    )
    assert sm.name == "workflow"
    assert len(sm.states) == 2
    assert len(sm.transitions) == 1
    assert sm.initial_state is s1
    assert sm.final_states == [s2]
    assert sm.blackboard is bb


def test_state_machine_defaults():
    s1 = SimpleState(name="only")
    sm = StateMachine(name="minimal", initial_state=s1)
    assert sm.states == []
    assert sm.transitions == []
    assert sm.final_states == []
    assert sm.blackboard is not None
