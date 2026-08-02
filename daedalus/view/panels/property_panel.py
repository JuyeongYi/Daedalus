from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
from daedalus.view.commands.state_commands import RenameStateCmd
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.widgets.tag_input import TagInput, get_blackboard_candidates


class PropertyPanel(QWidget):
    """선택한 노드/전이의 속성을 표시/편집."""

    def __init__(self, project_vm: ProjectViewModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_vm = project_vm

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._title = QLabel("선택 없음")
        self._title.setStyleSheet("color: #888; font-size: 10px;")
        self._layout.addWidget(self._title)

        self._form_widget = QWidget()
        self._form = QFormLayout(self._form_widget)
        self._layout.addWidget(self._form_widget)
        self._layout.addStretch()

    def show_state(self, state_vm: StateViewModel) -> None:
        self._clear_form()
        self._title.setText("PROPERTIES — SimpleState")

        name_edit = QLineEdit(state_vm.model.name)
        name_edit.editingFinished.connect(
            lambda: self._rename_state(state_vm, name_edit.text())
        )
        self._form.addRow("Name", name_edit)
        self._form.addRow("on_entry", QLabel(f"{len(state_vm.model.on_entry)} action(s)"))
        self._form.addRow("on_exit", QLabel(f"{len(state_vm.model.on_exit)} action(s)"))
        self._form.addRow("x", QLabel(f"{state_vm.x:.0f}"))
        self._form.addRow("y", QLabel(f"{state_vm.y:.0f}"))

        # WP-BB Part C-1 — 상태 접근 선언(reads/writes). 자동완성 후보는 프로젝트
        # 블랙보드의 "클래스"/"클래스.필드" 전체(호출 시점 스냅샷).
        reads_input = TagInput()
        reads_input.set_candidates(get_blackboard_candidates())
        reads_input.set_tags(state_vm.model.reads)
        reads_input.tags_changed.connect(
            lambda: self._save_access(state_vm, "reads", reads_input)
        )
        self._form.addRow("reads", reads_input)

        writes_input = TagInput()
        writes_input.set_candidates(get_blackboard_candidates())
        writes_input.set_tags(state_vm.model.writes)
        writes_input.tags_changed.connect(
            lambda: self._save_access(state_vm, "writes", writes_input)
        )
        self._form.addRow("writes", writes_input)

    def show_transition(self, transition_vm: TransitionViewModel) -> None:
        self._clear_form()
        self._title.setText("PROPERTIES — Transition")
        self._form.addRow("Source", QLabel(transition_vm.source_vm.model.name))
        self._form.addRow("Target", QLabel(transition_vm.target_vm.model.name))
        self._form.addRow("Type", QLabel(transition_vm.model.type.value))

    def set_project_vm(self, project_vm: ProjectViewModel) -> None:
        """활성 탭이 바뀔 때 커맨드 실행 대상 VM을 교체."""
        self._project_vm = project_vm

    def clear(self) -> None:
        self._clear_form()
        self._title.setText("선택 없음")

    def _clear_form(self) -> None:
        while self._form.rowCount() > 0:
            self._form.removeRow(0)

    def _rename_state(self, state_vm: StateViewModel, new_name: str) -> None:
        old_name = state_vm.model.name
        if new_name and new_name != old_name:
            self._project_vm.execute(RenameStateCmd(state_vm, old_name, new_name))

    def _save_access(self, state_vm: StateViewModel, attr: str, widget: TagInput) -> None:
        """reads/writes TagInput write-back — 커맨드화 범위 밖(모델 직접 기록,
        블랙보드/훅 shelf 폼과 동일 정책) + notify로 뱃지·검증 갱신을 알린다."""
        setattr(state_vm.model, attr, widget.get_tags())
        self._project_vm.notify()
