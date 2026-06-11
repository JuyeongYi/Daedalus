# daedalus/view/editors/hook_editor.py
"""훅 라이브러리(HookLibrary) 편집기 — hook_library의 HookDef 목록 + 폼.

진입점: 메뉴 "훅 라이브러리..." → HookLibraryDialog.
편집 결과는 모델(project.hook_library)에 직접 기록 + notify
(undo 커맨드화 범위 외 — delegation_editor 폼 정책과 동일).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.hook import HookDef, HookEvent, TOOL_MATCH_EVENTS
from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS, preset_copy
from daedalus.model.project import PluginProject


class _HookForm(QWidget):
    """선택된 HookDef 1건의 편집 폼."""

    def __init__(
        self,
        on_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._hook: HookDef | None = None
        self._on_changed = on_changed
        self._loading = False

        form = QFormLayout(self)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("식별자 (config.hooks 키가 참조)")
        form.addRow("이름:", self._name_edit)

        self._desc_edit = QLineEdit()
        form.addRow("설명:", self._desc_edit)

        self._event_combo = QComboBox()
        for ev in HookEvent:
            self._event_combo.addItem(ev.value, ev)
        form.addRow("이벤트:", self._event_combo)

        self._matcher_edit = QLineEdit()
        self._matcher_edit.setPlaceholderText("도구명 패턴 (Pre/PostToolUse 전용, 예: Edit|Write)")
        self._matcher_label = QLabel("matcher:")
        form.addRow(self._matcher_label, self._matcher_edit)

        self._command_edit = QTextEdit()
        self._command_edit.setMaximumHeight(80)
        self._command_edit.setPlaceholderText("실행 커맨드")
        form.addRow("커맨드:", self._command_edit)

        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(0, 3600)
        self._timeout_spin.setSpecialValueText("(없음)")  # 0 = None
        self._timeout_spin.setSuffix(" s")
        form.addRow("타임아웃:", self._timeout_spin)

        self.setEnabled(False)

        self._name_edit.textChanged.connect(self._on_edit)
        self._desc_edit.textChanged.connect(self._on_edit)
        self._event_combo.currentIndexChanged.connect(self._on_event_changed)
        self._matcher_edit.textChanged.connect(self._on_edit)
        self._command_edit.textChanged.connect(self._on_edit)
        self._timeout_spin.valueChanged.connect(self._on_edit)

    def set_hook(self, hook: HookDef | None) -> None:
        self._hook = hook
        self.setEnabled(hook is not None)
        if hook is None:
            return
        self._loading = True
        self._name_edit.setText(hook.name)
        self._desc_edit.setText(hook.description)
        for i in range(self._event_combo.count()):
            if self._event_combo.itemData(i) is hook.event:
                self._event_combo.setCurrentIndex(i)
                break
        self._matcher_edit.setText(hook.matcher)
        self._command_edit.setPlainText(hook.command)
        self._timeout_spin.setValue(hook.timeout if hook.timeout is not None else 0)
        self._loading = False
        self._update_matcher_enabled()

    def _current_event(self) -> HookEvent:
        return self._event_combo.currentData()

    def _update_matcher_enabled(self) -> None:
        is_tool = self._current_event() in TOOL_MATCH_EVENTS
        self._matcher_edit.setEnabled(is_tool)
        self._matcher_label.setEnabled(is_tool)

    def _on_event_changed(self) -> None:
        self._update_matcher_enabled()
        self._on_edit()

    def _on_edit(self) -> None:
        if self._loading or self._hook is None:
            return
        self._hook.name = self._name_edit.text().strip()
        self._hook.description = self._desc_edit.text()
        self._hook.event = self._current_event()
        self._hook.matcher = self._matcher_edit.text().strip()
        self._hook.command = self._command_edit.toPlainText()
        tv = self._timeout_spin.value()
        self._hook.timeout = None if tv == 0 else tv
        self._on_changed()


class HookLibraryDialog(QDialog):
    """프로젝트 hook_library 편집 다이얼로그.

    좌: 훅 목록 + 추가/삭제/프리셋에서 추가. 우: 선택 훅 폼.
    모델 직접 기록 + on_notify_fn 콜백.
    """

    def __init__(
        self,
        project: PluginProject,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._on_notify_fn = on_notify_fn

        self.setWindowTitle("훅 라이브러리")
        self.resize(640, 480)

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # 좌측: 목록 + 버튼
        left = QVBoxLayout()
        left.addWidget(QLabel("훅 라이브러리:"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 추가")
        add_btn.clicked.connect(self._add_hook)
        del_btn = QPushButton("✕ 삭제")
        del_btn.clicked.connect(self._delete_hook)
        preset_btn = QPushButton("프리셋에서 추가…")
        preset_btn.clicked.connect(self._add_from_preset)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(preset_btn)
        left.addLayout(btn_row)
        body.addLayout(left, 1)

        # 우측: 폼
        self._form = _HookForm(on_changed=self._on_form_changed)
        body.addWidget(self._form, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

        self._reload_list()

    # ── 목록 ──

    def _reload_list(self, select_index: int | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for hook in self._project.hook_library:
            label = f"{hook.name or '(이름 없음)'}  ·  {hook.event.value}"
            item = QListWidgetItem(label)
            self._list.addItem(item)
        self._list.blockSignals(False)
        if select_index is not None and 0 <= select_index < self._list.count():
            self._list.setCurrentRow(select_index)
        elif self._list.count() and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)
        else:
            self._on_row_changed(self._list.currentRow())

    def _current_hook(self) -> HookDef | None:
        row = self._list.currentRow()
        lib = self._project.hook_library
        if 0 <= row < len(lib):
            return lib[row]
        return None

    def _on_row_changed(self, row: int) -> None:
        self._form.set_hook(self._current_hook())

    # ── 편집 동작 ──

    def _add_hook(self) -> None:
        hook = HookDef(name="new-hook", description="", event=HookEvent.PRE_TOOL_USE)
        self._project.hook_library.append(hook)
        self._reload_list(select_index=len(self._project.hook_library) - 1)
        self._notify()

    def _delete_hook(self) -> None:
        row = self._list.currentRow()
        lib = self._project.hook_library
        if 0 <= row < len(lib):
            lib.pop(row)
            self._reload_list(select_index=min(row, len(lib) - 1) if lib else None)
            self._notify()

    def _add_from_preset(self) -> None:
        names = [p.name for p in BUILTIN_HOOK_PRESETS]
        name, ok = QInputDialog.getItem(
            self, "프리셋에서 추가", "훅 프리셋:", names, 0, False
        )
        if not ok or not name:
            return
        preset = next((p for p in BUILTIN_HOOK_PRESETS if p.name == name), None)
        if preset is None:
            return
        self._project.hook_library.append(preset_copy(preset))
        self._reload_list(select_index=len(self._project.hook_library) - 1)
        self._notify()

    def _on_form_changed(self) -> None:
        # 폼이 이름/이벤트를 바꾸면 목록 라벨 갱신 (선택 유지)
        self._refresh_current_label()
        self._notify()

    def _refresh_current_label(self) -> None:
        hook = self._current_hook()
        item = self._list.currentItem()
        if hook is not None and item is not None:
            item.setText(f"{hook.name or '(이름 없음)'}  ·  {hook.event.value}")

    def _notify(self) -> None:
        if self._on_notify_fn is not None:
            self._on_notify_fn()
