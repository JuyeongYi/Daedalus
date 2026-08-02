from __future__ import annotations

from enum import Enum


class FieldEmit(Enum):
    """컴파일러가 필드를 배출할 위치 — 프론트매터 직출 / 본문 합류 / 호출 시점 파라미터(Agent tool 인수) / 설정 파일(.mcp.json, settings 등)."""
    FRONTMATTER = "frontmatter"
    BODY = "body"
    INVOCATION = "invocation"
    SETTINGS = "settings"


class ModelType(Enum):
    """CC 모델 별칭 4종 + INHERIT. 별칭은 항상 해당 계열 최신 모델로 해석되므로
    버전 명시 멤버(opus-5 등)는 두지 않는다 — 2026-07 기준 CC Agent tool enum과 일치."""
    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"
    FABLE = "fable"
    INHERIT = "inherit"


class EffortLevel(Enum):
    """CC effort 5단 (2026-07 기준: low/medium/high/xhigh/max)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class SkillContext(Enum):
    INLINE = "inline"
    FORK = "fork"


class SkillShell(Enum):
    BASH = "bash"
    POWERSHELL = "powershell"


class PermissionMode(Enum):
    """Claude Code Agent tool의 mode enum(acceptEdits/auto/bypassPermissions/default/dontAsk/plan)과 일치함을 2026-06 기준 검증함."""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"
    PLAN = "plan"


class BuildTarget(Enum):
    """프로젝트 빌드 타깃 — 마켓플레이스 플러그인 vs 로컬 플러그인(.claude/ 반입형).

    MCP를 쓰는 에이전트는 CC 정책상 마켓플레이스 플러그인으로 배포할 수 없어
    (mcpServers 등 프론트매터 미지원), 프로젝트 수준에서 빌드 타깃을 가른다
    (WP-TG). LOCAL은 plugin.json을 생성하지 않고 설치 스크립트를 동봉한다."""
    MARKETPLACE = "marketplace"
    LOCAL = "local"


class MemoryScope(Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class AgentIsolation(Enum):
    NONE = "none"
    WORKTREE = "worktree"
    REMOTE = "remote"


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

    @property
    def frontmatter_key(self) -> str | None:
        """SKILL.md 프론트매터에 직출되는 kebab-case 키.

        WHEN_TO_USE는 프론트매터 직출 금지 — description/본문 합류는 컴파일러
        정책이므로 None을 반환한다. 나머지는 snake_case → kebab-case 변환.
        """
        if self is SkillField.WHEN_TO_USE:
            return None
        return self.value.replace("_", "-")


class AgentField(Enum):
    """에이전트 프론트매터/설정 필드 식별자."""
    NAME = "name"
    DESCRIPTION = "description"
    MODEL = "model"
    EFFORT = "effort"
    TOOLS = "tools"
    DISALLOWED_TOOLS = "disallowed_tools"
    PERMISSION_MODE = "permission_mode"
    SKILLS = "skills"
    MEMORY = "memory"
    COLOR = "color"
    HOOKS = "hooks"
    MAX_TURNS = "max_turns"
    BACKGROUND = "background"
    ISOLATION = "isolation"
    MCP_SERVERS = "mcp_servers"

    @property
    def frontmatter_key(self) -> str:
        """CC agent .md 실제 키 케이싱(camelCase 여부) 확정은 컴파일러 WP 정책 —
        여기서는 kebab-case 기준값만 제공."""
        return self.value.replace("_", "-")
