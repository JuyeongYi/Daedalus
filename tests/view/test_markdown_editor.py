from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCursor, QTextDocument
from PySide6.QtTest import QTest

from daedalus.model.fsm.section import Section
from daedalus.view.widgets.markdown_editor import (
    MARKDOWN_PALETTE,
    MarkdownEditor,
    MarkdownHighlighter,
)


def _make_doc(text: str) -> QTextDocument:
    doc = QTextDocument()
    doc.setPlainText(text)
    highlighter = MarkdownHighlighter(doc)
    highlighter.rehighlight()
    doc._highlighter = highlighter  # GC 방지 — 포맷 조회 전 해제되면 안 됨
    return doc


@dataclass
class _FormatSnapshot:
    """QTextLayout.FormatRange.format은 조회 시점의 리스트가 GC되면 함께 무효화되므로,
    필요한 값만 즉시 뽑아 독립적인 파이썬 값으로 스냅샷한다."""

    fg: QColor
    bg: QColor
    bold: bool
    italic: bool
    strike: bool
    underline: bool
    point_size: float


def _format_at(doc: QTextDocument, block_number: int, col: int) -> _FormatSnapshot | None:
    block = doc.findBlockByNumber(block_number)
    for fr in block.layout().formats():
        if fr.start <= col < fr.start + fr.length:
            fmt = fr.format
            return _FormatSnapshot(
                fg=fmt.foreground().color(),
                bg=fmt.background().color(),
                bold=fmt.fontWeight() >= QFont.Weight.Bold,
                italic=fmt.fontItalic(),
                strike=fmt.fontStrikeOut(),
                underline=fmt.fontUnderline(),
                point_size=fmt.fontPointSize(),
            )
    return None


# --- 하이라이터 (9케이스) ---


def test_heading_h1(qapp):
    doc = _make_doc("# 제목")
    marker_fmt = _format_at(doc, 0, 0)
    text_fmt = _format_at(doc, 0, 2)
    assert marker_fmt.fg == MARKDOWN_PALETTE["marker"]
    assert text_fmt.fg == MARKDOWN_PALETTE["heading"]
    assert text_fmt.bold
    assert text_fmt.point_size > 10.5


def test_bold(qapp):
    doc = _make_doc("**굵게**")
    inner_fmt = _format_at(doc, 0, 2)
    marker_fmt = _format_at(doc, 0, 0)
    assert inner_fmt.fg == MARKDOWN_PALETTE["bold"]
    assert inner_fmt.bold
    assert marker_fmt.fg == MARKDOWN_PALETTE["marker"]


def test_inline_code(qapp):
    doc = _make_doc("`코드`")
    fmt = _format_at(doc, 0, 1)
    assert fmt.fg == MARKDOWN_PALETTE["code_fg"]
    assert fmt.bg == MARKDOWN_PALETTE["code_bg"]


def test_code_span_protects_from_bold(qapp):
    doc = _make_doc("`**코드 안**`")
    fmt = _format_at(doc, 0, 2)  # 백틱 안쪽 '*' 위치
    assert fmt.fg == MARKDOWN_PALETTE["code_fg"]
    assert not fmt.bold


def test_code_fence_state_transition(qapp):
    doc = _make_doc("```\nx = 1\n```")
    assert doc.findBlockByNumber(0).userState() == MarkdownHighlighter._STATE_CODE_FENCE
    mid_fmt = _format_at(doc, 1, 0)
    assert mid_fmt.bg == MARKDOWN_PALETTE["fence_bg"]
    assert doc.findBlockByNumber(2).userState() == MarkdownHighlighter._STATE_NONE


def test_task_done(qapp):
    doc = _make_doc("- [x] 완료")
    body_fmt = _format_at(doc, 0, 6)
    assert body_fmt.fg == MARKDOWN_PALETTE["done_text"]
    assert body_fmt.strike


def test_list_marker(qapp):
    doc = _make_doc("- 항목")
    fmt = _format_at(doc, 0, 0)
    assert fmt.fg == MARKDOWN_PALETTE["list_marker"]


def test_link(qapp):
    doc = _make_doc("[텍스트](http://a)")
    text_fmt = _format_at(doc, 0, 1)
    url_fmt = _format_at(doc, 0, 6)
    assert text_fmt.fg == MARKDOWN_PALETTE["link_text"]
    assert text_fmt.underline
    assert url_fmt.fg == MARKDOWN_PALETTE["link_url"]


def test_hr_not_confused_with_list(qapp):
    doc = _make_doc("---")
    fmt = _format_at(doc, 0, 1)
    assert fmt.fg == MARKDOWN_PALETTE["hr"]


# --- 에디터 동작 (8케이스) ---


def _set_cursor_at_end(editor: MarkdownEditor) -> None:
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)


def test_enter_continues_bullet_list(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- 항목")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "- 항목\n- "


def test_enter_on_empty_bullet_exits_list(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- ")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == ""


def test_enter_continues_ordered_list(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("3. 항목")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "3. 항목\n4. "


def test_enter_continues_task_list(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- [ ] 할일")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "- [ ] 할일\n- [ ] "


def test_tab_indents_list_line_by_two(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- item")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    assert ed.toPlainText() == "  - item"
    QTest.keyClick(ed, Qt.Key.Key_Backtab)
    assert ed.toPlainText() == "- item"


def test_tab_normal_line_inserts_four_at_cursor(qapp):
    # 일반 줄 + 선택 없음: 줄 들여쓰기가 아니라 커서 위치에 4칸 삽입 (타 에디터 관례)
    ed = MarkdownEditor()
    ed.setPlainText("plain text")
    _set_cursor_at_end(ed)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    assert ed.toPlainText() == "plain text    "


def test_ctrl_b_toggles_bold_wrap(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("선택")
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cursor)
    QTest.keyClick(ed, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "**선택**"
    QTest.keyClick(ed, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "선택"


def test_toggle_task_at_round_trip(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- [ ] task")
    block = ed.document().findBlockByNumber(0)
    assert ed._toggle_task_at(block) is True
    assert ed.toPlainText() == "- [x] task"
    assert ed._toggle_task_at(block) is True
    assert ed.toPlainText() == "- [ ] task"


# --- 통합 (2케이스) ---


def test_section_content_panel_uses_markdown_editor(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    assert isinstance(panel._w_content, MarkdownEditor)


def test_section_content_panel_typing_updates_content(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    section = Section("T", content="old")
    panel.show_section(section, ["T"])

    received = []
    panel.content_changed.connect(lambda: received.append(True))

    panel._w_content.setPlainText("new content")

    assert section.content == "new content"
    assert received


# --- 리뷰 후속 회귀 (사소 지적 수정 잠금) ---


def test_enter_at_line_start_does_not_duplicate_marker(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("- item")
    cursor = ed.textCursor()
    cursor.setPosition(0)
    ed.setTextCursor(cursor)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "\n- item"


def test_ctrl_i_on_bold_selection_adds_italic(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("**w**")
    cursor = ed.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    ed.setTextCursor(cursor)
    QTest.keyClick(ed, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "***w***"
    QTest.keyClick(ed, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "**w**"


def test_tab_without_selection_inserts_at_cursor(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("hello world")
    cursor = ed.textCursor()
    cursor.setPosition(5)
    ed.setTextCursor(cursor)
    QTest.keyClick(ed, Qt.Key.Key_Tab)
    assert ed.toPlainText() == "hello     world"
