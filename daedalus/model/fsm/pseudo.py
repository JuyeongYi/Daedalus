from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from daedalus.model.fsm.state import State


@dataclass
class HistoryState(State):
    """재진입 시 마지막 위치에서 재개."""
    mode: Literal["shallow", "deep"] = "shallow"

    @property
    def kind(self) -> str:
        return "history"


@dataclass
class ChoiceState(State):
    """즉시 평가 후 분기. 머무르지 않음."""

    @property
    def kind(self) -> str:
        return "choice"


@dataclass
class TerminateState(State):
    """FSM 강제 종료."""

    @property
    def kind(self) -> str:
        return "terminate"


@dataclass
class EntryPoint(State):
    """CompositeState의 특정 하위 상태로 직접 진입."""

    @property
    def kind(self) -> str:
        return "entry_point"


@dataclass
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
    color: str = "#cc6666"

    @property
    def kind(self) -> str:
        return "exit_point"
