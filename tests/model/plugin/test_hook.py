"""WP-HOOK: HookDef / HookEvent / 프리셋 단위 테스트."""
from __future__ import annotations

from dataclasses import replace

from daedalus.model.plugin.hook import HookDef, HookEvent, TOOL_MATCH_EVENTS
from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS, preset_copy


def test_hook_def_kind():
    h = HookDef(name="fmt", description="d", event=HookEvent.POST_TOOL_USE)
    assert h.kind == "hook"


def test_hook_def_defaults():
    h = HookDef(name="h", description="d")
    assert h.event is HookEvent.PRE_TOOL_USE
    assert h.matcher == ""
    assert h.command == ""
    assert h.timeout is None


def test_hook_event_values():
    """CC settings hooks 키로 쓰이는 PascalCase 값 고정."""
    assert HookEvent.PRE_TOOL_USE.value == "PreToolUse"
    assert HookEvent.POST_TOOL_USE.value == "PostToolUse"
    assert HookEvent.SESSION_START.value == "SessionStart"
    assert HookEvent.PRE_COMPACT.value == "PreCompact"
    assert HookEvent.SUBAGENT_STOP.value == "SubagentStop"


def test_tool_match_events():
    assert TOOL_MATCH_EVENTS == frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE})


def test_hook_id_unique_and_kw_only():
    a = HookDef(name="x", description="d")
    b = HookDef(name="x", description="d")
    assert a.id and b.id
    assert a.id != b.id


def test_hook_id_excluded_from_equality():
    a = HookDef(name="x", description="d", command="c")
    b = HookDef(name="x", description="d", command="c")
    assert a == b  # id만 다름


# ── 프리셋 무결성 ──

def test_presets_nonempty():
    assert 5 <= len(BUILTIN_HOOK_PRESETS) <= 8


def test_presets_unique_names():
    names = [p.name for p in BUILTIN_HOOK_PRESETS]
    assert len(names) == len(set(names))


def test_presets_matcher_only_on_tool_events():
    """matcher가 있는 프리셋은 event가 Pre/PostToolUse여야 한다."""
    for p in BUILTIN_HOOK_PRESETS:
        if p.matcher.strip():
            assert p.event in TOOL_MATCH_EVENTS, p.name


def test_presets_have_command():
    for p in BUILTIN_HOOK_PRESETS:
        assert p.command.strip(), p.name


def test_preset_copy_new_id():
    src = BUILTIN_HOOK_PRESETS[0]
    cp = preset_copy(src)
    assert cp.id != src.id
    assert cp == src  # id 외 동일 (compare=False)


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
