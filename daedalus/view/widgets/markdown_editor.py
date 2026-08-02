"""마크다운 에디터 위젯 — 하이브리드(마커 유지 + 스타일) 방식.

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit, QWidget

MARKDOWN_PALETTE: dict[str, QColor] = {
    "text": QColor("#cccccc"),
    "heading": QColor("#88aaff"),
    "marker": QColor("#556699"),
    "bold": QColor("#eeeeee"),
    "italic": QColor("#dddddd"),
    "strike": QColor("#777777"),
    "code_fg": QColor("#ffcc66"),
    "code_bg": QColor("#252540"),
    "fence_bg": QColor("#20203a"),
    "quote": QColor("#7a9a7a"),
    "list_marker": QColor("#6674cc"),
    "link_text": QColor("#66aaff"),
    "link_url": QColor("#555577"),
    "checkbox": QColor("#cc8844"),
    "done_text": QColor("#666666"),
    "hr": QColor("#444455"),
}

_BASE_FONT_FAMILY = "Segoe UI"
_CODE_FONT_FAMILY = "Consolas"
_BASE_POINT_SIZE = 10.5
_HEADING_SIZE_MULTIPLIER = {1: 1.5, 2: 1.3, 3: 1.15, 4: 1.0, 5: 1.0, 6: 1.0}

# --- 블록 수준 규칙 ---
_HEADING_RE = re.compile(r"^(#{1,6})\s+.+$")
_HEADING_PREFIX_RE = re.compile(r"^(#{1,6})(\s+)")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_QUOTE_RE = re.compile(r"^\s{0,3}(>\s?)+")
_TASK_RE = re.compile(r"^(\s*)([-*+])\s+\[([ xX])\]\s")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+")
_OL_RE = re.compile(r"^(\s*)(\d{1,9}[.)])\s+")
_FENCE_OPEN_RE = re.compile(r"^\s{0,3}(```|~~~)[^`]*$")
_FENCE_CLOSE_RE = re.compile(r"^\s{0,3}(```|~~~)\s*$")

# --- 인라인 규칙 ---
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_STAR_RE = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")
_BOLD_US_RE = re.compile(r"__(?!\s)(.+?)(?<!\s)__")
_ITALIC_STAR_RE = re.compile(r"(?<![*\w])\*(?!\s|\*)([^*\n]+?)(?<!\s)\*(?!\*)")
_ITALIC_US_RE = re.compile(r"(?<![_\w])_(?!\s|_)([^_\n]+?)(?<!\s)_(?!_)")
_STRIKE_RE = re.compile(r"~~(?!\s)(.+?)(?<!\s)~~")

# --- Enter 키 처리용 (전체 줄 매치, 내용/마커 구분) ---
_TASK_LINE_RE = re.compile(r"^(\s*)([-*+]) \[[ xX]\] (.*)$")
_BULLET_LINE_RE = re.compile(r"^(\s*)([-*+]) (.*)$")
_ORDERED_LINE_RE = re.compile(r"^(\s*)(\d+)([.)]) (.*)$")
_QUOTE_LINE_RE = re.compile(r"^(\s*>\s?)(.*)$")

# --- 체크박스 클릭 토글용 ---
_TASK_CHECK_RE = re.compile(r"^(\s*[-*+]\s+\[)([ xX])(\])")

# --- toggle_line_marker용 ---
_LEADING_WS_RE = re.compile(r"^(\s*)")
_QUOTE_MARKER_RE = re.compile(r"^(\s{0,3})((?:>\s?)+)")
_MARKER_KIND: dict[str, str] = {
    "- ": "bullet",
    "1. ": "ordered",
    "- [ ] ": "task",
    "> ": "quote",
}


def _detect_line_marker(text: str) -> tuple[str, str, str] | None:
    """줄의 리스트/인용 마커를 감지한다. (kind, indent, rest) 또는 마커 없으면 None.

    task는 UL 패턴도 만족하므로 먼저 검사한다(하이라이터 규칙 순서와 동일).
    """
    m = _TASK_RE.match(text)
    if m:
        return ("task", m.group(1), text[m.end():])
    m = _UL_RE.match(text)
    if m:
        return ("bullet", m.group(1), text[m.end():])
    m = _OL_RE.match(text)
    if m:
        return ("ordered", m.group(1), text[m.end():])
    m = _QUOTE_MARKER_RE.match(text)
    if m:
        return ("quote", m.group(1), text[m.end():])
    return None


def _make_format(
    color_key: str | None = None,
    *,
    bold: bool = False,
    italic: bool = False,
    strike: bool = False,
    underline: bool = False,
    bg_key: str | None = None,
    font_family: str | None = None,
    point_size: float | None = None,
) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if color_key is not None:
        fmt.setForeground(MARKDOWN_PALETTE[color_key])
    if bg_key is not None:
        fmt.setBackground(MARKDOWN_PALETTE[bg_key])
    if font_family is not None:
        fmt.setFontFamilies([font_family])
    if point_size is not None:
        fmt.setFontPointSize(point_size)
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    if strike:
        fmt.setFontStrikeOut(True)
    if underline:
        fmt.setFontUnderline(True)
    return fmt


class MarkdownHighlighter(QSyntaxHighlighter):
    """마크다운 문법 하이라이터 — 하이브리드(마커 유지 + 스타일) 방식.

    코드 펜스는 블록 상태(`_STATE_NONE`/`_STATE_CODE_FENCE`)로 추적한다.
    """

    _STATE_NONE = 0
    _STATE_CODE_FENCE = 1

    def __init__(self, document: QTextDocument, base_point_size: float = _BASE_POINT_SIZE) -> None:
        super().__init__(document)
        self._base_point_size = base_point_size
        self._build_formats()

    def _build_formats(self) -> None:
        self._fmt_marker = _make_format("marker")
        self._fmt_bold = _make_format("bold", bold=True)
        self._fmt_italic = _make_format("italic", italic=True)
        self._fmt_strike = _make_format("strike", strike=True)
        self._fmt_code = _make_format("code_fg", bg_key="code_bg", font_family=_CODE_FONT_FAMILY)
        self._fmt_fence = _make_format("code_fg", bg_key="fence_bg", font_family=_CODE_FONT_FAMILY)
        self._fmt_quote = _make_format("quote", italic=True)
        self._fmt_list_marker = _make_format("list_marker")
        self._fmt_link_text = _make_format("link_text", underline=True)
        self._fmt_link_url = _make_format("link_url")
        self._fmt_checkbox = _make_format("checkbox")
        self._fmt_done = _make_format("done_text", strike=True)
        self._fmt_hr = _make_format("hr")
        self._fmt_heading = {
            level: _make_format(
                "heading", bold=True, point_size=self._base_point_size * mult,
            )
            for level, mult in _HEADING_SIZE_MULTIPLIER.items()
        }

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt override)
        prev_state = self.previousBlockState()

        if prev_state == self._STATE_CODE_FENCE:
            if _FENCE_CLOSE_RE.match(text):
                self.setFormat(0, len(text), self._fmt_marker)
                self.setCurrentBlockState(self._STATE_NONE)
            else:
                self.setFormat(0, len(text), self._fmt_fence)
                self.setCurrentBlockState(self._STATE_CODE_FENCE)
            return

        if _FENCE_OPEN_RE.match(text):
            self.setFormat(0, len(text), self._fmt_marker)
            self.setCurrentBlockState(self._STATE_CODE_FENCE)
            return

        self.setCurrentBlockState(self._STATE_NONE)

        if self._apply_heading(text):
            return  # 헤딩 줄은 인라인 스킵

        if not self._apply_hr(text):
            if not self._apply_quote(text):
                if not self._apply_task(text):
                    if not self._apply_ul(text):
                        self._apply_ol(text)

        self._apply_inline(text)

    # --- 블록 규칙 ---

    def _apply_heading(self, text: str) -> bool:
        if not _HEADING_RE.match(text):
            return False
        m = _HEADING_PREFIX_RE.match(text)
        if m is None:
            return False
        level = len(m.group(1))
        text_start = m.end()
        self.setFormat(0, len(m.group(1)), self._fmt_marker)
        self.setFormat(text_start, len(text) - text_start, self._fmt_heading[level])
        return True

    def _apply_hr(self, text: str) -> bool:
        if not _HR_RE.match(text):
            return False
        self.setFormat(0, len(text), self._fmt_hr)
        return True

    def _apply_quote(self, text: str) -> bool:
        m = _QUOTE_RE.match(text)
        if not m:
            return False
        prefix_end = m.end()
        self.setFormat(0, prefix_end, self._fmt_marker)
        if prefix_end < len(text):
            self.setFormat(prefix_end, len(text) - prefix_end, self._fmt_quote)
        return True

    def _apply_task(self, text: str) -> bool:
        m = _TASK_RE.match(text)
        if not m:
            return False
        end = m.end()
        self.setFormat(0, end, self._fmt_checkbox)
        checked = m.group(3) in ("x", "X")
        if checked and end < len(text):
            self.setFormat(end, len(text) - end, self._fmt_done)
        return True

    def _apply_ul(self, text: str) -> bool:
        m = _UL_RE.match(text)
        if not m:
            return False
        self.setFormat(0, m.end(), self._fmt_list_marker)
        return True

    def _apply_ol(self, text: str) -> bool:
        m = _OL_RE.match(text)
        if not m:
            return False
        self.setFormat(0, m.end(), self._fmt_list_marker)
        return True

    # --- 인라인 규칙 ---

    def _apply_inline(self, text: str) -> None:
        protected: list[tuple[int, int]] = []

        def blocked(start: int, end: int) -> bool:
            return any(start < p_end and p_start < end for p_start, p_end in protected)

        for m in _INLINE_CODE_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_code)
            protected.append((m.start(), m.end()))

        for m in _IMAGE_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_link_like(m)
            protected.append((m.start(), m.end()))

        for m in _LINK_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_link_like(m)
            protected.append((m.start(), m.end()))

        for m in _BOLD_STAR_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_wrapped(m, self._fmt_bold)
            protected.append((m.start(), m.end()))

        for m in _BOLD_US_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_wrapped(m, self._fmt_bold)
            protected.append((m.start(), m.end()))

        for m in _ITALIC_STAR_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_wrapped(m, self._fmt_italic)
            protected.append((m.start(), m.end()))

        for m in _ITALIC_US_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_wrapped(m, self._fmt_italic)
            protected.append((m.start(), m.end()))

        for m in _STRIKE_RE.finditer(text):
            if blocked(m.start(), m.end()):
                continue
            self._format_wrapped(m, self._fmt_strike)
            protected.append((m.start(), m.end()))

    def _format_wrapped(self, m: re.Match[str], fmt: QTextCharFormat) -> None:
        """`구분자 + 내용 + 구분자` 형태 매치 서식 적용 (bold/italic/strike 공용)."""
        self.setFormat(m.start(), m.start(1) - m.start(), self._fmt_marker)
        self.setFormat(m.start(1), m.end(1) - m.start(1), fmt)
        self.setFormat(m.end(1), m.end() - m.end(1), self._fmt_marker)

    def _format_link_like(self, m: re.Match[str]) -> None:
        """링크/이미지 공용 — `[텍스트](url)` 구조. group(1)=텍스트, group(2)=url."""
        bracket_end = m.end(1) + 1  # ']' 다음, 즉 '(' 시작 위치
        self.setFormat(m.start(), bracket_end - m.start(), self._fmt_link_text)
        self.setFormat(bracket_end, m.end() - bracket_end, self._fmt_link_url)


class MarkdownEditor(QPlainTextEdit):
    """마크다운 본문 에디터 — 하이라이팅 + 리스트/인용 이어쓰기 + 서식 단축키."""

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

    # --- 키 입력 ---

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
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

        super().keyPressEvent(event)

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
        desired_kind = _MARKER_KIND[marker]
        cursor = self.textCursor()
        doc = self.document()

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

    # --- 체크박스 클릭 토글 ---

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
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
