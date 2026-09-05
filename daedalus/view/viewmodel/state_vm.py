from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.state import State
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
    # WP-ER — 경유점(waypoint) 좌표 목록(소스→타깃 순서). 뷰 전용 —
    # 저장 시점에 PluginProject.edge_layout / AgentDefinition.edge_layout으로
    # (키: Transition.id) 평탄화된다.
    waypoints: list[tuple[float, float]] = field(default_factory=list)


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
