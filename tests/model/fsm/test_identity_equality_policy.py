# tests/model/fsm/test_identity_equality_policy.py
"""FSM 계열의 **identity 동등성 + hashable 정책** 회귀망 (WP-11).

CLAUDE.md "dataclass 동등성 정책": FSM 모델 클래스(State 계열·pseudo 4종·
Transition·StateMachine·Region·Section)는 `@dataclass(eq=False)`다 — identity
동등성이고 hashable이다. 서브클래스에 `@dataclass`를 다시 적용하면서 `eq=False`를
빠뜨리면 `__eq__`가 재생성되고 **unhashable로 되돌아간다**.

그 회귀는 조용하다. `set`/`dict` 키로 쓰는 자리(`iter_states`의 방문 집합,
`_ordered_states`의 `seen`, 검증 규칙의 도달 집합)가 `TypeError`로 죽거나, 동명
상태 둘이 같은 것으로 취급돼 그래프가 접힌다. 클래스를 하나씩 개별 테스트에
적어 두면 새 종류가 생길 때 빠진다 — 그래서 **패키지를 훑어 전수**로 본다.

WP-11이 이 망을 도입한 이유: 상태·전략 사다리를 `singledispatch`로 바꾸며 FSM
클래스에 손을 댔고, 이 계열을 만질 때마다 `@dataclass` 재선언 함정이 열린다.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil

import pytest

import daedalus.model.fsm as fsm_pkg
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import (
    ChoiceState,
    EntryPoint,
    ExitPoint,
    TerminateState,
)
from daedalus.model.fsm.section import Section
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    Region,
    SimpleState,
    State,
)
from daedalus.model.fsm.transition import Transition


def _import_every_fsm_module() -> None:
    for info in pkgutil.walk_packages(fsm_pkg.__path__, prefix=fsm_pkg.__name__ + "."):
        importlib.import_module(info.name)


def _concrete_state_classes() -> set[type]:
    _import_every_fsm_module()
    found: set[type] = set()
    stack = [State]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub in found:
                continue
            found.add(sub)
            stack.append(sub)
    return {c for c in found if not inspect.isabstract(c) and c.__module__.startswith("daedalus.")}


def _machine() -> StateMachine:
    return StateMachine(name="m", initial_state=SimpleState(name="i"))


def _make(cls: type):
    """상태 한 개를 만든다 — 필수 kw 필드가 있는 종류만 특례."""
    if cls is CompositeState:
        return cls(name="n", sub_machine=_machine())
    return cls(name="n")


# ─────────────────── 상태 계열: 전수 (새 종류가 자동 합류) ───────────────────


def test_every_concrete_state_class_is_identity_equal():
    """동명 인스턴스 둘은 **다르다** — 값 동등성으로 되돌아가면 그래프가 접힌다."""
    for cls in _concrete_state_classes():
        a, b = _make(cls), _make(cls)
        assert a != b, f"{cls.__name__}: 값 동등성으로 되돌아갔다(eq=False 누락)"
        assert a == a, cls.__name__


def test_every_concrete_state_class_is_hashable():
    """`set`/`dict` 키로 쓸 수 있어야 한다 — 순회·검증이 전부 그렇게 쓴다."""
    for cls in _concrete_state_classes():
        state = _make(cls)
        assert hash(state) == hash(state), cls.__name__
        assert state in {state}, cls.__name__


def test_state_subclasses_do_not_regenerate_eq():
    """`__eq__`가 재생성되지 않았는지를 **직접** 본다(동등성 결과보다 이른 신호)."""
    for cls in _concrete_state_classes():
        assert cls.__eq__ is object.__eq__, (
            f"{cls.__name__}: @dataclass 재선언에서 eq=False를 빠뜨렸다"
        )
        assert cls.__hash__ is object.__hash__, cls.__name__


def test_the_scanner_actually_finds_the_known_state_classes():
    """스캐너가 조용히 빈 집합을 돌지 않는지."""
    found = _concrete_state_classes()
    for cls in (SimpleState, CompositeState, ParallelState, ChoiceState,
                TerminateState, EntryPoint, ExitPoint):
        assert cls in found, cls.__name__


# ─────────────────── 상태가 아닌 identity 정책 클래스 ───────────────────

_OTHER_IDENTITY_CLASSES = [
    lambda: _machine(),
    lambda: Region(name="r", sub_machine=_machine()),
    lambda: Section(title="s"),
    lambda: Transition(source=SimpleState(name="a"), target=SimpleState(name="b")),
]


@pytest.mark.parametrize("factory", _OTHER_IDENTITY_CLASSES)
def test_other_fsm_classes_are_identity_equal_and_hashable(factory):
    a, b = factory(), factory()
    assert a != b
    assert a == a
    assert a in {a}
    assert type(a).__eq__ is object.__eq__
    assert dataclasses.is_dataclass(a)
