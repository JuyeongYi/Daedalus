# daedalus/model/fsm/walk.py
"""머신 재귀 순회 — ``CompositeState.sub_machine`` + ``ParallelState.regions[*].sub_machine``
을 내려가는 골격의 **단일 진실**.

같은 재귀 골격이 검증기·컴파일러·모델 정리·삭제 커맨드에 각각 복제돼 있었다.
한쪽만 고쳐지면 규칙마다 보는 그래프가 달라지므로(그 위험은
``project_rules._scan_transitions`` 주석이 이미 명시하고 있었다) 여기로 모은다.

**순수 fsm 모듈이다** — plugin/compiler/view 어느 쪽도 알지 못하므로 core 경계
계약(``tests/test_import_contracts.py``)에 저촉되지 않고 어디서든 임포트할 수 있다.

방문 순서 계약 (기존 사본들의 순서를 그대로 옮긴 것 — 산출 텍스트·검증 결과의
항목 순서가 여기에 달려 있다):

- ``iter_machines(sm)``: **자기 자신을 먼저** yield하고, ``sm.states`` 선언
  순서대로 ``CompositeState.sub_machine`` → ``ParallelState.regions[*].sub_machine``
  을 재귀한다.
- ``iter_states(sm)``: 상태 선언 순서의 **깊이 우선 전위(pre-order)** —
  상태를 먼저 yield하고 **곧바로** 그 상태의 하위 머신으로 내려간다.
  ``iter_machines``의 상태를 이어붙인 것과는 다르다(그쪽은 머신 단위로 묶인다).
  기존 사본 전부가 이 전위 순서였으므로 이쪽을 계약으로 삼는다.
- ``iter_transitions(sm)``: ``iter_machines`` 순서로 각 머신의 ``transitions``를
  선언 순서대로 yield한다(머신 단위 묶음).

``machine_rules._validate_machine``은 의도적으로 환원 대상이 아니다 — path
누적(``agent:``/``region:`` 접두)과 머신별 규칙 적용이 재귀 골격과 얽혀 있어
순회만 떼어내면 동작 불변을 보장하기 어렵다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from daedalus.model.fsm.state import CompositeState, ParallelState

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import State
    from daedalus.model.fsm.transition import Transition

__all__ = ["iter_machines", "iter_states", "iter_transitions"]


def _sub_machines(state) -> Iterator["StateMachine"]:
    """한 상태가 직접 소유한 하위 머신들 (선언 순서)."""
    if isinstance(state, CompositeState):
        yield state.sub_machine
    elif isinstance(state, ParallelState):
        for region in state.regions:
            yield region.sub_machine


def iter_machines(sm: "StateMachine") -> Iterator["StateMachine"]:
    """``sm``과 그 하위 머신 전부를 yield한다 (자기 자신 먼저, 상태 선언 순서)."""
    if sm is None:
        return
    yield sm
    for state in getattr(sm, "states", None) or []:
        for sub in _sub_machines(state):
            yield from iter_machines(sub)


def iter_states(sm: "StateMachine") -> Iterator["State"]:
    """``sm``의 모든 상태를 깊이 우선 전위 순서로 yield한다.

    상태를 yield한 **직후** 그 상태의 하위 머신으로 내려간다 — 기존 사본
    (``_scan_state_access``/``_collect_state_access``/``_nullify_skill_refs_in_machine``
    /``_skill_ref_holders``)이 공유하던 순서다.
    """
    if sm is None:
        return
    for state in getattr(sm, "states", None) or []:
        yield state
        for sub in _sub_machines(state):
            yield from iter_states(sub)


def iter_transitions(sm: "StateMachine") -> Iterator["Transition"]:
    """``sm``과 하위 머신 전부의 전이를 머신 단위(``iter_machines`` 순서)로 yield."""
    for machine in iter_machines(sm):
        yield from (getattr(machine, "transitions", None) or [])
