from __future__ import annotations

from daedalus.model.fsm.transition import Transition, TransitionType
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import ExpressionEvaluation, ToolExecution
from daedalus.model.fsm.event import BlackboardTrigger


def test_transition_type_enum():
    assert TransitionType.EXTERNAL.value == "external"
    assert TransitionType.INTERNAL.value == "internal"
    assert TransitionType.SELF.value == "self"
    assert TransitionType.LOCAL.value == "local"


def test_transition_basic():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    t = Transition(source=s1, target=s2)
    assert t.source is s1
    assert t.target is s2
    assert t.type == TransitionType.EXTERNAL
    assert t.trigger is None
    assert t.guard is None
    assert t.data_map == {}


def test_transition_with_guard():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    guard = Guard(evaluation=ExpressionEvaluation(expression="${bb.ready}"))
    t = Transition(source=s1, target=s2, guard=guard)
    assert t.guard is guard


def test_transition_with_trigger():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    trigger = BlackboardTrigger(name="status_change", variable="status")
    t = Transition(source=s1, target=s2, trigger=trigger)
    assert t.trigger is trigger


def test_transition_with_data_map():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    t = Transition(
        source=s1,
        target=s2,
        data_map={"result": "input_data", "status": "priority"},
    )
    assert t.data_map["result"] == "input_data"
    assert len(t.data_map) == 2


def test_transition_with_traverse_actions():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    action = Action(name="log", execution=ToolExecution(tool="Bash", command="echo transition"))
    t = Transition(
        source=s1,
        target=s2,
        on_traverse=[action],
    )
    assert len(t.on_traverse) == 1


def test_transition_self_type():
    s1 = SimpleState(name="A")
    t = Transition(source=s1, target=s1, type=TransitionType.SELF)
    assert t.type == TransitionType.SELF
    assert t.source is t.target
