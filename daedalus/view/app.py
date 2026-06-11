# daedalus/view/app.py
from __future__ import annotations

import json
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.editors.skill_editor import SkillEditor
from daedalus.model.validation import ValidationError, Validator
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.registry_panel import RegistryPanel
from daedalus.view.panels.script_listener import ScriptListenerPanel
from daedalus.view.panels.validation_panel import ValidationPanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel

_FSM_TAB_INDEX = 0  # 프로젝트 FSM 캔버스는 항상 탭 0


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._current_path: str | None = None  # 현재 저장 경로 (.daedalus.json)
        self._project_vm = ProjectViewModel()
        self._fsm_scene: FsmScene | None = None
        self._open_tabs: dict[str, int] = {}  # 컴포넌트 id → 탭 인덱스
        self._active_stack = self._project_vm.command_stack
        self._active_notify = self._project_vm.notify
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

        self._validation_panel = ValidationPanel(
            on_item_activated=self._on_validation_item_activated,
        )
        validation_dock = QDockWidget("검증")
        validation_dock.setWidget(self._validation_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, validation_dock)
        validation_dock.hide()

    def _setup_menus(self) -> None:
        menubar = self.menuBar()
        if menubar is None:
            return

        file_menu = menubar.addMenu("File")
        if file_menu is not None:
            open_action = QAction("열기", self)
            open_action.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O
            open_action.triggered.connect(self._open_project_dialog)
            file_menu.addAction(open_action)

            save_action = QAction("저장", self)
            save_action.setShortcut(QKeySequence.StandardKey.Save)  # Ctrl+S
            save_action.triggered.connect(self._save_project)
            file_menu.addAction(save_action)

            save_as_action = QAction("다른 이름으로 저장", self)
            save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
            save_as_action.triggered.connect(self._save_project_as)
            file_menu.addAction(save_as_action)

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

        validate_menu = menubar.addMenu("검증")
        if validate_menu is not None:
            self._validate_action = QAction("프로젝트 검증", self)
            self._validate_action.setShortcut(QKeySequence(Qt.Key.Key_F7))
            self._validate_action.triggered.connect(self._run_validation)
            validate_menu.addAction(self._validate_action)

        build_menu = menubar.addMenu("빌드")
        if build_menu is not None:
            self._compile_action = QAction("컴파일", self)
            self._compile_action.setShortcut(QKeySequence("Ctrl+B"))
            self._compile_action.triggered.connect(self._compile_project_dialog)
            build_menu.addAction(self._compile_action)

        tools_menu = menubar.addMenu("도구")
        if tools_menu is not None:
            self._hook_lib_action = QAction("훅 라이브러리...", self)
            self._hook_lib_action.triggered.connect(self._open_hook_library)
            tools_menu.addAction(self._hook_lib_action)

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
        # HookPresetPicker가 이 프로젝트의 hook_library 이름을 동적으로 표시하도록 연결.
        from daedalus.view.widgets.preset_picker import set_hook_name_provider
        set_hook_name_provider(lambda p=project: [h.name for h in p.hook_library])

    def load_project(self, project: PluginProject) -> None:
        """기존 세션을 정리하고 새 프로젝트를 로드한다.

        열린 에디터 탭을 닫고, 프로젝트 VM(캔버스 상태)을 비운 뒤
        레지스트리/씬을 새 프로젝트로 재구성한다.
        """
        # 1) 열린 에디터 탭 정리 (Project FSM 탭 0 제외, 역순 제거)
        for index in range(self._tabs.count() - 1, _FSM_TAB_INDEX, -1):
            self._close_tab(index)
        self._open_tabs.clear()

        # 2) 프로젝트 VM(캔버스) 초기화
        self._project_vm.state_vms.clear()
        self._project_vm.transition_vms.clear()
        self._project_vm.reference_vms.clear()
        self._project_vm.reference_links.clear()

        # 3) 새 프로젝트 로드 — set_project가 registry/scene 갱신
        self.set_project(project)
        self._project_vm.notify()

    # --- 저장 / 열기 ---

    def _update_title(self) -> None:
        base = "Daedalus — FSM Plugin Designer"
        if self._current_path:
            self.setWindowTitle(f"{os.path.basename(self._current_path)} — {base}")
        else:
            self.setWindowTitle(base)

    def _save_to_path(self, path: str) -> None:
        if self._project is None:
            return
        try:
            data = serialize_project(self._project)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            # OSError: IO 실패 / TypeError·ValueError: 직렬화 불가 객체 혼입
            self._status_label.setText(f"저장 실패: {exc}")
            return
        self._current_path = path
        self._update_title()
        self._status_label.setText(f"저장됨: {path}")

    def _save_project(self) -> None:
        if self._current_path:
            self._save_to_path(self._current_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장", self._current_path or "",
            "Daedalus 프로젝트 (*.daedalus.json *.json)",
        )
        if path:
            self._save_to_path(path)

    def _open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "열기", self._current_path or "",
            "Daedalus 프로젝트 (*.daedalus.json *.json)",
        )
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        """경로에서 프로젝트를 로드한다 (다이얼로그 없이 — 테스트/CLI 재사용)."""
        deser_warnings: list[str] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = deserialize_project(data, collect_warnings=deser_warnings)
        except (OSError, ValueError) as exc:
            self._status_label.setText(f"열기 실패: {exc}")
            return
        self.load_project(project)
        self._current_path = path
        self._update_title()
        fname = os.path.basename(path)
        if deser_warnings:
            self._status_label.setText(
                f"열림: {fname} (경고 {len(deser_warnings)}건 — F7로 확인)"
            )
        else:
            self._status_label.setText(f"열림: {fname}")

    def _skill_lookup(self, name: str) -> object | None:
        if self._project is None:
            return None
        for skill in self._project.skills:
            if skill.name == name:
                return skill
        for agent in self._project.agents:
            if agent.name == name:
                return agent
        for deleg in self._project.delegations:
            if deleg.name == name:
                return deleg
        return None

    def _get_placed_ids(self) -> set[int]:
        result = set()
        for svm in self._project_vm.state_vms:
            if hasattr(svm.model, "skill_ref") and svm.model.skill_ref is not None:  # type: ignore[union-attr]
                result.add(id(svm.model.skill_ref))  # type: ignore[union-attr]
        return result

    def _on_project_vm_changed(self) -> None:
        self._registry_panel.set_placed_ids(self._get_placed_ids())
        self._sync_agent_editors()

    def _sync_agent_editors(self) -> None:
        """열린 AgentEditor 탭의 계약 패널 동기화."""
        from daedalus.view.editors.agent_editor import AgentEditor as _AE
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if isinstance(widget, _AE) and hasattr(widget, "_caller_contract_panel"):
                widget._caller_contract_panel.refresh()

    # --- 탭 관리 ---

    def _open_component(self, component: object) -> None:
        """레지스트리에서 더블클릭 → SkillEditor/AgentEditor/DelegationEditor 탭 열기."""
        from daedalus.model.plugin.delegation import DelegationDef
        name = getattr(component, "name", None)
        comp_id = getattr(component, "id", None)
        if name is None or comp_id is None:
            return
        if comp_id in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[comp_id])
            return

        if isinstance(component, AgentDefinition):
            from daedalus.view.editors.agent_editor import AgentEditor
            editor = AgentEditor(component, on_notify_fn=self._project_vm.notify, project=self._project)
            idx = self._tabs.addTab(editor, f"🤖 {name}")
            self._open_tabs[comp_id] = idx
            self._tabs.setCurrentIndex(idx)
        elif isinstance(component, DelegationDef):
            from daedalus.view.editors.delegation_editor import DelegationEditor
            editor = DelegationEditor(
                component,
                on_notify_fn=self._project_vm.notify,
                project=self._project,
            )
            icon = {"team_spawn": "👥", "dynamic_workflow": "🔀", "agora_dispatch": "🛰"}.get(component.kind, "🛰")
            idx = self._tabs.addTab(editor, f"{icon} {name}")
            self._open_tabs[comp_id] = idx
            self._tabs.setCurrentIndex(idx)
        elif isinstance(component, (ProceduralSkill, DeclarativeSkill, TransferSkill, ReferenceSkill)):
            editor = SkillEditor(component, on_notify_fn=self._project_vm.notify)
            idx = self._tabs.addTab(editor, name)
            self._open_tabs[comp_id] = idx
            self._tabs.setCurrentIndex(idx)

    def _ask_unique_name(self, dialog_title: str) -> str | None:
        """이름 입력 다이얼로그 + 중복 검증. 취소 시 None."""
        if self._project is None:
            return None
        existing = (
            {s.name for s in self._project.skills}
            | {a.name for a in self._project.agents}
            | {d.name for d in self._project.delegations}
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
        from daedalus.model.plugin.delegation import DelegationDef
        if self._project is None:
            return
        if isinstance(component, AgentDefinition):
            self._project.agents.append(component)
        elif isinstance(component, DelegationDef):
            self._project.delegations.append(component)
        else:
            self._project.skills.append(component)
        # 블랙보드 스코핑 배선 — 새로 생성한 컴포넌트의 FSM 블랙보드를 프로젝트
        # 블랙보드의 자식으로 연결한다 (생성 경로의 책임, 마이그레이션 없음).
        fsm = getattr(component, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = self._project.blackboard
        self._registry_panel.set_project(self._project)

    _COMPONENT_TITLES = {
        "procedural": "새 Procedural Skill",
        "declarative": "새 Declarative Skill",
        "transfer": "새 Transfer Skill",
        "reference": "새 Reference Skill",
        "agent": "새 Agent",
        "delegation": "새 Delegation",
    }

    def _on_new_component(self, kind: str) -> None:
        if kind == "delegation":
            self._on_new_delegation()
            return
        name = self._ask_unique_name(self._COMPONENT_TITLES.get(kind, "새 컴포넌트"))
        if name is None:
            return
        factories = {
            "procedural": lambda: ProceduralSkill(fsm=self._make_fsm(name), name=name, description=""),
            "declarative": lambda: DeclarativeSkill(name=name, description=""),
            "transfer": lambda: TransferSkill(fsm=self._make_fsm(name), name=name, description=""),
            "reference": lambda: ReferenceSkill(name=name, description=""),
            "agent": lambda: AgentDefinition(fsm=self._make_agent_fsm(name), name=name, description=""),  # type: ignore[arg-type]
        }
        self._register_component(factories[kind]())

    def _on_new_delegation(self) -> None:
        """위임 정의 생성: kind 선택 → 이름 입력 → 등록."""
        from daedalus.model.plugin.delegation import AgoraDispatchDef, DynamicWorkflowDef, TeamSpawnDef
        from daedalus.view.editors.delegation_editor import DELEGATION_KIND_TITLES
        items = list(DELEGATION_KIND_TITLES.values())
        item, ok = QInputDialog.getItem(
            self, "위임 종류 선택", "종류:", items, 0, False
        )
        if not ok or not item:
            return
        # item → kind 역매핑
        kind = next(k for k, v in DELEGATION_KIND_TITLES.items() if v == item)
        name = self._ask_unique_name(f"새 {item}")
        if name is None:
            return
        factories = {
            "team_spawn": lambda: TeamSpawnDef(name=name, description=""),
            "dynamic_workflow": lambda: DynamicWorkflowDef(name=name, description=""),
            "agora_dispatch": lambda: AgoraDispatchDef(name=name, description=""),
        }
        deleg = factories[kind]()
        if self._project is None:
            return
        self._project.delegations.append(deleg)
        self._registry_panel.set_project(self._project)

    def _close_tab(self, index: int) -> None:
        if index == _FSM_TAB_INDEX:
            return  # Project FSM은 닫을 수 없음
        widget = self._tabs.widget(index)
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }
        if widget is not None:
            # closeEvent 발화 (AgentEditor의 씬 리스너 해제 등) + Qt 메모리 정리
            widget.close()
            widget.deleteLater()

    def _on_tab_changed(self, index: int) -> None:
        if not self._initialized:
            return

        self._active_stack.remove_listener(self._update_undo_redo)

        if index == _FSM_TAB_INDEX:
            # Project FSM 캔버스
            self._active_stack = self._project_vm.command_stack
            self._active_notify = self._project_vm.notify
            self._history_panel.set_stack(
                self._project_vm.command_stack, on_goto=self._project_vm.notify
            )
            self._property_panel.set_project_vm(self._project_vm)
            self._script_panel.set_stack(self._project_vm.command_stack)
        else:
            from daedalus.view.editors.agent_editor import AgentEditor as _AE
            widget = self._tabs.widget(index)
            if isinstance(widget, _AE):
                # AgentEditor — undo/redo는 에이전트 그래프 VM 기준
                agent_stack = widget._graph_vm.command_stack
                self._active_stack = agent_stack
                self._active_notify = widget._graph_vm.notify
                self._history_panel.set_stack(
                    agent_stack, on_goto=widget._graph_vm.notify
                )
                self._script_panel.set_stack(agent_stack)
            else:
                # SkillEditor — undo/redo는 project VM 기준
                self._active_stack = self._project_vm.command_stack
                self._active_notify = self._project_vm.notify
                self._history_panel.set_stack(
                    self._project_vm.command_stack, on_goto=self._project_vm.notify
                )
                self._script_panel.set_stack(self._project_vm.command_stack)
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
        stack = self._active_stack
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        self._undo_action.setText(
            f"Undo: {stack.history[-1].description}" if stack.can_undo else "Undo"
        )
        self._redo_action.setText(
            f"Redo: {stack.redo_history[0].description}" if stack.can_redo else "Redo"
        )

    def _undo(self) -> None:
        self._active_stack.undo()
        self._active_notify()

    def _redo(self) -> None:
        self._active_stack.redo()
        self._active_notify()

    # --- 검증 ---

    def _run_validation(self) -> None:
        """F7 — 프로젝트 전체 검증 실행 후 ValidationPanel 갱신."""
        if self._project is None:
            self._status_label.setText("검증: 프로젝트가 없습니다.")
            return

        errors = Validator.validate_project(self._project)
        self._validation_panel.set_errors(errors)

        # 검증 패널이 숨겨져 있으면 표시
        self._show_validation_dock()

        error_count = sum(1 for e in errors if not e.is_warning)
        warning_count = sum(1 for e in errors if e.is_warning)
        if not errors:
            self._status_label.setText("검증: 문제 없음")
        else:
            self._status_label.setText(
                f"검증: 오류 {error_count} / 경고 {warning_count}"
            )

    # --- 컴파일 ---

    def _compile_project_dialog(self) -> None:
        """Ctrl+B — 출력 폴더 선택 후 프로젝트를 컴파일한다.

        에러가 있으면 ValidationPanel을 갱신하고 거부 메시지를 상태바에 표시한다.
        """
        if self._project is None:
            self._status_label.setText("컴파일: 프로젝트가 없습니다.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "컴파일 출력 폴더 선택", "")
        if not out_dir:
            return

        from daedalus.compiler import compile_project

        result = compile_project(self._project, out_dir)
        if not result.ok:
            # 에러 — 검증 패널에 동봉(경고 포함) 표시
            self._validation_panel.set_errors(result.errors + result.warnings)
            self._show_validation_dock()
            self._status_label.setText(
                f"컴파일 거부: 에러 {len(result.errors)}건 (F7로 확인)"
            )
            return

        warn = len(result.warnings)
        warn_str = f" / 경고 {warn}건" if warn else ""
        self._status_label.setText(
            f"컴파일 완료: {len(result.written)}파일 생성{warn_str} → {out_dir}"
        )
        if warn:
            # F7 검증 흐름과 동일하게 dock도 표시 — 경고를 상태바 문구로만
            # 인지하게 두지 않는다.
            self._validation_panel.set_errors(result.warnings)
            self._show_validation_dock()

    def _open_hook_library(self) -> None:
        """도구 메뉴 — 훅 라이브러리 편집 다이얼로그를 연다."""
        if self._project is None:
            self._status_label.setText("훅 라이브러리: 프로젝트가 없습니다.")
            return
        from daedalus.view.editors.hook_editor import HookLibraryDialog

        dlg = HookLibraryDialog(
            self._project, on_notify_fn=self._on_hook_library_changed, parent=self
        )
        dlg.exec()

    def _on_hook_library_changed(self) -> None:
        """훅 라이브러리 변경 시 — 열린 편집기의 HookPresetPicker 목록 갱신."""
        from daedalus.view.widgets.preset_picker import HookPresetPicker

        for picker in self.findChildren(HookPresetPicker):
            picker.refresh()

    def _show_validation_dock(self) -> None:
        """검증 dock을 표시하고 앞으로 올린다 (F7/컴파일 공용)."""
        validation_dock = self._find_validation_dock()
        if validation_dock is not None:
            validation_dock.show()
            validation_dock.raise_()

    def _find_validation_dock(self) -> QDockWidget | None:
        """'검증' 도킹 위젯을 반환한다."""
        for dock in self.findChildren(QDockWidget):
            if dock.widget() is self._validation_panel:
                return dock
        return None

    def _on_validation_item_activated(self, error: ValidationError) -> None:
        """ValidationPanel 더블클릭 → 해당 노드 포커스."""
        if self._project is None:
            return

        subject = error.subject
        if subject is None:
            return

        # path의 첫 요소로 에이전트 컨텍스트 판별
        path = error.path
        agent_name: str | None = None
        if path:
            first = path[0]
            if first.startswith("agent:"):
                agent_name = first[len("agent:"):]

        if agent_name is not None:
            # 에이전트 탭 내부 노드
            self._focus_in_agent_tab(agent_name, subject)
        else:
            # 프로젝트 캔버스(탭 0)
            self._focus_in_project_canvas(subject)

    def _focus_in_project_canvas(self, subject: object) -> None:
        """프로젝트 FSM 캔버스(탭 0)에서 subject와 identity 일치하는 노드를 선택+센터링."""
        self._tabs.setCurrentIndex(_FSM_TAB_INDEX)
        if self._fsm_scene is None:
            return
        for svm, node_item in self._fsm_scene._node_items.items():
            if svm.model is subject:
                self._fsm_scene.clearSelection()
                node_item.setSelected(True)
                view = self._tabs.widget(_FSM_TAB_INDEX)
                if hasattr(view, "centerOn"):
                    view.centerOn(node_item)  # type: ignore[union-attr]
                elif hasattr(view, "ensureVisible"):
                    view.ensureVisible(node_item)  # type: ignore[union-attr]
                return

    def _focus_in_agent_tab(self, agent_name: str, subject: object) -> None:
        """에이전트 탭이 열려 있으면 해당 노드를 포커스, 없으면 상태바 안내."""
        from daedalus.view.editors.agent_editor import AgentEditor
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if isinstance(widget, AgentEditor):
                ag = getattr(widget, "_agent", None)
                if ag is not None and ag.name == agent_name:
                    self._tabs.setCurrentIndex(i)
                    # AgentEditor 내부 씬에서 노드 탐색
                    scene = getattr(widget, "_graph_scene", None)
                    if scene is not None:
                        for svm, node_item in scene._node_items.items():
                            if svm.model is subject:
                                scene.clearSelection()
                                node_item.setSelected(True)
                                view = getattr(widget, "_canvas_view", None)
                                if view is not None and hasattr(view, "centerOn"):
                                    view.centerOn(node_item)
                                return
                    return
        # 탭이 열려 있지 않음
        self._status_label.setText(
            f"에이전트 '{agent_name}' 탭을 열어 확인하세요."
        )
