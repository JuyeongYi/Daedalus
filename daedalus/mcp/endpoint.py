"""MCP 접속 정보 파일 (WP-MCP). Qt 무관 — 순수 stdlib.

CC의 ``.mcp.json``은 정적 파일이라 포트를 매번 바꿀 수 없다. 그래서 기본 포트를
고정으로 쓰되, 이미 점유돼 있으면(대개 먼저 켜진 다른 Daedalus 인스턴스) 다음
포트로 물러난다. **실제로 열린 포트는 이 파일에 기록**되므로, 사람이든 CC든
지금 어느 주소로 붙어야 하는지 확인할 수 있다.

고정 포트를 가리키는 ``.mcp.json`` 설정은 결과적으로 "먼저 켜진 인스턴스"에
붙는다 — 여러 창을 띄운 경우 협업 대상이 하나로 정해지는 편이 예측 가능하다.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

DEFAULT_PORT = 8787
"""기본 포트. .mcp.json에 적어 두는 값이라 함부로 바꾸면 기존 설정이 끊긴다."""

PORT_SCAN_LIMIT = 20
"""기본 포트가 막혀 있을 때 위로 훑어볼 포트 개수."""

ENDPOINT_PATH = Path.home() / ".daedalus" / "mcp-endpoint.json"


def url_for(port: int, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{port}/mcp"


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """해당 포트에 바인딩 가능한지 확인한다.

    SO_REUSEADDR을 켜지 않는다 — 켜면 TIME_WAIT 소켓 위에도 바인딩이 성공해
    "비어 있다"는 판정이 실제 기동 성공을 보장하지 못한다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(start: int = DEFAULT_PORT, limit: int = PORT_SCAN_LIMIT) -> int | None:
    """start부터 limit개를 훑어 처음 비어 있는 포트를 돌려준다. 없으면 None."""
    for port in range(start, start + limit):
        if is_port_free(port):
            return port
    return None


def write(port: int, project_path: str | None = None, host: str = "127.0.0.1") -> Path:
    """접속 정보를 파일로 남긴다. 실패해도 예외를 밖으로 내지 않는다.

    이 파일은 편의 기능이다 — 기록에 실패했다고 서버가 못 뜰 이유는 없다.
    """
    payload: dict[str, Any] = {
        "url": url_for(port, host),
        "host": host,
        "port": port,
        "pid": os.getpid(),
        "project": project_path,
    }
    try:
        ENDPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ENDPOINT_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return ENDPOINT_PATH


def clear() -> None:
    """접속 정보 파일을 지운다(앱 종료 시). 실패는 무시한다."""
    try:
        ENDPOINT_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def read() -> dict[str, Any] | None:
    """기록된 접속 정보를 읽는다. 없거나 깨졌으면 None."""
    try:
        return json.loads(ENDPOINT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def mcp_json_snippet(port: int, host: str = "127.0.0.1") -> str:
    """CC의 .mcp.json에 붙여넣을 설정 조각."""
    return json.dumps(
        {"mcpServers": {"daedalus": {"type": "http", "url": url_for(port, host)}}},
        ensure_ascii=False,
        indent=2,
    )
