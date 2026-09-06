# daedalus/compiler/emit/hooks.py
"""hooks.json + 훅 스크립트 파일 산출 (SETTINGS) — WP-RS 진행 상태 합성 훅 포함."""
from __future__ import annotations

import json
from typing import Any

from daedalus.compiler.emit.common import _graph_placements_any, _is_local_build
from daedalus.compiler.emit.manifest import expand_root_token
from daedalus.model.plugin.hook import (
    HOOK_SCRIPT_REF_PREFIX,
    HookDef,
    HookEvent,
)


def hook_library(project, resolved_hooks: dict[str, HookDef] | None = None) -> list[HookDef]:
    """이 컴파일이 볼 훅 정의 목록 (A1 — 전역 훅 2단 스코프).

    ``resolved_hooks``는 **호출자가 주입**한다(``model/plugin/hook_store``의
    ``resolve_hooks``). 컴파일러는 파일시스템을 읽지 않는다 — 읽어 버리면
    "이 프로젝트를 컴파일한 결과"가 컴파일한 사람의 홈 디렉토리에 따라
    달라지는 것을 코드에서 볼 수 없게 된다.

    생략(None)하면 ``project.hook_library``만 본다 — 기존 호출부의 산출이
    바이트 단위로 불변이다(하위 호환 게이트).
    """
    if resolved_hooks is None:
        return list(getattr(project, "hook_library", None) or [])
    return list(resolved_hooks.values())


def emitted_hooks(
    project, resolved_hooks: dict[str, HookDef] | None = None
) -> list[HookDef]:
    """이 컴파일이 실제로 배출할 훅 (라이브러리 선언 순서 — 결정적).

    **플러그인 훅은 전역이다**(공식 plugins-reference 확인 2026-09-07:
    `hooks/hooks.json`과 plugin.json의 `hooks`는 **플러그인이 활성화되면
    자동으로 동작**하며, 스킬·에이전트가 참조해야 켜지는 것이 아니다).
    그래서 **프로젝트 훅 라이브러리는 참조 여부와 무관하게 전부 배출한다** —
    예전에는 `config.hooks`로 부착된 것만 실어, 부착하지 않은 훅이 산출에서
    말없이 사라졌다(사용자 보고: 만들어 둔 `log-tool-usage`가 빠졌다).

    전역 훅(`~/.daedalus/hooks/`)은 다르다 — 다른 프로젝트가 쓰라고 둔 재사용
    풀이므로 **명시 참조(`config.hooks`)가 있는 것만** 들어온다. 그러지 않으면
    컴파일한 사람의 홈에 있는 훅 전부가 모든 산출에 실린다.

    선별은 **훅 자신의 `enabled`**가 한다(사용자 확정) — 라이브러리는 "정의를
    모아 두고 고르는 곳"이므로 만들어 두고 아직 켜지 않은 훅이 있을 수 있다.
    컴포넌트 참조로 켜고 끌 수 없는 이유는 위와 같다(참조는 규격상 스위치가
    아니다).
    """
    library = hook_library(project, resolved_hooks)
    own = {
        h.name for h in (getattr(project, "hook_library", None) or [])
    }
    referenced = set(_collect_referenced_hook_names(project))
    return [
        h for h in library
        if (h.name in own or h.name in referenced)
        and getattr(h, "enabled", True)
    ]


def hooks_needing_scripts(
    project, resolved_hooks: dict[str, HookDef] | None = None
) -> list[HookDef]:
    """스크립트 파일을 배출해야 할 훅 (라이브러리 선언 순서 — 결정적).

    ``emitted_hooks``(전역 등록 대상) **∪ 에이전트 프론트매터가 참조하는 훅**이다.
    후자는 ``enabled=False``여도 포함된다(사용자 확정 2026-09-07): `enabled`는
    "플러그인 전역 훅으로 켤지"의 스위치이고, 에이전트 프론트매터 훅은 **그
    에이전트 안에서만 도는 별개 경로**라 전역으로는 끄고 특정 에이전트에서만
    쓰는 것이 정상적인 사용이다. 그 커맨드가 가리키는 스크립트가 없으면
    에이전트는 존재하지 않는 파일을 실행하게 된다.

    에이전트 참조를 LOCAL 빌드에서만 세는 이유는 그 프론트매터가 거기서만
    배출되기 때문이다(WP-LA — 마켓 배포 에이전트의 hooks는 CC가 무시한다).
    마켓 빌드에서까지 세면 아무 데서도 쓰이지 않는 스크립트가 산출에 남는다.
    """
    library = hook_library(project, resolved_hooks)
    wanted = {h.name for h in emitted_hooks(project, resolved_hooks)}
    if _is_local_build(project):
        for agent in getattr(project, "agents", []):
            cfg_hooks = getattr(getattr(agent, "config", None), "hooks", None)
            if isinstance(cfg_hooks, dict):
                wanted.update(cfg_hooks)
    return [h for h in library if h.name in wanted]


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


def compile_hook_scripts(
    project, resolved_hooks: dict[str, HookDef] | None = None
) -> list[tuple[str, str]]:
    """훅 스크립트 파일 — [(``hooks/scripts/`` 기준 상대경로, 내용), …] (WP-HS).

    커맨드는 아무리 짧아도 파일로 나간다 — hooks.json에는 루트 기반 경로만
    남는다. 참조된 훅만 대상이며(hooks.json에 실리는 것과 같은 집합), 진행 상태
    합성 훅도 같은 규칙으로 파일이 된다.

    반환 순서는 결정적이다(라이브러리 선언 순서 → 훅 내 핸들러 순서).
    같은 파일명이 둘 나오면 **먼저 선언된 훅이 이기고** 나머지는 버려진다 —
    다만 서로 다른 훅 사이의 이름 충돌은 그 전에 컴파일 게이트
    (`project_compiler._hook_script_name_conflicts` → `duplicate_hook_script`)가
    거부하므로, 여기 드롭은 게이트를 통과한 뒤에는 도달하지 않는다.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for hook in hooks_needing_scripts(project, resolved_hooks):
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


def compile_hooks_json(
    project, resolved_hooks: dict[str, HookDef] | None = None
) -> str | None:
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
    library = hook_library(project, resolved_hooks)
    resolved = emitted_hooks(project, resolved_hooks)

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
