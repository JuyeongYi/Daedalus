"""프론트매터 필드 편집 (set_component_field / list_component_fields).

description / when_to_use / hooks 말고는 전부 GUI 전용이었다. 에이전트에
`tools`를 넣지 못해 MCP만으로는 플러그인을 완성할 수 없었다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.enums import ModelType, PermissionMode, SkillContext
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    project = PluginProject(name="p", skills=[
        ProceduralSkill(fsm=fsm, name="init", description="초기화"),
        DeclarativeSkill(name="kb", description="지식"),
    ])
    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    t = DaedalusTools(window)
    t.create_agent("worker")
    return t


def _config(tools, name):
    return tools._find_component(name).config


# --- 목록 ---


def test_lists_agent_fields_with_choices(tools):
    out = tools.list_component_fields("worker")
    by_field = {f["field"]: f for f in out["fields"]}
    assert "tools" in by_field
    assert "permission_mode" in by_field
    assert "acceptEdits" in by_field["permission_mode"]["choices"]


def test_lists_skill_fields_differently(tools):
    agent_fields = {f["field"] for f in tools.list_component_fields("worker")["fields"]}
    skill_fields = {f["field"] for f in tools.list_component_fields("init")["fields"]}
    assert "allowed_tools" in skill_fields
    assert "allowed_tools" not in agent_fields
    assert "permission_mode" in agent_fields
    assert "permission_mode" not in skill_fields


def test_declarative_has_no_shell_field(tools):
    """스킬 종류마다 받는 필드가 다르다."""
    fields = {f["field"] for f in tools.list_component_fields("kb")["fields"]}
    assert "shell" not in fields


def test_list_reports_emit_location(tools):
    by_field = {f["field"]: f for f in tools.list_component_fields("worker")["fields"]}
    assert by_field["mcp_servers"]["emit"] == "settings"
    assert by_field["tools"]["emit"] == "frontmatter"


def test_list_reports_current_value(tools):
    tools.set_component_field("worker", "model", "sonnet")
    by_field = {f["field"]: f for f in tools.list_component_fields("worker")["fields"]}
    assert by_field["model"]["current"] == "sonnet"


# --- 설정 ---


def test_set_enum_field_by_value_string(tools):
    tools.set_component_field("worker", "permission_mode", "acceptEdits")
    assert _config(tools, "worker").permission_mode is PermissionMode.ACCEPT_EDITS


def test_set_list_field(tools):
    tools.set_component_field(
        "worker", "tools", ["Read", "mcp__daedalus__get_project"]
    )
    assert _config(tools, "worker").tools == ["Read", "mcp__daedalus__get_project"]


def test_set_bool_field(tools):
    tools.set_component_field("init", "disable_model_invocation", True)
    assert _config(tools, "init").disable_model_invocation is True


def test_set_int_field(tools):
    tools.set_component_field("worker", "max_turns", 12)
    assert _config(tools, "worker").max_turns == 12


def test_set_string_field(tools):
    tools.set_component_field("init", "argument_hint", "<파일>")
    assert _config(tools, "init").argument_hint == "<파일>"


def test_set_is_undoable(tools):
    tools.set_component_field("worker", "model", "opus")
    assert _config(tools, "worker").model is ModelType.OPUS
    tools.undo()
    assert _config(tools, "worker").model is ModelType.INHERIT


def test_returns_old_and_new(tools):
    out = tools.set_component_field("init", "context", "fork")
    assert out["old"] == SkillContext.INLINE.value
    assert out["new"] == "fork"


# --- 거부 ---


def test_unknown_field_lists_available(tools):
    with pytest.raises(ValueError, match="tools"):
        tools.set_component_field("worker", "nonexistent", 1)


def test_bad_enum_value_lists_choices(tools):
    """조용히 문자열이 들어가면 컴파일 산출이 이상해질 때까지 안 드러난다."""
    with pytest.raises(ValueError, match="acceptEdits"):
        tools.set_component_field("worker", "permission_mode", "nope")


def test_list_field_rejects_scalar(tools):
    with pytest.raises(ValueError, match="목록"):
        tools.set_component_field("worker", "tools", "Read")


def test_hooks_redirected_to_dedicated_tool(tools):
    with pytest.raises(ValueError, match="set_component_hooks"):
        tools.set_component_field("worker", "hooks", {})


def test_skill_field_on_agent_is_rejected(tools):
    with pytest.raises(ValueError, match="없습니다"):
        tools.set_component_field("worker", "allowed_tools", ["Read"])


# --- 컴파일까지 이어지는가 ---


def test_agent_tools_reach_compiled_frontmatter(tools, window):
    from daedalus.compiler.emit import compile_agent

    tools.set_component_field("worker", "tools", ["Read", "mcp__daedalus__undo"])
    text = compile_agent(
        tools._find_component("worker"), project=window._project
    )
    assert "tools: [Read, mcp__daedalus__undo]" in text
    # tools의 mcp__ 접두에서 서버 이름이 추출돼 요구 환경에 합류한다
    assert "daedalus" in text


# --- bool 코어션 (실사고 회귀: bool("false") == True) ---


def test_bool_field_accepts_string_false(tools):
    """MCP 클라이언트가 불리언을 문자열로 보내는 경우가 실재한다 — "false"는
    False여야 한다(실사고: user_invocable=false 지정이 조용히 True로 저장됐다)."""
    tools.set_component_field("init", "user_invocable", "false")
    assert _config(tools, "init").user_invocable is False
    tools.set_component_field("init", "user_invocable", "true")
    assert _config(tools, "init").user_invocable is True


def test_bool_field_accepts_real_boolean(tools):
    tools.set_component_field("init", "user_invocable", False)
    assert _config(tools, "init").user_invocable is False


def test_bool_field_rejects_garbage_string(tools):
    with pytest.raises(ValueError, match="불리언"):
        tools.set_component_field("init", "user_invocable", "maybe")
