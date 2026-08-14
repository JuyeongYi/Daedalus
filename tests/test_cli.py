"""명령줄 인자 (--mcp-port / --no-mcp).

파싱은 Qt 없이 검증하고, 포트 지정이 실제 서버 기동에 반영되는지는
DaedalusMCPService.start 쪽에서 확인한다.
"""
from __future__ import annotations

import pytest

from daedalus.__main__ import parse_args


def _parse(*argv):
    return parse_args(["daedalus", *argv])


def test_defaults_are_auto_port_with_mcp_on():
    args, _ = _parse()
    assert args.mcp_port is None
    assert args.no_mcp is False


def test_mcp_port_parsed_as_int():
    args, _ = _parse("--mcp-port", "9123")
    assert args.mcp_port == 9123


def test_mcp_port_equals_form():
    args, _ = _parse("--mcp-port=9123")
    assert args.mcp_port == 9123


def test_no_mcp_flag():
    args, _ = _parse("--no-mcp")
    assert args.no_mcp is True


def test_unknown_args_go_to_qt():
    """Qt 자체 옵션(-style 등)을 우리가 삼키면 안 된다."""
    args, qt_argv = _parse("--mcp-port", "8800", "-style", "fusion")
    assert args.mcp_port == 8800
    assert qt_argv == ["daedalus", "-style", "fusion"]


def test_program_name_kept_first():
    _args, qt_argv = _parse("--no-mcp")
    assert qt_argv[0] == "daedalus"


def test_invalid_port_exits():
    with pytest.raises(SystemExit):
        _parse("--mcp-port", "not-a-number")


# --- 서비스 쪽 반영 ---


@pytest.fixture
def service(qapp):
    from daedalus.mcp.service import DaedalusMCPService
    from daedalus.model.project import PluginProject
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    svc = DaedalusMCPService(win)
    yield svc
    win.close()


def test_explicit_port_is_not_scanned_away(service, monkeypatch):
    """지정한 포트가 막혀 있으면 다른 포트로 물러나지 않고 실패한다.

    물러나면 지정한 의미가 없다 — 고정 포트를 가리키는 .mcp.json이 엉뚱한
    인스턴스에 붙는다.
    """
    from daedalus.mcp import endpoint

    monkeypatch.setattr(endpoint, "is_port_free", lambda p, host="127.0.0.1": False)
    monkeypatch.setattr(
        endpoint, "find_free_port",
        lambda *a, **k: pytest.fail("지정 포트가 있으면 스캔하면 안 된다"),
    )

    assert service.start(9999) is None
    assert "9999" in (service.error or "")


def test_auto_port_scans_when_unspecified(service, monkeypatch):
    from daedalus.mcp import endpoint

    monkeypatch.setattr(endpoint, "find_free_port", lambda *a, **k: None)
    assert service.start() is None
    assert "사용 중" in (service.error or "")
