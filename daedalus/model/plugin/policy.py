from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# JoinStrategy는 순수 FSM 개념이라 model/fsm/join.py가 정본이다 — 필요한 곳은
# 거기서 직수입한다 (여기서는 ExecutionPolicy 기본값에만 쓴다).
from daedalus.model.fsm.join import JoinStrategy

__all__ = ["ExecutionPolicy"]


@dataclass
class ExecutionPolicy:
    mode: Literal["fixed", "dynamic"] = "fixed"
    count: int = 1
    join: JoinStrategy = JoinStrategy.ALL
    join_count: int | None = None
