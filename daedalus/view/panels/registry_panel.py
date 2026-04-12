# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2

_COLOR_PROCEDURAL = QColor("#88cc88")
_COLOR_DECLARATIVE = QColor("#cccc88")
_COLOR_AGENT = QColor("#cc8888")
_COLOR_PLACED = QColor("#445544")
_COLOR_NO_PLACE = QColor("#666644")  # DeclarativeSkill: 배치 불가 표시

_ICON = {
    "procedural_skill": "⚙",
    "declarative_skill": "📄",
    "agent": "🤖",
}


class _DraggableList(QListWidget):
    """배치된 항목은 드래그 불가인 목록 위젯."""

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.data(_ROLE_PLACED):
            return
        component = item.data(_ROLE_COMPONENT)
        if component is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(component.name)
        drag.setMimeData(mime)
        # QDrag.exec() 로 드래그 실행 — PyQt6 메서드명
        _run_drag = getattr(drag, "exec")
        _run_drag(Qt.DropAction.CopyAction)


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트."""

    component_double_clicked = pyqtSignal(object)
    new_skill_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        layout.addWidget(self._section_label("⚙ PROCEDURAL"))
        self._proc_list = self._make_list()
        layout.addWidget(self._proc_list)

        layout.addWidget(self._section_label("📄 DECLARATIVE"))
        self._decl_list = self._make_list()
        layout.addWidget(self._decl_list)

        layout.addWidget(self._section_label("🤖 AGENTS"))
        self._agent_list = self._make_list()
        layout.addWidget(self._agent_list)

        btn = QPushButton("+ 새 스킬 정의")
        btn.clicked.connect(self.new_skill_requested)
        layout.addWidget(btn)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #668; font-size: 9px; padding: 4px 2px 0px 2px;")
        return lbl

    def _make_list(self) -> _DraggableList:
        lst = _DraggableList()
        lst.setDragEnabled(True)
        lst.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        lst.setMaximumHeight(130)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.doubleClicked.connect(self._on_double_click)
        lst.setStyleSheet(
            "QListWidget { background: #13132a; border: 1px solid #2a2a44; }"
            "QListWidget::item { padding: 4px 6px; }"
            "QListWidget::item:selected { background: #2a2a4a; }"
        )
        return lst

    def _rebuild(self) -> None:
        for lst in (self._proc_list, self._decl_list, self._agent_list):
            lst.clear()
        if self._project is None:
            return
        for skill in self._project.skills:
            placed = id(skill) in self._placed_ids
            if isinstance(skill, ProceduralSkill):
                self._add_item(self._proc_list, skill, _COLOR_PROCEDURAL, placed)
            elif isinstance(skill, DeclarativeSkill):
                # DeclarativeSkill은 항상 드래그 불가 (graph 배치 대상 아님)
                self._add_item(self._decl_list, skill, _COLOR_DECLARATIVE, placed=False, no_place=True)
        for agent in self._project.agents:
            placed = id(agent) in self._placed_ids
            self._add_item(self._agent_list, agent, _COLOR_AGENT, placed)

    def _add_item(
        self,
        lst: QListWidget,
        component: object,
        color: QColor,
        placed: bool,
        no_place: bool = False,
    ) -> None:
        kind = getattr(component, "kind", "")
        icon = _ICON.get(kind, "")
        name = getattr(component, "name", str(component))
        if no_place:
            label = f"{icon} {name}  (배치 불가)"
        else:
            label = f"{icon} {name}"
        item = QListWidgetItem(label)
        item.setData(_ROLE_COMPONENT, component)
        item.setData(_ROLE_PLACED, placed)
        if no_place:
            item.setForeground(_COLOR_NO_PLACE)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        elif placed:
            item.setForeground(_COLOR_PLACED)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        else:
            item.setForeground(color)
        lst.addItem(item)

    def _on_double_click(self, index) -> None:
        lst = self.sender()
        if not isinstance(lst, QListWidget):
            return
        item = lst.itemFromIndex(index)
        if item:
            comp = item.data(_ROLE_COMPONENT)
            if comp is not None:
                self.component_double_clicked.emit(comp)
