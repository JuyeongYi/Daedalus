"""마크다운 에디터 위젯 — 재-export 파사드 (WP-RF-3c).

구현은 ``daedalus/view/widgets/markdown/`` 패키지로 분해됐다(이동만, 동작 불변).
이 모듈은 분해 전 모듈의 속성(public + 소스·테스트가 임포트하는 언더스코어
이름 + 부수 임포트)을 그대로 제공하므로 기존 임포트가 무수정으로 동작한다.

예외: 제공자 전역 ``_FILES_ROOT_PROVIDER``/``_SKILL_FILES_ROOT_PROVIDER``는
재-export하지 않는다 — 재바인딩되는 가변 전역이라 여기로 복사하면 스냅샷이
스테일해진다. 등록/조회는 ``set_*_provider``/``get_*_root`` 함수로만 한다
(``providers.py``가 그 전역의 단일 진실).

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

# ── 분해 전 모듈의 부수 임포트 (파사드 완전성 — dir 기준 속성 집합 보존) ──
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

# ── 분해된 구현 재-export ──
from daedalus.view.widgets.markdown.syntax import (
    MARKDOWN_PALETTE,
    _BASE_FONT_FAMILY,
    _BASE_POINT_SIZE,
    _BOLD_STAR_RE,
    _BOLD_US_RE,
    _BULLET_LINE_RE,
    _CODE_FONT_FAMILY,
    _FENCE_CLOSE_RE,
    _FENCE_OPEN_RE,
    _HEADING_PREFIX_RE,
    _HEADING_RE,
    _HEADING_SIZE_MULTIPLIER,
    _HR_RE,
    _IMAGE_RE,
    _INLINE_CODE_RE,
    _ITALIC_STAR_RE,
    _ITALIC_US_RE,
    _LEADING_WS_RE,
    _LINK_RE,
    _MARKER_KIND,
    _OL_RE,
    _ORDERED_LINE_RE,
    _QUOTE_LINE_RE,
    _QUOTE_MARKER_RE,
    _QUOTE_RE,
    _STRIKE_RE,
    _TASK_CHECK_RE,
    _TASK_LINE_RE,
    _TASK_RE,
    _UL_RE,
    _detect_line_marker,
    _make_format,
)
from daedalus.view.widgets.markdown.highlighter import MarkdownHighlighter
from daedalus.view.widgets.markdown.providers import (
    _file_ref_token,
    _skill_file_ref_token,
    get_files_root,
    get_skill_files_root,
    set_files_root_provider,
    set_skill_files_root_provider,
)
from daedalus.view.widgets.markdown.slash import (
    SLASH_CATALOG,
    SlashItem,
    _SLASH_ITEM_ROLE,
    _SLASH_MAX_VISIBLE_ROWS,
    _SLASH_MENU_WIDTH,
    _SLASH_ROW_HEIGHT,
    _SlashMenu,
)
from daedalus.view.widgets.markdown.editor import (
    MarkdownEditor,
    _HEADING_DIGIT_KEYS,
    _HEADING_DIGIT_TEXT,
    _MARKER_SHORTCUT_KEYS,
    _MARKER_SHORTCUT_TEXT,
    _heading_digit_from_event,
    _line_marker_from_event,
)
from daedalus.view.widgets.markdown.search import (
    SearchBar,
    _SEARCH_CURRENT_BG,
    _SEARCH_MATCH_BG,
)
from daedalus.view.widgets.markdown.toolbar import MarkdownToolbar
from daedalus.view.widgets.markdown.toc import (
    TocEntry,
    TocPanel,
    _TOC_BLOCK_ROLE,
    _TOC_DEBOUNCE_MS,
    _TOC_HEADING_RE,
)

__all__ = [
    "MARKDOWN_PALETTE",
    "SLASH_CATALOG",
    "MarkdownEditor",
    "MarkdownHighlighter",
    "MarkdownToolbar",
    "SearchBar",
    "SlashItem",
    "TocEntry",
    "TocPanel",
    "get_files_root",
    "get_skill_files_root",
    "set_files_root_provider",
    "set_skill_files_root_provider",
]
