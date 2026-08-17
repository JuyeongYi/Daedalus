"""TOC 사이드바 (WP-MD3) — 문서의 ATX 헤딩을 읽기 전용으로 나열."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from daedalus.view.widgets.markdown.highlighter import MarkdownHighlighter

if TYPE_CHECKING:  # pragma: no cover - 타입 힌트 전용
    from daedalus.view.widgets.markdown.editor import MarkdownEditor

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
