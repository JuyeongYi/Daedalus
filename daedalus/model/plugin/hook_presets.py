# daedalus/model/plugin/hook_presets.py
"""내장 훅 프리셋 — "복사해 시작점으로 쓰는 템플릿" 모음 (순수 모델).

각 항목은 프로젝트 hook_library에 추가해 출발점으로 삼는 HookDef 템플릿이다.
커맨드는 합리적 예시일 뿐 그대로 동작을 보장하지 않으며, 사용자가 자신의
환경(셸/경로/도구)에 맞게 수정하는 것을 전제한다. 크로스 플랫폼 주의가 필요한
곳은 설명적 placeholder를 둔다.

UI(HookLibraryPanel)는 ``BUILTIN_HOOK_PRESETS``를 노출해 "프리셋에서 추가"
경로를 제공한다. 추가 시 사본(새 id)을 만들어 hook_library에 넣는다 — 원본 템플릿은
변형되지 않는다 (``preset_copy`` 헬퍼).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from daedalus.model.plugin.hook import (
    AgentHook,
    CommandHook,
    HookDef,
    HookEvent,
    PromptHook,
)

# 주의: 모듈 수준 단일 인스턴스이므로 그대로 hook_library에 넣지 말고 preset_copy로
# 사본을 만들어 쓴다 (id 충돌·공유 변형 방지).
BUILTIN_HOOK_PRESETS: list[HookDef] = [
    HookDef(
        name="format-on-edit",
        description="Edit/Write 직후 포맷터를 실행한다.",
        event=HookEvent.POST_TOOL_USE,
        matcher="Edit|Write",
        handlers=[CommandHook(
            script='echo "$CLAUDE_TOOL_FILE" | xargs -r your-formatter',
            timeout=30,
        )],
    ),
    HookDef(
        name="block-dangerous-bash",
        description="위험한 Bash 명령(rm -rf 등)을 사전 차단한다.",
        event=HookEvent.PRE_TOOL_USE,
        matcher="Bash",
        handlers=[CommandHook(
            script="your-guard-script  # 위험 패턴이면 비정상 종료(exit 2)로 차단",
            timeout=10,
            status_message="Bash 명령 검사 중…",
        )],
    ),
    HookDef(
        name="notify-on-stop",
        description="작업 완료 시 데스크톱/슬랙 알림을 보낸다.",
        event=HookEvent.STOP,
        handlers=[CommandHook(
            script='your-notify-script "Claude 작업이 완료되었습니다"',
            run_async=True,
        )],
    ),
    HookDef(
        name="inject-session-context",
        description="세션 시작 시 프로젝트 컨텍스트를 주입한다.",
        event=HookEvent.SESSION_START,
        handlers=[CommandHook(
            script="cat .claude/session-context.md  # stdout이 컨텍스트로 주입됨",
        )],
    ),
    HookDef(
        name="save-state-before-compact",
        description="컴팩트 직전 작업 상태를 파일로 저장한다.",
        event=HookEvent.PRE_COMPACT,
        handlers=[CommandHook(
            script="your-snapshot-script  # state/ 폴더에 진행 상태 백업",
            timeout=20,
        )],
    ),
    HookDef(
        name="log-prompt-submit",
        description="사용자 프롬프트 제출을 감사 로그에 기록한다.",
        event=HookEvent.USER_PROMPT_SUBMIT,
        handlers=[CommandHook(
            script="your-audit-logger  # stdin으로 프롬프트 페이로드 수신",
        )],
    ),
    # --- command 이외 핸들러 타입의 출발점 (WP-HK) ---
    HookDef(
        name="llm-review-edit",
        description="파일 수정 내용을 빠른 모델이 검토하고 문제가 있으면 막는다.",
        event=HookEvent.PRE_TOOL_USE,
        matcher="Edit|Write",
        handlers=[PromptHook(
            prompt="이 수정이 프로젝트 규약을 어기는지 판단하라. 어긴다면 이유를 설명하라.",
            status_message="수정 내용 검토 중…",
        )],
    ),
    HookDef(
        name="verify-before-stop",
        description="응답을 마치기 전에 검증 에이전트가 결과를 확인한다.",
        event=HookEvent.STOP,
        handlers=[AgentHook(
            prompt="이번 턴의 변경이 실제로 요구를 충족하는지 확인하고, 미흡하면 무엇이 빠졌는지 보고하라.",
            timeout=120,
        )],
    ),
]


def preset_copy(preset: HookDef) -> HookDef:
    """프리셋 HookDef의 사본을 새 id로 만든다 (hook_library 추가용).

    핸들러도 깊은 복사한다 — 얕게 복사하면 여러 프로젝트가 같은 핸들러
    객체를 공유해, 한쪽을 고치면 다른 쪽이 함께 바뀐다.
    """
    handlers = [replace(h, id=uuid4().hex) for h in deepcopy(preset.handlers)]
    return replace(preset, id=uuid4().hex, handlers=handlers)
