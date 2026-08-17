# daedalus/compiler/emit/hooks.py
"""hooks.json + 훅 스크립트 파일 산출 (SETTINGS) — WP-RS 진행 상태 합성 훅 포함."""
from __future__ import annotations

import json
from typing import Any

from daedalus.compiler.emit.common import _graph_placements_any
from daedalus.compiler.emit.manifest import expand_root_token
from daedalus.model.plugin.hook import (
    HOOK_SCRIPT_REF_PREFIX,
    HookDef,
    HookEvent,
)


def _collect_referenced_hook_names(project) -> list[str]:
    """프로젝트 전체 config.hooks 키(훅 이름 참조)를 첫 등장 순서·중복 제거로 수집.

    스킬·에이전트의 config.hooks를 모두 훑는다. 출력은 결정적(선언 순회
    순서)이며, hook_library에 없는 이름은 여기서 거르지 않는다
    (dangling은 검증/게이트 경고로 별도 처리 — emit은 라이브러리 교집합만 출력).
    """
    names: list[str] = []
    seen: set[str] = set()

    def _add_from(cfg) -> None:
        hooks = getattr(cfg, "hooks", None)
        if isinstance(hooks, dict):
            for name in hooks:
                if name not in seen:
                    seen.add(name)
                    names.append(name)

    for skill in getattr(project, "skills", []):
        _add_from(getattr(skill, "config", None))
    for agent in getattr(project, "agents", []):
        _add_from(getattr(agent, "config", None))
    return names


# WP-RS Part B: SessionStart에 합성 배출되는 진행 상태 주입 훅.
# hook_library를 오염시키지 않는다 — hooks.json 합류는 컴파일 시점에만 합성된다.
# WP-HS: 다른 훅과 같은 규칙으로 스크립트 파일이 되고, hooks.json에는 경로만 남는다.
_PROGRESS_SESSION_START_COMMAND = 'cat state/__progress__.json 2>/dev/null || true'
_PROGRESS_SCRIPT_NAME = "__progress__.sh"
_PROGRESS_SCRIPT_REF = f"{HOOK_SCRIPT_REF_PREFIX}{_PROGRESS_SCRIPT_NAME}"


def _progress_hook_entry() -> dict[str, Any]:
    return {"type": "command", "command": _PROGRESS_SCRIPT_REF}


def compile_hook_scripts(project) -> list[tuple[str, str]]:
    """훅 스크립트 파일 — [(``hooks/scripts/`` 기준 상대경로, 내용), …] (WP-HS).

    커맨드는 아무리 짧아도 파일로 나간다 — hooks.json에는 루트 기반 경로만
    남는다. 참조된 훅만 대상이며(hooks.json에 실리는 것과 같은 집합), 진행 상태
    합성 훅도 같은 규칙으로 파일이 된다.

    반환 순서는 결정적이다(라이브러리 선언 순서 → 훅 내 핸들러 순서).
    같은 파일명이 둘 나오면 나중 것이 앞의 것을 덮으므로 **먼저 선언된 훅이
    이긴다** — 이름 충돌은 `duplicate_hook_script`가 컴파일 게이트에서 잡는다.
    """
    library = getattr(project, "hook_library", None) or []
    referenced = set(_collect_referenced_hook_names(project))

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for hook in library:
        if hook.name not in referenced:
            continue
        for filename, body in hook.script_files():
            if filename in seen:
                continue
            seen.add(filename)
            out.append((filename, _script_text(body)))

    if _should_emit_progress_hook(project) and _PROGRESS_SCRIPT_NAME not in seen:
        out.append((_PROGRESS_SCRIPT_NAME, _script_text(_PROGRESS_SESSION_START_COMMAND)))
    return out


def _script_text(body: str) -> str:
    """스크립트 본문을 파일 텍스트로 — LF 고정, 끝 개행 1개."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _should_emit_progress_hook(project) -> bool:
    return bool(getattr(project, "emit_progress_hook", True)) and bool(
        _graph_placements_any(project)
    )


def compile_hooks_json(project) -> str | None:
    """프로젝트가 참조하는 HookDef를 모아 CC settings hooks.json 텍스트로.

    스키마:
        {"hooks": {"<EventName>": [{"matcher": "...", "hooks": [{"type": "command",
          "command": "...", "timeout": ...}]}]}}
    - matcher는 도구 이벤트(Pre/PostToolUse)에서만 출력. 그 외 이벤트는 matcher 생략.
    - 같은 이벤트의 복수 훅은 hook_library 선언 순서로 정렬(결정적).
    - 이벤트 키 순서는 HookEvent 선언 순서(결정적).

    WP-RS Part B: `project.emit_progress_hook`(기본 True)이고 프로젝트 그래프에
    placement가 1개 이상이면 SessionStart 이벤트에 진행 상태 주입 커맨드를
    합성해 합류시킨다(hook_library에는 기록하지 않음 — 순수 컴파일 시점 합성).
    사용자 정의 SessionStart 훅이 있으면 그 뒤에 공존한다.

    참조된 라이브러리 훅도 없고 합성 진행 훅도 없으면 None(파일 생성 안 함).

    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    library = getattr(project, "hook_library", None) or []
    by_name = {h.name: h for h in library}
    referenced = _collect_referenced_hook_names(project)
    resolved = [by_name[n] for n in referenced if n in by_name]

    emit_progress = _should_emit_progress_hook(project)

    if not resolved and not emit_progress:
        return None

    # 이벤트 → HookDef 목록 (라이브러리 선언 순서 유지, 결정적).
    resolved_names = {h.name for h in resolved}
    event_buckets: dict[HookEvent, list[HookDef]] = {}
    for hook in library:
        if hook.name in resolved_names:
            event_buckets.setdefault(hook.event, []).append(hook)

    hooks_obj: dict[str, Any] = {}
    for event in HookEvent:  # 선언 순서 = 결정적 이벤트 키 순서
        bucket = event_buckets.get(event) or []
        # 핸들러가 하나도 없는 훅은 배출하지 않는다 — CC 스키마에서 hooks는
        # 필수이고, 빈 배열은 아무 일도 하지 않으면서 파일만 늘린다.
        groups: list[dict[str, Any]] = [h.to_json() for h in bucket if h.handlers]
        if event is HookEvent.SESSION_START and emit_progress:
            # 사용자 정의 SessionStart 훅 뒤에 합성 훅을 이어붙인다(공존).
            groups.append({"hooks": [_progress_hook_entry()]})
        if groups:
            hooks_obj[event.value] = groups

    text = json.dumps({"hooks": hooks_obj}, ensure_ascii=False, indent=2)
    # 스크립트 참조의 ${ROOT}를 빌드 타깃에 맞는 CC 변수로 확장한다 (WP-HS/WP-RT).
    text = expand_root_token(text, project)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text
