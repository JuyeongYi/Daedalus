from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.state import State


@dataclass(eq=False)
class ChoiceState(State):
    """즉시 평가 후 분기. 머무르지 않음."""

    @property
    def kind(self) -> str:
        return "choice"


@dataclass(eq=False)
class TerminateState(State):
    """FSM 강제 종료."""

    @property
    def kind(self) -> str:
        return "terminate"


@dataclass(eq=False)
class EntryPoint(State):
    """CompositeState의 특정 하위 상태로 직접 진입."""

    @property
    def kind(self) -> str:
        return "entry_point"


@dataclass(eq=False)
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
    color: str = "#cc6666"

    @property
    def kind(self) -> str:
        return "exit_point"
