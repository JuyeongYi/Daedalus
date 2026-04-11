from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class JoinStrategy(Enum):
    ALL = "all"
    ANY = "any"
    N_OF = "n_of"


@dataclass
class ExecutionPolicy:
    mode: Literal["fixed", "dynamic"] = "fixed"
    count: int = 1
    join: JoinStrategy = JoinStrategy.ALL
    join_count: int | None = None
