from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.variable import Variable

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.base import PluginComponent


@dataclass(eq=False)
class State(ABC):
    name: str
    # 안정 식별자 — 직렬화 시 참조 평탄화의 기준. identity 동등성/해시와는 무관.
    id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)
    on_entry_start: list[Action] = field(default_factory=list)
    on_entry: list[Action] = field(default_factory=list)
    on_entry_end: list[Action] = field(default_factory=list)
    on_exit_start: list[Action] = field(default_factory=list)
    on_exit: list[Action] = field(default_factory=list)
    on_exit_end: list[Action] = field(default_factory=list)
    on_active: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    inputs: list[Variable] = field(default_factory=list)
    outputs: list[Variable] = field(default_factory=list)
    # WP-BB — 상태 접근 선언. "Class" 또는 "Class.field" 문자열 참조(Tool 관례와
    # 동일 — 블랙보드 객체 참조 금지, fsm 레이어 순수성 유지). 실존은 Validator가 검증.
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)

    @property
    @abstractmethod
    def kind(self) -> str:
        """상태 종류 식별자."""


@dataclass(eq=False)
class SimpleState(State):
    """리프 상태. 하위 상태 없음."""
    # 배치될 수 있는 것만 온다 — 실체 판정은 `c.effective_placement() is
    # PlacementRole.STATE`(= `model.plugin.placement.is_state_placeable`)이고,
    # fork 에이전트처럼 PLACEMENT가 NONE인 종류는 여기 오지 않는다.
    #
    # 타입은 **종류 목록이 아니라 기저**다(Q35): 예전의
    # `StepSkill | DeclarativeSkill | AgentDefinition`은 배치 가능한
    # `WrappedSkill`이 빠져 있어도 아무도 실패하지 않는 낡은 선언 표였다
    # (스멜 ⑤). 새 종류는 `fsm/**`를 한 줄도 건드리지 않는다 —
    # `tests/model/fsm/test_state_is_kind_neutral.py`가 그것을 고정한다.
    skill_ref: PluginComponent | None = None

    @property
    def kind(self) -> str:
        return "simple"


@dataclass(eq=False)
class Region:
    """ParallelState 내 독립 실행 단위."""
    name: str
    sub_machine: StateMachine
    id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)


@dataclass(eq=False)
class CompositeState(State):
    """별도 컨텍스트의 상태 기계."""
    sub_machine: StateMachine = field(kw_only=True)

    @property
    def kind(self) -> str:
        return "composite"


@dataclass(eq=False)
class ParallelState(State):
    """병렬 리전. 동시 실행.

    join: 전 Region 완료 종합 전략 (기본 ALL). N_OF면 join_count개 완료 시 join.
    join_count: N_OF 전략에서 완료를 기다릴 Region 수 (그 외 전략에서는 무시).
    """
    regions: list[Region] = field(default_factory=list)
    join: JoinStrategy = JoinStrategy.ALL
    join_count: int | None = None

    @property
    def kind(self) -> str:
        return "parallel"
