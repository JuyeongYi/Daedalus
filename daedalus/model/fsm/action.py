from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.strategy import ExecutionStrategy
from daedalus.model.fsm.variable import Variable


@dataclass
class Action:
    name: str
    execution: ExecutionStrategy
    output_variable: Variable | None = None
