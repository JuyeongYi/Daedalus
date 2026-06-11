"""WP-HOOK: hook_library 검증 규칙 4종 테스트.

  duplicate_hook_name (에러)
  empty_hook_command (경고)
  hook_matcher_without_tool_event (경고)
  dangling_hook_ref (경고)

각 규칙 검출+미검출 + 등급.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import AgentConfig, DeclarativeSkillConfig
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.plugin.skill import DeclarativeSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import WARNING_RULES, Validator


def _rules(errors) -> set[str]:
    return {e.rule for e in errors}


def _agent(hooks=None) -> AgentDefinition:
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    cfg = AgentConfig()
    cfg.hooks = hooks
    return AgentDefinition(fsm=fsm, name="ag", description="d", config=cfg)


# ── duplicate_hook_name ──

def test_duplicate_hook_name_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="dup", description="a", command="x"),
        HookDef(name="dup", description="b", command="y"),
    ])
    assert "duplicate_hook_name" in _rules(Validator.validate_project(proj))


def test_duplicate_hook_name_not_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="a", description="a", command="x"),
        HookDef(name="b", description="b", command="y"),
    ])
    assert "duplicate_hook_name" not in _rules(Validator.validate_project(proj))


def test_duplicate_hook_name_is_error():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="d", description="a", command="x"),
        HookDef(name="d", description="b", command="y"),
    ])
    err = next(e for e in Validator.validate_project(proj) if e.rule == "duplicate_hook_name")
    assert not err.is_warning


# ── empty_hook_command ──

def test_empty_hook_command_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", command="   "),
    ])
    assert "empty_hook_command" in _rules(Validator.validate_project(proj))


def test_empty_hook_command_not_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", command="echo hi"),
    ])
    assert "empty_hook_command" not in _rules(Validator.validate_project(proj))


def test_empty_hook_command_is_warning():
    assert "empty_hook_command" in WARNING_RULES


# ── hook_matcher_without_tool_event ──

def test_hook_matcher_without_tool_event_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", command="x",
                event=HookEvent.STOP, matcher="Edit"),
    ])
    assert "hook_matcher_without_tool_event" in _rules(Validator.validate_project(proj))


def test_hook_matcher_with_tool_event_ok():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", command="x",
                event=HookEvent.POST_TOOL_USE, matcher="Edit"),
    ])
    assert "hook_matcher_without_tool_event" not in _rules(Validator.validate_project(proj))


def test_hook_no_matcher_non_tool_event_ok():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", command="x",
                event=HookEvent.STOP, matcher=""),
    ])
    assert "hook_matcher_without_tool_event" not in _rules(Validator.validate_project(proj))


def test_hook_matcher_without_tool_event_is_warning():
    assert "hook_matcher_without_tool_event" in WARNING_RULES


# ── dangling_hook_ref ──

def test_dangling_hook_ref_detected_on_agent():
    proj = PluginProject(name="p", agents=[_agent(hooks={"ghost": {}})])
    assert "dangling_hook_ref" in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_resolved_by_library():
    proj = PluginProject(
        name="p",
        agents=[_agent(hooks={"fmt": {}})],
        hook_library=[HookDef(name="fmt", description="d", command="x")],
    )
    assert "dangling_hook_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_on_skill():
    cfg = DeclarativeSkillConfig()
    cfg.hooks = {"missing": {}}
    skill = DeclarativeSkill(name="sk", description="d", config=cfg)
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_hook_ref" in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_on_agent_local_skill():
    cfg = DeclarativeSkillConfig()
    cfg.hooks = {"missing": {}}
    local = DeclarativeSkill(name="lsk", description="d", config=cfg)
    ag = _agent()
    ag.skills.append(local)
    proj = PluginProject(name="p", agents=[ag])
    assert "dangling_hook_ref" in _rules(Validator.validate_project(proj))


def test_no_hooks_no_dangling():
    proj = PluginProject(name="p", agents=[_agent(hooks=None)])
    assert "dangling_hook_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_is_warning():
    assert "dangling_hook_ref" in WARNING_RULES
