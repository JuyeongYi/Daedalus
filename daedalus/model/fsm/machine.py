from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.blackboard import Blackboard
from daedalus.model.fsm.state import State
from daedalus.model.fsm.transition import Transition


@dataclass
class StateMachine:
    name: str
    initial_state: State
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    final_states: list[State] = field(default_factory=list)
    blackboard: Blackboard = field(default_factory=Blackboard)
