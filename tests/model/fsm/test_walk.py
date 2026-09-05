# tests/model/fsm/test_walk.py
"""model/fsm/walk.py — 머신 재귀 순회의 방문 순서 계약 고정.

이 순서가 곧 검증 경고의 나열 순서이고 컴파일 산출의 항목 순서다. 환원 대상
6곳이 전부 같은 골격을 복제하고 있었으므로, 여기서 순서를 못 박아 두지 않으면
어느 한 곳이 조용히 다른 그래프를 보게 된다.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    Region,
    SimpleState,
)
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.walk import iter_machines, iter_states, iter_transitions


def _machine(name: str, states: list, transitions: list | None = None) -> StateMachine:
    return StateMachine(
        name=name,
        initial_state=states[0],
        states=states,
        transitions=transitions or [],
    )


def _fixture():
    """중첩 픽스처.

        root: [s0, comp, par, s3]
          comp.sub  : [c0, deep_comp[d0]]
          par.r1.sub: [r1a]
          par.r2.sub: [r2a]

    각 머신에 전이를 하나씩 둔다.
    """
    d0 = SimpleState(name="d0")
    deep_sub = _machine("deep_sub", [d0], [Transition(id="t_deep", source=d0, target=d0)])
    deep_comp = CompositeState(name="deep_comp", sub_machine=deep_sub)

    c0 = SimpleState(name="c0")
    comp_sub = _machine(
        "comp_sub", [c0, deep_comp], [Transition(id="t_comp", source=c0, target=deep_comp)]
    )
    comp = CompositeState(name="comp", sub_machine=comp_sub)

    r1a = SimpleState(name="r1a")
    r1_sub = _machine("r1_sub", [r1a], [Transition(id="t_r1", source=r1a, target=r1a)])
    r2a = SimpleState(name="r2a")
    r2_sub = _machine("r2_sub", [r2a], [Transition(id="t_r2", source=r2a, target=r2a)])
    par = ParallelState(
        name="par",
        regions=[Region(name="r1", sub_machine=r1_sub), Region(name="r2", sub_machine=r2_sub)],
    )

    s0 = SimpleState(name="s0")
    s3 = SimpleState(name="s3")
    root = _machine("root", [s0, comp, par, s3], [Transition(id="t_root", source=s0, target=s3)])
    return root


def test_iter_machines_self_first_then_declaration_order():
    """자기 자신 먼저 → states 선언 순서로 sub_machine / regions[*] 재귀."""
    names = [m.name for m in iter_machines(_fixture())]
    assert names == ["root", "comp_sub", "deep_sub", "r1_sub", "r2_sub"]


def test_iter_states_depth_first_preorder():
    """상태를 yield한 직후 그 상태의 하위 머신으로 내려간다 (전위 순서)."""
    names = [s.name for s in iter_states(_fixture())]
    assert names == [
        "s0",
        "comp",
        "c0",
        "deep_comp",
        "d0",
        "par",
        "r1a",
        "r2a",
        "s3",
    ]


def test_iter_transitions_grouped_by_machine():
    """전이는 머신 단위 묶음 — iter_machines 순서 그대로."""
    names = [t.id for t in iter_transitions(_fixture())]
    assert names == ["t_root", "t_comp", "t_deep", "t_r1", "t_r2"]


def test_iter_states_matches_machine_states_as_a_set():
    """두 순회의 순서는 다르지만 대상 집합은 같다 (빠뜨리는 머신이 없다)."""
    root = _fixture()
    from_states = {id(s) for s in iter_states(root)}
    from_machines = {id(s) for m in iter_machines(root) for s in m.states}
    assert from_states == from_machines


def test_flat_machine_has_no_recursion():
    """중첩이 없으면 자기 자신 하나 — 하위 호환(기존 사본과 동일)."""
    s0 = SimpleState(name="s0")
    sm = _machine("flat", [s0], [Transition(id="t", source=s0, target=s0)])
    assert [m.name for m in iter_machines(sm)] == ["flat"]
    assert [s.name for s in iter_states(sm)] == ["s0"]
    assert [t.id for t in iter_transitions(sm)] == ["t"]


def test_empty_regions_and_none_are_safe():
    """빈 ParallelState·None 머신에서 죽지 않는다."""
    par = ParallelState(name="par", regions=[])
    sm = _machine("m", [par])
    assert [s.name for s in iter_states(sm)] == ["par"]
    assert list(iter_transitions(sm)) == []
    assert list(iter_machines(None)) == []
    assert list(iter_states(None)) == []
    assert list(iter_transitions(None)) == []
