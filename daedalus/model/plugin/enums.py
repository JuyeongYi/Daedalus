from __future__ import annotations

from enum import Enum


class ModelType(Enum):
    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"
    INHERIT = "inherit"


class EffortLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class SkillContext(Enum):
    INLINE = "inline"
    FORK = "fork"


class SkillShell(Enum):
    BASH = "bash"
    POWERSHELL = "powershell"


class PermissionMode(Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"
    PLAN = "plan"


class MemoryScope(Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class AgentIsolation(Enum):
    NONE = "none"
    WORKTREE = "worktree"


class AgentColor(Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    PURPLE = "purple"
    ORANGE = "orange"
    PINK = "pink"
    CYAN = "cyan"


class FieldVisibility(Enum):
    """프론트매터 필드 표시 모드."""
    REQUIRED = "required"
    OPTIONAL = "optional"
    DEFAULT = "default"
    FIXED = "fixed"


class SkillField(Enum):
    """스킬 프론트매터 필드 식별자."""
    NAME = "name"
    DESCRIPTION = "description"
    WHEN_TO_USE = "when_to_use"
    ARGUMENT_HINT = "argument_hint"
    MODEL = "model"
    EFFORT = "effort"
    ALLOWED_TOOLS = "allowed_tools"
    CONTEXT = "context"
    AGENT = "agent"
    SHELL = "shell"
    PATHS = "paths"
    HOOKS = "hooks"
    DISABLE_MODEL = "disable_model_invocation"
    USER_INVOCABLE = "user_invocable"
