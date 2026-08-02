from __future__ import annotations

from dataclasses import dataclass

import pytest

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeyEvent,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from daedalus.model.plugin.skill import DeclarativeSkill
from daedalus.view.widgets.markdown_editor import (
    MARKDOWN_PALETTE,
    MarkdownEditor,
    MarkdownHighlighter,
    MarkdownToolbar,
    SearchBar,
    TocPanel,
    set_files_root_provider,
)


def _make_comp(body: str = "") -> DeclarativeSkill:
    """SectionContentPanel.show_body 테스트용 최소 컴포넌트."""
    return DeclarativeSkill(name="T", description="d", body=body)


def _find_toolbar_button(toolbar: MarkdownToolbar, text: str) -> QPushButton:
    for btn in toolbar.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    raise AssertionError(f"toolbar button {text!r} not found")


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
    comp = _make_comp("old")
    panel.show_body(comp)

    received = []
    panel.content_changed.connect(lambda: received.append(True))

    panel._w_content.setPlainText("new content")

    assert comp.body == "new content"
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


# --- WP-MD2 Part A: 공개 편집 API (5케이스) ---


def test_set_heading_level_applies(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("제목")
    ed.set_heading_level(1)
    assert ed.toPlainText() == "# 제목"


def test_set_heading_level_reclick_removes(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("# 제목")
    ed.set_heading_level(1)
    assert ed.toPlainText() == "제목"


def test_set_heading_level_replaces_level(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("# 제목")
    ed.set_heading_level(2)
    assert ed.toPlainText() == "## 제목"


def test_toggle_line_marker_bullet_toggle(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("item")
    ed.toggle_line_marker("- ")
    assert ed.toPlainText() == "- item"
    ed.toggle_line_marker("- ")
    assert ed.toPlainText() == "item"


def test_toggle_line_marker_ordered_renumber(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("a\nb\nc")
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cursor)
    ed.toggle_line_marker("1. ")
    assert ed.toPlainText() == "1. a\n2. b\n3. c"


# --- WP-MD2 Part B: `/` 슬래시 메뉴 (6케이스) ---


def test_slash_menu_opens_on_empty_line(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    assert ed.toPlainText() == "/"
    assert ed._slash_start is not None


def test_slash_menu_not_opened_mid_line(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("abc")
    _set_cursor_at_end(ed)
    QTest.keyClicks(ed, "/")
    assert ed.toPlainText() == "abc/"
    assert ed._slash_start is None


def test_slash_menu_filters_by_keyword(qapp):
    """'co'는 code 키워드를 가진 두 항목(인라인 코드·코드 블록)에 매칭된다.
    (카탈로그 내용에 과결합되지 않도록 '무엇이 걸러지는가'로 단언)"""
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    QTest.keyClicks(ed, "co")
    labels = [ed._slash_menu.item(i).text() for i in range(ed._slash_menu.count())]
    assert labels == ["인라인 코드", "코드 블록"]


def test_slash_menu_enter_confirms_code_block(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    QTest.keyClicks(ed, "fence")  # 코드 블록만 매칭 (순서 의존 제거)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "```\n\n```"
    assert ed.textCursor().position() == 4
    assert ed._slash_start is None


def test_slash_menu_esc_closes_keeps_text(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    QTest.keyClicks(ed, "co")
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    assert ed._slash_start is None
    assert ed.toPlainText() == "/co"


def test_slash_menu_backspace_deletes_slash_closes(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    assert ed._slash_start is not None
    QTest.keyClick(ed, Qt.Key.Key_Backspace)
    assert ed._slash_start is None
    assert ed.toPlainText() == ""


# --- WP-MD2 Part C: 서식 툴바 (4케이스) ---


def test_toolbar_bold_button_wraps_selection(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("hello")
    cursor = ed.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    ed.setTextCursor(cursor)
    toolbar = MarkdownToolbar(ed)
    _find_toolbar_button(toolbar, "B").click()
    assert ed.toPlainText() == "**hello**"


def test_toolbar_h2_button_applies_and_removes(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("title")
    toolbar = MarkdownToolbar(ed)
    btn = _find_toolbar_button(toolbar, "H2")
    btn.click()
    assert ed.toPlainText() == "## title"
    btn.click()
    assert ed.toPlainText() == "title"


def test_toolbar_checklist_button_toggles(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("todo")
    toolbar = MarkdownToolbar(ed)
    btn = _find_toolbar_button(toolbar, "☑")
    btn.click()
    assert ed.toPlainText() == "- [ ] todo"
    btn.click()
    assert ed.toPlainText() == "todo"


def test_toolbar_preview_button_emits_signal(qapp):
    ed = MarkdownEditor()
    toolbar = MarkdownToolbar(ed)
    received = []
    toolbar.preview_toggled.connect(received.append)
    _find_toolbar_button(toolbar, "👁").click()
    assert received == [True]


# --- WP-MD2 Part D: 프리뷰 토글 + 패널 통합 (3케이스) ---


def test_panel_preview_toggle_switches_stack_and_renders_heading(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp = _make_comp("# 제목")
    panel.show_body(comp)

    _find_toolbar_button(panel._md_toolbar, "👁").click()

    assert panel._content_stack.currentIndex() == 1
    rendered_text = panel._w_preview.document().toPlainText()
    assert "#" not in rendered_text
    assert "제목" in rendered_text


def test_panel_preview_toggle_off_restores_editor_and_content(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp = _make_comp("본문 내용")
    panel.show_body(comp)

    btn = _find_toolbar_button(panel._md_toolbar, "👁")
    btn.click()
    assert panel._content_stack.currentIndex() == 1
    btn.click()
    assert panel._content_stack.currentIndex() == 0
    assert panel._w_content.toPlainText() == "본문 내용"


def test_panel_show_body_resets_preview(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp1 = _make_comp("a")
    panel.show_body(comp1)
    _find_toolbar_button(panel._md_toolbar, "👁").click()
    assert panel._content_stack.currentIndex() == 1

    comp2 = _make_comp("b")
    panel.show_body(comp2)
    assert panel._content_stack.currentIndex() == 0
    assert not _find_toolbar_button(panel._md_toolbar, "👁").isChecked()


# --- 리뷰 후속 회귀 (WP-MD2 권고 반영 잠금) ---


def test_slash_menu_flips_above_when_no_space_below(qapp):
    ed = MarkdownEditor()
    ed.resize(400, 120)
    ed.show()
    qapp.processEvents()
    ed.setPlainText("x\n" * 30)
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    ed.setTextCursor(cursor)
    QTest.keyClicks(ed, "/")
    assert ed._slash_start is not None
    geo = ed._slash_menu.geometry()
    assert geo.top() >= 0
    assert geo.bottom() <= ed.viewport().height()
    ed.hide()


def test_preview_toggle_disables_edit_buttons(qapp):
    ed = MarkdownEditor()
    tb = MarkdownToolbar(ed)
    assert all(b.isEnabled() for b in tb._edit_buttons)
    tb._btn_preview.click()
    assert all(not b.isEnabled() for b in tb._edit_buttons)
    tb._btn_preview.click()
    assert all(b.isEnabled() for b in tb._edit_buttons)


def test_preview_toggle_disables_variable_button(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp = _make_comp("body")
    panel.show_body(comp)
    panel._md_toolbar._btn_preview.click()
    assert not panel._btn_variable.isEnabled()
    panel._md_toolbar._btn_preview.click()
    assert panel._btn_variable.isEnabled()


def test_toggle_line_marker_preserves_cursor(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("hello")
    cursor = ed.textCursor()
    cursor.setPosition(3)
    ed.setTextCursor(cursor)
    ed.toggle_line_marker("- ")
    assert ed.toPlainText() == "- hello"
    assert ed.textCursor().position() == 5


def test_toggle_line_marker_invalid_marker_raises(qapp):
    ed = MarkdownEditor()
    with pytest.raises(ValueError):
        ed.toggle_line_marker("* ")


def test_ctrl_shortcut_closes_slash_menu(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    assert ed._slash_start is not None
    QTest.keyClick(ed, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert ed._slash_start is None
    assert ed.toPlainText() == "/****"


# --- WP-MD3 Part A: SearchBar (7케이스) ---


def test_search_bar_highlights_all_matches_and_updates_count(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("foo bar foo baz foo")
    sb = SearchBar(ed)
    sb.open("foo")
    assert sb._matches == [(0, 3), (8, 11), (16, 19)]
    assert len(ed.extraSelections()) == 3
    assert sb._count_label.text() == "1/3"


def test_search_bar_next_prev_wraps_around(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("foo bar foo")
    sb = SearchBar(ed)
    sb.open("foo")
    assert sb._count_label.text() == "1/2"
    sb.search_next()
    assert sb._count_label.text() == "2/2"
    sb.search_next()  # 끝에서 랩어라운드
    assert sb._count_label.text() == "1/2"
    sb.search_prev()  # 처음에서 반대로 랩어라운드
    assert sb._count_label.text() == "2/2"


def test_search_bar_case_toggle_reruns_search(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("Foo foo FOO")
    sb = SearchBar(ed)
    sb.open("foo")
    assert len(sb._matches) == 3  # 기본은 대소문자 무시
    sb._case_btn.setChecked(True)
    assert sb._matches == [(4, 7)]
    assert sb._count_label.text() == "1/1"


def test_search_bar_replace_current_moves_to_next(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("foo bar foo")
    sb = SearchBar(ed)
    sb.open("foo")
    sb._replace_edit.setText("XX")
    sb.replace_current()
    assert ed.toPlainText() == "XX bar foo"
    # 남은 유일한 일치(foo)로 커서가 이동해 있어야 한다(앞 치환으로 2->3글자 폭이
    # 줄어 위치가 1칸 당겨진 (7, 10)이 된다)
    assert ed.textCursor().selectedText() == "foo"
    assert sb._matches == [(7, 10)]


def test_search_bar_replace_all_is_single_undo_unit(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("foo bar foo baz foo")
    sb = SearchBar(ed)
    sb.open("foo")
    sb._replace_edit.setText("Q")
    sb.replace_all()
    assert ed.toPlainText() == "Q bar Q baz Q"
    assert sb._count_label.text() == "3건 바꿈"
    ed.undo()  # 단일 undo로 전체 치환이 통째로 되돌아가야 한다
    assert ed.toPlainText() == "foo bar foo baz foo"


def test_search_bar_esc_closes_and_clears_highlights(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("foo bar")
    sb = SearchBar(ed)
    sb.open("foo")
    assert len(ed.extraSelections()) == 1
    QTest.keyClick(sb._search_edit, Qt.Key.Key_Escape)
    assert sb.isHidden()
    assert len(ed.extraSelections()) == 0


def test_ctrl_f_emits_search_requested_with_selection(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("hello world")
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(
        QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 5,
    )
    ed.setTextCursor(cursor)
    received: list[str] = []
    ed.search_requested.connect(received.append)
    QTest.keyClick(ed, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert received == ["hello"]

    sb = SearchBar(ed)
    sb.open(received[0])
    assert sb._search_edit.text() == "hello"
    assert sb._matches == [(0, 5)]


# --- WP-MD3 Part B: TocPanel (5케이스) ---


def test_toc_extracts_headings_with_level_hierarchy(qapp):
    ed = MarkdownEditor()
    toc = TocPanel(ed)
    ed.setPlainText("# A\n## B\n### C\n## D")
    toc.refresh()
    top = toc._tree.topLevelItem(0)
    assert top.text(0) == "A"
    assert top.childCount() == 2
    assert top.child(0).text(0) == "B"
    assert top.child(0).childCount() == 1
    assert top.child(0).child(0).text(0) == "C"
    assert top.child(1).text(0) == "D"


def test_toc_excludes_heading_inside_code_fence(qapp):
    ed = MarkdownEditor()
    toc = TocPanel(ed)
    ed.setPlainText("# Real\n```\n# not a heading\n```\n## Also Real")
    toc.refresh()
    assert [e.text for e in toc._entries] == ["Real", "Also Real"]


def test_toc_click_jumps_to_heading_block(qapp):
    ed = MarkdownEditor()
    toc = TocPanel(ed)
    ed.setPlainText("intro\n\n## Target\n\nbody")
    toc.refresh()
    item = toc._tree.topLevelItem(0)
    assert item.text(0) == "Target"
    toc._on_item_clicked(item, 0)
    assert ed.textCursor().block().text() == "## Target"


def test_toc_debounced_update(qapp):
    # 주의(스위트 순서 의존 크래시 회피): QTest.qWait(...)로 실제 300ms를 대기시키면
    # 이 테스트만 실행할 때는 통과하지만, tests/view/ 전체(1000+ 케이스)를 먼저 실행한
    # 뒤에는 실제 이벤트 루프가 도는 그 400ms 동안 이전 테스트들이 남긴 잔여
    # QTimer/위젯이 함께 플러시되며 재현되는 네이티브 크래시(Fatal Python error:
    # Aborted)가 확인됐다(WP-MD3 로직과 무관 — 격리 실행/-k 필터 실행 시 미재현).
    # 따라서 실제 대기 대신 타이머 예약 여부·간격을 확인하고 timeout을 직접
    # 발화시켜 디바운스 자체를 결정적으로 검증한다.
    ed = MarkdownEditor()
    toc = TocPanel(ed)
    assert toc._entries == []
    ed.setPlainText("# Heading")
    assert toc._timer.isActive()  # 디바운스 타이머가 예약됨
    assert toc._timer.interval() == 300
    assert toc._entries == []  # 타이머가 실제로 발화하기 전까지는 갱신되지 않는다
    toc._timer.timeout.emit()  # 디바운스 만료를 결정적으로 시뮬레이션
    assert [e.text for e in toc._entries] == ["Heading"]


def test_toc_empty_document(qapp):
    ed = MarkdownEditor()
    toc = TocPanel(ed)
    assert toc._entries == []
    assert toc._tree.topLevelItemCount() == 0


# --- WP-MD3 Part C: SectionContentPanel 통합 (4케이스) ---


def test_panel_ctrl_f_opens_search_bar(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp = _make_comp("findable text")
    panel.show_body(comp)

    assert panel._search_bar.isHidden()
    QTest.keyClick(panel._w_content, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert not panel._search_bar.isHidden()


def test_panel_preview_mode_disables_search_and_toc(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp = _make_comp("some text")
    panel.show_body(comp)
    QTest.keyClick(panel._w_content, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert not panel._search_bar.isHidden()

    _find_toolbar_button(panel._md_toolbar, "👁").click()
    assert panel._search_bar.isHidden()  # 프리뷰 진입 시 찾기 바 닫힘
    assert not panel._md_toolbar._btn_toc.isEnabled()  # TOC 버튼 비활성


def test_panel_show_body_closes_search_bar(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp1 = _make_comp("first foo")
    panel.show_body(comp1)
    QTest.keyClick(panel._w_content, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert not panel._search_bar.isHidden()

    comp2 = _make_comp("second")
    panel.show_body(comp2)
    assert panel._search_bar.isHidden()


def test_panel_show_body_refreshes_toc(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel

    panel = SectionContentPanel()
    comp1 = _make_comp("# First Doc")
    panel.show_body(comp1)
    assert [e.text for e in panel._toc_panel._entries] == ["First Doc"]

    comp2 = _make_comp("# Second Doc")
    panel.show_body(comp2)
    assert [e.text for e in panel._toc_panel._entries] == ["Second Doc"]


# --- 리뷰 후속 회귀 (WP-MD3 결함 1~4 잠금) ---


def test_search_matches_refresh_after_external_edit(qapp):
    """검색 바가 열린 채 문서를 편집해도 스테일 오프셋으로 엉뚱한 구간을
    치환하지 않는다 (리뷰 결함 1)."""
    ed = MarkdownEditor()
    ed.setPlainText("foo bar foo")
    bar = SearchBar(ed)
    bar.open()
    bar._search_edit.setText("foo")
    # 에디터에서 직접 편집 — 맨 앞에 XXXXX 삽입
    cursor = ed.textCursor()
    cursor.setPosition(0)
    cursor.insertText("XXXXX")
    ed.setTextCursor(cursor)
    bar._replace_edit.setText("ZZZ")
    bar.replace_current()
    text = ed.toPlainText()
    assert text.startswith("XXXXX")          # 사용자가 친 텍스트 무사
    assert text == "XXXXXZZZ bar foo"        # 실제 foo가 치환됨


def test_search_anchor_uses_selection_start(qapp):
    """단어를 선택하고 열면 그 단어가 현재 일치가 된다 (리뷰 결함 2 —
    선택 '끝' 앵커는 문서 첫 일치로 튀었다)."""
    ed = MarkdownEditor()
    ed.setPlainText("alpha beta alpha")
    cursor = ed.textCursor()
    cursor.setPosition(11)
    cursor.setPosition(16, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(cursor)
    bar = SearchBar(ed)
    bar.open(prefill="alpha")
    assert bar._count_label.text() == "2/2"


def test_close_bar_noop_when_hidden(qapp):
    """숨어 있는 바의 close_bar는 아무것도 하지 않는다 (리뷰 결함 3 —
    show_body 경유 호출이 포커스/셀렉션을 건드리지 않게)."""
    ed = MarkdownEditor()
    ed.setPlainText("x")
    bar = SearchBar(ed)
    from PySide6.QtWidgets import QTextEdit as _QTE
    sel = _QTE.ExtraSelection()
    sel.cursor = ed.textCursor()
    ed.setExtraSelections([sel])
    bar.close_bar()  # 숨김 상태 — no-op이어야 한다
    assert len(ed.extraSelections()) == 1


def test_multiline_selection_prefill_skipped(qapp):
    """여러 줄 선택(U+2029 포함) 프리필은 생략된다 (리뷰 결함 4)."""
    ed = MarkdownEditor()
    bar = SearchBar(ed)
    bar.open(prefill="line one\u2029line two")
    assert bar._search_edit.text() == ""


# --- 파일 드롭 치환 (WP-FR Part B) ---


def _drop_event_at(ed: MarkdownEditor, cursor_pos: int, mime: QMimeData) -> QDropEvent:
    """ed의 cursor_pos 위치에 해당하는 화면 좌표에서 드롭 이벤트를 합성한다."""
    cursor = ed.textCursor()
    cursor.setPosition(cursor_pos)
    ed.setTextCursor(cursor)
    rect = ed.cursorRect()
    pos = QPointF(rect.left(), rect.top() + 2)
    return QDropEvent(
        pos, Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def _prepare_editor(qapp, text: str = "hello world") -> MarkdownEditor:
    ed = MarkdownEditor()
    ed.setPlainText(text)
    ed.resize(400, 100)
    return ed


def test_drop_file_under_files_root_inserts_token(qapp, tmp_path):
    """files/ 하위(중첩 경로) 파일 URL 드롭 → 토큰 경로가 커서 위치에 삽입."""
    files_root = tmp_path / "files"
    nested = files_root / "A"
    nested.mkdir(parents=True)
    target = nested / "c.txt"
    target.write_text("x", encoding="utf-8")
    set_files_root_provider(lambda: str(files_root))

    ed = _prepare_editor(qapp)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])
    event = _drop_event_at(ed, 5, mime)
    ed.dropEvent(event)

    assert event.isAccepted()
    assert ed.toPlainText() == "hello${CLAUDE_PLUGIN_ROOT}/files/A/c.txt world"


def test_drop_multiple_files_joined_by_newline(qapp, tmp_path):
    """복수 파일 드롭 → 줄바꿈으로 구분된 토큰이 삽입된다."""
    files_root = tmp_path / "files"
    files_root.mkdir()
    f1 = files_root / "a.txt"
    f2 = files_root / "b.txt"
    f1.write_text("1", encoding="utf-8")
    f2.write_text("2", encoding="utf-8")
    set_files_root_provider(lambda: str(files_root))

    ed = _prepare_editor(qapp, text="")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(f1)), QUrl.fromLocalFile(str(f2))])
    event = _drop_event_at(ed, 0, mime)
    ed.dropEvent(event)

    assert ed.toPlainText() == (
        "${CLAUDE_PLUGIN_ROOT}/files/a.txt\n${CLAUDE_PLUGIN_ROOT}/files/b.txt"
    )


def test_drop_file_outside_files_root_falls_through(qapp, tmp_path):
    """files/ 밖 파일은 토큰으로 치환하지 않는다(기존 기본 처리로 흘림)."""
    files_root = tmp_path / "files"
    files_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    set_files_root_provider(lambda: str(files_root))

    ed = _prepare_editor(qapp)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(outside))])
    event = _drop_event_at(ed, 5, mime)
    ed.dropEvent(event)

    assert "${CLAUDE_PLUGIN_ROOT}" not in ed.toPlainText()


def test_drop_without_files_root_provider_falls_through(qapp, tmp_path):
    """files 루트 제공자가 없으면(미저장 프로젝트) 토큰 치환을 하지 않는다."""
    target = tmp_path / "c.txt"
    target.write_text("x", encoding="utf-8")
    # provider 미등록 상태(conftest autouse가 None으로 초기화해 둠)

    ed = _prepare_editor(qapp)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])
    event = _drop_event_at(ed, 5, mime)
    ed.dropEvent(event)

    assert "${CLAUDE_PLUGIN_ROOT}" not in ed.toPlainText()


def test_drop_plain_text_still_works(qapp):
    """files 무관 일반 텍스트 드롭 — 기존 QPlainTextEdit 기본 동작 유지."""
    ed = _prepare_editor(qapp)
    mime = QMimeData()
    mime.setText("XYZ")
    event = _drop_event_at(ed, 5, mime)
    ed.dropEvent(event)

    assert ed.toPlainText() == "helloXYZ world"


def test_drag_enter_accepts_when_file_under_root(qapp, tmp_path):
    """files/ 하위 파일 URL이 있으면 dragEnterEvent가 즉시 수락한다."""
    files_root = tmp_path / "files"
    files_root.mkdir()
    target = files_root / "c.txt"
    target.write_text("x", encoding="utf-8")
    set_files_root_provider(lambda: str(files_root))

    ed = _prepare_editor(qapp)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])
    event = QDragEnterEvent(
        ed.cursorRect().topLeft(), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    ed.dragEnterEvent(event)
    assert event.isAccepted()


def test_drop_space_path_wraps_in_angle_brackets(qapp, tmp_path):
    """공백 있는 경로는 <...>로 감싸 삽입 — 컴파일러 스캐너 오탐 방지."""
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDropEvent

    from daedalus.view.widgets.markdown_editor import set_files_root_provider

    files = tmp_path / "files"
    files.mkdir()
    target = files / "with space.txt"
    target.write_text("x", encoding="utf-8")
    set_files_root_provider(lambda: str(files))

    ed = MarkdownEditor()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(target))])
    ed.dropEvent(QDropEvent(
        QPointF(1, 1), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    assert ed.toPlainText().strip() == "<${CLAUDE_PLUGIN_ROOT}/files/with space.txt>"


def test_mixed_drop_keeps_outside_urls(qapp, tmp_path):
    """files 안팎이 섞인 드롭에서 바깥 URL이 조용히 사라지지 않는다."""
    from PySide6.QtCore import QMimeData, QPointF, QUrl
    from PySide6.QtGui import QDropEvent

    from daedalus.view.widgets.markdown_editor import set_files_root_provider

    files = tmp_path / "files"
    files.mkdir()
    inside = files / "a.txt"
    inside.write_text("x", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("y", encoding="utf-8")
    set_files_root_provider(lambda: str(files))

    ed = MarkdownEditor()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(inside)), QUrl.fromLocalFile(str(outside))])
    ed.dropEvent(QDropEvent(
        QPointF(1, 1), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    text = ed.toPlainText()
    assert "${CLAUDE_PLUGIN_ROOT}/files/a.txt" in text
    assert "outside.txt" in text


# --- WP-MK Part A: 코드 인용 (7케이스) ---


def _select_all(ed: MarkdownEditor) -> None:
    cursor = ed.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    ed.setTextCursor(cursor)


def test_toggle_inline_code_wraps_selection(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("code")
    _select_all(ed)
    ed.toggle_inline_code()
    assert ed.toPlainText() == "`code`"


def test_toggle_inline_code_unwraps_when_already_in_code(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("`code`")
    _select_all(ed)
    ed.toggle_inline_code()
    assert ed.toPlainText() == "code"


def test_toggle_inline_code_no_selection_inserts_pair_with_centered_cursor(qapp):
    ed = MarkdownEditor()
    ed.toggle_inline_code()
    assert ed.toPlainText() == "``"
    assert ed.textCursor().position() == 1


def test_toggle_code_block_wraps_single_line(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("x = 1")
    _select_all(ed)
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\nx = 1\n```"


def test_toggle_code_block_multiline_selection_expands_to_line_boundaries(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("line1\nline2\nline3")
    cursor = ed.textCursor()
    cursor.setPosition(2)  # line1 중간
    cursor.setPosition(8, QTextCursor.MoveMode.KeepAnchor)  # line2 중간까지
    ed.setTextCursor(cursor)
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\nline1\nline2\n```\nline3"


def test_toggle_code_block_unwraps_when_reapplied(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("x = 1")
    _select_all(ed)
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\nx = 1\n```"
    # wrap 직후 남은 선택(펜스 포함 전체)으로 재호출하면 벗겨진다(왕복 토글)
    ed.toggle_code_block()
    assert ed.toPlainText() == "x = 1"


def test_toggle_code_block_empty_line_inserts_empty_fence_with_centered_cursor(qapp):
    ed = MarkdownEditor()
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\n\n```"
    assert ed.textCursor().position() == 4


def test_toggle_code_block_is_single_undo_unit(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("x = 1")
    _select_all(ed)
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\nx = 1\n```"
    ed.undo()
    assert ed.toPlainText() == "x = 1"


# --- WP-MK Part B: 단축키 확장 (12케이스) ---


def test_ctrl_backtick_toggles_inline_code(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("code")
    _select_all(ed)
    QTest.keyClick(ed, Qt.Key.Key_QuoteLeft, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "`code`"


def test_ctrl_shift_c_toggles_code_block(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("x")
    _select_all(ed)
    QTest.keyClick(
        ed, Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert ed.toPlainText() == "```\nx\n```"


def test_ctrl_digit_1_to_6_sets_heading_level(qapp):
    for level in range(1, 7):
        ed = MarkdownEditor()
        ed.setPlainText("title")
        key = Qt.Key(Qt.Key.Key_0.value + level)
        QTest.keyClick(ed, key, Qt.KeyboardModifier.ControlModifier)
        assert ed.toPlainText() == "#" * level + " title"


def test_ctrl_0_clears_heading_level(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("# title")
    QTest.keyClick(ed, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
    assert ed.toPlainText() == "title"


def test_ctrl_shift_8_toggles_bullet_marker(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("item")
    QTest.keyClick(
        ed, Qt.Key.Key_8,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert ed.toPlainText() == "- item"


def test_ctrl_shift_7_toggles_ordered_marker(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("item")
    QTest.keyClick(
        ed, Qt.Key.Key_7,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert ed.toPlainText() == "1. item"


def test_ctrl_shift_9_toggles_task_marker(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("item")
    QTest.keyClick(
        ed, Qt.Key.Key_9,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert ed.toPlainText() == "- [ ] item"


def test_ctrl_shift_period_toggles_quote_marker(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("item")
    QTest.keyClick(
        ed, Qt.Key.Key_Period,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert ed.toPlainText() == "> item"


def test_ctrl_digit_text_fallback_when_key_code_mismatched(qapp):
    """일부 플랫폼에서 event.key()가 표준 숫자 키 코드와 다르게 와도
    event.text()로 판정할 수 있어야 한다(플랫폼 키맵 차이 대응)."""
    ed = MarkdownEditor()
    ed.setPlainText("title")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_unknown,
        Qt.KeyboardModifier.ControlModifier, "3",
    )
    ed.keyPressEvent(event)
    assert ed.toPlainText() == "### title"


def test_ctrl_shift_marker_text_fallback_when_key_code_mismatched(qapp):
    """Ctrl+Shift+8 같은 조합이 event.key()로 오지 않고 event.text()의 shift
    기호('*')로만 판별 가능한 플랫폼 대응."""
    ed = MarkdownEditor()
    ed.setPlainText("item")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_unknown,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, "*",
    )
    ed.keyPressEvent(event)
    assert ed.toPlainText() == "- item"


def test_ctrl_backtick_closes_slash_menu(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    assert ed._slash_start is not None
    QTest.keyClick(ed, Qt.Key.Key_QuoteLeft, Qt.KeyboardModifier.ControlModifier)
    assert ed._slash_start is None


# --- WP-MK Part C: 툴바 · 슬래시 메뉴 반영 (4케이스) ---


def test_toolbar_inline_code_button_wraps_selection(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("code")
    _select_all(ed)
    toolbar = MarkdownToolbar(ed)
    _find_toolbar_button(toolbar, "<>").click()
    assert ed.toPlainText() == "`code`"


def test_toolbar_code_block_button_wraps_selection(qapp):
    ed = MarkdownEditor()
    ed.setPlainText("x")
    _select_all(ed)
    toolbar = MarkdownToolbar(ed)
    _find_toolbar_button(toolbar, "{}").click()
    assert ed.toPlainText() == "```\nx\n```"


def test_toolbar_code_buttons_disabled_during_preview(qapp):
    ed = MarkdownEditor()
    tb = MarkdownToolbar(ed)
    inline_btn = _find_toolbar_button(tb, "<>")
    block_btn = _find_toolbar_button(tb, "{}")
    tb._btn_preview.click()
    assert not inline_btn.isEnabled()
    assert not block_btn.isEnabled()
    tb._btn_preview.click()
    assert inline_btn.isEnabled()
    assert block_btn.isEnabled()


def test_slash_menu_inline_code_item_inserts_backtick_pair(qapp):
    ed = MarkdownEditor()
    QTest.keyClicks(ed, "/")
    QTest.keyClicks(ed, "backtick")
    assert ed._slash_menu.count() == 1
    assert ed._slash_menu.item(0).text() == "인라인 코드"
    QTest.keyClick(ed, Qt.Key.Key_Return)
    assert ed.toPlainText() == "``"
    assert ed.textCursor().position() == 1


# ── 리뷰 반영 회귀 (D1 실키코드 · D2 인접 펜스 · 캐럿 보존) ──


def _native_key_event(key, text, *, ctrl=True, shift=False):
    """실제 Windows가 주는 형태의 키 이벤트 — key()에는 shift된 기호,
    text()에는 shift 안 된 숫자가 온다(리뷰 실측). QTest 합성은 이 조합을
    만들지 못해 key() 경로가 죽어도 통과해 버린다."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    mods = Qt.KeyboardModifier.ControlModifier
    if shift:
        mods |= Qt.KeyboardModifier.ShiftModifier
    return QKeyEvent(QEvent.Type.KeyPress, key, mods, text)


def test_marker_shortcuts_with_native_key_codes(qapp):
    """Ctrl+Shift+7/8/9/.의 실제 키코드(Key_Ampersand 등)로 동작해야 한다 (결함 D1)."""
    cases = [
        (Qt.Key.Key_Ampersand, "7", "1. item"),
        (Qt.Key.Key_Asterisk, "8", "- item"),
        (Qt.Key.Key_ParenLeft, "9", "- [ ] item"),
        (Qt.Key.Key_Greater, ".", "> item"),
    ]
    for key, text, expected in cases:
        ed = MarkdownEditor()
        ed.setPlainText("item")
        ed.keyPressEvent(_native_key_event(key, text, shift=True))
        assert ed.toPlainText() == expected, f"{key} 실키코드 경로 실패"


def test_heading_shortcuts_with_native_key_codes(qapp):
    """Ctrl+1~6/0도 실경로 키코드로 동작한다."""
    ed = MarkdownEditor()
    ed.setPlainText("title")
    ed.keyPressEvent(_native_key_event(Qt.Key.Key_3, "3"))
    assert ed.toPlainText() == "### title"
    ed.keyPressEvent(_native_key_event(Qt.Key.Key_0, "0"))
    assert ed.toPlainText() == "title"


def test_code_block_does_not_merge_adjacent_fences(qapp):
    """두 코드 블록 사이 평문에서 토글해도 인접 블록이 파괴되지 않는다 (결함 D2).

    인접 줄 텍스트 매칭은 위 블록의 닫는 펜스와 아래 블록의 여는 펜스를
    감싸는 쌍으로 오인해 평문을 코드로 빨아들이고 두 블록을 합쳤다.
    """
    fence = "```"
    ed = MarkdownEditor()
    ed.setPlainText(f"{fence}\nfoo\n{fence}\nPLAIN\n{fence}\nbar\n{fence}")
    cursor = ed.textCursor()
    cursor.setPosition(ed.document().findBlockByNumber(3).position())
    ed.setTextCursor(cursor)
    ed.toggle_code_block()
    out = ed.toPlainText()
    assert "PLAIN" in out, "평문이 사라졌다"
    assert "foo" in out and "bar" in out
    assert out.count(fence) == 6, f"펜스 쌍이 깨졌다: {out!r}"


def test_code_block_unwraps_from_inside_middle_line(qapp):
    """펜스 안쪽 가운데 줄에서 토글하면 중첩이 아니라 언랩된다."""
    fence = "```"
    ed = MarkdownEditor()
    ed.setPlainText(f"{fence}\na\nb\nc\n{fence}")
    cursor = ed.textCursor()
    cursor.setPosition(ed.document().findBlockByNumber(2).position())
    ed.setTextCursor(cursor)
    ed.toggle_code_block()
    assert ed.toPlainText() == "a\nb\nc"


def test_code_block_without_selection_keeps_caret(qapp):
    """선택 없이 감싸면 캐럿을 보존한다 (set_heading_level 관례와 통일)."""
    ed = MarkdownEditor()
    ed.setPlainText("hello")
    cursor = ed.textCursor()
    cursor.setPosition(2)
    ed.setTextCursor(cursor)
    ed.toggle_code_block()
    assert ed.toPlainText() == "```\nhello\n```"
    assert not ed.textCursor().hasSelection(), "캐럿만 있었는데 전체가 선택됐다"
    assert ed.textCursor().block().text() == "hello"
