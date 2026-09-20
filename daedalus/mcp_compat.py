# daedalus/mcp_compat.py
"""MCP SDK 버전 흡수 — 서버 클래스 팩토리 (WP-BM).

Daedalus는 MCP 서버를 **둘** 띄운다: 앱 내장 편집 서버(`daedalus.mcp.service`,
Streamable HTTP)와 설치 대상에서 도는 블랙보드 서버(`daedalus.cli.mcp_server`,
stdio). 둘 다 같은 SDK를 쓰므로 버전 차이를 흡수하는 자리는 **한 곳**이어야
한다 — 복제하면 SDK가 또 바뀔 때 한쪽만 고쳐지고 다른 쪽이 조용히 죽는다.

`daedalus.model`을 임포트하지 않는다(모델 무의존). 그래서 순수 stdlib 제약을
지는 `daedalus/cli/**`가 이 모듈을 임포트해도 그 제약이 깨지지 않는다 — 깨지는
것은 "stdlib만"이 아니라 "mcp SDK도 허용"으로 명시된 계약이다
(`tests/test_import_contracts.py`).
"""
from __future__ import annotations

from typing import Any


def server_factory() -> Any:
    """SDK 버전에 맞는 서버 클래스를 고른다.

    mcp 2.0에서 ``FastMCP``가 ``MCPServer``로 대체됐다. 두 클래스는 우리가 쓰는
    표면(``name``/``instructions`` 생성자 인자, ``add_tool``, ``run``,
    ``streamable_http_app``)이 동일하므로 클래스만 갈아끼우면 된다.
    """
    try:
        from mcp.server import MCPServer  # mcp >= 2.0

        return MCPServer
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x

        return FastMCP
