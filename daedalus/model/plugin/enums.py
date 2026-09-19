from __future__ import annotations

from enum import Enum


class FieldEmit(Enum):
    """컴파일러가 필드를 배출할 위치 — 프론트매터 직출 / 본문 합류 / 설정 파일(.mcp.json, settings 등).

    `NONE`은 **배출되지 않는 편집 필드**다(WP-9). 산출 파일을 내지 않는 종류
    (`OutputLocation.NONE` — 외부 플러그인 서브에이전트)의 필드가 여기 속한다:
    편집기·MCP는 값을 받고 저장하지만 어떤 산출 텍스트에도 나가지 않는다.
    `FRONTMATTER`로 두면 `FieldRule.emit`("배출할 위치")이 거짓말을 하고,
    행 자체를 빼면 편집 표면이 사라진다.
    """
    FRONTMATTER = "frontmatter"
    BODY = "body"
    SETTINGS = "settings"
    NONE = "none"


class ModelType(Enum):
    """CC 모델 별칭 4종 + INHERIT. 별칭은 항상 해당 계열 최신 모델로 해석되므로
    버전 명시 멤버(opus-5 등)는 두지 않는다 — 2026-07 기준 CC Agent tool enum과 일치."""
    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"
    FABLE = "fable"
    INHERIT = "inherit"


#: 모델 티어 순서 — 값이 클수록 상위 모델. 에이전트가 **자기보다 상위 모델의
#: 에이전트를 부르지 못하게** 하는 규칙(agent_calls_higher_model)의 단일 진실이다.
#: INHERIT는 표에 없다 — 부르는 쪽 맥락을 물려받으므로 "상위/하위"가 성립하지
#: 않는다(어느 한쪽이 INHERIT면 판정을 건너뛴다).
MODEL_TIER: dict[ModelType, int] = {
    ModelType.HAIKU: 1,
    ModelType.SONNET: 2,
    ModelType.OPUS: 3,
    ModelType.FABLE: 4,
}


class EffortLevel(Enum):
    """CC effort 5단 (2026-07 기준: low/medium/high/xhigh/max)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


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
    # fork 2종을 가르는 값 (사용자 확정 2026-09-17): false = 동기 fork, true =
    # 비동기 fork. AGENT 바로 뒤에 선언한다 — 프론트매터 출력 순서가 enum 선언
    # 순서라 `context` · `agent` · `background`가 붙어 나온다.
    BACKGROUND = "background"
    SHELL = "shell"
    PATHS = "paths"
    HOOKS = "hooks"
    DISABLE_MODEL = "disable_model_invocation"
    USER_INVOCABLE = "user_invocable"
    SOURCE = "source"  # WP-WR 랩핑 스킬 전용 — 외부 스킬 참조

    @property
    def frontmatter_key(self) -> str | None:
        """SKILL.md 프론트매터에 직출되는 kebab-case 키.

        WHEN_TO_USE는 프론트매터 직출 금지 — description/본문 합류는 컴파일러
        정책이므로 None을 반환한다. 나머지는 snake_case → kebab-case 변환.
        """
        if self is SkillField.WHEN_TO_USE:
            return None
        if self is SkillField.SOURCE:
            # WP-WR — 프론트매터 키가 아니라 본문 지시("Follow skill …")로
            # 배출된다. 프론트매터에 내면 CC가 모르는 키라 조용히 무시된다.
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
    SOURCE = "source"  # WP-9 외부 플러그인 에이전트 전용 — 외부 에이전트 참조

    @property
    def frontmatter_key(self) -> str | None:
        """CC 서브에이전트 프론트매터의 실제 키 — **camelCase** (WP-LA에서 확정).

        `SOURCE`는 `None`이다(`SkillField.SOURCE`와 같은 규약) — 외부 플러그인
        에이전트를 가리키는 참조일 뿐이고, 그 종류는 산출 파일 자체가 없다.
        프론트매터 키로 내면 CC가 모르는 키라 조용히 무시된다.

        공식 sub-agents 문서의 필드 표 기준(2026-08 확인): `disallowedTools`,
        `permissionMode`, `maxTurns`, `mcpServers`. 단일 단어 필드는 그대로다.
        이전에는 케이싱이 미확정이라 kebab-case를 잠정값으로 썼는데, 그 키들은
        CC가 인식하지 못해 **조용히 무시**된다 — 스킬 프론트매터(`allowed-tools`
        등 kebab-case)와 규약이 다르므로 한쪽을 보고 다른 쪽을 유추하면 안 된다.
        """
        if self is AgentField.SOURCE:
            return None
        head, *rest = self.value.split("_")
        return head + "".join(word.capitalize() for word in rest)
