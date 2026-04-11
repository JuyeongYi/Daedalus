from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTreeView, QVBoxLayout, QWidget

from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject

_COLOR_PROCEDURAL = QColor("#88cc88")
_COLOR_DECLARATIVE = QColor("#cccc88")
_COLOR_AGENT = QColor("#cc8888")
_COLOR_FOLDER = QColor("#aab8ff")
_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1


class ProjectTreePanel(QWidget):
    """프로젝트 트리뷰 + 스킬 타입 필터 토글."""

    component_double_clicked = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._show_procedural = True
        self._show_declarative = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(4, 4, 4, 4)
        self._btn_proc = QPushButton("Procedural")
        self._btn_proc.setCheckable(True)
        self._btn_proc.setChecked(True)
        self._btn_proc.clicked.connect(self._on_filter_changed)
        self._btn_decl = QPushButton("Declarative")
        self._btn_decl.setCheckable(True)
        self._btn_decl.setChecked(True)
        self._btn_decl.clicked.connect(self._on_filter_changed)
        filter_bar.addWidget(self._btn_proc)
        filter_bar.addWidget(self._btn_decl)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._model = QStandardItemModel()
        self._tree.setModel(self._model)
        layout.addWidget(self._tree)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def _rebuild(self) -> None:
        self._model.clear()
        if not self._project:
            return
        root = self._model.invisibleRootItem()

        proj_item = QStandardItem(self._project.name)
        proj_item.setForeground(_COLOR_FOLDER)
        proj_item.setEditable(False)
        root.appendRow(proj_item)

        skills_folder = QStandardItem("Skills")
        skills_folder.setForeground(_COLOR_FOLDER)
        skills_folder.setEditable(False)
        proj_item.appendRow(skills_folder)

        for skill in self._project.skills:
            if isinstance(skill, ProceduralSkill) and not self._show_procedural:
                continue
            if isinstance(skill, DeclarativeSkill) and not self._show_declarative:
                continue
            item = QStandardItem(skill.name)
            item.setData(skill, _ROLE_COMPONENT)
            item.setEditable(False)
            if isinstance(skill, ProceduralSkill):
                item.setForeground(_COLOR_PROCEDURAL)
            else:
                item.setForeground(_COLOR_DECLARATIVE)
            skills_folder.appendRow(item)

        agents_folder = QStandardItem("Agents")
        agents_folder.setForeground(_COLOR_FOLDER)
        agents_folder.setEditable(False)
        proj_item.appendRow(agents_folder)

        for agent in self._project.agents:
            item = QStandardItem(agent.name)
            item.setData(agent, _ROLE_COMPONENT)
            item.setEditable(False)
            item.setForeground(_COLOR_AGENT)
            agents_folder.appendRow(item)

        self._tree.expandAll()

    def _on_filter_changed(self) -> None:
        self._show_procedural = self._btn_proc.isChecked()
        self._show_declarative = self._btn_decl.isChecked()
        self._rebuild()

    def _on_double_click(self, index) -> None:
        item = self._model.itemFromIndex(index)
        if item:
            component = item.data(_ROLE_COMPONENT)
            if component is not None:
                self.component_double_clicked.emit(component)
