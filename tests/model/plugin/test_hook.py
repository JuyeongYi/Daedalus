"""HookDef / HookEvent / 핸들러 5종 / 프리셋 단위 테스트 (WP-HOOK, WP-HK).

규격 정본은 SchemaStore의 `claude-code-settings.json`이다 — 공식 문서에는 전체
형식이 없다. 이 테스트는 그 스키마와 우리 모델이 어긋나지 않게 고정한다.
"""
from __future__ import annotations

from daedalus.model.plugin.hook import (
    MATCHER_EVENTS,
    NO_MATCHER_EVENTS,
    AgentHook,
    CommandHook,
    HookDef,
    HookEvent,
    HookShell,
    HttpHook,
    McpToolHook,
    PromptHook,
)
from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS, preset_copy


def test_hook_def_kind():
    h = HookDef(name="fmt", description="d", event=HookEvent.POST_TOOL_USE)
    assert h.kind == "hook"


def test_hook_def_defaults():
    h = HookDef(name="h", description="d")
    assert h.event is HookEvent.PRE_TOOL_USE
    assert h.matcher == ""
    assert h.handlers == []


def test_hook_event_values():
    """CC settings hooks 키로 쓰이는 PascalCase 값 고정."""
    assert HookEvent.PRE_TOOL_USE.value == "PreToolUse"
    assert HookEvent.POST_TOOL_USE.value == "PostToolUse"
    assert HookEvent.SESSION_START.value == "SessionStart"
    assert HookEvent.PRE_COMPACT.value == "PreCompact"
    assert HookEvent.SUBAGENT_STOP.value == "SubagentStop"


def test_all_schema_events_present():
    """스키마의 이벤트 31종이 전부 있어야 한다 — 빠지면 그 훅을 만들 수 없다."""
    assert len(HookEvent) == 31
    for name in ("PostToolUseFailure", "PermissionRequest", "StopFailure",
                 "SubagentStart", "PostCompact", "Elicitation", "TeammateIdle",
                 "TaskCompleted", "InstructionsLoaded", "CwdChanged",
                 "FileChanged", "ConfigChange", "WorktreeCreate", "PostToolBatch",
                 "TaskCreated", "PermissionDenied", "UserPromptExpansion",
                 "MessageDisplay"):
        assert any(e.value == name for e in HookEvent), name


def test_matcher_events_split_is_complete():
    assert MATCHER_EVENTS | NO_MATCHER_EVENTS == frozenset(HookEvent)
    assert not (MATCHER_EVENTS & NO_MATCHER_EVENTS)


def test_no_matcher_events_match_schema():
    """스키마가 "does not support matchers"라고 명시한 이벤트들."""
    assert HookEvent.TASK_COMPLETED in NO_MATCHER_EVENTS
    assert HookEvent.CWD_CHANGED in NO_MATCHER_EVENTS
    assert HookEvent.WORKTREE_CREATE in NO_MATCHER_EVENTS
    assert HookEvent.PRE_TOOL_USE in MATCHER_EVENTS
    assert HookEvent.FILE_CHANGED in MATCHER_EVENTS


def test_hook_id_unique_and_kw_only():
    a = HookDef(name="x", description="d")
    b = HookDef(name="x", description="d")
    assert a.id and b.id
    assert a.id != b.id


def test_hook_id_excluded_from_equality():
    a = HookDef(name="x", description="d", handlers=[CommandHook(script="c")])
    b = HookDef(name="x", description="d", handlers=[CommandHook(script="c")])
    assert a == b  # id만 다름


# ── 핸들러 5종 → CC JSON ──


def test_command_handler_json():
    """command 값은 스크립트 **경로**다 — 본문은 파일로 나간다 (WP-HS)."""
    h = CommandHook(script="echo hi", timeout=5)
    assert h.to_json("${ROOT}/hooks/scripts/a.sh") == {
        "type": "command", "command": "${ROOT}/hooks/scripts/a.sh", "timeout": 5,
    }


def test_command_handler_optional_keys_omitted():
    """빈 값 키를 내보내면 hooks.json이 잡음으로 채워진다."""
    assert CommandHook(script="x").to_json("p") == {"type": "command", "command": "p"}


def test_command_handler_full():
    h = CommandHook(
        script="run", args=["--a"], shell=HookShell.POWERSHELL,
        run_async=True, async_rewake=True, timeout=3,
        condition="Bash(git *)", status_message="검사 중",
    )
    assert h.to_json("p.ps1") == {
        "type": "command", "command": "p.ps1", "args": ["--a"],
        "shell": "powershell", "async": True, "asyncRewake": True,
        "timeout": 3, "if": "Bash(git *)", "statusMessage": "검사 중",
    }


def test_command_extension_follows_shell():
    assert CommandHook().extension == ".sh"
    assert CommandHook(shell=HookShell.BASH).extension == ".sh"
    assert CommandHook(shell=HookShell.POWERSHELL).extension == ".ps1"


def test_script_files_named_after_hook():
    hook = HookDef(name="guard-bash", description="", handlers=[CommandHook(script="x")])
    assert hook.script_files() == [("guard-bash.sh", "x")]


def test_script_files_numbered_when_multiple_commands():
    hook = HookDef(name="h", description="", handlers=[
        CommandHook(script="a"), CommandHook(script="b"),
    ])
    assert [n for n, _ in hook.script_files()] == ["h-1.sh", "h-2.sh"]


def test_explicit_script_name_wins():
    hook = HookDef(name="h", description="", handlers=[
        CommandHook(script="a", script_name="custom"),
    ])
    assert hook.script_files() == [("custom.sh", "a")]


def test_script_name_sanitized_from_hook_name():
    """이름은 자유 문자열이라 경로 구분자·상위 참조가 섞일 수 있다."""
    hook = HookDef(name="../evil name", description="", handlers=[CommandHook(script="x")])
    filename = hook.script_files()[0][0]
    assert "/" not in filename and "\\" not in filename and ".." not in filename


def test_script_refs_map_only_command_handlers():
    hook = HookDef(name="h", description="", handlers=[
        AgentHook(prompt="a"), CommandHook(script="b"),
    ])
    refs = hook.script_refs()
    assert list(refs) == [1]
    assert refs[1] == "${ROOT}/hooks/scripts/h.sh"


def test_prompt_handler_json():
    h = PromptHook(prompt="검토하라", model="haiku", continue_on_block=True)
    assert h.to_json() == {
        "type": "prompt", "prompt": "검토하라", "model": "haiku",
        "continueOnBlock": True,
    }


def test_agent_handler_json():
    assert AgentHook(prompt="확인").to_json() == {"type": "agent", "prompt": "확인"}


def test_http_handler_json():
    h = HttpHook(url="https://x/y", headers={"X": "1"}, allowed_env_vars=["TOKEN"])
    assert h.to_json() == {
        "type": "http", "url": "https://x/y", "headers": {"X": "1"},
        "allowedEnvVars": ["TOKEN"],
    }


def test_mcp_tool_handler_json():
    h = McpToolHook(server="slack", tool="post", tool_input={"ch": "#a"})
    assert h.to_json() == {
        "type": "mcp_tool", "server": "slack", "tool": "post", "input": {"ch": "#a"},
    }


def test_handler_kinds_are_schema_type_values():
    kinds = {
        CommandHook().kind, PromptHook().kind, AgentHook().kind,
        HttpHook().kind, McpToolHook().kind,
    }
    assert kinds == {"command", "prompt", "agent", "http", "mcp_tool"}


# ── 그룹(hookMatcher) → CC JSON ──


def test_hook_group_json_with_matcher():
    hook = HookDef(
        name="h", description="", event=HookEvent.PRE_TOOL_USE, matcher="Bash",
        handlers=[CommandHook(script="./a.sh")],
    )
    assert hook.to_json() == {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "${ROOT}/hooks/scripts/h.sh"}],
    }


def test_matcher_dropped_for_events_that_ignore_it():
    """무시되는 키를 내보내면 설정한 사람은 걸린 줄 안다."""
    hook = HookDef(
        name="h", description="", event=HookEvent.CWD_CHANGED, matcher="x",
        handlers=[CommandHook(script="./a.sh")],
    )
    assert "matcher" not in hook.to_json()


def test_multiple_handlers_in_one_group():
    hook = HookDef(
        name="h", description="", event=HookEvent.STOP,
        handlers=[CommandHook(script="a"), AgentHook(prompt="b")],
    )
    assert [x["type"] for x in hook.to_json()["hooks"]] == ["command", "agent"]


# ── 프리셋 무결성 ──


def test_presets_nonempty():
    assert 5 <= len(BUILTIN_HOOK_PRESETS) <= 12


def test_presets_unique_names():
    names = [p.name for p in BUILTIN_HOOK_PRESETS]
    assert len(names) == len(set(names))


def test_presets_matcher_only_on_matcher_events():
    for p in BUILTIN_HOOK_PRESETS:
        if p.matcher.strip():
            assert p.event in MATCHER_EVENTS, p.name


def test_presets_have_handlers():
    for p in BUILTIN_HOOK_PRESETS:
        assert p.handlers, p.name
        for h in p.handlers:
            assert not h.summary().startswith("("), f"{p.name}: {h.kind} 필수 값 비었음"


def test_presets_cover_more_than_command_type():
    """command 말고도 출발점이 있어야 다른 타입을 쓸 생각을 한다."""
    kinds = {h.kind for p in BUILTIN_HOOK_PRESETS for h in p.handlers}
    assert len(kinds) >= 2


def test_preset_copy_new_id():
    src = BUILTIN_HOOK_PRESETS[0]
    cp = preset_copy(src)
    assert cp.id != src.id
    assert cp == src  # id 외 동일 (compare=False)


def test_preset_copy_does_not_share_handlers():
    """얕게 복사하면 한 프로젝트의 수정이 다른 프로젝트에 새어 나간다."""
    src = BUILTIN_HOOK_PRESETS[0]
    a, b = preset_copy(src), preset_copy(src)
    assert a.handlers[0] is not b.handlers[0]
    assert a.handlers[0] is not src.handlers[0]

    a.handlers[0].timeout = 999
    assert b.handlers[0].timeout != 999
    assert src.handlers[0].timeout != 999


def test_presets_pass_validation():
    """모든 프리셋을 hook_library에 넣으면 검증 경고/에러가 없다."""
    from daedalus.model.project import PluginProject
    from daedalus.model.validation import Validator

    proj = PluginProject(
        name="p", hook_library=[preset_copy(p) for p in BUILTIN_HOOK_PRESETS]
    )
    errors = Validator.validate_project(proj)
    hook_rules = {
        "duplicate_hook_name", "empty_hook_command",
        "hook_matcher_without_tool_event", "dangling_hook_ref",
    }
    found = {e.rule for e in errors} & hook_rules
    assert not found, found
