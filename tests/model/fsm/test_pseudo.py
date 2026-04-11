from __future__ import annotations

from daedalus.model.fsm.pseudo import (
    HistoryState,
    ChoiceState,
    TerminateState,
    EntryPoint,
    ExitPoint,
)


def test_history_state_shallow():
    h = HistoryState(name="H", mode="shallow")
    assert h.mode == "shallow"


def test_history_state_deep():
    h = HistoryState(name="H*", mode="deep")
    assert h.mode == "deep"


def test_choice_state():
    c = ChoiceState(name="check_status")
    assert c.name == "check_status"


def test_terminate_state():
    t = TerminateState(name="abort")
    assert t.name == "abort"


def test_entry_point():
    ep = EntryPoint(name="alt_entry")
    assert ep.name == "alt_entry"


def test_exit_point():
    xp = ExitPoint(name="error_exit")
    assert xp.name == "error_exit"
