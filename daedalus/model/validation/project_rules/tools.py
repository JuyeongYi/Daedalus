# daedalus/model/validation/project_rules/tools.py
"""도구(tool_shelf) 규칙 + 참조 수집 헬퍼 (이동만 — 동작 불변)."""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.walk import iter_states, iter_transitions
from daedalus.model.validation.machine_rules import _MachineRules
from daedalus.model.validation.project_rules.scan import project_machines
from daedalus.model.validation.severity import ValidationError

# CC 내장 도구 이름 집합 — tool_shelf에 선언하지 않아도 ToolEvaluation/ToolExecution이
# 직접 참조할 수 있는 도구들. dangling_tool_ref 검사 시 shelf와 합쳐 유효 집합을 이룬다.
# (2026-06 기준 CC 1급 도구 + 본 환경 PowerShell. MCP 도구는 mcp__로 시작하므로 별도.)
CC_BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebFetch", "WebSearch", "Agent", "Task",
    "TodoWrite", "NotebookEdit", "SlashCommand", "PowerShell",
})


class _ToolRules:
    """도구(tool_shelf) 규칙 모음 (_ProjectRules 믹스인)."""

    _project_machines = staticmethod(project_machines)

    @staticmethod
    def _collect_eval_tools(ev: EvaluationStrategy | None) -> list[str]:
        """EvaluationStrategy(중첩 CompositeEvaluation 포함)에서 비어있지 않은
        ToolEvaluation.tool 이름을 수집한다.

        MCPEvaluation은 **의도적으로 제외** — MCPEvaluation.tool은 shelf의
        Tool.name이 아니라 MCP 서버 내 도구명이며, 참조 단위가 server+tool
        조합이라 dangling 검증은 Tier 2(MCP 서버 레지스트리)에서 별도 처리한다.
        """
        if ev is None:
            return []
        names: list[str] = []
        if isinstance(ev, ToolEvaluation):
            if ev.tool:
                names.append(ev.tool)
        elif isinstance(ev, CompositeEvaluation):
            for child in ev.children:
                names.extend(_ToolRules._collect_eval_tools(child))
        return names

    @staticmethod
    def _collect_exec_tools(ex: ExecutionStrategy | None) -> list[str]:
        """ExecutionStrategy(중첩 CompositeExecution 포함)에서 비어있지 않은
        ToolExecution.tool 이름을 수집한다.

        MCPExecution은 **의도적으로 제외** — _collect_eval_tools와 동일 사유
        (server+tool 조합이 참조 단위, Tier 2에서 별도 처리).
        """
        if ex is None:
            return []
        names: list[str] = []
        if isinstance(ex, ToolExecution):
            if ex.tool:
                names.append(ex.tool)
        elif isinstance(ex, CompositeExecution):
            for child in ex.children:
                names.extend(_ToolRules._collect_exec_tools(child))
        return names

    @staticmethod
    def _collect_machine_tool_refs(sm: StateMachine) -> list[str]:
        """머신 전체(상태 액션 체인 + 전이 가드/액션 체인)에서 참조하는 도구 이름을
        재귀적으로 수집한다. sub_machine(CompositeState)·Region도 내려간다.

        도구 참조 출처:
          - State 라이프사이클 훅 + custom_events의 Action.execution (ToolExecution)
          - Transition 가드 evaluation (ToolEvaluation) + 액션 체인 + custom_events
        """
        names: list[str] = []

        def _actions(lst) -> None:
            for a in (lst or []):
                names.extend(_ToolRules._collect_exec_tools(a.execution))

        for state in iter_states(sm):
            for fname in _MachineRules._STATE_ACTION_FIELDS:
                _actions(getattr(state, fname, None))
            for lst in getattr(state, "custom_events", {}).values():
                _actions(lst)

        for t in iter_transitions(sm):
            if t.guard is not None:
                names.extend(_ToolRules._collect_eval_tools(t.guard.evaluation))
            for fname in _MachineRules._TRANSITION_ACTION_FIELDS:
                _actions(getattr(t, fname, None))
            for lst in getattr(t, "custom_events", {}).values():
                _actions(lst)

        return names

    @staticmethod
    def _check_duplicate_tool_name(project) -> list[ValidationError]:
        """duplicate_tool_name — tool_shelf 내 동명 Tool 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        for tool in getattr(project, "tool_shelf", []):
            if tool.name in seen:
                errors.append(ValidationError(
                    rule="duplicate_tool_name",
                    message=(
                        f"tool_shelf에 도구 이름 '{tool.name}'이 중복됩니다. "
                        f"이름 참조가 모호해집니다."
                    ),
                    source=tool.name,
                    subject=tool,
                ))
            else:
                seen[tool.name] = tool
        return errors

    @staticmethod
    def _check_empty_tool_definition(project) -> list[ValidationError]:
        """empty_tool_definition — UserDefinedTool 본문(body) 빈 값 등 내용 누락 경고."""
        from daedalus.model.plugin.tool import MCPTool, UserDefinedTool
        errors: list[ValidationError] = []
        for tool in getattr(project, "tool_shelf", []):
            empty_msg = None
            if isinstance(tool, UserDefinedTool) and not tool.body.strip():
                empty_msg = f"사용자 정의 도구 '{tool.name}'의 본문이 비어 있습니다."
            elif isinstance(tool, MCPTool) and (not tool.server or not tool.tool_name):
                empty_msg = f"MCP 도구 '{tool.name}'의 server/tool_name이 비어 있습니다."
            if empty_msg:
                errors.append(ValidationError(
                    rule="empty_tool_definition",
                    message=empty_msg,
                    source=tool.name,
                    subject=tool,
                ))
        return errors

    @staticmethod
    def _check_dangling_tool_refs(project) -> list[ValidationError]:
        """dangling_tool_ref — FSM이 참조하는 도구 이름이 tool_shelf와 CC 내장 도구
        집합 어디에도 없으면 경고. 빈 문자열 참조는 미지정으로 간주(스킵)."""
        shelf_names = {t.name for t in getattr(project, "tool_shelf", [])}
        valid = shelf_names | CC_BUILTIN_TOOLS
        errors: list[ValidationError] = []
        for label, fsm in project_machines(project):
            for name in _ToolRules._collect_machine_tool_refs(fsm):
                if name not in valid:
                    errors.append(ValidationError(
                        rule="dangling_tool_ref",
                        message=(
                            f"{label}: FSM이 참조하는 도구 '{name}'이 tool_shelf와 "
                            f"CC 내장 도구 어디에도 없습니다."
                        ),
                        source=name,
                        subject=fsm,
                        path=(label,),
                    ))
        return errors
