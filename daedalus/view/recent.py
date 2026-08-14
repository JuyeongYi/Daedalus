"""최근 프로젝트 목록 (WP-RP). Qt 무관 — 순수 stdlib.

단일 진실은 ``~/.daedalus/recent.json`` 파일이다(MCP 접속 정보와 같은 디렉토리).
내용은 경로 문자열 배열 하나뿐 — 최근 것이 앞이다.

기록 실패는 삼킨다: 최근 목록은 편의 기능이므로, 여기서 난 오류가 저장이나
열기 자체를 실패로 만들면 안 된다(``mcp/endpoint.py``의 접속 정보 기록과 같은
정책).

파일 실존 여부는 **여기서 확인하지 않는다** — 메뉴를 열 때마다 경로마다
stat을 때리면 네트워크 드라이브에서 UI가 멈춘다. 사라진 파일은 실제로
열려고 할 때 걸러내고 그 시점에 목록에서 떨군다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

RECENT_PATH = Path.home() / ".daedalus" / "recent.json"

MAX_RECENT = 10
"""메뉴에 담을 최대 개수. 넘치면 오래된 것부터 밀려난다."""


def _key(path: str) -> str:
    """중복 판정용 정규화 키.

    ``normcase``가 Windows의 대소문자 무시 비교까지 흡수하므로, 같은 파일을
    다른 표기로 열어도 항목이 둘로 늘어나지 않는다.
    """
    return os.path.normcase(os.path.abspath(path))


def load() -> list[str]:
    """저장된 목록을 읽는다. 파일이 없거나 깨졌으면 빈 목록."""
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str) or not item.strip():
            continue
        key = _key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out[:MAX_RECENT]


def save(paths: Iterable[str]) -> None:
    """목록을 파일에 쓴다. 실패는 무시한다."""
    try:
        RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECENT_PATH.write_text(
            json.dumps(list(paths)[:MAX_RECENT], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def push(path: str) -> list[str]:
    """경로를 맨 앞으로 올리고 저장한다. 갱신된 목록을 돌려준다."""
    if not path or not path.strip():
        return load()
    absolute = os.path.abspath(path)
    key = _key(absolute)
    paths = [p for p in load() if _key(p) != key]
    paths.insert(0, absolute)
    paths = paths[:MAX_RECENT]
    save(paths)
    return paths


def remove(path: str) -> list[str]:
    """경로를 목록에서 뺀다(사라진 파일 정리용). 갱신된 목록을 돌려준다."""
    key = _key(path)
    paths = [p for p in load() if _key(p) != key]
    save(paths)
    return paths


def clear() -> None:
    """목록을 비운다."""
    save([])
