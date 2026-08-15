"""작업 폴더 배선 공유 함수 (wiring.wire_workspace, WP-MW).

LOCAL 컴파일과 "Claude Code 실행" 메뉴가 같은 폴더를 만진다 — 두 경로가 다르게
만지면 안 되므로 병합 로직은 이 한 함수뿐이어야 한다. 여기서는 함수 자체의
계약을 고정한다(컴파일 경유 동작은 test_build_target.py).
"""
from __future__ import annotations

import json

from daedalus.compiler.wiring import wire_workspace

_ENTRY = {"type": "http", "url": "http://127.0.0.1:8787/mcp"}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_creates_both_files_from_nothing(tmp_path):
    result = wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})

    assert _read(tmp_path / ".mcp.json")["mcpServers"]["daedalus"] == _ENTRY
    settings = _read(tmp_path / ".claude" / "settings.local.json")
    assert settings["enabledMcpjsonServers"] == ["daedalus"]
    assert len(result.written) == 2
    assert result.unmergeable == []


def test_rerun_is_noop(tmp_path):
    """바뀐 것이 없으면 파일을 다시 쓰지 않는다 — written이 비어야 한다."""
    wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})
    second = wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})
    assert second.written == []


def test_same_server_updates_in_place(tmp_path):
    """같은 이름 서버는 갱신된다 — 포트가 바뀌어도 항목이 둘로 늘지 않는다."""
    wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})
    moved = {"type": "http", "url": "http://127.0.0.1:9999/mcp"}
    wire_workspace(tmp_path, {"daedalus": moved})

    servers = _read(tmp_path / ".mcp.json")["mcpServers"]
    assert servers == {"daedalus": moved}


def test_preserves_unrelated_content(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({
        "mcpServers": {"other": {"command": "x"}},
    }), encoding="utf-8")
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    (settings_dir / "settings.local.json").write_text(json.dumps({
        "permissions": {"allow": ["Read"]},
        "enabledMcpjsonServers": ["other"],
    }), encoding="utf-8")

    wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})

    assert _read(tmp_path / ".mcp.json")["mcpServers"]["other"] == {"command": "x"}
    settings = _read(settings_dir / "settings.local.json")
    assert settings["permissions"] == {"allow": ["Read"]}
    assert settings["enabledMcpjsonServers"] == ["other", "daedalus"]


def test_hooks_merge_dedupes_identical_groups(tmp_path):
    group = {"hooks": [{"type": "command", "command": "echo hi"}]}
    wire_workspace(tmp_path, hooks_map={"SessionStart": [group]})
    wire_workspace(tmp_path, hooks_map={"SessionStart": [group]})

    settings = _read(tmp_path / ".claude" / "settings.local.json")
    assert len(settings["hooks"]["SessionStart"]) == 1


def test_broken_json_reported_not_clobbered(tmp_path):
    (tmp_path / ".mcp.json").write_text("{ nope", encoding="utf-8")
    result = wire_workspace(tmp_path, {"daedalus": dict(_ENTRY)})

    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{ nope"
    assert (tmp_path / ".mcp.json") in result.unmergeable
    # settings.local.json 쪽은 정상이므로 배선된다
    settings = _read(tmp_path / ".claude" / "settings.local.json")
    assert settings["enabledMcpjsonServers"] == ["daedalus"]


def test_nothing_to_do_creates_nothing(tmp_path):
    result = wire_workspace(tmp_path)
    assert result.written == []
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".claude").exists()
