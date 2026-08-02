# daedalus/view/editors/catalogue_loader.py
"""도구/MCP 카탈로그 로더 (view 측, variable_loader.py 패턴).

카탈로그 = ``~/.daedalus/catalogue/*.json``(글로벌) +
``<프로젝트>/.daedalus/catalogue/*.json``(프로젝트, 이름 충돌 시 우선). 파일 1개 =
항목 1개, 파일명 stem이 항목/서버 이름이 된다.

파일 스키마: ``{"description": str?, "tool": [str...]?, "mcp": [str...]?}``
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from daedalus.model.validation import CC_BUILTIN_TOOLS


@dataclass(frozen=True)
class CatalogueEntry:
    name: str                  # 파일명 stem
    description: str
    tools: tuple[str, ...]     # "tool" 키 — CC allowed-tools 문법 그대로
    mcp: tuple[str, ...]       # "mcp" 키 — 원문(도구 이름), 확장은 expanded_mcp()가 담당
    source: Literal["global", "project"]


def load_catalogue(project_dir: Path | None = None) -> list[CatalogueEntry]:
    """글로벌 + 프로젝트 카탈로그를 병합해 반환한다.

    이름(파일명 stem) 충돌 시 프로젝트 항목이 글로벌 항목을 덮는다.
    두 위치 모두 디렉토리가 없으면 해당 레벨은 빈 목록.
    """
    merged: dict[str, CatalogueEntry] = {}

    global_dir = Path.home() / ".daedalus" / "catalogue"
    for entry in _load_dir(global_dir, "global"):
        merged[entry.name] = entry

    if project_dir is not None:
        project_dir_path = project_dir / ".daedalus" / "catalogue"
        for entry in _load_dir(project_dir_path, "project"):
            merged[entry.name] = entry

    return list(merged.values())


def _load_dir(dir_path: Path, source: Literal["global", "project"]) -> list[CatalogueEntry]:
    if not dir_path.is_dir():
        return []
    result: list[CatalogueEntry] = []
    for path in sorted(dir_path.glob("*.json")):
        entry = _load_entry_file(path, source)
        if entry is not None:
            result.append(entry)
    return result


def _load_entry_file(path: Path, source: Literal["global", "project"]) -> CatalogueEntry | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("최상위 값이 객체(dict)가 아님")
        tools = data.get("tool", [])
        mcp = data.get("mcp", [])
        if not isinstance(tools, list) or not isinstance(mcp, list):
            raise ValueError("'tool'/'mcp' 키는 문자열 배열이어야 함")
        return CatalogueEntry(
            name=path.stem,
            description=str(data.get("description", "")),
            tools=tuple(str(t) for t in tools),
            mcp=tuple(str(m) for m in mcp),
            source=source,
        )
    except Exception as exc:  # noqa: BLE001 — 파싱 실패 파일은 경고 후 스킵(하네스 중단 금지)
        print(f"[daedalus] 카탈로그 파일 파싱 실패, 무시함: {path} ({exc})", file=sys.stderr)
        return None


def expanded_mcp(entry: CatalogueEntry) -> list[str]:
    """entry.mcp의 각 도구 이름을 ``mcp__<entry.name>__<도구>``로 확장한다.

    이미 ``mcp__``로 시작하는 항목은 그대로 둔다(사용자가 완전한 이름을 직접
    적어둔 경우).
    """
    result: list[str] = []
    for tool_name in entry.mcp:
        if tool_name.startswith("mcp__"):
            result.append(tool_name)
        else:
            result.append(f"mcp__{entry.name}__{tool_name}")
    return result


def candidate_strings(entries: list[CatalogueEntry], project: object = None) -> list[str]:
    """allowed-tools 계열 TagInput에 제공할 자동완성 후보 문자열 목록.

    합성 순서: CC_BUILTIN_TOOLS(정렬) + 각 entry의 tool/expanded_mcp(카탈로그
    순서) + 프로젝트 에이전트들의 ``Agent(<이름>)``. 중복은 첫 등장만 유지한다.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(value: str) -> None:
        if value not in seen:
            seen.add(value)
            result.append(value)

    for builtin in sorted(CC_BUILTIN_TOOLS):
        _add(builtin)

    for entry in entries:
        for tool_name in entry.tools:
            _add(tool_name)
        for mcp_name in expanded_mcp(entry):
            _add(mcp_name)

    if project is not None:
        for agent in getattr(project, "agents", []) or []:
            name = getattr(agent, "name", None)
            if name:
                _add(f"Agent({name})")

    return result
