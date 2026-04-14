from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.state import SimpleState, State
from daedalus.model.fsm.transition import Transition


@dataclass(eq=False)
class StateViewModel:
    """State + UI 전용 상태."""

    model: State
    x: float = 0.0
    y: float = 0.0
    width: float = 140.0
    height: float = 60.0
    selected: bool = False


@dataclass(eq=False)
class TransitionViewModel:
    """Transition + UI 전용 상태."""

    model: Transition
    source_vm: StateViewModel
    target_vm: StateViewModel
    selected: bool = False


@dataclass(eq=False)
class ReferenceViewModel:
    """ReferenceSkill 노드의 뷰 모델."""

    model: object  # ReferenceSkill (circular import 방지)
    x: float = 0.0
    y: float = 0.0


@dataclass(eq=False)
class ReferenceLinkViewModel:
    """상태 노드 → 참조 노드 연결."""

    state_vm: StateViewModel
    reference_vm: ReferenceViewModel
