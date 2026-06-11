from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.event import Event
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.state import State

if TYPE_CHECKING:
    from daedalus.model.plugin.skill import TransferSkill


class TransitionType(Enum):
    """전이 유형.

    역할 분리 (의미론 정본):
      - EXTERNAL: 상태를 벗어나는 일반 전이 (source의 exit 훅 발화 후 target의 entry 훅 발화).
        source ≠ target일 수도, 같을 수도 있다.
      - INTERNAL: **상태 비이탈** + guard/action이 있는 반응. entry/exit 훅을 **발화하지 않는다**.
        guard 평가나 액션 체인이 필요한 자기 반응에 쓴다. ``source is target`` 필수.
        단순 반응(guard·data_map 없이 액션만)은 INTERNAL 대신 ``State.custom_events``로 표현하라.
      - SELF: 상태를 떠났다 같은 상태로 재진입 (exit→entry 훅 재발화). ``source is target`` 필수.
      - LOCAL: composite 경계를 넘지 않는 지역 전이 (외곽 상태 재진입 회피).

    ``transition_type_consistency`` 검증 규칙이 INTERNAL/SELF의 ``source is target``을 강제한다.
    """
    EXTERNAL = "external"
    INTERNAL = "internal"
    SELF = "self"
    LOCAL = "local"


@dataclass(eq=False)
class Transition:
    source: State
    target: State
    id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)
    type: TransitionType = TransitionType.EXTERNAL
    trigger: Event | None = None
    guard: Guard | None = None
    # 이벤트
    on_guard_check: list[Action] = field(default_factory=list)
    on_traverse_start: list[Action] = field(default_factory=list)
    on_traverse: list[Action] = field(default_factory=list)
    on_traverse_end: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    # 데이터
    data_map: dict[str, str] = field(default_factory=dict)
    skill_ref: TransferSkill | None = None
