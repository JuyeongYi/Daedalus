# daedalus/view/app.py
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
from daedalus.view.editors.skill_editor import SkillEditor
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.registry_panel import RegistryPanel
from daedalus.view.panels.script_listener import ScriptListenerPanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._project_vm = ProjectViewModel()
        self._tab_vms: dict[int, ProjectViewModel] = {}
        self._open_tabs: dict[str, int] = {}
        self._active_stack = self._project_vm.command_stack

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
        self._registry_panel = RegistryPanel()
        registry_dock = QDockWidget("Registry")
        registry_dock.setWidget(self._registry_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, registry_dock)

        self._history_panel = HistoryPanel(
            self._project_vm.command_stack, on_goto=self._project_vm.notify,
        )
        history_dock = QDockWidget("History")
        history_dock.setWidget(self._history_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, history_dock)

        self._property_panel = PropertyPanel(self._project_vm)
        prop_dock = QDockWidget("Properties")
        prop_dock.setWidget(self._property_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, prop_dock)

        self._script_panel = ScriptListenerPanel()
        script_dock = QDockWidget("Script Listener")
        script_dock.setWidget(self._script_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, script_dock)

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
        self._registry_panel.component_double_clicked.connect(self._open_component)
        self._registry_panel.new_skill_requested.connect(self._on_new_skill_requested)
        self._active_stack.add_listener(self._update_undo_redo)

    # --- 프로젝트 ---

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._registry_panel.set_project(project)

    def _skill_lookup(self, name: str) -> ProceduralSkill | DeclarativeSkill | AgentDefinition | None:
        if self._project is None:
            return None
        for skill in self._project.skills:
            if skill.name == name:
                return skill
        for agent in self._project.agents:
            if agent.name == name:
                return agent
        return None

    def _get_placed_ids(self, tab_vm: ProjectViewModel) -> set[int]:
        return {
            id(svm.model.skill_ref)
            for svm in tab_vm.state_vms
            if svm.model.skill_ref is not None
        }

    def _notify_all_tabs(self) -> None:
        self._project_vm.notify()
        for vm in self._tab_vms.values():
            vm.notify()

    # --- 탭 관리 ---

    def _open_component(self, component: object) -> None:
        name = getattr(component, "name", None)
        if name is None:
            return
        if name in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[name])
            return

        if isinstance(component, (ProceduralSkill, AgentDefinition)):
            tab_vm = ProjectViewModel()
            tab_vm.add_listener(lambda: self._on_tab_vm_changed(tab_vm))
            scene = FsmScene(tab_vm, skill_lookup=self._skill_lookup)
            view = FsmCanvasView(scene)
            scene.selectionChanged.connect(lambda s=scene: self._on_scene_selection(s))
            idx = self._tabs.addTab(view, name)
            self._tab_vms[idx] = tab_vm

        elif isinstance(component, DeclarativeSkill):
            editor = SkillEditor(component, on_notify_fn=self._notify_all_tabs)
            idx = self._tabs.addTab(editor, name)

        else:
            return

        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _on_tab_vm_changed(self, tab_vm: ProjectViewModel) -> None:
        placed = self._get_placed_ids(tab_vm)
        self._registry_panel.set_placed_ids(placed)

    def _on_new_skill_requested(self) -> None:
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState as _SS
        s = _SS(name="start")
        fsm = StateMachine(name="new_fsm", states=[s], initial_state=s)
        skill = ProceduralSkill(fsm=fsm, name="NewSkill", description="")
        if self._project is not None:
            self._project.skills.append(skill)
            self._registry_panel.set_project(self._project)
        editor = SkillEditor(skill, on_notify_fn=self._notify_all_tabs)
        idx = self._tabs.addTab(editor, "NewSkill")
        self._open_tabs["NewSkill"] = idx
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        widget = self._tabs.widget(index)
        if isinstance(widget, FsmCanvasView):
            scene = widget.scene()
            if isinstance(scene, FsmScene):
                scene.close()
        self._tab_vms.pop(index, None)
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }
        self._tab_vms = {
            (i if i < index else i - 1): vm
            for i, vm in self._tab_vms.items()
            if i != index
        }

    def _on_tab_changed(self, index: int) -> None:
        self._property_panel.clear()
        self._active_stack.remove_listener(self._update_undo_redo)

        if index >= 0 and index in self._tab_vms:
            active_vm = self._tab_vms[index]
            self._active_stack = active_vm.command_stack
            self._history_panel.set_stack(active_vm.command_stack, on_goto=active_vm.notify)
            self._property_panel.set_project_vm(active_vm)
            self._script_panel.set_stack(active_vm.command_stack)
            self._registry_panel.set_placed_ids(self._get_placed_ids(active_vm))
        else:
            self._active_stack = self._project_vm.command_stack
            self._registry_panel.set_placed_ids(set())

        self._active_stack.add_listener(self._update_undo_redo)
        self._update_undo_redo()

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

    def _update_undo_redo(self) -> None:
        index = self._tabs.currentIndex()
        stack = (
            self._tab_vms[index].command_stack
            if index >= 0 and index in self._tab_vms
            else self._project_vm.command_stack
        )
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        self._undo_action.setText(
            f"Undo: {stack.history[-1].description}" if stack.can_undo else "Undo"
        )
        self._redo_action.setText(
            f"Redo: {stack.redo_history[0].description}" if stack.can_redo else "Redo"
        )

    def _undo(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0 and index in self._tab_vms:
            vm = self._tab_vms[index]
            vm.command_stack.undo()
            vm.notify()
        else:
            self._project_vm.command_stack.undo()
            self._project_vm.notify()

    def _redo(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0 and index in self._tab_vms:
            vm = self._tab_vms[index]
            vm.command_stack.redo()
            vm.notify()
        else:
            self._project_vm.command_stack.redo()
            self._project_vm.notify()
