from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from daedalus.model.fsm.blackboard import Blackboard
from daedalus.model.fsm.state import State
from daedalus.model.fsm.transition import Transition


@dataclass(eq=False)
class StateMachine:
    name: str
    initial_state: State
    id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    final_states: list[State] = field(default_factory=list)
    blackboard: Blackboard = field(default_factory=Blackboard)
