from __future__ import annotations

from daedalus.model.fsm.pseudo import (
    ChoiceState,
    TerminateState,
    EntryPoint,
    ExitPoint,
)


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


def test_exit_point_default_color():
    xp = ExitPoint(name="done")
    assert xp.color == "#cc6666"


def test_exit_point_custom_color():
    xp = ExitPoint(name="error", color="#cc3333")
    assert xp.color == "#cc3333"


def test_pseudo_states_are_distinct_by_identity():
    """pseudo 서브클래스도 eq=False 적용 — 동명 인스턴스는 별개 (감사 1-5)."""
    a = EntryPoint(name="e")
    b = EntryPoint(name="e")
    assert a != b
    assert a == a
