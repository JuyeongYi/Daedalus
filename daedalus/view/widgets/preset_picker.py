# daedalus/view/widgets/preset_picker.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class PresetPicker(QWidget):
    """이름 목록 체크리스트. 선택한 이름을 반환.

    이름 출처는 두 가지:
      - scan_path: 폴더 스캔(.json 파일 stem) — 정적 프리셋 폴더용 (기존 동작).
      - names_provider: 호출 시점 이름 목록을 반환하는 콜백 — 동적 라이브러리용.
    names_provider가 주어지면 그 결과를 우선 사용한다.
    """

    selection_changed = Signal()

    def __init__(
        self,
        scan_path: str = "",
        label: str = "",
        names_provider: Callable[[], list[str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scan_path = scan_path
        self._names_provider = names_provider
        self._checkboxes: dict[str, QCheckBox] = {}
        # provider 도입 전 set_selected가 호출돼도 선택이 유실되지 않도록 보존.
        self._pending_selected: list[str] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        if label:
            lay.addWidget(QLabel(label))

        self._items_layout = QVBoxLayout()
        lay.addLayout(self._items_layout)

        self._scan()

    def _available_names(self) -> list[str]:
        """현재 표시할 이름 목록 — provider 우선, 없으면 폴더 스캔."""
        if self._names_provider is not None:
            return list(self._names_provider())
        if not self._scan_path or not os.path.isdir(self._scan_path):
            return []
        return [
            Path(name).stem
            for name in sorted(os.listdir(self._scan_path))
            if name.endswith(".json")
        ]

    def _scan(self) -> None:
        # 선택 상태 보존 후 재구성
        prev_selected = set(self.get_selected()) | set(self._pending_selected)
        self._checkboxes.clear()
        while self._items_layout.count():
            child = self._items_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        for name in self._available_names():
            cb = QCheckBox(name)
            cb.setChecked(name in prev_selected)
            cb.toggled.connect(lambda _checked: self.selection_changed.emit())
            self._checkboxes[name] = cb
            self._items_layout.addWidget(cb)
        # 여전히 표시되지 못한(이름 미존재) 선택은 pending으로 유지
        self._pending_selected = [
            n for n in prev_selected if n not in self._checkboxes
        ]

    def refresh(self) -> None:
        """이름 목록을 다시 읽어 체크리스트를 재구성한다 (provider 갱신 후 호출)."""
        self._scan()

    def get_available(self) -> list[str]:
        return list(self._checkboxes.keys())

    def get_selected(self) -> list[str]:
        live = [name for name, cb in self._checkboxes.items() if cb.isChecked()]
        # 표시되지 못한 선택(라이브러리에 아직 없는 이름)도 보존해 데이터 손실 방지.
        return live + list(self._pending_selected)

    def set_selected(self, names: list[str]) -> None:
        wanted = set(names)
        for name, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(name in wanted)
            cb.blockSignals(False)
        self._pending_selected = [n for n in names if n not in self._checkboxes]
        self.selection_changed.emit()


# 동적 훅 이름 제공자 — app.py가 프로젝트 로드 시 설정한다. None이면 폴더 스캔으로 폴백.
# (위젯 팩토리 시그니처를 ()로 유지하기 위한 모듈 수준 주입 지점.)
_HOOK_NAME_PROVIDER: Callable[[], list[str]] | None = None


def set_hook_name_provider(provider: Callable[[], list[str]] | None) -> None:
    """HookPresetPicker가 표시할 훅 이름 목록 제공자를 등록한다."""
    global _HOOK_NAME_PROVIDER
    _HOOK_NAME_PROVIDER = provider


def get_hook_names() -> list[str]:
    """등록된 제공자에서 현재 hook_library 이름 목록을 가져온다 (없으면 빈 리스트)."""
    if _HOOK_NAME_PROVIDER is not None:
        return list(_HOOK_NAME_PROVIDER())
    return []


class HookPresetPicker(PresetPicker):
    """Hooks 피커 — 등록된 hook_library 이름을 동적 표시(폴백: .claude/hooks 스캔)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            scan_path=".claude/hooks",
            label="Hooks",
            names_provider=self._provider,
            parent=parent,
        )

    @staticmethod
    def _provider() -> list[str]:
        # 동적 라이브러리 제공자가 등록되어 있으면 그것을 쓰고,
        # 없으면 정적 폴더(.claude/hooks/*.json) 스캔으로 폴백한다.
        if _HOOK_NAME_PROVIDER is not None:
            return list(_HOOK_NAME_PROVIDER())
        scan = ".claude/hooks"
        if os.path.isdir(scan):
            return [
                Path(n).stem for n in sorted(os.listdir(scan))
                if n.endswith(".json")
            ]
        return []


class McpPresetPicker(PresetPicker):
    """MCP 서버 프리셋 피커 — .claude/mcp/ 스캔."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(scan_path=".claude/mcp", label="MCP Servers", parent=parent)
