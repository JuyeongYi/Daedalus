# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, TransferSkill
from daedalus.model.project import PluginProject

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2

_COLOR_PLACED = QColor("#445544")
_COLOR_NO_PLACE = QColor("#666644")

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
        _run_drag = getattr(drag, "exec")
        _run_drag(Qt.DropAction.CopyAction)


class _RegistrySection(QWidget):
    """레이블 + 리스트 + "+" 버튼을 묶은 레지스트리 섹션."""

    add_requested = pyqtSignal()
    item_double_clicked = pyqtSignal(object)

    def __init__(self, label: str, color: QColor, no_place: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self._no_place = no_place

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(2)
        hdr.addWidget(QLabel(label))
        hdr.addStretch()
        btn = QPushButton("+")
        btn.setFixedSize(20, 20)
        btn.clicked.connect(self.add_requested)
        hdr.addWidget(btn)
        lay.addLayout(hdr)

        self._list = _DraggableList()
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list.setMaximumHeight(130)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.doubleClicked.connect(self._on_double_click)
        lay.addWidget(self._list)

    def clear(self) -> None:
        self._list.clear()

    def add_item(self, component: object, placed: bool) -> None:
        kind = getattr(component, "kind", "")
        icon = _ICON.get(kind, "")
        name = getattr(component, "name", str(component))
        no_place = self._no_place

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
            item.setForeground(self._color)
        self._list.addItem(item)

    def _on_double_click(self, index) -> None:
        item = self._list.itemFromIndex(index)
        if item:
            comp = item.data(_ROLE_COMPONENT)
            if comp is not None:
                self.item_double_clicked.emit(comp)


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트."""

    component_double_clicked = pyqtSignal(object)
    new_component_requested = pyqtSignal(str)  # kind: "procedural"|"declarative"|"agent"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._sections: dict[str, _RegistrySection] = {
            "procedural": _RegistrySection("⚙ PROCEDURAL", QColor("#88cc88")),
            "declarative": _RegistrySection("📄 DECLARATIVE", QColor("#cccc88"), no_place=True),
            "transfer": _RegistrySection("⚡ TRANSFER", QColor("#88aacc"), no_place=True),
            "agent": _RegistrySection("🤖 AGENTS", QColor("#cc8888")),
        }
        for kind, section in self._sections.items():
            section.add_requested.connect(lambda k=kind: self.new_component_requested.emit(k))
            section.item_double_clicked.connect(self.component_double_clicked)
            layout.addWidget(section)

        layout.addStretch()

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _rebuild(self) -> None:
        for section in self._sections.values():
            section.clear()
        if self._project is None:
            return
        for skill in self._project.skills:
            placed = id(skill) in self._placed_ids
            if isinstance(skill, TransferSkill):
                self._sections["transfer"].add_item(skill, placed=False)
            elif isinstance(skill, ProceduralSkill):
                self._sections["procedural"].add_item(skill, placed)
            elif isinstance(skill, DeclarativeSkill):
                self._sections["declarative"].add_item(skill, placed=False)
        for agent in self._project.agents:
            placed = id(agent) in self._placed_ids
            self._sections["agent"].add_item(agent, placed)
