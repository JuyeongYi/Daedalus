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
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
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
        HookDef(name="dup", description="a", handlers=[CommandHook(script="x")]),
        HookDef(name="dup", description="b", handlers=[CommandHook(script="y")]),
    ])
    assert "duplicate_hook_name" in _rules(Validator.validate_project(proj))


def test_duplicate_hook_name_not_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="a", description="a", handlers=[CommandHook(script="x")]),
        HookDef(name="b", description="b", handlers=[CommandHook(script="y")]),
    ])
    assert "duplicate_hook_name" not in _rules(Validator.validate_project(proj))


def test_duplicate_hook_name_is_error():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="d", description="a", handlers=[CommandHook(script="x")]),
        HookDef(name="d", description="b", handlers=[CommandHook(script="y")]),
    ])
    err = next(e for e in Validator.validate_project(proj) if e.rule == "duplicate_hook_name")
    assert not err.is_warning


# ── empty_hook_command ──

def test_empty_hook_command_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="   ")]),
    ])
    assert "empty_hook_command" in _rules(Validator.validate_project(proj))


def test_empty_hook_command_not_detected():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="echo hi")]),
    ])
    assert "empty_hook_command" not in _rules(Validator.validate_project(proj))


def test_empty_hook_command_is_warning():
    assert "empty_hook_command" in WARNING_RULES


# ── hook_matcher_without_tool_event ──

def test_hook_matcher_without_tool_event_detected():
    """matcher를 받지 않는 이벤트(스키마 명시)에 matcher를 주면 경고."""
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="x")],
                event=HookEvent.CWD_CHANGED, matcher="Edit"),
    ])
    assert "hook_matcher_without_tool_event" in _rules(Validator.validate_project(proj))


def test_hook_matcher_with_tool_event_ok():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="x")],
                event=HookEvent.POST_TOOL_USE, matcher="Edit"),
    ])
    assert "hook_matcher_without_tool_event" not in _rules(Validator.validate_project(proj))


def test_matcher_ok_on_non_tool_events_that_accept_it():
    """Stop 등도 matcher를 받는다 — 예전에는 Pre/PostToolUse만 받는다고 보았다."""
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="x")],
                event=HookEvent.STOP, matcher="x"),
    ])
    assert "hook_matcher_without_tool_event" not in _rules(Validator.validate_project(proj))


def test_hook_no_matcher_non_tool_event_ok():
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[CommandHook(script="x")],
                event=HookEvent.CWD_CHANGED, matcher=""),
    ])
    assert "hook_matcher_without_tool_event" not in _rules(Validator.validate_project(proj))


def test_hook_without_handlers_warns():
    """핸들러가 없는 훅은 아무 일도 하지 않는다."""
    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[]),
    ])
    assert "empty_hook_command" in _rules(Validator.validate_project(proj))


def test_empty_http_url_warns():
    """빈 값 판정은 타입마다 다르다 — command 훅만 검사하면 나머지가 새어 나간다."""
    from daedalus.model.plugin.hook import HttpHook

    proj = PluginProject(name="p", hook_library=[
        HookDef(name="h", description="a", handlers=[HttpHook(url="")]),
    ])
    assert "empty_hook_command" in _rules(Validator.validate_project(proj))


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
        hook_library=[HookDef(name="fmt", description="d", handlers=[CommandHook(script="x")])],
    )
    assert "dangling_hook_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_on_skill():
    cfg = DeclarativeSkillConfig()
    cfg.hooks = {"missing": {}}
    skill = DeclarativeSkill(name="sk", description="d", config=cfg)
    proj = PluginProject(name="p", skills=[skill])
    assert "dangling_hook_ref" in _rules(Validator.validate_project(proj))


def test_no_hooks_no_dangling():
    proj = PluginProject(name="p", agents=[_agent(hooks=None)])
    assert "dangling_hook_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_hook_ref_is_warning():
    assert "dangling_hook_ref" in WARNING_RULES


# ── 깨진 사용자 파일 내성 (WP-2b 리뷰 1) ──

def test_corrupted_hooks_value_survives_round_trip_and_validation():
    """손상된 `.daedalus.json`의 non-dict `hooks`는 **경고 없이 건너뛴다**.

    역직렬화(`deser_plugin`)는 `hooks`를 날것으로 싣는다 — 강제 변환이 없어
    목록·문자열이 그대로 모델에 들어온다. 참조 수집(`hook_refs()`)이 여기서
    터지면 `validate_project`가 통째로 죽고 검증 패널과 MCP `compile_check`가
    같이 죽는다. 깨진 사용자 파일은 건드리지 않고 조용히 지나가는 것이
    종전 동작이다(원칙 5).
    """
    from daedalus.model.serialize import deserialize_project, serialize_project

    cfg = DeclarativeSkillConfig()
    cfg.hooks = {"fmt": {}}
    proj = PluginProject(
        name="p",
        skills=[DeclarativeSkill(name="sk", description="d", config=cfg)],
        agents=[_agent(hooks={"fmt": {}})],
    )
    data = serialize_project(proj)
    data["skills"][0]["config"]["hooks"] = ["oops"]
    data["agents"][0]["config"]["hooks"] = "oops"

    loaded = deserialize_project(data)
    assert loaded.skills[0].config.hooks == ["oops"], (
        "역직렬화가 hooks를 강제 변환하면 이 테스트의 전제가 사라진다"
    )

    errors = Validator.validate_project(loaded)  # 터지지 않는 것이 단언이다
    assert "dangling_hook_ref" not in _rules(errors)
