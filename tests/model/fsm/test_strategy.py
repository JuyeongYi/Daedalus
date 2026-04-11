from __future__ import annotations

import pytest
from daedalus.model.fsm.strategy import (
    EvaluationStrategy,
    LLMEvaluation,
    ToolEvaluation,
    MCPEvaluation,
    ExpressionEvaluation,
    CompositeEvaluation,
    ExecutionStrategy,
    LLMExecution,
    ToolExecution,
    MCPExecution,
    CompositeExecution,
)


# -- EvaluationStrategy --

def test_evaluation_strategy_is_abstract():
    with pytest.raises(TypeError):
        EvaluationStrategy()


def test_llm_evaluation():
    e = LLMEvaluation(prompt="빌드가 성공했는가?")
    assert e.prompt == "빌드가 성공했는가?"


def test_tool_evaluation():
    e = ToolEvaluation(tool="Bash", command="npm test", success_condition="exit_code == 0")
    assert e.tool == "Bash"
    assert e.command == "npm test"
    assert e.success_condition == "exit_code == 0"


def test_mcp_evaluation():
    e = MCPEvaluation(
        server="github",
        tool="get_pr_status",
        arguments={"pr": 123},
        success_condition="result == 'merged'",
    )
    assert e.server == "github"
    assert e.arguments == {"pr": 123}


def test_expression_evaluation():
    e = ExpressionEvaluation(expression="${bb.retry_count} < 3")
    assert e.expression == "${bb.retry_count} < 3"


def test_composite_evaluation():
    child1 = LLMEvaluation(prompt="코드 품질 충분?")
    child2 = ToolEvaluation(tool="Bash", command="npm test", success_condition="exit_code == 0")
    comp = CompositeEvaluation(operator="and", children=[child1, child2])
    assert comp.operator == "and"
    assert len(comp.children) == 2


# -- ExecutionStrategy --

def test_execution_strategy_is_abstract():
    with pytest.raises(TypeError):
        ExecutionStrategy()


def test_llm_execution():
    e = LLMExecution(prompt="코드를 리뷰해라")
    assert e.prompt == "코드를 리뷰해라"


def test_tool_execution():
    e = ToolExecution(tool="Bash", command="npm run build")
    assert e.tool == "Bash"
    assert e.command == "npm run build"


def test_mcp_execution():
    e = MCPExecution(server="slack", tool="send_message", arguments={"channel": "#dev"})
    assert e.server == "slack"


def test_composite_execution_sequential():
    c1 = ToolExecution(tool="Bash", command="npm test")
    c2 = ToolExecution(tool="Bash", command="npm run build")
    comp = CompositeExecution(mode="sequential", children=[c1, c2])
    assert comp.mode == "sequential"
    assert len(comp.children) == 2


def test_composite_execution_parallel():
    c1 = LLMExecution(prompt="분석1")
    c2 = LLMExecution(prompt="분석2")
    comp = CompositeExecution(mode="parallel", children=[c1, c2])
    assert comp.mode == "parallel"
