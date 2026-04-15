# daedalus/view/editors/component_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.view.editors.body_editor import (
    BreadcrumbNav,
    SectionContentPanel,
    SectionTree,
    VariablePopup,
    find_path,
)
from daedalus.view.editors.skill_editor import _FrontmatterPanel
from daedalus.view.editors.variable_loader import load_variables

_ComponentType = ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition

_LEFT_MIN_W = 120
_LEFT_CHILD_MIN_H = 80
_CENTER_MIN_W = 200
_RIGHT_MIN_W = 120
_RIGHT_CHILD_MIN_H = 60


class ComponentEditor(QWidget):
    """재사용 복합 에디터 — 좌(SectionTree+Frontmatter) | 중(Breadcrumb+Content) | 우(옵션)."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: _ComponentType,
        right_widgets: list[QWidget] | None = None,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn

        variables = load_variables()

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 좌측: SectionTree + FrontmatterPanel (수직 스플리터) ---
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setMinimumWidth(_LEFT_MIN_W)

        self._section_tree = SectionTree(component.sections)
        self._section_tree.setMinimumHeight(_LEFT_CHILD_MIN_H)
        self._section_tree.section_selected.connect(self._on_tree_selected)
        self._section_tree.structure_changed.connect(self._on_structure_changed)
        self._section_tree.add_root_requested.connect(
            lambda: self._on_breadcrumb_add(None, 0)
        )
        left_splitter.addWidget(self._section_tree)

        self._fm = _FrontmatterPanel(component)
        self._fm.setMinimumHeight(_LEFT_CHILD_MIN_H)
        self._fm.changed.connect(self._on_model_changed)
        left_splitter.addWidget(self._fm)

        root_splitter.addWidget(left_splitter)

        # --- 중앙: BreadcrumbNav + SectionContentPanel ---
        center = QWidget()
        center.setMinimumWidth(_CENTER_MIN_W)
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)

        self._breadcrumb = BreadcrumbNav(component.sections)
        self._breadcrumb.section_selected.connect(self._on_breadcrumb_selected)
        self._breadcrumb.section_add_requested.connect(self._on_breadcrumb_add)
        center_lay.addWidget(self._breadcrumb)

        self._content_panel = SectionContentPanel()
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._content_panel.add_child_requested.connect(self._on_add_child)
        center_lay.addWidget(self._content_panel, 1)

        root_splitter.addWidget(center)

        # --- 우측: right_widgets (수직 스플리터, 있을 때만) ---
        rw = right_widgets or []
        if rw:
            right_splitter = QSplitter(Qt.Orientation.Vertical)
            right_splitter.setMinimumWidth(_RIGHT_MIN_W)
            for w in rw:
                w.setMinimumHeight(_RIGHT_CHILD_MIN_H)
                right_splitter.addWidget(w)
            root_splitter.addWidget(right_splitter)

        # stretch: 좌0, 중1, 우0
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)
        if rw:
            root_splitter.setStretchFactor(2, 0)

        root_lay.addWidget(root_splitter)

        # Variable popup
        self._var_popup = VariablePopup(variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        # Initial selection
        if component.sections:
            self._select_section(component.sections[0])

    # --- 섹션 네비게이션 ---

    def _select_section(self, section: Section) -> None:
        path = find_path(section, self._component.sections)
        if path is None:
            return
        path_titles = [s.title for s in path]
        self._section_tree.select_section(section)
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path_titles)

    def _on_tree_selected(self, section: Section, path: list[str]) -> None:
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path)

    def _on_breadcrumb_selected(self, section: Section, path: list[str]) -> None:
        self._section_tree.select_section(section)
        self._content_panel.show_section(section, path)

    def _on_breadcrumb_add(self, parent: Section | None, depth: int) -> None:
        siblings = self._component.sections if parent is None else parent.children
        existing_names = {s.title for s in siblings}
        while True:
            name, ok = QInputDialog.getText(self, "섹션 추가", "섹션 이름:")
            if not ok or not name.strip():
                return
            name = name.strip()
            if name in existing_names:
                QMessageBox.warning(self, "이름 중복", f"'{name}' 섹션이 이미 존재합니다.")
                continue
            break
        new = Section(title=name)
        siblings.append(new)
        self._on_structure_changed()
        self._select_section(new)

    def _on_add_child(self) -> None:
        if self._content_panel._section is None:
            return
        self._on_breadcrumb_add(self._content_panel._section, 0)

    def _on_structure_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
        self._on_model_changed()

    def _on_content_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
        self._on_model_changed()

    def _on_variable_insert(self) -> None:
        if self._var_popup.isVisible():
            self._var_popup.hide()
            return
        from PyQt6.QtCore import QPoint
        btn = self._content_panel._btn_variable
        pos = btn.mapTo(self._content_panel, QPoint(0, btn.height()))
        self._var_popup.move(pos)
        self._var_popup.show()
        self._var_popup.raise_()

    def _on_model_changed(self) -> None:
        self.changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    def show_contract_section(self, section: Section) -> None:
        """잠금 계약 섹션 표시 — 타이틀 잠금, 내용만 편집 가능."""
        self._content_panel.show_section(section, [section.title], title_locked=True)
