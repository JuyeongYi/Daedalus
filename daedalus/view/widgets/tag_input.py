# daedalus/view/widgets/tag_input.py
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _TagChip(QWidget):
    """개별 태그 칩 — 이름 + x 버튼."""

    remove_requested = pyqtSignal(str)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        lay.addWidget(QLabel(name))
        btn = QPushButton("x")
        btn.setFixedSize(16, 16)
        btn.clicked.connect(lambda: self.remove_requested.emit(self._name))
        lay.addWidget(btn)

    @property
    def name(self) -> str:
        return self._name


class TagInput(QWidget):
    """태그 입력 위젯 — list[str] 편집. Enter로 추가, x로 제거."""

    tags_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._input = QLineEdit()
        self._input.setPlaceholderText("입력 후 Enter")
        self._input.returnPressed.connect(self._on_enter)
        lay.addWidget(self._input)

        self._chips_widget = QWidget()
        self._chips_layout = QVBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(2)
        self._chips_layout.addStretch()
        lay.addWidget(self._chips_widget)

    def get_tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild()

    def add_tag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._tags:
            return
        self._tags.append(tag)
        self._rebuild()
        self.tags_changed.emit()

    def remove_tag(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.tags_changed.emit()

    def _on_enter(self) -> None:
        text = self._input.text().strip()
        if text:
            self.add_tag(text)
            self._input.clear()

    def _rebuild(self) -> None:
        while self._chips_layout.count() > 1:
            child = self._chips_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag)
            chip.remove_requested.connect(self.remove_tag)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)
