from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.event import Event
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.state import State


class TransitionType(Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    SELF = "self"
    LOCAL = "local"


@dataclass
class Transition:
    source: State
    target: State
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
    skill_ref: object | None = None  # TransferSkill | None (avoid circular import)
