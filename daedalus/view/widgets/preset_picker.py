# daedalus/view/widgets/preset_picker.py
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class PresetPicker(QWidget):
    """폴더 스캔 → .json 파일 체크리스트. 선택한 파일 이름(확장자 제외)을 반환."""

    selection_changed = pyqtSignal()

    def __init__(
        self,
        scan_path: str = "",
        label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scan_path = scan_path
        self._checkboxes: dict[str, QCheckBox] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        if label:
            lay.addWidget(QLabel(label))

        self._items_layout = QVBoxLayout()
        lay.addLayout(self._items_layout)

        self._scan()

    def _scan(self) -> None:
        self._checkboxes.clear()
        while self._items_layout.count():
            child = self._items_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        if not self._scan_path or not os.path.isdir(self._scan_path):
            return

        for name in sorted(os.listdir(self._scan_path)):
            if not name.endswith(".json"):
                continue
            stem = Path(name).stem
            cb = QCheckBox(stem)
            cb.toggled.connect(lambda _checked: self.selection_changed.emit())
            self._checkboxes[stem] = cb
            self._items_layout.addWidget(cb)

    def get_available(self) -> list[str]:
        return list(self._checkboxes.keys())

    def get_selected(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected(self, names: list[str]) -> None:
        for name, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(name in names)
            cb.blockSignals(False)
        self.selection_changed.emit()


class HookPresetPicker(PresetPicker):
    """Hooks 프리셋 피커 — .claude/hooks/ 스캔."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(scan_path=".claude/hooks", label="Hooks", parent=parent)


class McpPresetPicker(PresetPicker):
    """MCP 서버 프리셋 피커 — .claude/mcp/ 스캔."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(scan_path=".claude/mcp", label="MCP Servers", parent=parent)
