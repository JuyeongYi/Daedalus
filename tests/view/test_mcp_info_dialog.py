"""MCP 서버 정보 다이얼로그 — 본문 선택/복사 가능성 고정.

이전 구현은 `QMessageBox` + RichText였고, Qt 기본 스타일 힌트가 링크 클릭만
허용해 `.mcp.json` 스니펫을 드래그로 긁을 수 없었다(사용자 보고). 스니펫은
"복사해 다른 파일에 붙여넣는 텍스트"라 선택 불가능은 기능 부재다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from daedalus.mcp import endpoint
from daedalus.view.launch_actions import McpInfoDialog


SNIPPET = endpoint.mcp_json_snippet(8787)


def _dialog(qapp):
    return McpInfoDialog(
        None,
        url=endpoint.url_for(8787),
        snippet=SNIPPET,
        endpoint_path="C:/tmp/mcp-endpoint.json",
    )


def test_snippet_box_is_readonly_but_selectable(qapp):
    dlg = _dialog(qapp)
    box = dlg.snippet_view()
    assert box.isReadOnly()
    assert box.toPlainText() == SNIPPET
    # 읽기 전용이어도 커서로 긁어 Ctrl+C 할 수 있어야 한다.
    flags = box.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard


def test_snippet_box_select_all_yields_full_snippet(qapp):
    """전체 선택 → 복사 경로가 실제로 스니펫 전문을 준다."""
    dlg = _dialog(qapp)
    box = dlg.snippet_view()
    box.selectAll()
    assert box.textCursor().selectedText().replace("\u2029", "\n") == SNIPPET


def test_url_and_endpoint_labels_are_selectable(qapp):
    dlg = _dialog(qapp)
    for label in dlg.selectable_labels():
        flags = label.textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.TextSelectableByMouse, label.text()


def test_copy_button_puts_snippet_on_clipboard(qapp):
    dlg = _dialog(qapp)
    clipboard = QApplication.clipboard()
    clipboard.setText("이전 내용")
    dlg.copy_snippet()
    assert clipboard.text() == SNIPPET


def test_copy_does_not_close_dialog(qapp):
    """복사는 액션이지 확인이 아니다 — 눌러도 다이얼로그가 살아 있어야 한다."""
    dlg = _dialog(qapp)
    dlg.copy_snippet()
    assert not dlg.isHidden() or dlg.result() == 0


def test_show_mcp_info_uses_dialog(qapp, monkeypatch):
    """`show_mcp_info`가 QMessageBox가 아니라 이 다이얼로그를 띄운다."""
    from daedalus.view import launch_actions

    class _FakeService:
        running = True
        port = 8787
        url = endpoint.url_for(8787)

    class _FakeWindow(QWidget):
        """QDialog의 부모는 실제 위젯이어야 한다(부모가 아니면 TypeError)."""

        _mcp_service = _FakeService()

    shown: list[McpInfoDialog] = []
    monkeypatch.setattr(
        McpInfoDialog, "exec", lambda self: shown.append(self) or 0, raising=False
    )
    # 부모 위젯을 지역 변수로 붙잡아 둔다 — 임시 객체로 넘기면 호출 직후 GC가
    # 부모를 파괴하고 자식 위젯(스니펫 박스)까지 함께 죽는다.
    window = _FakeWindow()
    launch_actions.LaunchActions(window).show_mcp_info()  # type: ignore[arg-type]

    assert len(shown) == 1
    assert shown[0].snippet_view().toPlainText() == SNIPPET
