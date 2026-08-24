# daedalus/model/plugin/hook_store.py
"""전역 훅 저장소 — `~/.daedalus/hooks/*.json` (A1).

훅은 프로젝트를 넘어 재사용된다. 같은 "커밋 전 포맷 검사"를 프로젝트마다
다시 만드는 것은 카탈로그(도구/MCP 후보) 이전과 똑같은 상황이고, 해법도
같다 — **전역 + 프로젝트 2단 스코프에 프로젝트 우선 병합**이다.

- 파일 1개 = 훅 1개, **파일명 stem이 훅 이름**(카탈로그와 같은 규약).
  파일 안의 `name` 키는 무시한다 — 이름의 단일 진실이 둘이면 파일을
  복사해 이름을 바꿨을 때 어느 쪽이 이겼는지 알 수 없다.
- 내용 형상은 `serialize`의 훅 직렬화와 **같다**(`event`/`matcher`/
  `description` + `kind` 태그 handlers). 그래서 프로젝트 훅을 그대로 떼어
  파일로 저장할 수 있고, 역직렬화도 `_deser_hook`를 그대로 쓴다.
- 파싱 실패·형상 불일치 파일은 stderr 경고 후 **건너뛴다**(카탈로그 관례) —
  파일 하나가 깨졌다고 앱이 뜨지 않으면 안 된다.

**이 모듈만 파일시스템을 안다.** 검증기(`model/validation`)와 컴파일러는
파일시스템 무접근 원칙을 지키므로, 해소된 dict를 **호출자가 주입**한다
(`compile_project(..., resolved_hooks=)` / `validate_project(...,
known_hook_names=)`). 그 경계가 없으면 "이 프로젝트를 컴파일한 결과"가
컴파일한 사람의 홈 디렉토리에 따라 달라지는 것을 코드에서 볼 수 없게 된다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from daedalus.model.plugin.hook import HookDef

GLOBAL_HOOKS_DIRNAME = "hooks"


def global_hooks_dir(home_dir: Path | None = None) -> Path:
    """전역 훅 폴더 경로. home_dir는 테스트용 주입점(None이면 실제 홈)."""
    base = home_dir if home_dir is not None else Path.home()
    return base / ".daedalus" / GLOBAL_HOOKS_DIRNAME


def load_global_hooks(home_dir: Path | None = None) -> list[HookDef]:
    """`~/.daedalus/hooks/*.json`을 읽어 HookDef 목록으로. 파일명순(결정적).

    폴더가 없으면 빈 목록. 읽을 수 없는 파일은 경고 후 건너뛴다.
    """
    directory = global_hooks_dir(home_dir)
    if not directory.is_dir():
        return []

    hooks: list[HookDef] = []
    for path in sorted(directory.glob("*.json")):
        hook = _load_hook_file(path)
        if hook is not None:
            hooks.append(hook)
    return hooks


def _load_hook_file(path: Path) -> HookDef | None:
    from daedalus.model.serialize import _deser_hook

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[daedalus] 전역 훅 파일을 읽을 수 없습니다: {path} — {exc}", file=sys.stderr)
        return None
    if not isinstance(raw, dict):
        print(
            f"[daedalus] 전역 훅 파일 형식이 올바르지 않습니다(객체가 아님): {path}",
            file=sys.stderr,
        )
        return None
    try:
        hook = _deser_hook(dict(raw))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[daedalus] 전역 훅을 해석할 수 없습니다: {path} — {exc}", file=sys.stderr)
        return None
    # 파일명이 이름의 단일 진실 (위 docstring 참조).
    hook.name = path.stem
    return hook


def resolve_hooks(project, home_dir: Path | None = None) -> dict[str, HookDef]:
    """이름 → HookDef, **전역 ← 프로젝트 순 갱신**(동명이면 프로젝트가 이긴다).

    컴파일·검증·UI가 "이 프로젝트에서 이 이름이 무슨 훅인가"를 물을 때 보는
    단일 진실이다. 프로젝트 훅이 전역을 덮는 이유는 카탈로그와 같다 —
    프로젝트에 넣었다는 것 자체가 "여기서는 이걸 쓴다"는 선언이다.
    """
    resolved: dict[str, HookDef] = {h.name: h for h in load_global_hooks(home_dir)}
    for hook in getattr(project, "hook_library", None) or []:
        resolved[hook.name] = hook
    return resolved


def hook_to_json(hook: HookDef) -> dict:
    """HookDef → 전역 훅 파일에 쓸 dict (`name`/`id` 제외).

    이름은 파일명이 정하고, id는 프로젝트 안의 안정 식별자라 파일로 나갈
    이유가 없다(복사한 훅이 원본과 같은 id를 갖는 편이 오히려 혼란스럽다).
    """
    from daedalus.model.serialize import _ser_hook

    data = _ser_hook(hook)
    data.pop("id", None)
    data.pop("name", None)
    for handler in data.get("handlers", []):
        handler.pop("id", None)
    return data
