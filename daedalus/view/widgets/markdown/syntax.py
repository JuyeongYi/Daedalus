"""마크다운 문법 상수 — 팔레트·폰트·정규식의 **단일 진실** (WP-RF-3c).

하이라이터·에디터·TOC가 같은 규칙을 봐야 하므로 정규식을 여기 한 곳에 모은다
(복제 금지 — 두 곳이 어긋나면 화면에 보이는 구조와 편집이 집는 구조가 달라진다).
``daedalus/model/outline.py``의 펜스 규칙은 이 모듈의 ``_FENCE_OPEN_RE``/
``_FENCE_CLOSE_RE``를 미러한 것이다.

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QTextCharFormat

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
