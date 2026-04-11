from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.editors.decl_skill_editor import DeclSkillEditor
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.tree_panel import ProjectTreePanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1200, 800)

        self._project_vm = ProjectViewModel()
        self._open_tabs: dict[str, int] = {}

        self._setup_central()
        self._setup_docks()
        self._setup_menus()
        self._setup_statusbar()
        self._connect_signals()

    def _setup_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

    def _setup_docks(self) -> None:
        self._tree_panel = ProjectTreePanel()
        tree_dock = QDockWidget("Project")
        tree_dock.setWidget(self._tree_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tree_dock)

        self._history_panel = HistoryPanel(self._project_vm.command_stack)
        history_dock = QDockWidget("History")
        history_dock.setWidget(self._history_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, history_dock)

        self._property_panel = PropertyPanel(self._project_vm)
        prop_dock = QDockWidget("Properties")
        prop_dock.setWidget(self._property_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, prop_dock)

    def _setup_menus(self) -> None:
        menubar = self.menuBar()
        if menubar is None:
            return

        edit_menu = menubar.addMenu("Edit")
        if edit_menu is None:
            return
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menubar.addMenu("View")
        if view_menu is None:
            return
        for dock in self.findChildren(QDockWidget):
            view_menu.addAction(dock.toggleViewAction())

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel("Ready")
        self._statusbar.addWidget(self._status_label)
        self._project_vm.add_listener(self._update_statusbar)

    def _update_statusbar(self) -> None:
        s = len(self._project_vm.state_vms)
        t = len(self._project_vm.transition_vms)
        self._status_label.setText(f"States: {s} | Transitions: {t}")

    def _connect_signals(self) -> None:
        self._tree_panel.component_double_clicked.connect(self._open_component)
        self._project_vm.command_stack.add_listener(self._update_undo_redo)

    def _update_undo_redo(self) -> None:
        stack = self._project_vm.command_stack
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        if stack.can_undo:
            self._undo_action.setText(f"Undo: {stack.history[-1].description}")
        else:
            self._undo_action.setText("Undo")

    def _open_component(self, component: object) -> None:
        name = getattr(component, "name", None)
        if name is None:
            return
        if name in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[name])
            return
        if isinstance(component, (ProceduralSkill, AgentDefinition)):
            scene = FsmScene(self._project_vm)
            view = FsmCanvasView(scene)
            scene.selectionChanged.connect(lambda s=scene: self._on_scene_selection(s))
            idx = self._tabs.addTab(view, name)
        elif isinstance(component, DeclarativeSkill):
            idx = self._tabs.addTab(DeclSkillEditor(component), name)
        else:
            return
        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }

    def _on_tab_changed(self, index: int) -> None:
        if index < 0:
            self._property_panel.clear()

    def _on_scene_selection(self, scene: FsmScene) -> None:
        selected = scene.selectedItems()
        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, StateNodeItem):
                self._property_panel.show_state(item.state_vm)
            elif isinstance(item, TransitionEdgeItem):
                self._property_panel.show_transition(item.transition_vm)
        else:
            self._property_panel.clear()

    def _undo(self) -> None:
        self._project_vm.command_stack.undo()
        self._project_vm.notify()

    def _redo(self) -> None:
        self._project_vm.command_stack.redo()
        self._project_vm.notify()

    def set_project(self, project: PluginProject) -> None:
        self._tree_panel.set_project(project)
