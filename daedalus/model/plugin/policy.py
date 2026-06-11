from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# JoinStrategy는 model/fsm/join.py로 이전됨 (순수 FSM 개념). 하위 호환을 위해
# 기존 import 경로(daedalus.model.plugin.policy.JoinStrategy)를 re-export로 유지한다.
from daedalus.model.fsm.join import JoinStrategy

__all__ = ["ExecutionPolicy", "JoinStrategy"]


@dataclass
class ExecutionPolicy:
    mode: Literal["fixed", "dynamic"] = "fixed"
    count: int = 1
    join: JoinStrategy = JoinStrategy.ALL
    join_count: int | None = None
