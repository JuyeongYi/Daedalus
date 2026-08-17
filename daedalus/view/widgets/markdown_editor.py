"""마크다운 에디터 위젯 — 하이브리드(마커 유지 + 스타일) 방식.

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
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
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
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
    SlashItem("인라인 코드", "인라인 코드 inline code backtick tick", "``", 1),
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


# --- files/ 루트 제공자 (WP-FR) — TagInput의 도구/블랙보드 후보 제공자와 동일한
# 패턴. app이 `_current_path` 변화에 맞춰 등록하고, MarkdownEditor의 드롭 치환이
# 조회한다. None이면(미저장 프로젝트 등) 드롭 치환이 비활성화되고 기본 동작으로
# 흐른다.
_FILES_ROOT_PROVIDER: Callable[[], str | None] | None = None


def set_files_root_provider(provider: Callable[[], str | None] | None) -> None:
    """MarkdownEditor 드롭 치환이 참조할 현재 프로젝트 files/ 루트 제공자를 등록한다."""
    global _FILES_ROOT_PROVIDER
    _FILES_ROOT_PROVIDER = provider


def get_files_root() -> str | None:
    """등록된 제공자에서 현재 files/ 루트 경로를 가져온다 (없으면 None)."""
    if _FILES_ROOT_PROVIDER is not None:
        return _FILES_ROOT_PROVIDER()
    return None


_SKILL_FILES_ROOT_PROVIDER: Callable[[], str | None] | None = None


def set_skill_files_root_provider(provider: Callable[[], str | None] | None) -> None:
    """skill-files/ 루트 제공자를 등록한다 (WP-SF — files 제공자와 동일 패턴)."""
    global _SKILL_FILES_ROOT_PROVIDER
    _SKILL_FILES_ROOT_PROVIDER = provider


def get_skill_files_root() -> str | None:
    """등록된 제공자에서 현재 skill-files/ 루트 경로를 가져온다 (없으면 None)."""
    if _SKILL_FILES_ROOT_PROVIDER is not None:
        return _SKILL_FILES_ROOT_PROVIDER()
    return None



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


def _file_ref_token(local_path: str, files_root: str) -> str | None:
    """local_path가 files_root 하위 파일이면 참조 토큰을 계산한다. 아니면 None.

    토큰은 타깃 중립 ``${ROOT}/files/<상대경로>``다(WP-RT) — 어느 CC 변수가
    되는지는 컴파일 시점에 빌드 타깃이 정한다. 경로 구분자는 POSIX(``/``)로
    정규화한다.

    경로에 공백이 있으면 마크다운 관례대로 ``<...>``로 감싼다 — 감싸지 않으면
    컴파일러의 참조 스캐너가 공백에서 끊어 자기가 만든 토큰을 dangling으로
    오탐한다(리뷰 지적: Part B/C 자기모순).
    """
    try:
        rel = Path(local_path).resolve().relative_to(Path(files_root).resolve())
    except ValueError:
        return None
    if str(rel) == ".":
        return None  # files_root 자체가 드롭된 경우 — 삽입 대상 아님
    from daedalus.model.plugin.variables import file_ref_token

    posix_rel = PurePosixPath(rel.as_posix())
    token = file_ref_token(str(posix_rel))
    return f"<{token}>" if " " in str(posix_rel) else token


def _skill_file_ref_token(local_path: str, skill_files_root: str) -> str | None:
    """local_path가 skill-files/<스킬>/ 하위 파일이면 참조 토큰을 계산한다 (WP-SF).

    토큰은 ``${CLAUDE_SKILL_DIR}/<스킬 폴더 안 상대경로>`` — 첫 경로 조각(스킬
    폴더 이름)은 토큰에 들어가지 않는다. 런타임에 CC가 이 변수를 그 스킬의
    디렉토리로 치환하기 때문이다. skill-files/ 바로 밑 파일(스킬 폴더 없음)은
    소속을 알 수 없어 None — 기본 드롭으로 흘린다(컴파일도 복사하지 않는다).
    공백 경로의 ``<...>`` 감싸기는 files 토큰과 같은 이유다.
    """
    try:
        rel = Path(local_path).resolve().relative_to(Path(skill_files_root).resolve())
    except ValueError:
        return None
    parts = PurePosixPath(rel.as_posix()).parts
    if len(parts) < 2:
        return None  # 루트 자체 또는 스킬 폴더 미소속 파일
    inner = "/".join(parts[1:])
    token = "${CLAUDE_SKILL_DIR}/" + inner
    return f"<{token}>" if " " in inner else token


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


_SEARCH_MATCH_BG = QColor("#665522")
_SEARCH_CURRENT_BG = QColor("#a3843a")


class SearchBar(QWidget):
    """찾기/바꾸기 바 — `MarkdownEditor` 위에 접히는 바(기본 숨김).

    포팅 정답지: qmarkdowntextedit의 QPlainTextEditSearchWidget을 단순화
    (정규식/단어 단위/선택 범위 검색 없음 — WP-MD3 Part A 명세 범위).
    검색은 `toPlainText()`에 대한 평문 부분 문자열 매칭이며 `QTextDocument.find`를
    쓰지 않는다 — 매치 목록을 직접 들고 있어야 다음/이전·바꾸기 순서 제어가 쉽다.
    """

    def __init__(self, editor: "MarkdownEditor", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._matches: list[tuple[int, int]] = []
        self._current: int = -1
        # 문서 편집 시 정수 오프셋 매치가 스테일 — dirty 표시 후 다음 조작
        # 진입 시 재수집한다 (스테일 오프셋으로 엉뚱한 구간을 치환하는 결함 방지).
        self._matches_dirty = False
        self._editor.textChanged.connect(self._mark_matches_dirty)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("찾기")
        lay.addWidget(self._search_edit, 1)

        self._prev_btn = QPushButton("↑")
        self._prev_btn.setFixedWidth(24)
        self._prev_btn.setToolTip("이전 (Shift+Enter)")
        lay.addWidget(self._prev_btn)

        self._next_btn = QPushButton("↓")
        self._next_btn.setFixedWidth(24)
        self._next_btn.setToolTip("다음 (Enter)")
        lay.addWidget(self._next_btn)

        self._case_btn = QPushButton("Aa")
        self._case_btn.setCheckable(True)
        self._case_btn.setFixedWidth(28)
        self._case_btn.setToolTip("대소문자 구분")
        lay.addWidget(self._case_btn)

        self._count_label = QLabel("0/0")
        self._count_label.setStyleSheet("color: #888;")
        self._count_label.setFixedWidth(56)
        lay.addWidget(self._count_label)

        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("바꾸기")
        lay.addWidget(self._replace_edit, 1)

        self._replace_btn = QPushButton("바꾸기")
        lay.addWidget(self._replace_btn)

        self._replace_all_btn = QPushButton("모두 바꾸기")
        lay.addWidget(self._replace_all_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFlat(True)
        self._close_btn.setFixedWidth(20)
        self._close_btn.setToolTip("닫기 (Esc)")
        lay.addWidget(self._close_btn)

        self.setStyleSheet(
            "SearchBar { background-color: #252540; }"
            "QLineEdit { background-color: #1e1e32; color: #ccc; "
            "border: 1px solid #3a3a5c; }",
        )

        self._search_edit.textChanged.connect(lambda _t: self._perform_search())
        self._case_btn.toggled.connect(lambda _c: self._perform_search())
        self._next_btn.clicked.connect(self.search_next)
        self._prev_btn.clicked.connect(self.search_prev)
        self._replace_btn.clicked.connect(self.replace_current)
        self._replace_all_btn.clicked.connect(self.replace_all)
        self._close_btn.clicked.connect(self.close_bar)

        self._search_edit.installEventFilter(self)
        self._replace_edit.installEventFilter(self)

        self.hide()

    # --- 표시/숨김 ---

    def open(self, prefill: str = "") -> None:
        """바를 열고 검색창에 포커스한다. prefill이 있으면 검색어로 채운다.

        `setText`가 실제로 값을 바꾸면 `textChanged` → `_perform_search`가 이미
        원래 커서 위치를 앵커로 실행되므로, 그 경우 재호출하지 않는다(재호출하면
        직전 호출이 옮겨 둔 커서를 앵커로 다시 검색해 한 칸 더 건너뛰는 버그가 된다).
        값이 그대로면(빈 prefill 포함, 재오픈 등) 여기서 명시적으로 1회 실행한다.
        """
        if " " in prefill:
            prefill = ""  # 여러 줄 선택(U+2029 문단 구분자) — 프리필 생략
        self.show()
        changed = bool(prefill) and self._search_edit.text() != prefill
        if changed:
            self._search_edit.setText(prefill)
        self._search_edit.selectAll()
        self._search_edit.setFocus()
        if not changed:
            self._perform_search()

    def close_bar(self) -> None:
        """바를 숨기고 하이라이트를 지운 뒤 에디터로 포커스를 돌려준다.

        이미 숨어 있으면 아무것도 하지 않는다 — show_body 등 경유 호출이
        포커스를 훔치지 않게 (리뷰 지적 3).
        """
        if self.isHidden():
            return
        self.hide()
        self._matches = []
        self._current = -1
        self._editor.setExtraSelections([])
        self._editor.setFocus()

    # --- Esc/Enter/Shift+Enter/Up/Down 배선 (검색·바꾸기 입력창 공용) ---

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if event.type() == QEvent.Type.KeyPress and obj in (
            self._search_edit,
            self._replace_edit,
        ):
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Escape:
                self.close_bar()
                return True
            if key == Qt.Key.Key_Up or (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and mods & Qt.KeyboardModifier.ShiftModifier
            ):
                self.search_prev()
                return True
            if key == Qt.Key.Key_Down or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.search_next()
                return True
        return super().eventFilter(obj, event)

    # --- 검색 ---

    def _collect_matches(self) -> list[tuple[int, int]]:
        term = self._search_edit.text()
        if term == "":
            return []
        text = self._editor.toPlainText()
        case_sensitive = self._case_btn.isChecked()
        haystack = text if case_sensitive else text.lower()
        needle = term if case_sensitive else term.lower()
        step = len(needle)
        matches: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = haystack.find(needle, start)
            if idx == -1:
                break
            matches.append((idx, idx + step))
            start = idx + step
        return matches

    def _nearest_match_index(self, pos: int) -> int:
        for i, (start, _end) in enumerate(self._matches):
            if start >= pos:
                return i
        return 0

    def _mark_matches_dirty(self) -> None:
        self._matches_dirty = True

    def _ensure_fresh_matches(self) -> bool:
        """편집으로 스테일된 매치를 재수집한다. 재수집했으면 True."""
        if not self._matches_dirty:
            return False
        self._matches_dirty = False
        anchor = self._editor.textCursor().selectionStart()
        self._matches = self._collect_matches()
        self._current = self._nearest_match_index(anchor) if self._matches else -1
        return True

    def _perform_search(self) -> None:
        # 앵커는 선택 "시작" — 선택 끝을 쓰면 프리필된 그 단어를 건너뛰고
        # 다음/첫 일치로 튄다 (리뷰 지적 2).
        anchor = self._editor.textCursor().selectionStart()
        self._matches = self._collect_matches()
        self._matches_dirty = False
        if not self._matches:
            self._current = -1
            self._update_highlights()
            self._update_count_label()
            return
        self._current = self._nearest_match_index(anchor)
        self._select_current()

    def _select_current(self) -> None:
        start, end = self._matches[self._current]
        cursor = self._editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()
        self._update_highlights()
        self._update_count_label()

    def search_next(self) -> None:
        refreshed = self._ensure_fresh_matches()
        if not self._matches:
            return
        if not refreshed:
            # 재수집 직후에는 커서 기준 최근접 일치가 이미 current — 건너뛰지 않는다
            self._current = (self._current + 1) % len(self._matches)
        self._select_current()

    def search_prev(self) -> None:
        refreshed = self._ensure_fresh_matches()
        if not self._matches:
            return
        if not refreshed:
            self._current = (self._current - 1) % len(self._matches)
        self._select_current()

    def _update_highlights(self) -> None:
        selections = []
        for i, (start, end) in enumerate(self._matches):
            cursor = QTextCursor(self._editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(_SEARCH_CURRENT_BG if i == self._current else _SEARCH_MATCH_BG)
            selection = QTextEdit.ExtraSelection()
            selection.format = fmt
            selection.cursor = cursor
            selections.append(selection)
        self._editor.setExtraSelections(selections)

    def _update_count_label(self) -> None:
        total = len(self._matches)
        current = self._current + 1 if self._current >= 0 else 0
        self._count_label.setText(f"{current}/{total}")

    # --- 바꾸기 ---

    def replace_current(self) -> None:
        """현재 일치 1건을 치환하고 다음 일치로 이동한다."""
        self._ensure_fresh_matches()
        if not self._matches or self._current < 0:
            return
        start, end = self._matches[self._current]
        replacement = self._replace_edit.text()
        cursor = QTextCursor(self._editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        new_pos = start + len(replacement)

        self._matches = self._collect_matches()
        self._matches_dirty = False
        if self._matches:
            self._current = self._nearest_match_index(new_pos)
            self._select_current()
        else:
            self._current = -1
            result_cursor = self._editor.textCursor()
            result_cursor.setPosition(min(new_pos, len(self._editor.toPlainText())))
            self._editor.setTextCursor(result_cursor)
            self._update_highlights()
            self._update_count_label()

    def replace_all(self) -> None:
        """전체 일치를 1 undo 단위로 치환하고 치환 건수를 일치 수 라벨에 표시한다."""
        self._ensure_fresh_matches()
        if not self._matches:
            return
        count = len(self._matches)
        replacement = self._replace_edit.text()
        edit_cursor = self._editor.textCursor()
        edit_cursor.beginEditBlock()
        for start, end in reversed(self._matches):
            cursor = QTextCursor(self._editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        edit_cursor.endEditBlock()

        self._matches = self._collect_matches()
        self._current = -1
        self._update_highlights()
        self._count_label.setText(f"{count}건 바꿈")


class MarkdownToolbar(QWidget):
    """서식 툴바 — `MarkdownEditor` 공개 API에 배선된 버튼 행.

    `H1 H2 H3 │ B I S │ <> {} │ • 1. ☑ │ " 🔗 │ ☰ 👁` — ☰(TOC 토글)·👁(프리뷰)는
    문서를 건드리지 않고 각각 `toc_toggled`/`preview_toggled` 시그널만 방출한다
    (TOC 패널 표시/숨김·프리뷰 자체는 `SectionContentPanel` 소관).
    """

    preview_toggled = Signal(bool)
    toc_toggled = Signal(bool)

    _BUTTON_WIDTH = 30

    def __init__(self, editor: MarkdownEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._edit_buttons: list[QPushButton] = []  # 프리뷰 중 비활성화 대상

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)

        self._add_button(lay, "H1", "제목 1 (Ctrl+1)", lambda: self._apply_heading(1))
        self._add_button(lay, "H2", "제목 2 (Ctrl+2)", lambda: self._apply_heading(2))
        self._add_button(lay, "H3", "제목 3 (Ctrl+3)", lambda: self._apply_heading(3))
        self._add_separator(lay)
        self._add_button(lay, "B", "굵게 (Ctrl+B)", lambda: self._apply_wrap("**", "**"))
        self._add_button(lay, "I", "기울임 (Ctrl+I)", lambda: self._apply_wrap("*", "*"))
        self._add_button(lay, "S", "취소선 (Ctrl+Shift+X)", lambda: self._apply_wrap("~~", "~~"))
        self._add_separator(lay)
        self._add_button(lay, "<>", "인라인 코드 (Ctrl+`)", self._apply_inline_code)
        self._add_button(lay, "{}", "코드 블록 (Ctrl+Shift+C)", self._apply_code_block)
        self._add_separator(lay)
        self._add_button(lay, "•", "불릿 리스트 (Ctrl+Shift+8)", lambda: self._apply_marker("- "))
        self._add_button(lay, "1.", "번호 리스트 (Ctrl+Shift+7)", lambda: self._apply_marker("1. "))
        self._add_button(lay, "☑", "체크리스트 (Ctrl+Shift+9)", lambda: self._apply_marker("- [ ] "))
        self._add_separator(lay)
        self._add_button(lay, "\"", "인용 (Ctrl+Shift+.)", lambda: self._apply_marker("> "))
        self._add_button(lay, "🔗", "링크 (Ctrl+K)", self._apply_link)
        self._add_separator(lay)
        self._btn_toc = self._add_button(
            lay, "☰", "목차 토글", self._on_toc_toggled, checkable=True,
        )
        self._edit_buttons.append(self._btn_toc)  # 프리뷰 중 비활성화 대상에 포함
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
            # checkable은 ☰(TOC)/👁(프리뷰) 전용 — 문서를 건드리지 않으므로
            # 호출부가 필요할 때만 개별적으로 _edit_buttons에 편입시킨다
            btn.toggled.connect(handler)
        else:
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

    def _apply_inline_code(self) -> None:
        self._editor.toggle_inline_code()
        self._editor.setFocus()

    def _apply_code_block(self) -> None:
        self._editor.toggle_code_block()
        self._editor.setFocus()

    def _apply_link(self) -> None:
        self._editor.insert_link()
        self._editor.setFocus()

    def _on_toc_toggled(self, checked: bool) -> None:
        self.toc_toggled.emit(checked)
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


_TOC_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_TOC_DEBOUNCE_MS = 300
_TOC_BLOCK_ROLE = Qt.ItemDataRole.UserRole


@dataclass(frozen=True)
class TocEntry:
    """TOC 항목 — 헤딩 레벨·텍스트·해당 블록 번호(점프용)."""

    level: int
    text: str
    block_number: int


class TocPanel(QWidget):
    """TOC 사이드바 — 문서의 ATX 헤딩을 읽기 전용으로 나열(왕복 파싱 아님).

    코드 펜스 내부의 `#` 줄은 `MarkdownHighlighter`가 이미 기록해 둔 블록
    상태(`userState() == _STATE_CODE_FENCE`)로 판별해 제외한다 — 별도 펜스
    추적 로직을 중복 구현하지 않는다.
    """

    def __init__(self, editor: "MarkdownEditor", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._entries: list[TocEntry] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            "QTreeWidget { background-color: #20203a; color: #ccc; border: none; }"
            "QTreeWidget::item { padding: 2px 4px; }",
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._tree)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_TOC_DEBOUNCE_MS)
        self._timer.timeout.connect(self._reparse)

        self._editor.textChanged.connect(self._schedule_reparse)
        self._reparse()

    # --- 파싱(읽기 전용) ---

    def _schedule_reparse(self) -> None:
        self._timer.start()

    def refresh(self) -> None:
        """디바운스를 우회해 즉시 재파싱한다 — 문서 갈아치우기(show_body) 등에 사용."""
        self._timer.stop()
        self._reparse()

    def _reparse(self) -> None:
        entries = self._extract_headings()
        if entries == self._entries:
            return  # 구조 불변 — 트리 재구성 생략(in-place 원칙)
        self._entries = entries
        self._rebuild_tree()

    def _extract_headings(self) -> list[TocEntry]:
        entries: list[TocEntry] = []
        block = self._editor.document().begin()
        while block.isValid():
            if block.userState() != MarkdownHighlighter._STATE_CODE_FENCE:
                m = _TOC_HEADING_RE.match(block.text())
                if m:
                    entries.append(
                        TocEntry(len(m.group(1)), m.group(2).strip(), block.blockNumber()),
                    )
            block = block.next()
        return entries

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for entry in self._entries:
            item = QTreeWidgetItem([entry.text])
            item.setData(0, _TOC_BLOCK_ROLE, entry.block_number)
            while stack and stack[-1][0] >= entry.level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)
            stack.append((entry.level, item))
        self._tree.expandAll()

    # --- 클릭 점프 ---

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        block_number = item.data(0, _TOC_BLOCK_ROLE)
        if block_number is None:
            return
        block = self._editor.document().findBlockByNumber(block_number)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._editor.setFocus()
