from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.strategy import EvaluationStrategy


@dataclass
class Guard:
    evaluation: EvaluationStrategy
