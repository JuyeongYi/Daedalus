from __future__ import annotations

from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.strategy import ExpressionEvaluation, LLMEvaluation


def test_guard_with_expression():
    g = Guard(evaluation=ExpressionEvaluation(expression="${bb.count} > 0"))
    assert isinstance(g.evaluation, ExpressionEvaluation)


def test_guard_with_llm():
    g = Guard(evaluation=LLMEvaluation(prompt="준비 완료?"))
    assert g.evaluation.prompt == "준비 완료?"
