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
