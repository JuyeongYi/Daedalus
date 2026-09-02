# daedalus/view/launch_actions.py
"""MCP 서버 수명주기 + Claude Code 실행 (WP-RF-3e).

`MainWindow`의 협력 객체다(Mixin 아님). MCP 서비스 핸들의 단일 진실은
계속 `window._mcp_service`이며 이 객체는 그것을 직접 읽고 쓴다 — 복제하면
"창은 서버가 떠 있다고 아는데 협력 객체는 모른다" 같은 어긋남이 생긴다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from daedalus.model import package

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


class McpInfoDialog(QDialog):
    """MCP 접속 정보 — 주소·`.mcp.json` 스니펫·접속 정보 파일 경로.

    `QMessageBox`가 아닌 전용 다이얼로그인 이유: 메시지 박스의 본문은 Qt 기본
    스타일 힌트가 링크 클릭만 허용해 **드래그 선택이 되지 않는다**. 이 창의
    내용물은 전부 "다른 파일에 붙여넣을 텍스트"라 선택·복사가 기능 그 자체다.
    스니펫은 읽기 전용 텍스트 박스에 넣어 전체 선택이 한 번에 되게 하고,
    한 손으로 끝내려는 경우를 위해 복사 버튼도 둔다.
    """

    def __init__(
        self,
        parent,
        *,
        url: str,
        snippet: str,
        endpoint_path: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MCP 서버")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        heading = QLabel("<b>Claude Code와 협업할 준비가 되었습니다.</b>", self)
        layout.addWidget(heading)

        self._url_label = self._make_selectable_label(f"접속 주소: {url}")
        layout.addWidget(self._url_label)

        layout.addWidget(
            QLabel(
                "Claude Code에서 쓰려면 프로젝트의 <code>.mcp.json</code>에 "
                "아래를 넣으세요:",
                self,
            )
        )

        self._snippet_view = QPlainTextEdit(snippet, self)
        self._snippet_view.setReadOnly(True)
        # 읽기 전용이어도 선택은 되어야 한다 — setReadOnly만으로는 마우스·키보드
        # 선택 플래그가 보장되지 않으므로 명시한다.
        self._snippet_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._snippet_view.setFont(QFont("Consolas", 10))
        self._snippet_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._snippet_view.setMinimumHeight(140)
        layout.addWidget(self._snippet_view)

        self._endpoint_label = self._make_selectable_label(
            f"접속 정보 파일: {endpoint_path}"
        )
        layout.addWidget(self._endpoint_label)

        self._notice = QLabel("", self)
        layout.addWidget(self._notice)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        copy_button = buttons.addButton(
            "스니펫 복사", QDialogButtonBox.ButtonRole.ActionRole
        )
        # ActionRole이라 눌러도 창이 닫히지 않는다(복사는 확인이 아니다).
        copy_button.clicked.connect(self.copy_snippet)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._snippet = snippet

    def _make_selectable_label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        return label

    # --- 테스트·호출자가 쓰는 접근자 ---

    def snippet_view(self) -> QPlainTextEdit:
        return self._snippet_view

    def selectable_labels(self) -> list[QLabel]:
        return [self._url_label, self._endpoint_label]

    def copy_snippet(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._snippet)
        # 모달을 하나 더 띄우지 않는다 — 복사는 흐름을 끊을 일이 아니다.
        self._notice.setText("클립보드에 복사했습니다.")


class LaunchActions:
    """MCP 서버 / Claude Code 실행을 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    # --- MCP 서버 (WP-MCP) ---

    def start_mcp_service(self, port: int | None = None) -> None:
        """앱과 함께 MCP 서버를 띄운다 — 실제 실행 경로에서만 호출된다.

        `MainWindow.__init__`에서 자동으로 시작하지 않는 이유: 테스트가
        MainWindow를 수십 개 만들기 때문에 매번 포트를 잡으면 서로 충돌한다.

        port를 주면 그 포트만 쓴다(`--mcp-port`). 여러 인스턴스를 동시에 띄우고
        각각 다른 CC 세션과 붙일 때 쓴다.
        """
        from daedalus.mcp.service import DaedalusMCPService

        w = self._w
        service = DaedalusMCPService(w)
        w._mcp_service = service
        port = service.start(port)
        if port is None:
            w._status_label.setText(f"MCP 서버 시작 실패 — {service.error}")
        else:
            w._status_label.setText(f"MCP 서버 대기 중 — {service.url}")

    def stop_mcp_service(self) -> None:
        """앱이 닫히면 MCP 서버도 함께 내린다."""
        service = self._w._mcp_service
        if service is not None:
            try:
                service.stop()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — 종료 경로를 막지 않는다
                pass

    def show_mcp_info(self) -> None:
        """도구 메뉴 — 접속 주소와 .mcp.json 설정 조각을 보여준다."""
        from daedalus.mcp import endpoint

        w = self._w
        service = w._mcp_service
        if service is None or not getattr(service, "running", False):
            reason = getattr(service, "error", None) if service is not None else None
            QMessageBox.information(
                w,
                "MCP 서버",
                "MCP 서버가 실행 중이 아닙니다."
                + (f"\n\n{reason}" if reason else ""),
            )
            return

        port = service.port
        # Show Details를 누르게 하지 않는다 — 정보 전부를 본문에 바로 보여준다
        # (사용자 요청). 스니펫은 복사해 쓰는 텍스트라 읽기 전용 텍스트 박스에
        # 담아 선택·복사가 되게 한다(QMessageBox 본문은 선택이 막혀 있다).
        dialog = McpInfoDialog(
            w,
            url=service.url,
            snippet=endpoint.mcp_json_snippet(port),
            endpoint_path=str(endpoint.ENDPOINT_PATH),
        )
        dialog.exec()

    # --- Claude Code 실행 ---

    def launch_claude_code(self) -> None:
        """도구 메뉴 — 프로젝트 폴더에서 Claude Code를 연다.

        시작 위치는 현재 프로젝트가 저장된 폴더다. 열기 전에 그 폴더의
        `.mcp.json`에 daedalus 서버 항목을 병합해 두므로(추가만 — 기존 항목
        보존), 새 세션이 바로 이 편집 세션에 붙을 수 있다.
        """
        import subprocess
        import sys

        w = self._w
        service = w._mcp_service
        if service is None or not getattr(service, "running", False):
            w._status_label.setText(
                "Claude Code 실행: MCP 서버가 실행 중이 아닙니다."
            )
            return
        if not w._current_path:
            w._status_label.setText(
                "Claude Code 실행: 먼저 프로젝트를 저장하세요 — 시작 폴더가 정해져야 합니다."
            )
            return
        work_dir = str(package.project_dir(w._current_path))
        self.ensure_daedalus_mcp_json(work_dir)
        try:
            if sys.platform == "win32":
                # start /D <dir> — 새 콘솔에서 claude를 연다. cmd /k라 claude가
                # 끝나도 창이 남아 에러 메시지를 읽을 수 있다.
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "Claude Code", "/D", work_dir,
                     "cmd", "/k", "claude"],
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Terminal", work_dir])
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", "claude"], cwd=work_dir)
        except OSError as exc:
            w._status_label.setText(f"Claude Code 실행 실패: {exc}")
            return
        w._status_label.setText(f"Claude Code 실행: {work_dir}")

    def ensure_daedalus_mcp_json(self, work_dir: str) -> None:
        """프로젝트 폴더에 daedalus 서버를 배선한다 — `.mcp.json`의 `mcpServers`와
        `.claude/settings.local.json`의 `enabledMcpjsonServers` 생성/수정.

        병합은 LOCAL 빌드의 설치 배선과 **같은 공유 함수**(`wiring.wire_workspace`)
        다 — 같은 폴더를 두 경로가 다르게 만지면 안 된다. 추가/갱신만 하고 깨진
        JSON은 건드리지 않는다(수기 설정 보호).
        """
        from daedalus.compiler.wiring import wire_workspace

        w = self._w
        service = w._mcp_service
        url = getattr(service, "url", None)
        if not url:
            return
        wired = wire_workspace(
            work_dir, {"daedalus": {"type": "http", "url": url}},
        )
        if wired.unmergeable:
            names = ", ".join(str(p) for p in wired.unmergeable)
            w._status_label.setText(
                f"올바른 JSON이 아니어서 배선하지 못했습니다: {names}"
            )
