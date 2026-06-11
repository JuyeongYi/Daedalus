# daedalus/model/plugin/hook.py
"""훅(Hook) 모델 — CC lifecycle hooks 정의 (순수 모델, PyQt 무관).

훅은 두 곳에서 쓰인다:
  1. 에이전트 SETTINGS → `<out>/hooks/hooks.json` (CC settings hooks 스키마).
  2. 스킬/에이전트 프론트매터 `hooks:` (라이브러리 HookDef 이름 참조 목록).

`PluginProject.hook_library`가 HookDef의 단일 진실(shelf 성격)이고,
``ComponentConfig.hooks``는 그 이름을 키로 참조한다 (tool_shelf ↔ 이름 참조 선례와 동일).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from daedalus.model.plugin.base import PluginComponent


class HookEvent(Enum):
    """CC 실제 훅 이벤트.

    CC hooks 스키마 기준 2026-06 검증. 추가 이벤트는 여기 갱신한다.
    값은 CC settings.json hooks 키로 그대로 쓰이는 PascalCase 이벤트명이다.
    """
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"
    NOTIFICATION = "Notification"
    PRE_COMPACT = "PreCompact"


# matcher(도구명 패턴)가 의미를 갖는 이벤트 — Pre/PostToolUse만 도구 매칭을 쓴다.
# 나머지 이벤트는 matcher가 빈 값이어야 한다 (검증 규칙 hook_matcher_without_tool_event).
TOOL_MATCH_EVENTS: frozenset[HookEvent] = frozenset({
    HookEvent.PRE_TOOL_USE,
    HookEvent.POST_TOOL_USE,
})


@dataclass
class HookDef(PluginComponent):
    """훅 정의 1건 — 라이브러리(hook_library)에 놓이는 단일 진실.

    name은 식별자(config.hooks 키가 참조). matcher는 Pre/PostToolUse 이벤트에서만
    도구명 패턴으로 쓰이고 그 외 이벤트는 빈 값을 유지한다. command는 실행 커맨드,
    timeout은 초 단위(없으면 None — hooks.json에서 키 생략).

    id는 안정 식별자(WP-F 패턴: uuid, kw_only, compare=False).
    """
    event: HookEvent = HookEvent.PRE_TOOL_USE
    matcher: str = ""
    command: str = ""
    timeout: int | None = None
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    @property
    def kind(self) -> str:
        return "hook"
