from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


# ── 평가 전략 (Guard용) ──


@dataclass
class EvaluationStrategy(ABC):
    """전이 조건 평가 방식."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """전략 종류 식별자."""


@dataclass
class LLMEvaluation(EvaluationStrategy):
    """LLM 자연어 판단."""
    prompt: str = ""

    @property
    def kind(self) -> str:
        return "llm_evaluation"


@dataclass
class ToolEvaluation(EvaluationStrategy):
    """CLI 도구 실행 결과 판단."""
    tool: str = ""
    command: str = ""
    success_condition: str = ""

    @property
    def kind(self) -> str:
        return "tool_evaluation"


@dataclass
class MCPEvaluation(EvaluationStrategy):
    """MCP 도구 호출 결과 판단."""
    server: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    success_condition: str = ""

    @property
    def kind(self) -> str:
        return "mcp_evaluation"


@dataclass
class ExpressionEvaluation(EvaluationStrategy):
    """BB 변수 기반 표현식 평가."""
    expression: str = ""

    @property
    def kind(self) -> str:
        return "expression_evaluation"


@dataclass
class CompositeEvaluation(EvaluationStrategy):
    """복합 조건 (AND/OR)."""
    operator: Literal["and", "or"] = "and"
    children: list[EvaluationStrategy] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "composite_evaluation"


# ── 실행 전략 (Action용) ──


@dataclass
class ExecutionStrategy(ABC):
    """액션 실행 방식."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """전략 종류 식별자."""


@dataclass
class LLMExecution(ExecutionStrategy):
    """LLM 프롬프트 실행."""
    prompt: str = ""

    @property
    def kind(self) -> str:
        return "llm_execution"


@dataclass
class ToolExecution(ExecutionStrategy):
    """CLI 도구 실행."""
    tool: str = ""
    command: str = ""

    @property
    def kind(self) -> str:
        return "tool_execution"


@dataclass
class MCPExecution(ExecutionStrategy):
    """MCP 도구 호출."""
    server: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "mcp_execution"


@dataclass
class CompositeExecution(ExecutionStrategy):
    """순차/병렬 실행 조합."""
    mode: Literal["sequential", "parallel"] = "sequential"
    children: list[ExecutionStrategy] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "composite_execution"
