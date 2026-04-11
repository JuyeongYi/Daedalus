from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daedalus.model.fsm.strategy import EvaluationStrategy


@dataclass
class Event(ABC):
    name: str

    @property
    @abstractmethod
    def kind(self) -> str:
        """이벤트 종류 식별자."""


@dataclass
class StateEvent(Event, ABC):
    """상태 관련 이벤트 베이스."""


@dataclass
class TransitionEvent(Event, ABC):
    """전이 관련 이벤트 베이스."""


@dataclass
class CompositeStateEvent(StateEvent, ABC):
    """CompositeState 전용 이벤트."""


@dataclass
class BlackboardEvent(Event, ABC):
    """블랙보드 변경 이벤트 베이스."""


@dataclass
class BlackboardTrigger(BlackboardEvent):
    """블랙보드 변수 변경 감지 트리거."""
    variable: str = ""
    condition: EvaluationStrategy | None = None

    @property
    def kind(self) -> str:
        return "blackboard_trigger"
