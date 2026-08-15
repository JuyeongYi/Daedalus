"""앱이 아는 서버 정의 자동 주입 (WP-MW).

daedalus 서버는 이 앱 자신이 띄운다 — 접속 정보를 앱이 이미 아는데 사용자에게
set_mcp_server_def 등록을 시키면 안 된다(사용자 지적). 컴파일이 자동 주입한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def test_daedalus_def_known_without_running_server(window):
    """MCP를 끄고 컴파일해도 기본 포트로 배선한다 — 설치 후 앱을 켜면 붙는다."""
    defs = window._known_server_defs()
    assert defs["daedalus"] == {
        "type": "http", "url": "http://127.0.0.1:8787/mcp",
    }


def test_running_service_port_wins(window):
    class _FakeService:
        url = "http://127.0.0.1:9123/mcp"

    window._mcp_service = _FakeService()
    assert window._known_server_defs()["daedalus"]["url"] == "http://127.0.0.1:9123/mcp"
