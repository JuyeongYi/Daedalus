"""마크다운 에디터 위젯 — 하이브리드(마커 유지 + 스타일) 방식.

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

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


@dataclass(frozen=True)
class SlashItem:
    """슬래시 메뉴 항목 — 표시/필터/삽입 스니펫을 묶는다."""

    label: str        # 표시 텍스트 (예: "제목 1")
    keywords: str      # 필터 매칭 대상 (label + 영문 별칭)
    snippet: str       # 삽입 텍스트
    cursor_back: int = 0  # 삽입 후 커서를 끝에서 뒤로 물릴 문자 수


SLASH_CATALOG: list[SlashItem] = [
    SlashItem("제목 1", "제목 1 h1 heading", "# "),
    SlashItem("제목 2", "제목 2 h2 heading", "## "),
    SlashItem("제목 3", "제목 3 h3 heading", "### "),
    SlashItem("불릿 리스트", "불릿 리스트 list bullet ul", "- "),
    SlashItem("번호 리스트", "번호 리스트 number ordered list ol", "1. "),
    SlashItem("체크리스트", "체크리스트 check task checklist todo", "- [ ] "),
    SlashItem("인용", "인용 quote blockquote", "> "),
    SlashItem("코드 블록", "코드 블록 code block fence", "```\n\n```", 4),
    SlashItem("구분선", "구분선 hr divider horizontal rule", "---\n"),
    SlashItem("링크", "링크 link url", "[](url)", 6),
]

_SLASH_ITEM_ROLE = Qt.ItemDataRole.UserRole
_SLASH_ROW_HEIGHT = 24
_SLASH_MAX_VISIBLE_ROWS = 8
_SLASH_MENU_WIDTH = 180


class _SlashMenu(QListWidget):
    """`/` 슬래시 메뉴 — 에디터 viewport의 자식 오버레이(Qt.Popup 아님).

    포커스는 에디터가 계속 보유한다(오프스크린 테스트를 위해).
    """

    def __init__(self, editor: "MarkdownEditor") -> None:
        super().__init__(editor.viewport())
        self._editor = editor
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setStyleSheet(
            "QListWidget { background-color: #252540; color: #ccc; "
            "border: 1px solid #3a3a5c; }"
            "QListWidget::item { padding: 2px 8px; }"
            "QListWidget::item:selected { background-color: #334; color: #88aaff; }"
        )
        self.itemClicked.connect(self._on_item_clicked)
        self.hide()

    def populate(self, items: list[SlashItem]) -> None:
        self.clear()
        for item in items:
            list_item = QListWidgetItem(item.label)
            list_item.setData(_SLASH_ITEM_ROLE, item)
            self.addItem(list_item)
        if self.count() > 0:
            self.setCurrentRow(0)
        self._resize_to_contents()

    def _resize_to_contents(self) -> None:
        visible_rows = min(max(self.count(), 1), _SLASH_MAX_VISIBLE_ROWS)
        self.setFixedWidth(_SLASH_MENU_WIDTH)
        self.setFixedHeight(_SLASH_ROW_HEIGHT * visible_rows + 4)

    def selected_item(self) -> SlashItem | None:
        current = self.currentItem()
        if current is None:
            return None
        return current.data(_SLASH_ITEM_ROLE)

    def move_selection(self, delta: int) -> None:
        if self.count() == 0:
            return
        row = (self.currentRow() + delta) % self.count()
        self.setCurrentRow(row)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self.setCurrentItem(item)
        self._editor._confirm_slash_item()
        self._editor.setFocus()


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
        self._slash_menu = _SlashMenu(self)
        self._slash_start: int | None = None

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


class MarkdownToolbar(QWidget):
    """서식 툴바 — `MarkdownEditor` 공개 API에 배선된 버튼 행.

    `H1 H2 H3 │ B I S │ • 1. ☑ │ " 🔗 │ 👁` — 프리뷰 버튼(👁)만 예외로
    `preview_toggled` 시그널을 방출할 뿐 문서를 건드리지 않는다(프리뷰 자체는
    `SectionContentPanel` 소관).
    """

    preview_toggled = Signal(bool)

    _BUTTON_WIDTH = 30

    def __init__(self, editor: MarkdownEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._edit_buttons: list[QPushButton] = []  # 프리뷰 중 비활성화 대상

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)

        self._add_button(lay, "H1", "제목 1", lambda: self._apply_heading(1))
        self._add_button(lay, "H2", "제목 2", lambda: self._apply_heading(2))
        self._add_button(lay, "H3", "제목 3", lambda: self._apply_heading(3))
        self._add_separator(lay)
        self._add_button(lay, "B", "굵게 (Ctrl+B)", lambda: self._apply_wrap("**", "**"))
        self._add_button(lay, "I", "기울임 (Ctrl+I)", lambda: self._apply_wrap("*", "*"))
        self._add_button(lay, "S", "취소선 (Ctrl+Shift+X)", lambda: self._apply_wrap("~~", "~~"))
        self._add_separator(lay)
        self._add_button(lay, "•", "불릿 리스트", lambda: self._apply_marker("- "))
        self._add_button(lay, "1.", "번호 리스트", lambda: self._apply_marker("1. "))
        self._add_button(lay, "☑", "체크리스트", lambda: self._apply_marker("- [ ] "))
        self._add_separator(lay)
        self._add_button(lay, "\"", "인용", lambda: self._apply_marker("> "))
        self._add_button(lay, "🔗", "링크 (Ctrl+K)", self._apply_link)
        self._add_separator(lay)
        self._btn_preview = self._add_button(
            lay, "👁", "미리보기 전환", self._on_preview_toggled, checkable=True,
        )
        lay.addStretch(1)

    def _add_button(
        self,
        lay: QHBoxLayout,
        text: str,
        tooltip: str,
        handler,
        *,
        checkable: bool = False,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setFixedWidth(self._BUTTON_WIDTH)
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        if checkable:
            btn.toggled.connect(handler)
        else:
            # checkable은 프리뷰(👁) 전용 — 나머지는 전부 편집 버튼
            btn.clicked.connect(handler)
            self._edit_buttons.append(btn)
        lay.addWidget(btn)
        return btn

    def _add_separator(self, lay: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(sep)

    def _apply_heading(self, level: int) -> None:
        self._editor.set_heading_level(level)
        self._editor.setFocus()

    def _apply_wrap(self, prefix: str, suffix: str) -> None:
        self._editor.toggle_wrap(prefix, suffix)
        self._editor.setFocus()

    def _apply_marker(self, marker: str) -> None:
        self._editor.toggle_line_marker(marker)
        self._editor.setFocus()

    def _apply_link(self) -> None:
        self._editor.insert_link()
        self._editor.setFocus()

    def _on_preview_toggled(self, checked: bool) -> None:
        # 프리뷰 중 편집 버튼이 숨은 문서를 조용히 바꾸지 못하게 잠근다
        for btn in self._edit_buttons:
            btn.setEnabled(not checked)
        self.preview_toggled.emit(checked)
        self._editor.setFocus()

    def set_preview_checked(self, checked: bool) -> None:
        """프리뷰(👁) 버튼 체크 상태를 외부에서 리셋할 때 쓰는 공개 API.

        `checked`가 현재 상태와 다르면 `toggled` 시그널이 발생해 `preview_toggled`도
        함께 방출된다(호출자가 이를 감안해야 함 — `SectionContentPanel.show_body`는
        이 방출로 스택이 편집 모드로 복귀하는 것을 활용한다).
        """
        self._btn_preview.setChecked(checked)
