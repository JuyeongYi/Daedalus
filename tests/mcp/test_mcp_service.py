"""MCP 서버 부속 계층 (WP-MCP) — 엔드포인트 파일, 도구 래핑, 마샬링.

서버를 실제로 띄우지 않는다(포트 점유·CI 불안정). 대신 "CC가 붙을 수 있는
형태로 구성되는가"를 구성 단계에서 확인한다.
"""
from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from daedalus.mcp import endpoint


def _list_tools(server):
    """list_tools는 mcp 1.x에서 코루틴, 2.x에서 동기 함수다."""
    result = server.list_tools()
    if inspect.iscoroutine(result):
        return asyncio.run(result)
    return result


# --- 엔드포인트 파일 (Qt 무관 순수 계층) ---


def test_url_for_builds_mcp_path():
    assert endpoint.url_for(8787) == "http://127.0.0.1:8787/mcp"


def test_find_free_port_returns_bindable_port():
    port = endpoint.find_free_port()
    assert port is not None
    assert endpoint.is_port_free(port)


def test_find_free_port_skips_occupied(monkeypatch):
    """점유된 포트는 건너뛴다 — 먼저 켜진 인스턴스와 충돌하지 않도록."""
    blocked = {endpoint.DEFAULT_PORT, endpoint.DEFAULT_PORT + 1}
    monkeypatch.setattr(endpoint, "is_port_free", lambda p, host="127.0.0.1": p not in blocked)
    assert endpoint.find_free_port() == endpoint.DEFAULT_PORT + 2


def test_find_free_port_gives_up_within_limit(monkeypatch):
    monkeypatch.setattr(endpoint, "is_port_free", lambda p, host="127.0.0.1": False)
    assert endpoint.find_free_port() is None


def test_write_read_clear_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / "endpoint.json"
    monkeypatch.setattr(endpoint, "ENDPOINT_PATH", path)

    endpoint.write(9001, project_path="C:/x/p.daedalus.json")
    data = endpoint.read()
    assert data is not None
    assert data["port"] == 9001
    assert data["url"] == endpoint.url_for(9001)
    assert data["project"] == "C:/x/p.daedalus.json"

    endpoint.clear()
    assert endpoint.read() is None


def test_write_failure_is_swallowed(monkeypatch, tmp_path):
    """접속 정보 기록 실패가 서버 기동을 막으면 안 된다."""
    monkeypatch.setattr(endpoint, "ENDPOINT_PATH", tmp_path / "nope" / "e.json")
    monkeypatch.setattr(
        endpoint.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("denied"))
    )
    endpoint.write(9002)  # 예외가 새어 나오지 않아야 한다


def test_mcp_json_snippet_is_valid_http_config():
    snippet = json.loads(endpoint.mcp_json_snippet(8787))
    server = snippet["mcpServers"]["daedalus"]
    assert server["type"] == "http"
    assert server["url"].endswith("/mcp")


# --- 서버 구성 ---


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


def test_server_builds_with_all_tools(service):
    from daedalus.mcp.service import TOOL_NAMES

    server = service._build_server()
    names = {t.name for t in _list_tools(server)}
    assert names == set(TOOL_NAMES)


def test_wrapped_tool_preserves_signature(service):
    """SDK가 입력 스키마를 만들려면 원본 시그니처가 보존돼야 한다.

    래퍼가 (**kwargs)로만 보이면 도구에 인자가 없는 것으로 노출돼, CC가
    name/x/y를 넘길 방법이 사라진다.
    """
    wrapped = service._wrap(service._tools.move_state)
    params = inspect.signature(wrapped).parameters
    assert list(params) == ["name", "x", "y", "agent"]


def test_wrapped_tool_docstring_survives(service):
    wrapped = service._wrap(service._tools.get_selection)
    assert wrapped.__doc__ and "선택" in wrapped.__doc__


def test_tool_schema_exposes_arguments(service):
    """스키마까지 실제로 인자를 담고 있는지 — 시그니처 보존의 최종 결과."""
    server = service._build_server()
    tool = next(t for t in _list_tools(server) if t.name == "place_component")
    props = tool.inputSchema["properties"]
    assert "name" in props and "x" in props and "y" in props


def test_service_starts_stopped(service):
    assert service.running is False
    assert service.url is None


def test_server_factory_picks_available_class(service):
    """mcp 1.x(FastMCP) / 2.x(MCPServer) 어느 쪽이든 클래스를 찾아야 한다."""
    cls = service._server_factory()
    assert cls.__name__ in {"MCPServer", "FastMCP"}


# --- 메인 스레드 마샬링 ---


def test_invoker_runs_callable_and_returns_result(qapp):
    from daedalus.mcp.invoker import MainThreadInvoker

    invoker = MainThreadInvoker()
    # 메인 스레드에서 직접 호출하면 큐 연결이 대기 상태로 남으므로,
    # 워커 스레드에서 호출해야 실제 경로가 된다.
    import threading

    out = {}

    def worker():
        try:
            out["value"] = invoker.call(lambda: 21 * 2)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    # 워커가 끝날 때까지 메인 스레드는 이벤트를 처리해야 한다
    while thread.is_alive():
        qapp.processEvents()
    thread.join()

    assert out.get("value") == 42


def test_invoker_propagates_exception(qapp):
    import threading

    from daedalus.mcp.invoker import MainThreadInvoker

    invoker = MainThreadInvoker()
    out = {}

    def boom():
        raise ValueError("터짐")

    def worker():
        try:
            invoker.call(boom)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    while thread.is_alive():
        qapp.processEvents()
    thread.join()

    assert isinstance(out.get("error"), ValueError)
    assert "터짐" in str(out["error"])


def test_invoker_times_out_when_loop_blocked(qapp):
    """이벤트 루프가 안 돌면 무한 대기가 아니라 TimeoutError로 끝나야 한다."""
    import threading

    from daedalus.mcp.invoker import MainThreadInvoker

    invoker = MainThreadInvoker()
    out = {}

    def worker():
        try:
            invoker.call(lambda: None, timeout=0.2)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()  # processEvents를 부르지 않는다 = 루프 정지 상태

    assert isinstance(out.get("error"), TimeoutError)
