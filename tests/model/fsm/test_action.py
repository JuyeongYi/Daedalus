from __future__ import annotations

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution, ToolExecution
from daedalus.model.fsm.variable import Variable


def test_action_basic():
    a = Action(
        name="run_tests",
        execution=ToolExecution(tool="Bash", command="pytest"),
    )
    assert a.name == "run_tests"
    assert a.output_variable is None


def test_action_with_output():
    var = Variable(name="result", description="테스트 결과")
    a = Action(
        name="analyze",
        execution=LLMExecution(prompt="코드 분석"),
        output_variable=var,
    )
    assert a.output_variable is var
    assert a.output_variable.name == "result"
