from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from daedalus.view.commands.base import CommandStack

_HIGHLIGHT_BG = QColor("#2a2a4a")
_TEXT_COLOR = QColor("#ccc")
_DIM_COLOR = QColor("#555")


class HistoryPanel(QWidget):
    """커맨드 이력 표시 + 클릭으로 goto."""

    def __init__(self, command_stack: CommandStack, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = command_stack
        self._stack.add_listener(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def _rebuild(self) -> None:
        self._list.clear()
        current = self._stack.current_index
        for i, cmd in enumerate(self._stack.history):
            item = QListWidgetItem(f"  {cmd.description}")
            if i == current:
                item.setBackground(_HIGHLIGHT_BG)
                item.setForeground(_TEXT_COLOR)
            else:
                item.setForeground(_DIM_COLOR)
            self._list.addItem(item)
        if self._stack.history:
            self._list.scrollToBottom()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        if row != self._stack.current_index:
            self._stack.goto(row)
