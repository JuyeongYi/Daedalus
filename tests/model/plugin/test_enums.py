from __future__ import annotations

from daedalus.model.plugin.enums import (
    ModelType,
    EffortLevel,
    SkillContext,
    SkillShell,
    PermissionMode,
    MemoryScope,
    AgentIsolation,
    AgentColor,
)


def test_model_type():
    assert ModelType.SONNET.value == "sonnet"
    assert ModelType.OPUS.value == "opus"
    assert ModelType.HAIKU.value == "haiku"
    assert ModelType.FABLE.value == "fable"
    assert ModelType.INHERIT.value == "inherit"


def test_effort_level():
    assert EffortLevel.LOW.value == "low"
    assert EffortLevel.XHIGH.value == "xhigh"
    assert EffortLevel.MAX.value == "max"


def test_effort_level_order():
    """CC effort 5단 순서 (low → max)."""
    assert [e.value for e in EffortLevel] == [
        "low", "medium", "high", "xhigh", "max"
    ]


def test_skill_context():
    assert SkillContext.INLINE.value == "inline"
    assert SkillContext.FORK.value == "fork"


def test_skill_shell():
    assert SkillShell.BASH.value == "bash"
    assert SkillShell.POWERSHELL.value == "powershell"


def test_permission_mode():
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.BYPASS.value == "bypassPermissions"
    assert PermissionMode.ACCEPT_EDITS.value == "acceptEdits"
    assert PermissionMode.DONT_ASK.value == "dontAsk"


def test_memory_scope():
    assert MemoryScope.USER.value == "user"
    assert MemoryScope.PROJECT.value == "project"
    assert MemoryScope.LOCAL.value == "local"


def test_agent_isolation():
    assert AgentIsolation.NONE.value == "none"
    assert AgentIsolation.WORKTREE.value == "worktree"
    assert AgentIsolation.REMOTE.value == "remote"


def test_agent_color_all_values():
    expected = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
    actual = {c.value for c in AgentColor}
    assert actual == expected
