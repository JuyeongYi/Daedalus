from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.variable import Variable

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine


@dataclass
class State(ABC):
    name: str
    # 진입 이벤트
    on_entry_start: list[Action] = field(default_factory=list)
    on_entry: list[Action] = field(default_factory=list)
    on_entry_end: list[Action] = field(default_factory=list)
    # 탈출 이벤트
    on_exit_start: list[Action] = field(default_factory=list)
    on_exit: list[Action] = field(default_factory=list)
    on_exit_end: list[Action] = field(default_factory=list)
    # 활동
    on_active: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    # 데이터
    inputs: list[Variable] = field(default_factory=list)
    outputs: list[Variable] = field(default_factory=list)

    @property
    @abstractmethod
    def kind(self) -> str:
        """상태 종류 식별자."""


@dataclass
class SimpleState(State):
    """리프 상태. 하위 상태 없음."""

    @property
    def kind(self) -> str:
        return "simple"


@dataclass
class Region:
    """ParallelState 내 독립 실행 단위."""
    name: str
    sub_machine: StateMachine


@dataclass
class CompositeState(State):
    """별도 컨텍스트의 상태 기계. 내부에 완전한 sub FSM 보유."""
    sub_machine: StateMachine = None

    @property
    def kind(self) -> str:
        return "composite"


@dataclass
class ParallelState(State):
    """병렬 리전. 동시 실행."""
    regions: list[Region] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "parallel"
