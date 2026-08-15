# daedalus/view/app.py
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from daedalus.model import package
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.view import recent
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.editors.skill_editor import SkillEditor
from daedalus.model.validation import ValidationError, Validator
from daedalus.view.panels.file_panel import FilePanel
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.registry_panel import RegistryPanel
from daedalus.view.panels.script_listener import ScriptListenerPanel
from daedalus.view.panels.validation_panel import ValidationPanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel

_FSM_TAB_INDEX = 0  # 프로젝트 FSM 캔버스는 항상 탭 0
_BLACKBOARD_TAB_INDEX = 1  # 블랙보드 편집 탭은 항상 탭 1 (WP-BB — 닫기 불가 고정 탭)
_HOOK_TAB_INDEX = 2  # 훅 라이브러리 탭은 항상 탭 2 (WP-HK — 닫기 불가 고정 탭)
# 고정 탭 = 컴포넌트 에디터가 아닌 상주 탭. 새 에디터는 이 뒤에 붙는다.
_FIXED_TAB_INDEXES = (_FSM_TAB_INDEX, _BLACKBOARD_TAB_INDEX, _HOOK_TAB_INDEX)
_LAST_FIXED_TAB_INDEX = max(_FIXED_TAB_INDEXES)


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
        # "최근 프로젝트" 서브메뉴 (WP-RP) — _setup_menus에서 생성
        self._recent_menu: QMenu | None = None
        # MCP 서버는 여기서 자동으로 띄우지 않는다 (WP-MCP) — 테스트가 MainWindow를
        # 수십 개 만들기 때문에, 실제 앱 실행 경로(__main__.main)에서만
        # start_mcp_service()로 기동한다.
        self._mcp_service: object | None = None

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

        # 블랙보드 편집 탭 — 항상 탭 1, 닫을 수 없음 (WP-BB)
        from daedalus.view.editors.blackboard_editor import BlackboardPanel
        self._blackboard_panel = BlackboardPanel(on_notify_fn=self._project_vm.notify)
        self._tabs.addTab(self._blackboard_panel, "🗂 블랙보드")

        # 훅 라이브러리 탭 — 항상 탭 2, 닫을 수 없음 (WP-HK).
        # 모달 다이얼로그였다가 상주 탭이 됐다: CC 훅은 이벤트 31종 × 핸들러 5종의
        # 3단 구조라 모달 폼으로는 다룰 수 없다.
        from daedalus.view.editors.hook_panel import HookLibraryPanel
        self._hook_panel = HookLibraryPanel(on_notify_fn=self._project_vm.notify)
        self._tabs.addTab(self._hook_panel, "🪝 훅")

        # 고정 탭의 닫기 버튼 숨김
        tab_bar = self._tabs.tabBar()
        if tab_bar is not None:
            for index in _FIXED_TAB_INDEXES:
                tab_bar.setTabButton(index, tab_bar.ButtonPosition.RightSide, None)

        # 프로젝트 VM 변경 시 레지스트리 dim 갱신
        self._project_vm.add_listener(self._on_project_vm_changed)

    def _setup_docks(self) -> None:
        self._registry_panel = RegistryPanel()
        registry_dock = QDockWidget("Registry")
        registry_dock.setWidget(self._registry_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, registry_dock)

        # 파일 독 패널 (WP-FR) — 프로젝트 옆 files/ 트리. _current_path 변경 시점
        # (저장/열기/새 프로젝트)마다 _sync_files_root가 루트를 재설정한다.
        # 레지스트리 **오른쪽에 나란히** 배치(세로 스택이 아니라 수평 분할) —
        # 트리에서 에디터로 드래그하는 동선이 짧아진다.
        self._file_panel = FilePanel()
        file_dock = QDockWidget("파일")
        file_dock.setWidget(self._file_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, file_dock)
        self.splitDockWidget(registry_dock, file_dock, Qt.Orientation.Horizontal)
        from daedalus.view.widgets.markdown_editor import set_files_root_provider
        set_files_root_provider(lambda: self._file_panel.files_root())

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
            new_action = QAction("새 프로젝트", self)
            new_action.setShortcut(QKeySequence.StandardKey.New)  # Ctrl+N
            new_action.triggered.connect(self._new_project)
            file_menu.addAction(new_action)

            file_menu.addSeparator()

            open_action = QAction("폴더 열기", self)
            open_action.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O
            open_action.triggered.connect(self._open_project_dialog)
            file_menu.addAction(open_action)

            open_file_action = QAction("파일에서 열기…", self)
            open_file_action.setToolTip("구버전 <이름>.daedalus.json을 직접 연다")
            open_file_action.triggered.connect(self._open_file_dialog)
            file_menu.addAction(open_file_action)

            self._recent_menu = file_menu.addMenu("최근 프로젝트")
            if self._recent_menu is not None:
                # 파일명만으로는 구분이 안 되는 경우가 흔해 툴팁에 전체 경로를 담는다
                self._recent_menu.setToolTipsVisible(True)
            self._rebuild_recent_menu()

            save_action = QAction("저장", self)
            save_action.setShortcut(QKeySequence.StandardKey.Save)  # Ctrl+S
            save_action.triggered.connect(self._save_project)
            file_menu.addAction(save_action)

            save_as_action = QAction("다른 이름으로 저장", self)
            save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
            save_as_action.triggered.connect(self._save_project_as)
            file_menu.addAction(save_as_action)

            file_menu.addSeparator()

            export_action = QAction("패키지로 내보내기… (.ddpj)", self)
            export_action.triggered.connect(self._export_package_dialog)
            file_menu.addAction(export_action)

            import_action = QAction("패키지 가져오기…", self)
            import_action.triggered.connect(self._import_package_dialog)
            file_menu.addAction(import_action)

            file_menu.addSeparator()

            properties_action = QAction("프로젝트 속성…", self)
            properties_action.triggered.connect(self._edit_project_properties)
            file_menu.addAction(properties_action)

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
            self._mcp_info_action = QAction("MCP 서버 정보...", self)
            self._mcp_info_action.triggered.connect(self._show_mcp_info)
            tools_menu.addAction(self._mcp_info_action)

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
        self._registry_panel.component_delete_requested.connect(self._on_delete_component)
        self._fsm_scene.node_double_clicked.connect(self._open_component)
        self._active_stack.add_listener(self._update_undo_redo)

    # --- 프로젝트 ---

    def set_project(self, project: PluginProject) -> None:
        # 본문 문서 캐시는 이전 프로젝트의 컴포넌트에 묶여 있다 — 프로젝트가
        # 바뀌면 통째로 버린다 (WP-BU).
        from daedalus.view.editors import body_documents
        body_documents.registry().clear()

        self._project = project
        self._registry_panel.set_project(project)
        self._blackboard_panel.set_project(project)
        self._hook_panel.set_project(project)
        if self._fsm_scene is not None:
            self._fsm_scene.set_project(project)
        # HookPresetPicker가 이 프로젝트의 hook_library 이름을 동적으로 표시하도록 연결.
        from daedalus.view.widgets.preset_picker import set_hook_name_provider
        set_hook_name_provider(lambda p=project: [h.name for h in p.hook_library])
        # ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS TagInput이 카탈로그+빌트인+
        # Agent(이름) 후보를 동적으로 표시하도록 연결 (WP-TM).
        from daedalus.view.editors.catalogue_loader import candidate_strings, load_catalogue
        from daedalus.view.widgets.tag_input import set_tool_candidate_provider

        def _tool_candidates(p=project) -> list[str]:
            project_dir = Path(self._current_path).parent if self._current_path else None
            entries = load_catalogue(project_dir=project_dir)
            return candidate_strings(entries, p)

        set_tool_candidate_provider(_tool_candidates)
        # 상태 reads/writes TagInput이 블랙보드 "클래스"/"클래스.필드" 후보를
        # 표시하도록 연결 (WP-BB). 호출 시점 스냅샷 — 도구 후보와 동일 정책.
        from daedalus.view.editors.blackboard_editor import blackboard_candidate_strings
        from daedalus.view.widgets.tag_input import set_blackboard_candidate_provider

        set_blackboard_candidate_provider(lambda p=project: blackboard_candidate_strings(p))
        # 프로젝트 그래프(워크플로 백킹 머신) → 캔버스 VM 재구성 (버그 1: 저장된
        # 노드 연결 복원). placement 노드 + 전이를 graph_layout 좌표로 배치한다
        # (WP-EP: EntryPoint는 그리지 않음). _load_agent_fsm 미러링.
        self._load_project_graph()

    def _load_project_graph(self) -> None:
        """project.graph + graph_layout으로부터 캔버스 VM(state_vms/transition_vms)을
        재구성한다. 기존 VM은 비우고 새로 채운다 (중복 방지). notify로 캔버스 갱신.

        WP-EP: CC 플러그인에는 단일 진입점이 없다(user_invocable 스킬은 전부
        독립 시작 가능) — 합성 EntryPoint("start")는 모델(graph.initial_state)에는
        여전히 존재하지만 프로젝트 캔버스에는 **그리지 않는다**. EntryPoint에
        닿는 전이(구버전 파일의 시작 전이 포함)도 VM이 없으므로 자연히 스킵된다
        (경고 없음). 에이전트 캔버스(_load_agent_fsm)는 이 WP의 영향을 받지 않는다.
        """
        from daedalus.model.fsm.pseudo import EntryPoint
        from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

        if self._project is None:
            return
        graph = self._project.graph

        # 기존 캔버스 VM 비우기 (set_project 재호출 시 중복 누적 방지)
        self._project_vm.state_vms.clear()
        self._project_vm.transition_vms.clear()

        placements = [s for s in graph.states if not isinstance(s, EntryPoint)]

        saved = self._project.graph_layout  # 키: state.id (안정 식별자)
        x = 0.0
        vm_map: dict[str, StateViewModel] = {}
        for state in placements:
            if state.id in saved:
                sx, sy = saved[state.id]
                vm = StateViewModel(model=state, x=sx, y=sy)
            else:
                vm = StateViewModel(model=state, x=x, y=100.0)
            self._project_vm.state_vms.append(vm)
            vm_map[state.id] = vm
            x += 220.0

        saved_edges = self._project.edge_layout  # 키: Transition.id (WP-ER)
        for trans in graph.transitions:
            # source/target이 EntryPoint면 vm_map에 없어 자연히 스킵된다.
            src_vm = vm_map.get(trans.source.id)
            tgt_vm = vm_map.get(trans.target.id)
            if src_vm and tgt_vm:
                waypoints = [(x, y) for x, y in saved_edges.get(trans.id, [])]
                tvm = TransitionViewModel(
                    model=trans, source_vm=src_vm, target_vm=tgt_vm,
                    waypoints=waypoints,
                )
                self._project_vm.transition_vms.append(tvm)

        # 참조 노드 복원 — 선재 결함 수정: 참조 배치는 저장(라이브 sync)만 되고
        # 로드 복원 경로가 없어 캔버스에서 사라졌고, 이후 참조 편집 시
        # sync_refs_to_model이 (빈 VM 기준으로) 로드분을 통째로 소실시켰다.
        from daedalus.view.viewmodel.state_vm import (
            ReferenceLinkViewModel,
            ReferenceViewModel,
        )
        self._project_vm.reference_vms.clear()
        self._project_vm.reference_links.clear()
        skills_by_name = {s.name: s for s in self._project.skills}
        vms_by_name = {svm.model.name: svm for svm in self._project_vm.state_vms}
        for rp in getattr(self._project, "reference_placements", None) or []:
            ref_skill = skills_by_name.get(rp.skill_name)
            if ref_skill is None:
                continue  # dangling_string_reference가 F7에서 짚는다
            rvm = ReferenceViewModel(model=ref_skill, x=rp.x, y=rp.y)
            self._project_vm.reference_vms.append(rvm)
            for state_name in rp.connected_states:
                svm = vms_by_name.get(state_name)
                if svm is not None:
                    self._project_vm.reference_links.append(
                        ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
                    )
        self._project_vm.notify()

    def _save_graph_layout(self) -> None:
        """캔버스 노드 위치를 project.graph_layout에 기록. 키는 state.id.

        WP-ER: 엣지 경유점(waypoint)도 함께 project.edge_layout에 기록한다.
        키는 Transition.id.
        """
        if self._project is None:
            return
        layout: dict[str, list[float]] = {}
        for svm in self._project_vm.state_vms:
            layout[svm.model.id] = [svm.x, svm.y]
        self._project.graph_layout = layout

        edge_layout: dict[str, list[list[float]]] = {}
        for tvm in self._project_vm.transition_vms:
            if tvm.waypoints:
                edge_layout[tvm.model.id] = [list(pt) for pt in tvm.waypoints]
        self._project.edge_layout = edge_layout

    def load_project(self, project: PluginProject) -> None:
        """기존 세션을 정리하고 새 프로젝트를 로드한다.

        열린 에디터 탭을 닫고, 프로젝트 VM(캔버스 상태)을 비운 뒤
        레지스트리/씬을 새 프로젝트로 재구성한다.
        """
        # 1) 열린 에디터 탭 정리 (고정 탭 제외, 역순 제거)
        for index in range(self._tabs.count() - 1, _LAST_FIXED_TAB_INDEX, -1):
            self._close_tab(index)
        self._open_tabs.clear()

        # 2) 프로젝트 VM(캔버스) 초기화
        self._project_vm.state_vms.clear()
        self._project_vm.transition_vms.clear()
        self._project_vm.reference_vms.clear()
        self._project_vm.reference_links.clear()

        # 3) 새 프로젝트 로드 — set_project가 registry/scene 갱신
        # (notify는 set_project → _load_project_graph 끝에서 1회 발화 — 중복 금지)
        self.set_project(project)

    # --- 저장 / 열기 ---

    def _sync_files_root(self) -> None:
        """FilePanel의 root를 `_current_path` 기준으로 재설정한다 (WP-FR).

        MCP 접속 정보의 프로젝트 경로도 같이 갱신한다 (WP-MCP) — CC가 지금 어떤
        프로젝트에 붙어 있는지 알 수 있도록. `_current_path`가 바뀌는 지점이
        여기 하나로 모여 있어 배선 지점도 하나로 유지된다.
        """
        project_dir = Path(self._current_path).parent if self._current_path else None
        self._file_panel.set_project_dir(project_dir)
        service = self._mcp_service
        if service is not None:
            service.update_project_path(self._current_path)  # type: ignore[attr-defined]

    def _update_title(self) -> None:
        base = "Daedalus — FSM Plugin Designer"
        if self._current_path:
            self.setWindowTitle(f"{package.display_name(self._current_path)} — {base}")
        else:
            self.setWindowTitle(base)

    def _save_to_path(self, path: str) -> bool:
        """프로젝트를 경로에 쓴다. 성공 여부를 돌려준다.

        반환값은 GUI 경로에서는 무시되지만(상태바 문구가 결과를 말한다) MCP의
        `open_project`처럼 **저장 성공을 전제로 다음 단계를 진행하는** 호출자는
        이 값으로 판정한다 — 실패를 못 보고 열면 그 순간 변경이 사라진다.
        """
        if self._project is None:
            return False
        # 폴더를 주면 그 안의 정본 파일이 저장 대상이다 (WP-PK). `_current_path`는
        # 계속 **파일**을 가리키므로 parent로 계산하는 곳들이 그대로 동작한다.
        target = str(package.resolve_project_file(path))
        # 저장 직전 캔버스 좌표를 graph_layout에 반영 (버그 1: 좌표 왕복)
        self._save_graph_layout()
        try:
            parent = Path(target).parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            data = serialize_project(self._project)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            # OSError: IO 실패 / TypeError·ValueError: 직렬화 불가 객체 혼입
            self._status_label.setText(f"저장 실패: {exc}")
            return False
        moved_files = self._carry_files_dir(target)
        path = target
        self._current_path = path
        self._update_title()
        self._sync_files_root()
        self._remember_recent(path)
        note = f" (files/ {moved_files}개 복사)" if moved_files else ""
        self._status_label.setText(f"저장됨: {path}{note}")
        return True

    def _carry_files_dir(self, new_file: str) -> int:
        """다른 폴더로 저장할 때 `files/`를 함께 옮긴다 (WP-PK).

        폴더가 곧 프로젝트이므로, 프로젝트를 다른 폴더에 저장했는데 동봉 파일이
        옛 폴더에 남아 있으면 그건 반쪽짜리 프로젝트다 — 컴파일하면 파일이
        빠지고, `dangling_file_ref` 경고로야 뒤늦게 드러난다.

        목적지에 이미 `files/`가 있으면 **건드리지 않는다** — 남의 것을 덮어쓰는
        것보다 아무것도 안 하는 편이 낫다(그 경우는 사용자가 의도한 배치다).
        """
        import shutil

        old = self._current_path
        if not old:
            return 0
        source = Path(old).parent / "files"
        dest = Path(new_file).parent / "files"
        if source.resolve() == dest.resolve() or not source.is_dir() or dest.exists():
            return 0
        try:
            shutil.copytree(source, dest, symlinks=False)
        except (OSError, shutil.Error) as exc:
            self._status_label.setText(f"files/ 복사 실패: {exc}")
            return 0
        return sum(1 for p in dest.rglob("*") if p.is_file())

    def _save_project(self) -> None:
        if self._current_path:
            self._save_to_path(self._current_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        """프로젝트 **폴더**를 골라 저장한다 (WP-PK).

        구버전 파일을 열어 두었더라도 여기서 폴더를 고르면 새 형식
        (`<폴더>/.daedalus.json`)으로 옮겨간다 — 그것이 형식을 바꾸는 유일한
        지점이다(Ctrl+S는 열려 있던 형식을 그대로 유지한다).
        """
        start = str(package.project_dir(self._current_path)) if self._current_path else ""
        directory = QFileDialog.getExistingDirectory(
            self, "프로젝트 폴더 선택 (폴더가 곧 프로젝트입니다)", start,
        )
        if directory:
            self._save_to_path(directory)

    def project_has_content(self) -> bool:
        """잃을 것이 있는 프로젝트인가 — 빈 프로젝트를 덮어쓰는 것은 손실이 아니다.

        "새 프로젝트"의 확인 다이얼로그와 MCP `open_project`의 저장 강제가 같은
        판정을 써야 한다 — 한쪽만 느슨하면 그 경로로만 변경이 사라진다.
        """
        project = self._project
        if project is None:
            return False
        return (
            bool(project.skills)
            or bool(project.agents)
            or bool(project.delegations)
            or len(project.graph.states) > 1  # EntryPoint 제외
        )

    def _new_project(self) -> None:
        """Ctrl+N — 새 빈 프로젝트를 생성한다.

        현재 프로젝트가 비어 있지 않으면(스킬/에이전트/위임/graph placement 중
        하나라도 존재) 저장 여부를 확인하는 다이얼로그를 표시한다. 빌드 타깃
        선택(WP-TG)을 취소하면 새 프로젝트 생성 자체를 취소한다.
        """
        if self._project is not None:
            if self.project_has_content():
                reply = QMessageBox.question(
                    self,
                    "새 프로젝트",
                    "저장하지 않은 변경이 사라질 수 있습니다.\n계속하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        target = self._prompt_build_target()
        if target is None:
            return  # 취소 — 프로젝트 생성 취소

        new_proj = PluginProject(name="new-plugin", build_target=target)
        self.load_project(new_proj)
        self._current_path = None
        self._update_title()
        self._sync_files_root()
        self._status_label.setText("새 프로젝트")

    def _prompt_build_target(self) -> BuildTarget | None:
        """새 프로젝트 생성 시 빌드 타깃을 고르게 한다. 취소 시 None(WP-TG)."""
        from daedalus.view.editors.project_properties import BUILD_TARGET_LABELS

        items = [label for _target, label in BUILD_TARGET_LABELS]
        choice, ok = QInputDialog.getItem(
            self, "빌드 타깃", "새 프로젝트의 빌드 타깃을 선택하세요:", items, 0, False,
        )
        if not ok:
            return None
        for target, label in BUILD_TARGET_LABELS:
            if label == choice:
                return target
        return BuildTarget.MARKETPLACE

    def _edit_project_properties(self) -> None:
        """"프로젝트 속성…" — name/description/version 편집.

        이름 규약 검사는 여기서 막지 않는다 — F7 경고 / 컴파일 게이트가 잡는다.
        """
        if self._project is None:
            return
        from daedalus.view.editors.project_properties import ProjectPropertiesDialog

        dialog = ProjectPropertiesDialog(self._project, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply_to(self._project)
            self._update_title()
            self._status_label.setText("프로젝트 속성 변경됨")

    def _open_project_dialog(self) -> None:
        """프로젝트 **폴더**를 골라 연다 (WP-PK).

        폴더 안의 정본(`.daedalus.json`)을 열고, 없으면 구버전
        `<이름>.daedalus.json` 하나를 받아들인다 — 기존 프로젝트 폴더도
        그대로 폴더째 열린다.
        """
        start = str(package.project_dir(self._current_path)) if self._current_path else ""
        directory = QFileDialog.getExistingDirectory(self, "프로젝트 폴더 열기", start)
        if directory:
            self.open_path(directory)

    def _open_file_dialog(self) -> None:
        """구버전 `<이름>.daedalus.json`을 파일로 직접 연다.

        한 폴더에 구버전 파일이 여럿이면 폴더 선택으로는 무엇을 여는지 정할 수
        없다 — 그때 쓰는 통로다.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "프로젝트 파일 열기", self._current_path or "",
            "Daedalus 프로젝트 (*.daedalus.json *.json)",
        )
        if path:
            self.open_path(path)

    # --- 패키지 (.ddpj) ---

    def _export_package_dialog(self) -> None:
        """현재 프로젝트 폴더를 `.ddpj` 하나로 묶는다.

        지금까지 프로젝트를 남에게 주려면 "json이랑 files 폴더를 같이 보내라"고
        해야 했다 — 틀리기 쉬운 안내였다.
        """
        if not self._current_path:
            QMessageBox.information(
                self, "패키지로 내보내기",
                "먼저 프로젝트를 저장하세요. 묶을 폴더가 정해져야 합니다.",
            )
            return
        source = package.project_dir(self._current_path)
        suggested = str(source.parent / package.default_archive_name(self._current_path))
        target, _ = QFileDialog.getSaveFileName(
            self, "패키지로 내보내기", suggested,
            f"Daedalus 패키지 (*{package.ARCHIVE_SUFFIX})",
        )
        if not target:
            return
        try:
            members = package.pack(source, target)
        except (package.PackageError, OSError) as exc:
            self._status_label.setText(f"내보내기 실패: {exc}")
            return
        self._status_label.setText(f"내보냄: {target} ({len(members)}개 파일)")

    def _import_package_dialog(self) -> None:
        """`.ddpj`를 폴더에 풀고 그 프로젝트를 연다.

        압축 안에서 직접 편집하지 않는다 — `files/` 드래그·컴파일·저장이 전부
        특수 경로가 되어 득보다 실이 크다.
        """
        archive, _ = QFileDialog.getOpenFileName(
            self, "패키지 가져오기", "",
            f"Daedalus 패키지 (*{package.ARCHIVE_SUFFIX})",
        )
        if not archive:
            return
        dest = QFileDialog.getExistingDirectory(
            self, "풀어놓을 폴더 선택 (비어 있어야 합니다)",
            str(Path(archive).parent),
        )
        if not dest:
            return
        try:
            project_file = package.unpack(archive, dest)
        except (package.PackageError, OSError) as exc:
            self._status_label.setText(f"가져오기 실패: {exc}")
            return
        self.open_path(str(project_file))

    # --- 최근 프로젝트 (WP-RP) ---

    def _remember_recent(self, path: str) -> None:
        """열기/저장이 성공한 경로를 최근 목록 맨 앞으로 올린다."""
        recent.push(path)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        """"최근 프로젝트" 서브메뉴를 목록 파일로부터 다시 만든다."""
        menu = self._recent_menu
        if menu is None:
            return
        menu.clear()

        paths = recent.load()
        if not paths:
            empty = menu.addAction("(없음)")
            if empty is not None:
                empty.setEnabled(False)
            return

        for index, path in enumerate(paths, start=1):
            action = QAction(self._recent_label(index, path), self)
            action.setToolTip(path)
            action.setStatusTip(path)
            # 기본 인자로 path를 묶어 둔다 — 늦은 바인딩이면 전부 마지막 경로를 연다
            action.triggered.connect(
                lambda _checked=False, p=path: self._open_recent(p)
            )
            menu.addAction(action)

        menu.addSeparator()
        clear_action = QAction("목록 지우기", self)
        clear_action.triggered.connect(self._clear_recent)
        menu.addAction(clear_action)

    @staticmethod
    def _recent_label(index: int, path: str) -> str:
        """`&1 파일명 — 상위폴더` 형태의 메뉴 라벨.

        파일명만으로는 구분이 안 되는 경우가 흔해(`project.daedalus.json` 등)
        상위 폴더 이름을 함께 보인다. 전체 경로는 툴팁에 있다.

        새 형식(WP-PK)에서는 파일 이름이 `.daedalus.json` 하나뿐이라 그대로
        보이면 전부 같은 이름이 된다 — 그때는 폴더 이름이 곧 이름이고, 상위
        폴더는 그 위 단계가 된다.
        """
        shown = path
        if os.path.basename(path) == package.PROJECT_FILENAME:
            shown = os.path.dirname(path)
        name = os.path.basename(shown)
        parent = os.path.basename(os.path.dirname(shown))
        if parent:
            name = f"{name} — {parent}"
        # 파일명의 &는 니모닉으로 먹히므로 escape
        name = name.replace("&", "&&")
        return f"&{index} {name}" if index < 10 else name

    def _open_recent(self, path: str) -> None:
        """최근 항목을 연다. 파일이 사라졌으면 목록에서 떨군다."""
        if not os.path.exists(path):
            recent.remove(path)
            self._rebuild_recent_menu()
            self._status_label.setText(f"파일을 찾을 수 없어 목록에서 제거했습니다: {path}")
            return
        self.open_path(path)

    def _clear_recent(self) -> None:
        recent.clear()
        self._rebuild_recent_menu()
        self._status_label.setText("최근 프로젝트 목록을 비웠습니다")

    def open_path(self, path: str) -> bool:
        """경로에서 프로젝트를 로드한다 (다이얼로그 없이 — 테스트/CLI/MCP 재사용).

        폴더를 주면 그 안의 프로젝트 파일을 찾아 연다 (WP-PK) — 정본
        `.daedalus.json`이 우선, 없으면 구버전 `<이름>.daedalus.json` 하나.

        성공 여부를 돌려준다 — `_save_to_path`와 같은 이유다(호출자가 실패를
        구분해야 한다). GUI 경로는 상태바 문구로 결과를 말하므로 무시한다.
        """
        deser_warnings: list[str] = []
        try:
            path = str(package.find_project_file(path))
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = deserialize_project(data, collect_warnings=deser_warnings)
        except (OSError, ValueError, package.PackageError) as exc:
            self._status_label.setText(f"열기 실패: {exc}")
            return False
        self.load_project(project)
        self._current_path = path
        self._update_title()
        self._sync_files_root()
        self._remember_recent(path)
        fname = os.path.basename(path)
        if deser_warnings:
            self._status_label.setText(
                f"열림: {fname} (경고 {len(deser_warnings)}건 — F7로 확인)"
            )
        else:
            self._status_label.setText(f"열림: {fname}")
        return True

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
        self._sync_tab_titles()
        # 상주 패널은 자기 편집만 알므로, 바깥(MCP 등)에서 온 변경을 여기서
        # 반영한다 — 패널 자신이 발화한 notify는 각 패널이 알아서 건너뛴다.
        self._hook_panel.refresh_external()
        self._blackboard_panel.refresh_external()

    def _sync_agent_editors(self) -> None:
        """열린 AgentEditor 탭의 계약 패널 동기화."""
        from daedalus.view.editors.agent_editor import AgentEditor as _AE
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if isinstance(widget, _AE) and hasattr(widget, "_caller_contract_panel"):
                widget._caller_contract_panel.refresh()

    def _sync_tab_titles(self) -> None:
        """열린 탭의 타이틀을 현재 컴포넌트 이름과 동기화한다.

        _open_tabs 키는 컴포넌트 id(str). 탭에 연결된 editor의 컴포넌트 이름을
        읽어 탭 텍스트가 달라졌으면 갱신한다. 키스트로크마다 notify가 오더라도
        문자열 비교로 갱신 여부를 판단하므로 비용이 낮다.
        """
        from daedalus.model.plugin.delegation import DelegationDef
        for comp_id, tab_idx in self._open_tabs.items():
            widget = self._tabs.widget(tab_idx)
            if widget is None:
                continue
            # editor에서 컴포넌트 이름을 읽는다
            comp: object | None = None
            from daedalus.view.editors.agent_editor import AgentEditor as _AE
            from daedalus.view.editors.skill_editor import SkillEditor as _SE
            if isinstance(widget, _AE):
                comp = getattr(widget, "_agent", None)
            elif isinstance(widget, _SE):
                # SkillEditor → ComponentEditor._fm._component
                editor = getattr(widget, "_editor", None)
                if editor is not None:
                    fm = getattr(editor, "_fm", None)
                    if fm is not None:
                        comp = getattr(fm, "_component", None)
            if comp is None:
                continue
            name = getattr(comp, "name", None)
            if name is None:
                continue
            # 아이콘 프리픽스 포함 여부에 따라 현재 탭 텍스트를 비교
            current_text = self._tabs.tabText(tab_idx)
            if isinstance(comp, AgentDefinition):
                expected = f"🤖 {name}"
            elif isinstance(comp, DelegationDef):
                icon = {"team_spawn": "👥", "dynamic_workflow": "🔀", "agora_dispatch": "🛰"}.get(comp.kind, "🛰")
                expected = f"{icon} {name}"
            else:
                expected = name
            if current_text != expected:
                self._tabs.setTabText(tab_idx, expected)

    # --- 컴포넌트 이름 변경 ---

    def _on_component_renamed(self, component: object, old_name: str, new_name: str) -> None:
        """_FrontmatterPanel.renamed 시그널 핸들러.

        1. 중복 이름 검사 — 다른 컴포넌트와 동명이면 거부(component.name을 old로 원복).
        2. rename_component로 문자열 참조 일괄 갱신.
        3. notify(structure) — 레지스트리/탭 타이틀 갱신 트리거.
        """
        if self._project is None:
            return

        # 중복 이름 방지
        existing = (
            {s.name for s in self._project.skills if s is not component}
            | {a.name for a in self._project.agents if a is not component}
            | {d.name for d in self._project.delegations if d is not component}
        )
        if new_name in existing:
            QMessageBox.warning(
                self, "이름 중복",
                f"'{new_name}' 이름이 이미 존재합니다.\n이름이 원래대로 되돌아갑니다.",
            )
            # component.name이 이미 new_name으로 바뀌었으므로 old_name으로 원복
            component.name = old_name  # type: ignore[union-attr]
            return

        # component.name은 _save_name에서 renamed 발화 전에 아직 old_name임.
        # RenameComponentCmd가 old_name → new_name 변경 + 참조 갱신을 수행하고,
        # undo 시 같은 함수를 옛 이름으로 불러 대칭으로 되돌린다 (WP-CE).
        from daedalus.view.commands.component_commands import RenameComponentCmd

        self._project_vm.execute(
            RenameComponentCmd(self._project, component, old_name, new_name)
        )

    # --- 컴포넌트 삭제 ---

    def _on_delete_component(self, component: object) -> None:
        """레지스트리 우클릭 '삭제' → 확인 후 모델·뷰 정리."""
        from daedalus.model.project import remove_component

        if self._project is None:
            return

        comp_name = getattr(component, "name", str(component))
        comp_id = getattr(component, "id", None)

        # 참조 요약 수집 (간략 — validate 없이 빠른 사전 검사)
        ref_lines: list[str] = []
        if self._project is not None:
            from daedalus.model.fsm.state import SimpleState
            from daedalus.model.plugin.delegation import DynamicWorkflowDef, TeamSpawnDef

            def _scan_fsm_refs(sm_obj) -> int:
                count = 0
                if sm_obj is None:
                    return 0
                for state in sm_obj.states:
                    if isinstance(state, SimpleState) and state.skill_ref is component:
                        count += 1
                return count

            for sk in self._project.skills:
                n = _scan_fsm_refs(getattr(sk, "fsm", None))
                if n:
                    ref_lines.append(f"  스킬 '{sk.name}'의 FSM: {n}개 배치")
            for ag in self._project.agents:
                n = _scan_fsm_refs(getattr(ag, "fsm", None))
                if n:
                    ref_lines.append(f"  에이전트 '{ag.name}'의 FSM: {n}개 배치")
            for dl in self._project.delegations:
                if isinstance(dl, TeamSpawnDef):
                    for spec in dl.teammates:
                        if spec.agent_ref is component:
                            ref_lines.append(f"  위임 '{dl.name}' teammates 참조")
                elif isinstance(dl, DynamicWorkflowDef):
                    for phase in dl.phases:
                        if phase.agent_ref is component:
                            ref_lines.append(f"  위임 '{dl.name}' phases 참조")

        msg = f"'{comp_name}'을(를) 삭제하시겠습니까?"
        if ref_lines:
            msg += "\n\n다음 위치에서 참조 중입니다 (삭제 시 None으로 정리됩니다):\n"
            msg += "\n".join(ref_lines[:10])
            if len(ref_lines) > 10:
                msg += f"\n  ... 외 {len(ref_lines) - 10}건"

        reply = QMessageBox.question(
            self,
            "컴포넌트 삭제",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 에이전트 삭제 시 로컬 스킬 탭도 닫아야 함 — 미리 수집
        local_skill_ids: set[str] = set()
        local_skills: list[object] = []
        if isinstance(component, AgentDefinition):
            fsm = getattr(component, "fsm", None)
            if fsm is not None:
                from daedalus.model.fsm.state import SimpleState
                for state in fsm.states:
                    if isinstance(state, SimpleState) and state.skill_ref is not None:
                        sid = getattr(state.skill_ref, "id", None)
                        if sid is not None:
                            local_skill_ids.add(sid)
                            local_skills.append(state.skill_ref)

        # 본문 문서 캐시 정리 — 삭제된 컴포넌트(+로컬 스킬)의 undo 이력을
        # 들고 있을 이유가 없다 (WP-BU).
        from daedalus.view.editors import body_documents
        docs = body_documents.registry()
        docs.discard(component)
        for local in local_skills:
            docs.discard(local)

        # 모델 정리
        remove_component(self._project, component)

        # view 정리 1) 열린 탭 닫기 (해당 컴포넌트 탭 + 로컬 스킬 탭)
        ids_to_close: set[str] = set()
        if comp_id is not None:
            ids_to_close.add(comp_id)
        ids_to_close.update(local_skill_ids)

        for cid in list(ids_to_close):
            if cid in self._open_tabs:
                self._close_tab(self._open_tabs[cid])

        # view 정리 2) 캔버스 + 레지스트리 + notify
        self._load_project_graph()
        self._registry_panel.set_project(self._project)
        self._project_vm.notify()
        self._status_label.setText(f"'{comp_name}' 삭제됨")

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
            # AgentEditor._component_editor._fm.renamed → 이름 변경 처리
            fm = getattr(getattr(editor, "_component_editor", None), "_fm", None)
            if fm is not None and hasattr(fm, "renamed"):
                fm.renamed.connect(self._on_component_renamed)
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
            # SkillEditor._editor._fm.renamed → 이름 변경 처리
            fm = getattr(getattr(editor, "_editor", None), "_fm", None)
            if fm is not None and hasattr(fm, "renamed"):
                fm.renamed.connect(self._on_component_renamed)
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
        """컴포넌트를 프로젝트에 등록한다 (WP-CE — 커맨드 경유라 Ctrl+Z로 되돌아간다).

        리스트 추가와 블랙보드 스코핑 배선은 CreateComponentCmd가 전담한다.
        """
        if self._project is None:
            return
        from daedalus.view.commands.component_commands import CreateComponentCmd

        self._project_vm.execute(CreateComponentCmd(self._project, component))
        self._registry_panel.set_project(self._project)

    _COMPONENT_TITLES = {
        "procedural": "새 Procedural Skill",
        "declarative": "새 Declarative Skill",
        "transfer": "새 Transfer Skill",
        "reference": "새 Reference Skill",
        "agent": "새 Agent",
    }

    def _on_new_component(self, kind: str) -> None:
        if kind not in self._COMPONENT_TITLES:
            return  # delegation 등 생성이 격하된 종류 — 프로그램적 발화 방어
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

    def _close_tab(self, index: int) -> None:
        if index in _FIXED_TAB_INDEXES:
            return  # Project FSM / 블랙보드 / 훅은 닫을 수 없음
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
        try:
            selected = self._fsm_scene.selectedItems()
        except RuntimeError:
            # 씬의 C++ 객체가 이미 파괴된 뒤 지연 발화된 시그널 — 무시
            # (agent_editor._on_graph_selection과 동일 가드).
            return
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

        files_dir = Path(self._current_path).parent / "files" if self._current_path else None
        result = compile_project(self._project, out_dir, files_dir=files_dir)
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
        copied_str = f" / files {len(result.copied_files)}개 복사" if result.copied_files else ""
        self._status_label.setText(
            f"컴파일 완료: {len(result.written)}파일 생성{copied_str}{warn_str} → {out_dir}"
        )
        if warn:
            # F7 검증 흐름과 동일하게 dock도 표시 — 경고를 상태바 문구로만
            # 인지하게 두지 않는다.
            self._validation_panel.set_errors(result.warnings)
            self._show_validation_dock()

    # --- MCP 서버 (WP-MCP) ---

    def start_mcp_service(self, port: int | None = None) -> None:
        """앱과 함께 MCP 서버를 띄운다 — 실제 실행 경로에서만 호출된다.

        __init__에서 자동으로 시작하지 않는 이유: 테스트가 MainWindow를 수십 개
        만들기 때문에 매번 포트를 잡으면 서로 충돌한다.

        port를 주면 그 포트만 쓴다(`--mcp-port`). 여러 인스턴스를 동시에 띄우고
        각각 다른 CC 세션과 붙일 때 쓴다.
        """
        from daedalus.mcp.service import DaedalusMCPService

        service = DaedalusMCPService(self)
        self._mcp_service = service
        port = service.start(port)
        if port is None:
            self._status_label.setText(f"MCP 서버 시작 실패 — {service.error}")
        else:
            self._status_label.setText(f"MCP 서버 대기 중 — {service.url}")

    def _show_mcp_info(self) -> None:
        """도구 메뉴 — 접속 주소와 .mcp.json 설정 조각을 보여준다."""
        from daedalus.mcp import endpoint

        service = self._mcp_service
        if service is None or not getattr(service, "running", False):
            reason = getattr(service, "error", None) if service is not None else None
            QMessageBox.information(
                self,
                "MCP 서버",
                "MCP 서버가 실행 중이 아닙니다."
                + (f"\n\n{reason}" if reason else ""),
            )
            return

        port = service.port
        text = (
            f"접속 주소: {service.url}\n\n"
            "Claude Code에서 쓰려면 프로젝트의 .mcp.json에 아래를 넣으세요:\n\n"
            f"{endpoint.mcp_json_snippet(port)}\n\n"
            f"접속 정보 파일: {endpoint.ENDPOINT_PATH}"
        )
        box = QMessageBox(self)
        box.setWindowTitle("MCP 서버")
        box.setText("Claude Code와 협업할 준비가 되었습니다.")
        box.setDetailedText(text)
        box.exec()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """앱이 닫히면 MCP 서버도 함께 내린다."""
        service = self._mcp_service
        if service is not None:
            try:
                service.stop()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — 종료 경로를 막지 않는다
                pass
        super().closeEvent(event)

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
        """프로젝트 FSM 캔버스(탭 0)에서 subject와 identity 일치하는 노드를 선택+센터링.

        subject가 캔버스에 없으면(삭제된 노드 등) 상태바에 안내를 표시하고 no-op.
        """
        # 프로젝트 자체가 subject인 검증 항목(예: 프로젝트 이름 규약)은 캔버스
        # 노드가 아니다 — 조치 위치를 안내하고 끝낸다.
        if subject is self._project:
            self._status_label.setText(
                "프로젝트 이름/속성은 파일 → 프로젝트 속성…에서 수정하세요."
            )
            return
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
        # subject가 캔버스에 없음 — 삭제된 노드일 수 있음
        name = getattr(subject, "name", None)
        if name:
            self._status_label.setText(
                f"'{name}' 노드가 캔버스에 없습니다 (이미 삭제되었을 수 있습니다)."
            )

    def _focus_in_agent_tab(self, agent_name: str, subject: object) -> None:
        """에이전트 탭이 열려 있으면 해당 노드를 포커스, 없으면 상태바 안내.

        subject가 캔버스에 없으면(삭제된 노드 등) 상태바에 안내를 표시하고 no-op.
        """
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
                    # 탭은 열려있지만 subject를 찾지 못함 — 삭제된 노드일 수 있음
                    name = getattr(subject, "name", None)
                    if name:
                        self._status_label.setText(
                            f"'{name}' 노드가 에이전트 '{agent_name}' 캔버스에 없습니다 "
                            f"(이미 삭제되었을 수 있습니다)."
                        )
                    return
        # 탭이 열려 있지 않음
        self._status_label.setText(
            f"에이전트 '{agent_name}' 탭을 열어 확인하세요."
        )
