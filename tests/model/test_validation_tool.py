"""WP-L: tool_shelf 검증 규칙 테스트.

규칙 3종:
  duplicate_tool_name (에러)   — shelf 내 동명
  empty_tool_definition (경고) — UserDefinedTool 본문 누락 / MCPTool server·tool_name 누락
  dangling_tool_ref (경고)     — FSM 도구 참조가 shelf+CC내장 어디에도 없음

각 규칙 검출+미검출 쌍 + WARNING_RULES 분류.
"""
from __future__ import annotations

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import CompositeState, SimpleState
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import SkillShell
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.plugin.tool import BuiltinTool, MCPTool, UserDefinedTool
from daedalus.model.project import PluginProject
from daedalus.model.validation import (
    CC_BUILTIN_TOOLS,
    WARNING_RULES,
    Validator,
)


def _rules(errors) -> set[str]:
    return {e.rule for e in errors}


def _skill_with_exec_tool(tool_name: str, name: str = "proc") -> ProceduralSkill:
    """on_entry에 ToolExecution(tool=tool_name)을 갖는 SimpleState 1개짜리 스킬."""
    s = SimpleState(name="s")
    s.on_entry = [Action(name="a", execution=ToolExecution(tool=tool_name))]
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(
        fsm=fsm, name=name, description="d",
        config=ProceduralSkillConfig(),
    )


# ── duplicate_tool_name ──

def test_duplicate_tool_name_detected():
    proj = PluginProject(name="p", tool_shelf=[
        UserDefinedTool(name="dup", description="a", body="x"),
        UserDefinedTool(name="dup", description="b", body="y"),
    ])
    errors = Validator.validate_project(proj)
    assert "duplicate_tool_name" in _rules(errors)


def test_duplicate_tool_name_not_detected():
    proj = PluginProject(name="p", tool_shelf=[
        UserDefinedTool(name="a", description="a", body="x"),
        UserDefinedTool(name="b", description="b", body="y"),
    ])
    errors = Validator.validate_project(proj)
    assert "duplicate_tool_name" not in _rules(errors)


def test_duplicate_tool_name_is_error():
    err = next(
        e for e in Validator.validate_project(
            PluginProject(name="p", tool_shelf=[
                UserDefinedTool(name="d", description="a", body="x"),
                UserDefinedTool(name="d", description="b", body="y"),
            ])
        )
        if e.rule == "duplicate_tool_name"
    )
    assert not err.is_warning


# ── empty_tool_definition ──

def test_empty_user_tool_body_detected():
    proj = PluginProject(name="p", tool_shelf=[
        UserDefinedTool(name="t", description="a", body="   "),
    ])
    assert "empty_tool_definition" in _rules(Validator.validate_project(proj))


def test_empty_mcp_tool_detected():
    proj = PluginProject(name="p", tool_shelf=[
        MCPTool(name="m", description="a", server="", tool_name=""),
    ])
    assert "empty_tool_definition" in _rules(Validator.validate_project(proj))


def test_empty_tool_definition_not_detected():
    proj = PluginProject(name="p", tool_shelf=[
        UserDefinedTool(name="t", description="a", body="echo hi"),
        MCPTool(name="m", description="a", server="srv", tool_name="tn"),
        BuiltinTool(name="Read", description="a"),  # builtin은 본문 검사 없음
    ])
    assert "empty_tool_definition" not in _rules(Validator.validate_project(proj))


def test_empty_tool_definition_is_warning():
    assert "empty_tool_definition" in WARNING_RULES


# ── dangling_tool_ref ──

def test_dangling_tool_ref_detected():
    skill = _skill_with_exec_tool("nonexistent-tool")
    proj = PluginProject(name="p", skills=[skill])  # shelf 비어있음
    assert "dangling_tool_ref" in _rules(Validator.validate_project(proj))


def test_dangling_tool_ref_resolved_by_shelf():
    skill = _skill_with_exec_tool("git-commit")
    proj = PluginProject(name="p", skills=[skill], tool_shelf=[
        UserDefinedTool(name="git-commit", description="a", body="git commit"),
    ])
    assert "dangling_tool_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_tool_ref_resolved_by_builtin():
    skill = _skill_with_exec_tool("Bash")
    assert "Bash" in CC_BUILTIN_TOOLS
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_tool_ref" not in _rules(Validator.validate_project(proj))


def test_empty_tool_ref_skipped():
    """빈 문자열 tool 참조는 미지정 — 검사 스킵."""
    skill = _skill_with_exec_tool("")
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_tool_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_tool_ref_in_guard_evaluation():
    """전이 가드의 ToolEvaluation도 수집된다."""
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    t = Transition(source=a, target=b, guard=Guard(evaluation=ToolEvaluation(tool="ghost")))
    fsm = StateMachine(name="f", states=[a, b], transitions=[t], initial_state=a)
    skill = ProceduralSkill(fsm=fsm, name="g", description="d", config=ProceduralSkillConfig())
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_tool_ref" in _rules(Validator.validate_project(proj))


def test_dangling_tool_ref_in_composite_strategy():
    """중첩 CompositeExecution/CompositeEvaluation 안의 참조도 수집된다."""
    s = SimpleState(name="s")
    s.on_entry = [Action(
        name="a",
        execution=CompositeExecution(children=[ToolExecution(tool="deep-ghost")]),
    )]
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(fsm=fsm, name="c", description="d", config=ProceduralSkillConfig())
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_tool_ref" in _rules(Validator.validate_project(proj))


def test_dangling_tool_ref_recurses_into_sub_machine():
    """CompositeState.sub_machine 내부 도구 참조도 수집된다 (agent.fsm 경유)."""
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.config import AgentConfig

    inner = SimpleState(name="inner")
    inner.on_entry = [Action(name="a", execution=ToolExecution(tool="inner-ghost"))]
    sub = StateMachine(name="sub", states=[inner], initial_state=inner)
    comp = CompositeState(name="comp", sub_machine=sub)
    top = StateMachine(name="top", states=[comp], initial_state=comp)
    agent = AgentDefinition(fsm=top, name="ag", description="d", config=AgentConfig())
    proj = PluginProject(name="p", agents=[agent])
    errors = Validator.validate_project(proj)
    assert "dangling_tool_ref" in _rules(errors)


def test_dangling_tool_ref_is_warning():
    assert "dangling_tool_ref" in WARNING_RULES
