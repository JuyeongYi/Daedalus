"""작업 폴더 MCP/훅 배선 — `.mcp.json` + `.claude/settings.local.json` 병합 (WP-MW).

두 호출자가 같은 병합을 쓴다:
  1. LOCAL 빌드 컴파일(project_compiler._wire_local_install) — 컴파일이 곧 설치.
  2. 앱의 "Claude Code 실행"(view/app._launch_claude_code) — 프로젝트 폴더에서
     CC를 열기 전에 daedalus 서버를 배선해 새 세션이 바로 붙게 한다.

정책(두 호출자 공통):
  - **추가/갱신만 한다** — 이 배선이 만들지 않은 기존 항목은 지우지 않는다.
  - 같은 이름 서버는 갱신, 동일 hooks 그룹은 중복 삽입하지 않는다 → 재실행 멱등.
  - 깨진 JSON은 건드리지 않는다 — 병합을 강행하면 사용자의 수기 설정을 통째로
    덮어쓴다. 그 파일 경로를 `unmergeable`로 보고하고 넘어간다.

순수 stdlib(Qt 무관) — view가 import해도 된다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WireResult:
    """배선 결과 — 실제로 쓴 파일과 병합 불가 파일."""
    written: list[Path] = field(default_factory=list)
    unmergeable: list[Path] = field(default_factory=list)


def _load_json_or_none(path: Path) -> dict | None:
    """기존 JSON 파일을 읽는다. 없으면 빈 dict, 깨져 있으면 None(병합 불가 신호)."""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _dump_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def wire_workspace(
    target_dir: Path | str,
    server_entries: dict[str, dict] | None = None,
    hooks_map: dict | None = None,
) -> WireResult:
    """대상 작업 폴더의 CC 설정 파일을 생성/수정한다.

    server_entries: 이름 → `.mcp.json` 서버 객체. `<target>/.mcp.json`의
        `mcpServers`에 병합하고, `<target>/.claude/settings.local.json`의
        `enabledMcpjsonServers`에 이름을 올린다.
    hooks_map: CC settings `hooks` 스키마 dict(이벤트 → 그룹 목록).
        `settings.local.json`의 `hooks`에 병합한다(동일 그룹은 중복 삽입 안 함).
    """
    target = Path(target_dir)
    result = WireResult()
    entries = server_entries or {}

    # 1. .mcp.json — mcpServers 병합
    if entries:
        mcp_path = target / ".mcp.json"
        mcp_obj = _load_json_or_none(mcp_path)
        if mcp_obj is None:
            result.unmergeable.append(mcp_path)
        else:
            servers = mcp_obj.setdefault("mcpServers", {})
            if not isinstance(servers, dict):
                result.unmergeable.append(mcp_path)
            elif any(servers.get(k) != v for k, v in entries.items()):
                servers.update(entries)
                _dump_json(mcp_path, mcp_obj)
                result.written.append(mcp_path)

    # 2. .claude/settings.local.json — enabledMcpjsonServers + hooks 병합
    if not entries and hooks_map is None:
        return result
    settings_path = target / ".claude" / "settings.local.json"
    settings_obj = _load_json_or_none(settings_path)
    if settings_obj is None:
        result.unmergeable.append(settings_path)
        return result

    changed = False
    if entries:
        enabled = settings_obj.setdefault("enabledMcpjsonServers", [])
        if not isinstance(enabled, list):
            result.unmergeable.append(settings_path)
            return result
        for name in entries:
            if name not in enabled:
                enabled.append(name)
                changed = True

    if hooks_map is not None:
        existing_hooks = settings_obj.setdefault("hooks", {})
        if not isinstance(existing_hooks, dict):
            result.unmergeable.append(settings_path)
            return result
        for event, groups in hooks_map.items():
            bucket = existing_hooks.setdefault(event, [])
            if not isinstance(bucket, list):
                result.unmergeable.append(settings_path)
                return result
            for group in groups:
                # 동일 그룹(matcher+핸들러가 완전히 같은 것)은 다시 넣지 않는다 —
                # 재실행할 때마다 훅이 불어나면 같은 훅이 여러 번 실행된다.
                if group not in bucket:
                    bucket.append(group)
                    changed = True

    if changed or not settings_path.exists():
        _dump_json(settings_path, settings_obj)
        result.written.append(settings_path)
    return result
