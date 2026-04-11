from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from daedalus.model.fsm.machine import StateMachine


@dataclass
class PluginComponent(ABC):
    """플러그인 구성 요소 공통."""
    name: str
    description: str

    @property
    @abstractmethod
    def kind(self) -> str:
        """컴포넌트 종류 식별자."""


@dataclass
class WorkflowComponent(ABC):
    """FSM 보유 믹스인."""
    fsm: StateMachine
