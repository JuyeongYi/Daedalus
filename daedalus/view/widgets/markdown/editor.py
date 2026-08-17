"""마크다운 본문 에디터 — 하이라이팅 + 리스트/인용 이어쓰기 + 서식 단축키.

단축키 판정 표(`_HEADING_DIGIT_*`/`_MARKER_SHORTCUT_*`)와 드롭 치환은 이
에디터 전용이라 여기 둔다. 문법 정규식·팔레트는 ``syntax.py``, 드롭 토큰
계산은 ``providers.py``, `/` 메뉴는 ``slash.py``가 단일 진실이다(WP-RF-3c).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from daedalus.view.widgets.markdown.highlighter import MarkdownHighlighter
from daedalus.view.widgets.markdown.providers import (
    _file_ref_token,
    _skill_file_ref_token,
    get_files_root,
    get_skill_files_root,
)
from daedalus.view.widgets.markdown.slash import (
    SLASH_CATALOG,
    _SLASH_ROW_HEIGHT,
    _SlashMenu,
)
from daedalus.view.widgets.markdown.syntax import (
    MARKDOWN_PALETTE,
    _BASE_FONT_FAMILY,
    _BASE_POINT_SIZE,
    _BULLET_LINE_RE,
    _FENCE_CLOSE_RE,
    _FENCE_OPEN_RE,
    _HEADING_PREFIX_RE,
    _LEADING_WS_RE,
    _MARKER_KIND,
    _OL_RE,
    _ORDERED_LINE_RE,
    _QUOTE_LINE_RE,
    _TASK_CHECK_RE,
    _TASK_LINE_RE,
    _TASK_RE,
    _UL_RE,
    _detect_line_marker,
)

# --- 단축키 판정 (Ctrl+숫자 / Ctrl+Shift+기호, 플랫폼 키맵 차이 대응) ---
# 일부 플랫폼/키보드 배열에서는 Ctrl+Shift+숫자 조합이 event.key()로 오지 않고
# event.text()로 shift된 기호 문자가 오는 경우가 있다 — key()/text() 양쪽을 보고
# 판정해 견고성을 확보한다(WP-MK).
_HEADING_DIGIT_KEYS: dict[int, int] = {
    Qt.Key.Key_0: 0,
    Qt.Key.Key_1: 1,
    Qt.Key.Key_2: 2,
    Qt.Key.Key_3: 3,
    Qt.Key.Key_4: 4,
    Qt.Key.Key_5: 5,
    Qt.Key.Key_6: 6,
}
_HEADING_DIGIT_TEXT: dict[str, int] = {str(v): v for v in range(7)}

# Ctrl+Shift+숫자의 실제 이벤트 값(Windows 실측): key()에는 **shift된 기호**가,
# text()에는 **shift 안 된 숫자**가 온다 — 합성 이벤트(QTest)와 정반대라 테스트만
# 보면 잡히지 않는다. 두 방향을 모두 담아 실경로·합성 경로·타 배열을 함께 커버한다.
_MARKER_SHORTCUT_KEYS: dict[int, str] = {
    # 실제 Windows 경로 (US/한국어 배열)
    Qt.Key.Key_Ampersand: "1. ",   # Ctrl+Shift+7
    Qt.Key.Key_Asterisk: "- ",     # Ctrl+Shift+8
    Qt.Key.Key_ParenLeft: "- [ ] ",  # Ctrl+Shift+9
    Qt.Key.Key_Greater: "> ",      # Ctrl+Shift+.
    # 합성 이벤트/키맵퍼가 숫자 키코드를 그대로 주는 환경
    Qt.Key.Key_7: "1. ",
    Qt.Key.Key_8: "- ",
    Qt.Key.Key_9: "- [ ] ",
    Qt.Key.Key_Period: "> ",
}
_MARKER_SHORTCUT_TEXT: dict[str, str] = {
    # 실제 Windows 경로가 주는 text
    "7": "1. ",
    "8": "- ",
    "9": "- [ ] ",
    ".": "> ",
    # US 배열 shift 기호가 text로 오는 환경
    "&": "1. ",
    "*": "- ",
    "(": "- [ ] ",
    ">": "> ",
}


def _heading_digit_from_event(event) -> int | None:
    """Ctrl+0~6 대응 헤딩 레벨을 event.key()/event.text() 양쪽으로 판정한다."""
    digit = _HEADING_DIGIT_KEYS.get(event.key())
    if digit is not None:
        return digit
    return _HEADING_DIGIT_TEXT.get(event.text())


def _line_marker_from_event(event) -> str | None:
    """Ctrl+Shift+7/8/9/. 대응 마커를 event.key()/event.text() 양쪽으로 판정한다."""
    marker = _MARKER_SHORTCUT_KEYS.get(event.key())
    if marker is not None:
        return marker
    return _MARKER_SHORTCUT_TEXT.get(event.text())


class MarkdownEditor(QPlainTextEdit):
    """마크다운 본문 에디터 — 하이라이팅 + 리스트/인용 이어쓰기 + 서식 단축키."""

    search_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        font = QFont(_BASE_FONT_FAMILY)
        font.setPointSizeF(_BASE_POINT_SIZE)
        self.setFont(font)
        self.setObjectName("markdownEditor")
        self.setStyleSheet(
            f"MarkdownEditor {{ background-color: #1e1e32; "
            f"color: {MARKDOWN_PALETTE['text'].name()}; border: none; }}",
        )
        self.setTabChangesFocus(False)
        self._highlighter = MarkdownHighlighter(self.document(), _BASE_POINT_SIZE)
        # 하이라이터의 부모를 에디터로 옮긴다 (WP-BU). QSyntaxHighlighter는 생성 시
        # 넘긴 문서를 부모로 삼는데, attach_document가 문서를 교체하면 이전 문서가
        # 파괴되면서 그 자식인 하이라이터까지 함께 삭제된다("Internal C++ object
        # (MarkdownHighlighter) already deleted").
        self._highlighter.setParent(self)
        self._slash_menu = _SlashMenu(self)
        self._slash_start: int | None = None

    def attach_document(self, doc: QTextDocument) -> None:
        """문서를 교체하고 하이라이터를 새 문서로 옮긴다 (WP-BU).

        ``setDocument``만 호출하면 하이라이터는 이전 문서에 붙은 채로 남아
        새 문서의 하이라이팅이 죽는다. ``setDocument``는 virtual이 아니라
        오버라이드로는 Qt 내부 호출까지 잡을 수 없으므로 명시적 메서드로 둔다.
        """
        if doc is self.document():
            return
        self.setDocument(doc)
        self._highlighter.setDocument(doc)

    # --- 키 입력 ---

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """`/` 슬래시 메뉴가 열려 있으면 ↑/↓/Enter/Tab/Esc를 메뉴가 소비하고,
        그 외 키는 평소대로 처리한 뒤 슬래시 메뉴 상태(필터/닫힘)를 동기화한다.
        메뉴가 닫혀 있었다면 처리 후 `/` 입력으로 새로 열릴 조건인지 확인한다.
        """
        # 메뉴가 열려 있는지는 위젯의 실제 화면 가시성(isVisible)이 아니라
        # 논리 상태(_slash_start)로 판단한다 — 그래야 top-level이 show()되지
        # 않은 오프스크린 테스트에서도 정상 동작한다.
        menu_was_open = self._slash_start is not None
        # Ctrl 조합 단축키는 삽입 흐름이 아니다 — 메뉴를 닫고 평소대로 처리한다.
        if menu_was_open and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._close_slash_menu()
            menu_was_open = False
        if menu_was_open and self._handle_slash_menu_key(event):
            return

        self._dispatch_key(event)

        if menu_was_open:
            self._sync_slash_menu_after_edit()
        else:
            self._maybe_open_slash_menu(event)

    def _handle_slash_menu_key(self, event) -> bool:
        """슬래시 메뉴가 열린 동안 소비하는 키 5종. 소비했으면 True."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._close_slash_menu()
            return True
        if key == Qt.Key.Key_Up:
            self._slash_menu.move_selection(-1)
            return True
        if key == Qt.Key.Key_Down:
            self._slash_menu.move_selection(1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self._confirm_slash_item()
            return True
        return False

    def _dispatch_key(self, event) -> None:
        """기존 Enter/Tab/서식 단축키 분기 — 슬래시 메뉴와 무관한 원래 동작."""
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            if self._handle_return():
                return
            super().keyPressEvent(event)
            return

        is_backtab = key == Qt.Key.Key_Backtab or (
            key == Qt.Key.Key_Tab and bool(mods & Qt.KeyboardModifier.ShiftModifier)
        )
        if key == Qt.Key.Key_Tab or is_backtab:
            self._handle_tab(reverse=is_backtab)
            return

        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if ctrl and not shift and key == Qt.Key.Key_B:
            self._toggle_wrap("**", "**")
            return
        if ctrl and not shift and key == Qt.Key.Key_I:
            self._toggle_wrap("*", "*")
            return
        if ctrl and shift and key == Qt.Key.Key_X:
            self._toggle_wrap("~~", "~~")
            return
        if ctrl and not shift and key == Qt.Key.Key_K:
            self._insert_link()
            return
        if ctrl and not shift and key == Qt.Key.Key_F:
            self.search_requested.emit(self.textCursor().selectedText())
            return
        if ctrl and not shift and (key == Qt.Key.Key_QuoteLeft or event.text() == "`"):
            self.toggle_inline_code()
            return
        if ctrl and shift and key == Qt.Key.Key_C:
            self.toggle_code_block()
            return
        if ctrl and not shift:
            digit = _heading_digit_from_event(event)
            if digit is not None:
                self.set_heading_level(digit)
                return
        if ctrl and shift:
            marker = _line_marker_from_event(event)
            if marker is not None:
                self.toggle_line_marker(marker)
                return

        super().keyPressEvent(event)

    # --- `/` 슬래시 메뉴 ---

    def _maybe_open_slash_menu(self, event) -> None:
        """방금 처리된 키가 여는 조건을 만족하는 `/`였으면 메뉴를 연다.

        조건: 커서 앞(같은 블록)이 공백뿐(빈 문자열 포함).
        """
        if event.text() != "/":
            return
        cursor = self.textCursor()
        block = cursor.block()
        col = cursor.positionInBlock()  # '/' 삽입 직후이므로 col-1이 슬래시 위치
        prefix = block.text()[: col - 1]
        if prefix.strip() != "":
            return
        self._slash_start = cursor.position() - 1
        self._open_slash_menu()

    def _open_slash_menu(self) -> None:
        self._slash_menu.populate(SLASH_CATALOG)
        self._position_slash_menu()
        self._slash_menu.show()
        self._slash_menu.raise_()

    def _position_slash_menu(self) -> None:
        rect = self.cursorRect()
        menu = self._slash_menu
        vp = self.viewport()
        # 뷰포트가 메뉴보다 낮으면 높이를 캡한다 (목록은 내부 스크롤)
        max_h = max(_SLASH_ROW_HEIGHT + 4, vp.height())
        if menu.height() > max_h:
            menu.setFixedHeight(max_h)
        x = rect.left()
        y = rect.bottom()
        # 아래 공간이 부족하면 커서 위로 뒤집는다 (viewport 자식이라 밖은 클리핑됨)
        if y + menu.height() > vp.height():
            y = rect.top() - menu.height()
        y = max(0, y)
        x = max(0, min(x, vp.width() - menu.width()))
        menu.move(x, y)

    def _close_slash_menu(self) -> None:
        self._slash_menu.hide()
        self._slash_start = None

    def _sync_slash_menu_after_edit(self) -> None:
        """필터 재계산 또는 닫힘 조건(커서가 슬래시 앞으로/슬래시 삭제됨) 처리."""
        if self._slash_start is None:
            return
        cursor = self.textCursor()
        pos = cursor.position()
        doc_text = self.toPlainText()
        if (
            pos <= self._slash_start
            or self._slash_start >= len(doc_text)
            or doc_text[self._slash_start] != "/"
        ):
            self._close_slash_menu()
            return
        filter_text = doc_text[self._slash_start + 1 : pos]
        if "\n" in filter_text:
            self._close_slash_menu()
            return
        self._filter_slash_menu(filter_text)
        self._position_slash_menu()

    def _filter_slash_menu(self, filter_text: str) -> None:
        needle = filter_text.lower()
        if needle == "":
            matched = list(SLASH_CATALOG)
        else:
            matched = [item for item in SLASH_CATALOG if needle in item.keywords.lower()]
        self._slash_menu.populate(matched)

    def _confirm_slash_item(self) -> None:
        item = self._slash_menu.selected_item()
        if item is None:
            # 매치 0개 -> Enter/Tab 무동작(메뉴 유지)
            return
        start = self._slash_start
        end = self.textCursor().position()
        self._close_slash_menu()
        if start is None:
            return
        edit_cursor = self.textCursor()
        edit_cursor.setPosition(start)
        edit_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit_cursor.beginEditBlock()
        edit_cursor.insertText(item.snippet)
        edit_cursor.endEditBlock()
        new_pos = edit_cursor.position() - item.cursor_back
        result_cursor = self.textCursor()
        result_cursor.setPosition(new_pos)
        self.setTextCursor(result_cursor)

    # --- Enter: 리스트/인용 이어쓰기 ---

    def _handle_return(self) -> bool:
        cursor = self.textCursor()
        text = cursor.block().text()

        m = _TASK_LINE_RE.match(text)
        if m:
            indent, bullet, content = m.groups()
            return self._finish_list_continuation(cursor, content, f"{indent}{bullet} [ ] ")

        m = _BULLET_LINE_RE.match(text)
        if m:
            indent, bullet, content = m.groups()
            return self._finish_list_continuation(cursor, content, f"{indent}{bullet} ")

        m = _ORDERED_LINE_RE.match(text)
        if m:
            indent, num, punct, content = m.groups()
            marker = f"{indent}{int(num) + 1}{punct} "
            return self._finish_list_continuation(cursor, content, marker)

        m = _QUOTE_LINE_RE.match(text)
        if m:
            prefix, content = m.groups()
            return self._finish_list_continuation(cursor, content, prefix)

        return False

    def _finish_list_continuation(self, cursor: QTextCursor, content: str, marker: str) -> bool:
        # 커서가 마커 접두 안(줄 맨 앞 포함)이면 이어쓰기 대신 기본 개행 —
        # 마커 앞 Enter 시 마커가 복제되는 것을 막는다.
        text = cursor.block().text()
        if cursor.positionInBlock() < len(text) - len(content):
            return False
        cursor.beginEditBlock()
        if content == "":
            # 내용 없음(마커만) — 마커 제거로 리스트 탈출
            line_cursor = self.textCursor()
            line_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            line_cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor,
            )
            line_cursor.removeSelectedText()
            cursor.endEditBlock()
            self.setTextCursor(line_cursor)
        else:
            cursor.insertText("\n" + marker)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        return True

    # --- Tab / Shift+Tab ---

    def _handle_tab(self, reverse: bool) -> None:
        cursor = self.textCursor()
        if not reverse and not cursor.hasSelection():
            text = cursor.block().text()
            is_list = bool(
                _TASK_RE.match(text) or _UL_RE.match(text) or _OL_RE.match(text)
            )
            if not is_list:
                # 일반/펜스 줄: 다른 에디터 관례대로 커서 위치에 삽입
                cursor.insertText(" " * self._indent_width_for(cursor.block()))
                return
        doc = self.document()
        start_pos = min(cursor.selectionStart(), cursor.selectionEnd())
        end_pos = max(cursor.selectionStart(), cursor.selectionEnd())
        start_block_num = doc.findBlock(start_pos).blockNumber()
        end_block = doc.findBlock(end_pos)
        end_block_num = end_block.blockNumber()
        if end_block_num > start_block_num and end_pos == end_block.position():
            end_block_num -= 1

        cursor.beginEditBlock()
        for block_num in range(start_block_num, end_block_num + 1):
            block = doc.findBlockByNumber(block_num)
            self._indent_block(block, reverse)
        cursor.endEditBlock()

    def _indent_width_for(self, block) -> int:
        if block.userState() == MarkdownHighlighter._STATE_CODE_FENCE:
            return 4
        text = block.text()
        if _TASK_RE.match(text) or _UL_RE.match(text) or _OL_RE.match(text):
            return 2
        return 4

    def _indent_block(self, block, reverse: bool) -> None:
        width = self._indent_width_for(block)
        text = block.text()
        block_cursor = QTextCursor(block)
        block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        if reverse:
            leading = len(text) - len(text.lstrip(" "))
            remove = min(width, leading)
            if remove > 0:
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, remove,
                )
                block_cursor.removeSelectedText()
        else:
            block_cursor.insertText(" " * width)

    # --- 서식 단축키 ---

    def _toggle_wrap(self, prefix: str, suffix: str) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            pos = cursor.position()
            cursor.insertText(prefix + suffix)
            cursor.setPosition(pos + len(prefix))
            self.setTextCursor(cursor)
            return

        start = cursor.selectionStart()
        selected = cursor.selectedText()

        is_wrapped = (
            len(selected) >= len(prefix) + len(suffix)
            and selected.startswith(prefix)
            and selected.endswith(suffix)
        )
        if is_wrapped and prefix == "*":
            # 짝수 `*` 런은 볼드 마커 — 이탤릭 벗기기가 `**w**`를 `*w*`로
            # 파괴하지 않도록 홀수 런(이탤릭 포함)일 때만 벗긴다.
            lead = len(selected) - len(selected.lstrip("*"))
            trail = len(selected) - len(selected.rstrip("*"))
            is_wrapped = lead % 2 == 1 and trail % 2 == 1
        if is_wrapped:
            inner = selected[len(prefix):len(selected) - len(suffix)]
            cursor.beginEditBlock()
            cursor.removeSelectedText()
            cursor.insertText(inner)
            cursor.endEditBlock()
            new_start, new_end = start, start + len(inner)
        else:
            cursor.beginEditBlock()
            cursor.removeSelectedText()
            cursor.insertText(prefix + selected + suffix)
            cursor.endEditBlock()
            new_start, new_end = start, start + len(prefix) + len(selected) + len(suffix)

        result_cursor = self.textCursor()
        result_cursor.setPosition(new_start)
        result_cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(result_cursor)

    def _insert_link(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            selected = cursor.selectedText()
            prefix_part = f"[{selected}]("
            cursor.beginEditBlock()
            cursor.removeSelectedText()
            cursor.insertText(prefix_part + "url)")
            cursor.endEditBlock()
            url_start = start + len(prefix_part)
            url_end = url_start + len("url")
            result_cursor = self.textCursor()
            result_cursor.setPosition(url_start)
            result_cursor.setPosition(url_end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(result_cursor)
        else:
            pos = cursor.position()
            cursor.insertText("[](url)")
            result_cursor = self.textCursor()
            result_cursor.setPosition(pos + 1)
            self.setTextCursor(result_cursor)

    # --- 코드 인용 (인라인 / 블록) ---

    def _toggle_code_block(self) -> None:
        cursor = self.textCursor()
        doc = self.document()

        if not cursor.hasSelection():
            block = cursor.block()
            if block.text().strip() == "":
                self._code_block_insert_empty(block)
            else:
                self._code_block_toggle_range(
                    doc, block.blockNumber(), block.blockNumber(), keep_caret=True,
                )
            return

        start_pos = min(cursor.selectionStart(), cursor.selectionEnd())
        end_pos = max(cursor.selectionStart(), cursor.selectionEnd())
        start_block_num = doc.findBlock(start_pos).blockNumber()
        end_block = doc.findBlock(end_pos)
        end_block_num = end_block.blockNumber()
        if end_block_num > start_block_num and end_pos == end_block.position():
            end_block_num -= 1

        self._code_block_toggle_range(doc, start_block_num, end_block_num)

    def _code_block_insert_empty(self, block) -> None:
        """빈 줄에서 호출 — 빈 펜스 3줄을 삽입하고 커서를 가운데 줄에 둔다."""
        start = block.position()
        end = start + len(block.text())
        edit_cursor = QTextCursor(self.document())
        edit_cursor.setPosition(start)
        edit_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit_cursor.beginEditBlock()
        edit_cursor.insertText("```\n\n```")
        edit_cursor.endEditBlock()
        result_cursor = self.textCursor()
        result_cursor.setPosition(start + len("```\n"))
        self.setTextCursor(result_cursor)

    def _code_block_toggle_range(
        self, doc, start_block_num: int, end_block_num: int, *, keep_caret: bool = False,
    ) -> None:
        if self._code_block_try_unwrap(doc, start_block_num, end_block_num):
            return
        self._code_block_wrap(doc, start_block_num, end_block_num, keep_caret=keep_caret)

    def _code_block_wrap(
        self, doc, start_block_num: int, end_block_num: int, *, keep_caret: bool = False,
    ) -> None:
        """[start_block_num, end_block_num] 줄들을 펜스로 감싼다(줄 경계 확장 후 호출됨).

        선택이 있었으면 새 펜스 블록 전체를 선택 상태로 남긴다(`_toggle_wrap` 관례).
        선택이 없었으면(keep_caret) **캐럿을 원래 줄 안에 보존**한다 —
        `set_heading_level`/`toggle_line_marker`의 커서 보존 관례와 통일(리뷰 지적).
        어느 쪽이든 재입력 시 안쪽 판정이 벗겨내므로 왕복 토글은 유지된다.
        """
        start_block = doc.findBlockByNumber(start_block_num)
        end_block = doc.findBlockByNumber(end_block_num)
        start = start_block.position()
        end = end_block.position() + len(end_block.text())
        lines = [doc.findBlockByNumber(n).text() for n in range(start_block_num, end_block_num + 1)]
        new_text = "```\n" + "\n".join(lines) + "\n```"

        edit_cursor = QTextCursor(doc)
        edit_cursor.setPosition(start)
        edit_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit_cursor.beginEditBlock()
        edit_cursor.insertText(new_text)
        edit_cursor.endEditBlock()

        result_cursor = self.textCursor()
        if keep_caret:
            # 여는 펜스(```\n = 4자) 다음이 원래 첫 줄의 시작
            result_cursor.setPosition(min(start + 4, len(self.toPlainText())))
        else:
            result_cursor.setPosition(start)
            result_cursor.setPosition(
                start + len(new_text), QTextCursor.MoveMode.KeepAnchor,
            )
        self.setTextCursor(result_cursor)

    def _code_block_try_unwrap(self, doc, start_block_num: int, end_block_num: int) -> bool:
        """이미 펜스로 감싸져 있으면 벗기고 True. 두 형태를 인식한다:
        선택이 펜스 줄 자체를 포함하는 경우, 선택이 펜스 **안쪽**에 있는 경우.

        안쪽 판정은 인접 줄 텍스트 매칭이 아니라 하이라이터의 블록 상태
        (`MarkdownHighlighter._STATE_CODE_FENCE`, `_indent_width_for`와 동일 신호)로
        한다 — 인접 줄만 보면 위 블록의 **닫는** 펜스와 아래 블록의 **여는** 펜스를
        감싸는 쌍으로 오인해, 사이에 있는 평문을 코드로 빨아들이며 두 블록을
        합쳐 버린다(리뷰 결함 D2).
        """
        start_block = doc.findBlockByNumber(start_block_num)
        end_block = doc.findBlockByNumber(end_block_num)

        if (
            end_block_num > start_block_num
            and _FENCE_OPEN_RE.match(start_block.text())
            and _FENCE_CLOSE_RE.match(end_block.text())
        ):
            self._code_block_unwrap(doc, start_block_num, end_block_num)
            return True

        span = self._enclosing_fence_span(doc, start_block_num, end_block_num)
        if span is not None:
            self._code_block_unwrap(doc, span[0], span[1])
            return True

        return False

    @staticmethod
    def _enclosing_fence_span(doc, start_block_num: int, end_block_num: int):
        """선택 줄들이 모두 한 펜스 블록 **안쪽**이면 (여는 줄, 닫는 줄) 반환.

        판정 기준은 블록 상태다: 펜스 안쪽 줄과 여는 펜스 줄은 FENCE 상태이고,
        닫는 펜스 줄은 NONE으로 돌아간다.
        """
        fence = MarkdownHighlighter._STATE_CODE_FENCE
        for n in range(start_block_num, end_block_num + 1):
            block = doc.findBlockByNumber(n)
            if block.userState() != fence or _FENCE_OPEN_RE.match(block.text()):
                return None  # 펜스 밖이거나 여는 펜스 줄 자체 — 안쪽이 아니다

        open_num = start_block_num
        while open_num >= 0:
            block = doc.findBlockByNumber(open_num)
            if _FENCE_OPEN_RE.match(block.text()) and block.userState() == fence:
                break
            open_num -= 1
        else:
            return None
        if open_num < 0:
            return None

        close_num = end_block_num + 1
        while close_num < doc.blockCount():
            block = doc.findBlockByNumber(close_num)
            if _FENCE_CLOSE_RE.match(block.text()):
                return (open_num, close_num)
            if block.userState() != fence:
                return None
            close_num += 1
        return None

    def _code_block_unwrap(self, doc, fence_open_num: int, fence_close_num: int) -> None:
        """fence_open_num/fence_close_num 줄(펜스 자체)을 제거하고 안쪽 내용만 남긴다."""
        open_block = doc.findBlockByNumber(fence_open_num)
        close_block = doc.findBlockByNumber(fence_close_num)
        start = open_block.position()
        end = close_block.position() + len(close_block.text())
        inner_lines = [
            doc.findBlockByNumber(n).text() for n in range(fence_open_num + 1, fence_close_num)
        ]
        new_text = "\n".join(inner_lines)

        edit_cursor = QTextCursor(doc)
        edit_cursor.setPosition(start)
        edit_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit_cursor.beginEditBlock()
        edit_cursor.insertText(new_text)
        edit_cursor.endEditBlock()

        result_cursor = self.textCursor()
        result_cursor.setPosition(start)
        result_cursor.setPosition(start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(result_cursor)

    # --- 공개 편집 API (툴바/슬래시 메뉴용) ---

    def toggle_wrap(self, prefix: str, suffix: str) -> None:
        """`_toggle_wrap`의 공개 래퍼."""
        self._toggle_wrap(prefix, suffix)

    def insert_link(self) -> None:
        """`_insert_link`의 공개 래퍼."""
        self._insert_link()

    def set_heading_level(self, level: int) -> None:
        """현재 줄의 헤딩 레벨을 설정한다.

        기존 `#{1,6}\\s+` 접두를 제거한 뒤 level(1-6)이면 `"#" * level + " "`을
        붙인다. 현재 접두 레벨과 같은 level을 다시 적용하면 접두 제거(본문 복귀).
        level == 0은 접두 제거만 한다.
        """
        if not 0 <= level <= 6:
            raise ValueError("level must be between 0 and 6")
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        m = _HEADING_PREFIX_RE.match(text)
        current_level = len(m.group(1)) if m else 0
        old_prefix_len = m.end() if m else 0
        content = text[old_prefix_len:]

        new_prefix = "" if level == 0 or level == current_level else "#" * level + " "
        new_text = new_prefix + content
        if new_text == text:
            return

        offset_in_content = max(0, cursor.positionInBlock() - old_prefix_len)
        new_cursor_pos = block.position() + len(new_prefix) + offset_in_content

        edit_cursor = QTextCursor(block)
        edit_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        edit_cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor,
        )
        edit_cursor.beginEditBlock()
        edit_cursor.insertText(new_text)
        edit_cursor.endEditBlock()

        result_cursor = self.textCursor()
        result_cursor.setPosition(new_cursor_pos)
        self.setTextCursor(result_cursor)

    def toggle_line_marker(self, marker: str) -> None:
        """선택에 걸친 모든 줄(선택 없으면 현재 줄)에 리스트/인용 마커를 토글한다.

        marker는 "- " / "1. " / "- [ ] " / "> " 중 하나. 이미 같은 종류의
        마커면 제거, 다른 리스트/인용 마커면 교체, 없으면 들여쓰기 뒤에 삽입한다.
        번호 리스트는 선택 범위 안에서 1부터 재번호한다. 빈 줄은 건너뛴다.
        """
        if marker not in _MARKER_KIND:
            raise ValueError(f"unsupported marker: {marker!r}")
        desired_kind = _MARKER_KIND[marker]
        cursor = self.textCursor()
        doc = self.document()

        # 선택이 없으면 편집 후 커서 위치를 보존한다 (set_heading_level과 일관)
        restore: tuple[int, int, int] | None = None
        if not cursor.hasSelection():
            cur_block = doc.findBlock(cursor.position())
            restore = (
                cur_block.blockNumber(),
                cursor.positionInBlock(),
                len(cur_block.text()),
            )

        if cursor.hasSelection():
            start_pos = min(cursor.selectionStart(), cursor.selectionEnd())
            end_pos = max(cursor.selectionStart(), cursor.selectionEnd())
        else:
            start_pos = end_pos = cursor.position()

        start_block_num = doc.findBlock(start_pos).blockNumber()
        end_block = doc.findBlock(end_pos)
        end_block_num = end_block.blockNumber()
        if end_block_num > start_block_num and end_pos == end_block.position():
            end_block_num -= 1

        edit_cursor = self.textCursor()
        edit_cursor.beginEditBlock()
        order_counter = 1
        for block_num in range(start_block_num, end_block_num + 1):
            block = doc.findBlockByNumber(block_num)
            text = block.text()
            if text.strip() == "":
                continue
            info = _detect_line_marker(text)
            if info is not None and info[0] == desired_kind:
                new_text = info[1] + info[2]
            else:
                if info is not None:
                    indent, rest = info[1], info[2]
                else:
                    indent_m = _LEADING_WS_RE.match(text)
                    indent = indent_m.group(1) if indent_m else ""
                    rest = text[len(indent):]
                if desired_kind == "ordered":
                    marker_text = f"{order_counter}. "
                    order_counter += 1
                else:
                    marker_text = marker
                new_text = indent + marker_text + rest
            if new_text != text:
                block_cursor = QTextCursor(block)
                block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                block_cursor.movePosition(
                    QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor,
                )
                block_cursor.insertText(new_text)
        edit_cursor.endEditBlock()

        if restore is not None:
            block_num, pos_in_block, old_len = restore
            block = doc.findBlockByNumber(block_num)
            new_len = len(block.text())
            new_pos = min(max(0, pos_in_block + new_len - old_len), new_len)
            result_cursor = self.textCursor()
            result_cursor.setPosition(block.position() + new_pos)
            self.setTextCursor(result_cursor)

    def toggle_inline_code(self) -> None:
        """선택을 인라인 코드(`` ` ``)로 감싸기/벗기기. `toggle_wrap` 재사용."""
        self._toggle_wrap("`", "`")

    def toggle_code_block(self) -> None:
        """선택 줄들(선택 없으면 현재 줄)을 코드 펜스(```)로 감싸기/벗기기.

        선택이 있으면 걸친 모든 줄 전체를 줄 단위로 감싼다(줄 중간 선택도 그 줄
        전체 포함). 이미 펜스로 감싸져 있으면 벗긴다. 선택이 없으면 현재 줄이
        비어 있을 때만 빈 펜스 3줄을 삽입하고 커서를 가운데 줄에 둔다(그 외엔
        현재 줄을 펜스로 감싼다). 언어 태그는 넣지 않는다(v1). 1 undo 단위.
        """
        self._toggle_code_block()

    # --- 체크박스 클릭 토글 ---

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self._slash_start is not None:
            self._close_slash_menu()
        if event.button() == Qt.MouseButton.LeftButton:
            hit_cursor = self.cursorForPosition(event.position().toPoint())
            block = hit_cursor.block()
            column = hit_cursor.positionInBlock()
            rng = self._checkbox_range(block)
            if rng is not None and rng[0] <= column < rng[1]:
                if self._toggle_task_at(block):
                    event.accept()
                    return
        super().mousePressEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._close_slash_menu()
        super().focusOutEvent(event)

    def _checkbox_range(self, block) -> tuple[int, int] | None:
        m = _TASK_CHECK_RE.match(block.text())
        if not m:
            return None
        return (m.end(1) - 1, m.end(3))

    def _toggle_task_at(self, block) -> bool:
        """block이 태스크 항목이면 체크 상태를 토글하고 True, 아니면 False."""
        m = _TASK_CHECK_RE.match(block.text())
        if not m:
            return False
        new_char = "x" if m.group(2) == " " else " "
        toggle_cursor = QTextCursor(block)
        toggle_cursor.setPosition(block.position() + m.start(2))
        toggle_cursor.setPosition(block.position() + m.end(2), QTextCursor.MoveMode.KeepAnchor)
        toggle_cursor.insertText(new_char)
        return True

    # --- 파일 드롭 치환 (WP-FR) ---

    def _collect_file_ref_tokens(self, mime) -> list[str]:
        """mime의 file URL 중 현재 files/ 루트 하위인 것만 토큰으로 변환한다.

        files 밖 파일·비파일 mime은 빈 리스트를 반환 — 호출부가 기존
        QPlainTextEdit 기본 처리(super())로 흘려보낸다.
        """
        if mime is None or not mime.hasUrls():
            return []
        tokens: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            token = self._token_for_path(url.toLocalFile())
            if token is not None:
                tokens.append(token)
        return tokens

    @staticmethod
    def _token_for_path(local_path: str) -> str | None:
        """files/·skill-files/ 두 루트에 대해 참조 토큰을 시도한다 (WP-FR/WP-SF)."""
        files_root = get_files_root()
        if files_root:
            token = _file_ref_token(local_path, files_root)
            if token is not None:
                return token
        skill_root = get_skill_files_root()
        if skill_root:
            return _skill_file_ref_token(local_path, skill_root)
        return None

    def _non_file_ref_urls(self, mime) -> list[str]:
        """토큰으로 변환되지 **않은** URL의 원문 목록 (혼합 드롭 보존용)."""
        if mime is None or not mime.hasUrls():
            return []
        rest: list[str] = []
        for url in mime.urls():
            if url.isLocalFile() and self._token_for_path(url.toLocalFile()):
                continue
            rest.append(url.toString())
        return rest

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._collect_file_ref_tokens(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self._collect_file_ref_tokens(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """files/ 하위 file URL은 드롭 지점에 참조 토큰을 삽입(복수면 줄바꿈
        구분)하고, 그 외(일반 텍스트 드래그 등)는 기존 QPlainTextEdit 동작으로
        흘린다.

        files 안팎이 섞인 드롭이면 밖 파일의 URL도 함께 남긴다 — 안쪽 토큰만
        넣고 바깥을 버리면 master가 삽입하던 내용이 조용히 사라진다(리뷰 지적).
        """
        tokens = self._collect_file_ref_tokens(event.mimeData())
        if not tokens:
            super().dropEvent(event)
            return
        tokens = tokens + self._non_file_ref_urls(event.mimeData())
        drop_point = self.cursorForPosition(event.position().toPoint())
        edit_cursor = self.textCursor()
        edit_cursor.setPosition(drop_point.position())
        edit_cursor.beginEditBlock()
        edit_cursor.insertText("\n".join(tokens))
        edit_cursor.endEditBlock()
        result_cursor = self.textCursor()
        result_cursor.setPosition(edit_cursor.position())
        self.setTextCursor(result_cursor)
        event.acceptProposedAction()
