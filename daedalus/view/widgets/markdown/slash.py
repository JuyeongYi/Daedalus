"""`/` 슬래시 메뉴 — 항목 카탈로그 + 에디터 오버레이 위젯 (WP-MD2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

if TYPE_CHECKING:  # pragma: no cover - 타입 힌트 전용 (런타임 순환 임포트 방지)
    from daedalus.view.widgets.markdown.editor import MarkdownEditor


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
