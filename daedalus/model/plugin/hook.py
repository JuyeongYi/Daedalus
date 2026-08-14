# daedalus/model/plugin/hook.py
"""훅(Hook) 모델 — CC lifecycle hooks 정의 (순수 모델, Qt 무관).

**규격 출처:** SchemaStore의 `claude-code-settings.json`(2026-08 확인) —
`$defs.hookMatcher` / `$defs.hookCommand` / `properties.hooks`. 공식 문서에는
전체 형식이 나오지 않아 스키마가 정본이다.

CC의 구조는 3단이다:

    hooks:
      <이벤트>:
        - matcher: "Bash"        # 그룹 = hookMatcher
          hooks:                  # 핸들러 목록 = hookCommand[]
            - type: command
              command: "./check.sh"

`HookDef` 하나가 그 **그룹 하나**에 대응하고, `handlers`가 그 안의 핸들러
목록이다. 예전 모델은 그룹당 command 핸들러 하나만 표현할 수 있었다.

훅은 두 곳에서 쓰인다:
  1. `<out>/hooks/hooks.json` (CC settings hooks 스키마).
  2. 에이전트 프론트매터 `hooks:` (프로젝트 설치 빌드에서만 — WP-LA).
  3. 스킬/에이전트 프론트매터 `hooks:` 목록은 라이브러리 HookDef **이름 참조**다.

`PluginProject.hook_library`가 HookDef의 단일 진실(shelf 성격)이고,
`ComponentConfig.hooks`는 그 이름을 키로 참조한다 (tool_shelf 선례와 동일).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from daedalus.model.plugin.base import PluginComponent


class HookEvent(Enum):
    """CC 훅 이벤트 — SchemaStore `properties.hooks`의 키 전체(선언 순서).

    값은 settings.json hooks 키로 그대로 쓰이는 PascalCase 이벤트명이다.
    """
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    PERMISSION_REQUEST = "PermissionRequest"
    NOTIFICATION = "Notification"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    STOP_FAILURE = "StopFailure"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    ELICITATION = "Elicitation"
    ELICITATION_RESULT = "ElicitationResult"
    TEAMMATE_IDLE = "TeammateIdle"
    TASK_COMPLETED = "TaskCompleted"
    SETUP = "Setup"
    INSTRUCTIONS_LOADED = "InstructionsLoaded"
    CWD_CHANGED = "CwdChanged"
    FILE_CHANGED = "FileChanged"
    CONFIG_CHANGE = "ConfigChange"
    WORKTREE_CREATE = "WorktreeCreate"
    WORKTREE_REMOVE = "WorktreeRemove"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    POST_TOOL_BATCH = "PostToolBatch"
    TASK_CREATED = "TaskCreated"
    PERMISSION_DENIED = "PermissionDenied"
    USER_PROMPT_EXPANSION = "UserPromptExpansion"
    MESSAGE_DISPLAY = "MessageDisplay"
    DIRECTORY_ADDED = "DirectoryAdded"


# 스키마 description이 "does not support matchers" / "Matchers are ignored" /
# "no matchers"라고 명시한 이벤트 — 여기에 matcher를 주면 무시된다.
# (나머지 이벤트는 matcher를 받는다. 무엇을 매칭하는지는 이벤트마다 다르다:
#  도구명, 에이전트 타입, 파일명, 설정 종류 등.)
NO_MATCHER_EVENTS: frozenset[HookEvent] = frozenset({
    HookEvent.TEAMMATE_IDLE,
    HookEvent.TASK_COMPLETED,
    HookEvent.INSTRUCTIONS_LOADED,
    HookEvent.CWD_CHANGED,
    HookEvent.WORKTREE_CREATE,
    HookEvent.WORKTREE_REMOVE,
    HookEvent.POST_TOOL_BATCH,
    HookEvent.TASK_CREATED,
})

# 공식 문서에 없고 스키마에만 "UNDOCUMENTED"로 있는 이벤트 — 쓸 수는 있으나
# 편집기가 표시할 때 그 사실을 알린다.
UNDOCUMENTED_EVENTS: frozenset[HookEvent] = frozenset({
    HookEvent.SETUP,
    HookEvent.DIRECTORY_ADDED,
})

# matcher를 받는 이벤트 — NO_MATCHER_EVENTS의 여집합.
MATCHER_EVENTS: frozenset[HookEvent] = frozenset(HookEvent) - NO_MATCHER_EVENTS

# 하위 호환 별칭 — 예전에는 Pre/PostToolUse만 matcher를 쓴다고 보았다.
# 이제 대부분 이벤트가 matcher를 받으므로 MATCHER_EVENTS를 쓰라.
TOOL_MATCH_EVENTS: frozenset[HookEvent] = MATCHER_EVENTS


class HookShell(Enum):
    """command 훅의 shell 지정. 미지정(빈 값)이면 CC 기본값."""
    DEFAULT = ""
    BASH = "bash"
    POWERSHELL = "powershell"


@dataclass
class HookHandler(ABC):
    """훅 핸들러 하나 — CC `hookCommand` 한 항목.

    공통 속성은 스키마의 다섯 변종 전부가 공유한다: timeout / if /
    statusMessage. `if`는 파이썬 예약어라 필드명은 `condition`이고,
    배출 시 `if` 키가 된다.
    """
    timeout: int | None = None
    condition: str = ""        # → "if" (permission-rule 문법 필터)
    status_message: str = ""   # → "statusMessage"
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    @property
    @abstractmethod
    def kind(self) -> str:
        """CC `type` 값 — 다형성 태그(직렬화·컴파일 공용)."""

    def to_json(self) -> dict[str, Any]:
        """CC hooks 스키마의 핸들러 객체로. 빈 값 키는 생략(결정적)."""
        out: dict[str, Any] = {"type": self.kind}
        out.update(self._payload())
        if self.timeout is not None:
            out["timeout"] = self.timeout
        if self.condition:
            out["if"] = self.condition
        if self.status_message:
            out["statusMessage"] = self.status_message
        return out

    @abstractmethod
    def _payload(self) -> dict[str, Any]:
        """타입별 고유 키 (type/공통 속성 제외)."""

    @abstractmethod
    def summary(self) -> str:
        """편집기 목록에 보일 한 줄 요약."""


@dataclass
class CommandHook(HookHandler):
    """셸 커맨드 실행. 가장 흔한 형태."""
    command: str = ""
    shell: HookShell = HookShell.DEFAULT
    args: list[str] = field(default_factory=list)
    run_async: bool = False      # → "async" (예약어라 필드명만 다르다)
    async_rewake: bool = False   # → "asyncRewake"

    @property
    def kind(self) -> str:
        return "command"

    def _payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"command": self.command}
        if self.args:
            out["args"] = list(self.args)
        if self.shell is not HookShell.DEFAULT:
            out["shell"] = self.shell.value
        if self.run_async:
            out["async"] = True
        if self.async_rewake:
            out["asyncRewake"] = True
        return out

    def summary(self) -> str:
        return self.command.strip() or "(커맨드 없음)"


@dataclass
class PromptHook(HookHandler):
    """LLM에게 판단을 맡기는 훅. 빠른 모델로 프롬프트를 평가한다."""
    prompt: str = ""
    model: str = ""
    continue_on_block: bool = False

    @property
    def kind(self) -> str:
        return "prompt"

    def _payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"prompt": self.prompt}
        if self.model:
            out["model"] = self.model
        if self.continue_on_block:
            out["continueOnBlock"] = True
        return out

    def summary(self) -> str:
        return self.prompt.strip() or "(프롬프트 없음)"


@dataclass
class AgentHook(HookHandler):
    """검증용 서브에이전트를 띄우는 훅. prompt가 그 에이전트의 지시다."""
    prompt: str = ""
    model: str = ""

    @property
    def kind(self) -> str:
        return "agent"

    def _payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"prompt": self.prompt}
        if self.model:
            out["model"] = self.model
        return out

    def summary(self) -> str:
        return self.prompt.strip() or "(프롬프트 없음)"


@dataclass
class HttpHook(HookHandler):
    """HTTP 엔드포인트로 POST하는 훅."""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    allowed_env_vars: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "http"

    def _payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"url": self.url}
        if self.headers:
            out["headers"] = dict(self.headers)
        if self.allowed_env_vars:
            out["allowedEnvVars"] = list(self.allowed_env_vars)
        return out

    def summary(self) -> str:
        return self.url.strip() or "(URL 없음)"


@dataclass
class McpToolHook(HookHandler):
    """설정된 MCP 서버의 도구를 호출하는 훅."""
    server: str = ""
    tool: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)  # → "input"

    @property
    def kind(self) -> str:
        return "mcp_tool"

    def _payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"server": self.server, "tool": self.tool}
        if self.tool_input:
            out["input"] = dict(self.tool_input)
        return out

    def summary(self) -> str:
        if self.server.strip() and self.tool.strip():
            return f"{self.server}.{self.tool}"
        return "(MCP 도구 없음)"


# kind 태그 → 클래스 (직렬화·편집기 공용 단일 진실)
HOOK_HANDLER_TYPES: dict[str, type[HookHandler]] = {
    "command": CommandHook,
    "prompt": PromptHook,
    "agent": AgentHook,
    "http": HttpHook,
    "mcp_tool": McpToolHook,
}

# 편집기 콤보 표시 문구
HOOK_HANDLER_LABELS: list[tuple[str, str]] = [
    ("command", "커맨드 실행"),
    ("prompt", "LLM 판단 (prompt)"),
    ("agent", "검증 에이전트 (agent)"),
    ("http", "HTTP 요청"),
    ("mcp_tool", "MCP 도구 호출"),
]


@dataclass
class HookDef(PluginComponent):
    """훅 그룹 1건 — 라이브러리(hook_library)에 놓이는 단일 진실.

    CC의 `hookMatcher` 하나에 대응한다: 하나의 이벤트 + 선택적 matcher +
    그 아래 실행될 핸들러 목록.

    name은 식별자(config.hooks 키가 참조)이며 CC 산출물에는 나가지 않는다 —
    Daedalus 안에서 훅을 지목하기 위한 이름이다.

    id는 안정 식별자(WP-F 패턴: uuid, kw_only, compare=False).
    """
    event: HookEvent = HookEvent.PRE_TOOL_USE
    matcher: str = ""
    handlers: list[HookHandler] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    @property
    def kind(self) -> str:
        return "hook"

    @property
    def supports_matcher(self) -> bool:
        return self.event in MATCHER_EVENTS

    def to_json(self) -> dict[str, Any]:
        """CC hooks 스키마의 그룹(hookMatcher) 객체로.

        matcher는 그 이벤트가 받을 때만 배출한다 — 무시되는 키를 내보내면
        설정한 사람은 걸린 줄 알지만 아무 일도 일어나지 않는다.
        """
        group: dict[str, Any] = {}
        if self.matcher and self.supports_matcher:
            group["matcher"] = self.matcher
        group["hooks"] = [h.to_json() for h in self.handlers]
        return group
