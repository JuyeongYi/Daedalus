"""MCP 서버 수명주기 (WP-MCP) — 앱이 켜지면 함께 뜨고, 닫히면 함께 내려간다.

Streamable HTTP를 쓰는 이유: stdio는 **클라이언트가 서버 프로세스를 실행하는**
모델이라, 이미 떠 있는 GUI에 나중에 붙을 수 없다. HTTP면 앱이 먼저 켜져 서버를
열어두고 CC가 원할 때 접속하는, 사람이 기대하는 순서가 그대로 성립한다.

서버는 데몬 스레드의 uvicorn에서 돌고, 도구 핸들러는 ``MainThreadInvoker``로 Qt
메인 스레드에 넘겨 실행한다. 바인딩은 항상 ``127.0.0.1`` — 로컬 전용이므로 TLS를
얹지 않는다(외부 노출이 필요해지면 그때 붙일 문제다).
"""
from __future__ import annotations

import functools
import threading
from typing import Any, Callable

from daedalus.mcp import endpoint
from daedalus.mcp.invoker import MainThreadInvoker
from daedalus.mcp.tools import DaedalusTools

TOOL_NAMES = (
    # 읽기 — 사람이 지금 무엇을 보고 있는지까지 포함한다
    "get_project",
    "get_selection",
    "get_component",
    "get_body_outline",
    "get_body_section",
    "get_history",
    "validate_project",
    "compile_preview",
    "list_hook_events",
    "hook_frontmatter_preview",
    "list_component_fields",
    "list_recent_projects",
    # 세션 — 저장은 undo 대상이 아니다(파일 쓰기)
    "save_project",
    "open_project",
    "export_package",
    # 편집 — 전부 undo 가능
    "create_skill",
    "create_agent",
    "add_agent_call",
    "remove_agent_call",
    "rename_component",
    "delete_component",
    "set_component_description",
    "set_component_when_to_use",
    "set_component_field",
    "set_project_properties",
    "set_mcp_server_def",
    "place_component",
    "create_state",
    "move_state",
    "rename_state",
    "delete_state",
    "connect_states",
    "disconnect_states",
    "set_transition",
    "set_transfer_on",
    "create_blackboard_class",
    "set_state_access",
    "create_hook",
    "update_hook",
    "delete_hook",
    "set_component_hooks",
    "place_reference",
    "link_reference",
    "unlink_reference",
    "unplace_reference",
    "set_component_body",
    "set_body_section",
    # 작업 폴더 문서 — .claude/CLAUDE.md 구역 + .claude/rules/ (WP-WD, LOCAL 전용)
    "list_workspace_docs",
    "get_workspace_doc",
    "set_claude_md",
    "create_rule",
    "set_rule_body",
    "set_rule_paths",
    "rename_rule",
    "delete_rule",
    "undo",
    "redo",
)

_INSTRUCTIONS = """\
Daedalus(FSM 기반 Claude Code 플러그인 설계 도구)의 열려 있는 편집 세션에 연결돼 \
있습니다. 이 서버는 조회용 API가 아니라 **사람과 같은 프로젝트를 함께 편집하는 \
통로**입니다.

- 작업 전에 `get_selection`으로 사용자가 지금 무엇을 선택하고 있는지 확인하세요. \
사용자가 "이거"라고 말할 때 그것을 가리킵니다.
- `get_history`는 사용자가 방금 한 편집을 보여줍니다.
- 편집 도구는 즉시 캔버스에 반영되며 전부 사용자의 undo 스택에 들어갑니다 — \
사용자가 Ctrl+Z로 되돌릴 수 있고, 스크립트 리스너에 사람 편집과 같은 형식으로 남습니다.
- 노출된 편집: 캔버스 구조(노드/전이/배치/참조 노드), 포트와 분기 의미론, \
블랙보드, 훅 라이브러리, 프로젝트 속성, 컴포넌트 본문, 컴포넌트 생성·이름 변경·삭제.
- **프로젝트의 단위는 폴더**입니다(`<폴더>/.daedalus.json` + `<폴더>/files/`). \
`open_project`에는 폴더 경로를 주세요(구버전 `<이름>.daedalus.json` 파일도 열립니다). \
경로는 `list_recent_projects`로 찾을 수 있습니다.
- `open_project`와 `export_package`는 현재 프로젝트를 **먼저 저장한 뒤** 진행합니다. \
저장할 수 없으면 진행하지 않습니다 — 편집 중인 내용은 메모리에만 있기 때문입니다.
- 긴 본문은 `get_body_outline`으로 구조만 보고 `get_body_section`/`set_body_section`으로 \
섹션 단위 접근하세요 — 전문 재전송 없이 필요한 부분만 읽고 고칠 수 있습니다.
- 구조(노드와 선)만 만들면 분기가 표현되지 않습니다. 여러 갈래로 나가는 노드는 \
`set_transfer_on`으로 갈래를 선언하고 각 전이에 trigger를 물려야 합니다. \
에이전트로 가는 전이는 `add_agent_call`로 만든 호출 포트에서만 나갈 수 있습니다.
"""


class DaedalusMCPService:
    """MainWindow 하나에 붙는 MCP 서버."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._invoker = MainThreadInvoker(window)  # 메인 스레드에서 생성해야 한다
        self._tools = DaedalusTools(window)
        self._uvicorn: Any = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None
        self._error: str | None = None

    # --- 상태 조회 ---

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def url(self) -> str | None:
        return endpoint.url_for(self._port) if self._port is not None else None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> str | None:
        return self._error

    # --- 도구 등록 ---

    def _wrap(self, method: Callable[..., Any]) -> Callable[..., Any]:
        """도구 호출을 메인 스레드로 넘기는 래퍼.

        ``functools.wraps``가 시그니처·타입힌트·docstring을 보존하므로 SDK가
        원본 메서드로부터 입력 스키마와 설명을 그대로 만들어 낸다.
        """
        invoker = self._invoker

        @functools.wraps(method)
        def caller(**kwargs: Any) -> Any:
            return invoker.call(lambda: method(**kwargs))

        return caller

    @staticmethod
    def _server_factory() -> Any:
        """SDK 버전에 맞는 서버 클래스를 고른다.

        mcp 2.0에서 ``FastMCP``가 ``MCPServer``로 대체됐다. 두 클래스는 여기서
        쓰는 표면(``name``/``instructions`` 생성자 인자, ``add_tool``,
        ``streamable_http_app``)이 동일하므로 클래스만 갈아끼우면 된다.
        """
        try:
            from mcp.server import MCPServer  # mcp >= 2.0

            return MCPServer
        except ImportError:
            from mcp.server.fastmcp import FastMCP  # mcp 1.x

            return FastMCP

    def _build_server(self) -> Any:
        server_cls = self._server_factory()
        server = server_cls(name="daedalus", instructions=_INSTRUCTIONS)
        for tool_name in TOOL_NAMES:
            method = getattr(self._tools, tool_name)
            server.add_tool(self._wrap(method), name=tool_name)
        return server

    # --- 수명주기 ---

    def start(self, port: int | None = None) -> int | None:
        """서버를 띄우고 포트를 돌려준다. 실패하면 None(원인은 ``error``).

        port를 주면 **그 포트만** 쓴다 — 점유돼 있으면 다른 포트로 물러나지 않고
        실패한다. 물러나면 지정한 의미가 없기 때문이다(고정 포트를 가리키는
        `.mcp.json`이 엉뚱한 인스턴스에 붙는다). 생략하면 기본 포트부터 훑어
        비어 있는 것을 찾는다.
        """
        if self.running:
            return self._port

        if port is not None:
            if not endpoint.is_port_free(port):
                self._error = f"포트 {port}가 이미 사용 중입니다."
                return None
        else:
            port = endpoint.find_free_port()
            if port is None:
                self._error = (
                    f"{endpoint.DEFAULT_PORT}부터 {endpoint.PORT_SCAN_LIMIT}개 포트가 모두 사용 중입니다."
                )
                return None

        try:
            import uvicorn

            server = self._build_server()
            app = server.streamable_http_app()
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                access_log=False,
            )
            self._uvicorn = uvicorn.Server(config)
        except Exception as exc:  # noqa: BLE001 — GUI는 MCP 없이도 떠야 한다
            self._error = f"MCP 서버를 구성하지 못했습니다: {exc}"
            return None

        self._thread = threading.Thread(
            target=self._uvicorn.run, daemon=True, name="daedalus-mcp"
        )
        self._thread.start()
        self._port = port
        self._error = None
        endpoint.write(port, getattr(self._window, "_current_path", None))
        return port

    def update_project_path(self, path: str | None) -> None:
        """저장 경로가 바뀌면 접속 정보에도 반영한다(CC가 어느 프로젝트인지 알 수 있게)."""
        if self._port is not None:
            endpoint.write(self._port, path)

    def stop(self) -> None:
        """서버를 내리고 접속 정보 파일을 지운다."""
        if self._uvicorn is not None:
            self._uvicorn.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None
        self._uvicorn = None
        self._port = None
        endpoint.clear()
