# daedalus/view/app.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, TransferSkill
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

_FSM_TAB_INDEX = 0  # 프로젝트 FSM 캔버스는 항상 탭 0


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._project_vm = ProjectViewModel()
        self._fsm_scene: FsmScene | None = None
        self._open_tabs: dict[str, int] = {}  # SkillEditor 탭만 관리
        self._active_stack = self._project_vm.command_stack
        self._initialized = False  # setup 완료 전 시그널 발화 방어용

        self._setup_central()
        self._setup_docks()
        self._setup_menus()
        self._setup_statusbar()
        self._initialized = True
        self._connect_signals()

    # --- 초기화 ---

    def _setup_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        # currentChanged는 _setup_docks() 완료 후 _connect_signals()에서 연결
        self.setCentralWidget(self._tabs)

        # 프로젝트 FSM 캔버스 — 항상 탭 0, 닫을 수 없음
        self._fsm_scene = FsmScene(self._project_vm, skill_lookup=self._skill_lookup)
        fsm_view = FsmCanvasView(self._fsm_scene)
        self._fsm_scene.selectionChanged.connect(self._on_scene_selection)
        self._tabs.addTab(fsm_view, "Project FSM")
        # 탭 0의 닫기 버튼 숨김
        tab_bar = self._tabs.tabBar()
        if tab_bar is not None:
            tab_bar.setTabButton(0, tab_bar.ButtonPosition.RightSide, None)

        # 프로젝트 VM 변경 시 레지스트리 dim 갱신
        self._project_vm.add_listener(self._on_project_vm_changed)

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
        prop_dock.hide()

        self._script_panel = ScriptListenerPanel()
        script_dock = QDockWidget("Script Listener")
        script_dock.setWidget(self._script_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, script_dock)
        script_dock.hide()

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
        # 모든 dock/panel이 초기화된 후 연결해야 _on_tab_changed에서 safe
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._registry_panel.component_double_clicked.connect(self._open_component)
        self._registry_panel.new_component_requested.connect(self._on_new_component)
        self._fsm_scene.node_double_clicked.connect(self._open_component)
        self._active_stack.add_listener(self._update_undo_redo)

    # --- 프로젝트 ---

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._registry_panel.set_project(project)
        if self._fsm_scene is not None:
            self._fsm_scene.set_project(project)

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

    def _get_placed_ids(self) -> set[int]:
        result = set()
        for svm in self._project_vm.state_vms:
            if hasattr(svm.model, "skill_ref") and svm.model.skill_ref is not None:  # type: ignore[union-attr]
                result.add(id(svm.model.skill_ref))  # type: ignore[union-attr]
        return result

    def _on_project_vm_changed(self) -> None:
        self._registry_panel.set_placed_ids(self._get_placed_ids())

    # --- 탭 관리 ---

    def _open_component(self, component: object) -> None:
        """레지스트리에서 더블클릭 → SkillEditor/AgentEditor 탭 열기."""
        name = getattr(component, "name", None)
        if name is None:
            return
        if name in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[name])
            return

        if isinstance(component, AgentDefinition):
            from daedalus.view.editors.agent_editor import AgentEditor
            editor = AgentEditor(component, on_notify_fn=self._project_vm.notify)
            idx = self._tabs.addTab(editor, f"🤖 {name}")
            self._open_tabs[name] = idx
            self._tabs.setCurrentIndex(idx)
        elif isinstance(component, (ProceduralSkill, DeclarativeSkill, TransferSkill)):
            editor = SkillEditor(component, on_notify_fn=self._project_vm.notify)
            idx = self._tabs.addTab(editor, name)
            self._open_tabs[name] = idx
            self._tabs.setCurrentIndex(idx)

    def _ask_unique_name(self, dialog_title: str) -> str | None:
        """이름 입력 다이얼로그 + 중복 검증. 취소 시 None."""
        if self._project is None:
            return None
        existing = (
            {s.name for s in self._project.skills}
            | {a.name for a in self._project.agents}
        )
        while True:
            name, ok = QInputDialog.getText(self, dialog_title, "이름:")
            if not ok or not name.strip():
                return None
            name = name.strip()
            if name in existing:
                QMessageBox.warning(self, "이름 중복", f"'{name}' 이름이 이미 존재합니다.")
                continue
            return name

    def _make_fsm(self, name: str) -> object:
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState as _SS
        s = _SS(name="start")
        return StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)

    def _make_agent_fsm(self, name: str) -> object:
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
        entry = EntryPoint(name="entry")
        exit_done = ExitPoint(name="done")
        return StateMachine(
            name=f"{name}_fsm",
            states=[entry, exit_done],
            initial_state=entry,
            final_states=[exit_done],
        )

    def _register_component(self, component: object) -> None:
        if self._project is None:
            return
        if isinstance(component, AgentDefinition):
            self._project.agents.append(component)
        else:
            self._project.skills.append(component)
        self._registry_panel.set_project(self._project)

    _COMPONENT_TITLES = {
        "procedural": "새 Procedural Skill",
        "declarative": "새 Declarative Skill",
        "transfer": "새 Transfer Skill",
        "agent": "새 Agent",
    }

    def _on_new_component(self, kind: str) -> None:
        name = self._ask_unique_name(self._COMPONENT_TITLES[kind])
        if name is None:
            return
        factories = {
            "procedural": lambda: ProceduralSkill(fsm=self._make_fsm(name), name=name, description=""),
            "declarative": lambda: DeclarativeSkill(name=name, description=""),
            "transfer": lambda: TransferSkill(fsm=self._make_fsm(name), name=name, description=""),
            "agent": lambda: AgentDefinition(fsm=self._make_agent_fsm(name), name=name, description=""),  # type: ignore[arg-type]
        }
        self._register_component(factories[kind]())

    def _close_tab(self, index: int) -> None:
        if index == _FSM_TAB_INDEX:
            return  # Project FSM은 닫을 수 없음
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }

    def _on_tab_changed(self, index: int) -> None:
        if not self._initialized:
            return

        self._active_stack.remove_listener(self._update_undo_redo)

        if index == _FSM_TAB_INDEX:
            # Project FSM 캔버스
            self._active_stack = self._project_vm.command_stack
            self._history_panel.set_stack(
                self._project_vm.command_stack, on_goto=self._project_vm.notify
            )
            self._property_panel.set_project_vm(self._project_vm)
            self._script_panel.set_stack(self._project_vm.command_stack)
        else:
            # SkillEditor 탭 — undo/redo는 project VM 기준
            self._active_stack = self._project_vm.command_stack
            self._property_panel.clear()

        self._active_stack.add_listener(self._update_undo_redo)
        self._update_undo_redo()

    def _on_scene_selection(self) -> None:
        if self._fsm_scene is None:
            return
        selected = self._fsm_scene.selectedItems()
        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, StateNodeItem):
                self._property_panel.show_state(item.state_vm)
            elif isinstance(item, TransitionEdgeItem):
                self._property_panel.show_transition(item.transition_vm)
        else:
            self._property_panel.clear()

    def _update_undo_redo(self) -> None:
        stack = self._project_vm.command_stack
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        self._undo_action.setText(
            f"Undo: {stack.history[-1].description}" if stack.can_undo else "Undo"
        )
        self._redo_action.setText(
            f"Redo: {stack.redo_history[0].description}" if stack.can_redo else "Redo"
        )

    def _undo(self) -> None:
        self._project_vm.command_stack.undo()
        self._project_vm.notify()

    def _redo(self) -> None:
        self._project_vm.command_stack.redo()
        self._project_vm.notify()
