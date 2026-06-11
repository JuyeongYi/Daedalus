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
    """CLI 도구 실행 결과 판단.

    ``tool``은 프로젝트 ``tool_shelf``의 ``Tool.name``을 가리키는 **이름 문자열**이다
    (객체 참조 아님). fsm/는 Claude 무관 원칙이라 plugin 레이어의 Tool 객체를 알지
    못하므로, 결합은 이름으로만 하고 실존 여부는 Validator(dangling_tool_ref)가 검증한다.
    빈 문자열이면 미지정으로 간주(검증 스킵).
    """
    tool: str = ""
    command: str = ""
    success_condition: str = ""

    @property
    def kind(self) -> str:
        return "tool_evaluation"


@dataclass
class MCPEvaluation(EvaluationStrategy):
    """MCP 도구 호출 결과 판단.

    ``tool``은 tool_shelf의 Tool.name이 **아니라** MCP 서버 내 도구명이다 —
    참조 단위가 server+tool 조합이라 dangling_tool_ref 검사 대상이 아니다
    (MCP 서버 레지스트리 검증은 Tier 2).
    """
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
    """CLI 도구 실행.

    ``tool``은 프로젝트 ``tool_shelf``의 ``Tool.name``을 가리키는 **이름 문자열**이다
    (객체 참조 아님). fsm/는 Claude 무관 원칙이라 plugin 레이어의 Tool 객체를 알지
    못하므로, 결합은 이름으로만 하고 실존 여부는 Validator(dangling_tool_ref)가 검증한다.
    빈 문자열이면 미지정으로 간주(검증 스킵).
    """
    tool: str = ""
    command: str = ""

    @property
    def kind(self) -> str:
        return "tool_execution"


@dataclass
class MCPExecution(ExecutionStrategy):
    """MCP 도구 호출.

    ``tool``은 tool_shelf의 Tool.name이 **아니라** MCP 서버 내 도구명이다 —
    참조 단위가 server+tool 조합이라 dangling_tool_ref 검사 대상이 아니다
    (MCP 서버 레지스트리 검증은 Tier 2).
    """
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
