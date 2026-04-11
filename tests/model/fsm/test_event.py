from __future__ import annotations

import pytest
from daedalus.model.fsm.event import (
    Event,
    StateEvent,
    BlackboardEvent,
    BlackboardTrigger,
    CompletionEvent,
)


def test_event_is_abstract():
    with pytest.raises(TypeError):
        Event(name="e")


def test_state_event_is_abstract():
    with pytest.raises(TypeError):
        StateEvent(name="e")


def test_blackboard_event_is_abstract():
    with pytest.raises(TypeError):
        BlackboardEvent(name="e")


def test_completion_event():
    ev = CompletionEvent(name="done")
    assert ev.name == "done"
    assert ev.kind == "completion"


def test_blackboard_trigger_instantiation():
    trigger = BlackboardTrigger(
        name="status_changed",
        variable="status",
    )
    assert trigger.name == "status_changed"
    assert trigger.variable == "status"
    assert trigger.condition is None


def test_blackboard_trigger_with_condition():
    from daedalus.model.fsm.strategy import ExpressionEvaluation

    cond = ExpressionEvaluation(expression="${bb.status} == 'done'")
    trigger = BlackboardTrigger(
        name="done_check",
        variable="status",
        condition=cond,
    )
    assert trigger.condition is cond
