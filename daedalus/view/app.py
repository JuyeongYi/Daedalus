# daedalus/view/app.py
"""Daedalus 메인 윈도우 골격 (WP-RF-3e).

윈도우가 직접 갖는 것은 **탭·독·메뉴 배선과 컴포넌트 편집 진입**뿐이다.
세션 입출력·컴파일·실행·검증은 각각 협력 객체(Mixin 아님)가 맡는다:

| 협력 객체 | 모듈 | 담당 |
|---|---|---|
| `SessionIO` | `view/session_io.py` | 저장/열기/최근 목록/패키지(.ddpj) |
| `CompileActions` | `view/compile_actions.py` | Ctrl+B 컴파일 + 서버 정의 주입 |
| `LaunchActions` | `view/launch_actions.py` | MCP 서버 수명주기 · Claude Code 실행 |
| `ValidationActions` | `view/validation_actions.py` | F7 검증 · 결과 항목 노드 포커스 |

**협력 객체가 실체이고 `MainWindow`에는 같은 이름의 한 줄 위임 메서드만
남는다** — 테스트와 MCP 도구가 `window._save_to_path(...)`처럼 윈도우의
내부 메서드를 직접 호출하기 때문이다. 상태(`_project`/`_current_path`/
`_mcp_service` …)의 단일 진실은 계속 윈도우에 있고, 협력 객체는 그것을
복제하지 않고 직접 읽고 쓴다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,  # noqa: F401 — 테스트가 이 모듈 경로로 다이얼로그를 몽키패치한다
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)

from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.model.validation import ValidationError
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.compile_actions import CompileActions
from daedalus.view.editors.skill_editor import SkillEditor
from daedalus.view.launch_actions import LaunchActions
from daedalus.view.panels.file_panel import FilePanel
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.registry_panel import RegistryPanel
from daedalus.view.panels.script_listener import ScriptListenerPanel
from daedalus.view.panels.validation_panel import ValidationPanel
from daedalus.view.session_io import SessionIO, recent_label
from daedalus.view.validation_actions import ValidationActions
from daedalus.view.viewmodel.project_vm import ProjectViewModel

_FSM_TAB_INDEX = 0  # 프로젝트 FSM 캔버스는 항상 탭 0
_BLACKBOARD_TAB_INDEX = 1  # 블랙보드 편집 탭은 항상 탭 1 (WP-BB — 닫기 불가 고정 탭)
_HOOK_TAB_INDEX = 2  # 훅 라이브러리 탭은 항상 탭 2 (WP-HK — 닫기 불가 고정 탭)
_CLAUDE_MD_TAB_INDEX = 3  # .claude/CLAUDE.md 구역 탭 (WP-WD — 닫기 불가 고정 탭)
_RULES_TAB_INDEX = 4  # .claude/rules/ 탭 (WP-WD — 닫기 불가 고정 탭)
# 고정 탭 = 컴포넌트 에디터가 아닌 상주 탭. 새 에디터는 이 뒤에 붙는다.
_FIXED_TAB_INDEXES = (
    _FSM_TAB_INDEX, _BLACKBOARD_TAB_INDEX, _HOOK_TAB_INDEX,
    _CLAUDE_MD_TAB_INDEX, _RULES_TAB_INDEX,
)
_LAST_FIXED_TAB_INDEX = max(_FIXED_TAB_INDEXES)


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._current_path: str | None = None  # 현재 저장 경로 (.daedalus.json)
        # 미저장 변경 플래그 (A7) — notify 양 채널 리스너가 True로 올리고,
        # 저장/로드/새 프로젝트가 내린다. closeEvent가 이 값으로 종료를 막는다.
        self._dirty = False
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

        # 협력 객체 (WP-RF-3e) — 위젯 배선보다 **먼저** 만든다: _setup_menus가
        # 최근 목록 서브메뉴를 채우며 곧바로 _session_io를 부른다.
        self._session_io = SessionIO(self)
        self._compile_actions = CompileActions(self)
        self._launch_actions = LaunchActions(self)
        self._validation_actions = ValidationActions(self)

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

        # 작업 폴더 문서 — 항상 탭 3·4, 닫을 수 없음 (WP-WD). CLAUDE.md와 규칙을
        # 한 탭에 목록으로 묶지 않고 각각 최상위로 둔 것은 사용자 확정이다 —
        # CLAUDE.md는 하나뿐이고 규칙은 여럿이라 성격이 다르다.
        from daedalus.view.editors.workspace_editor import ClaudeMdPanel, RulesPanel
        self._claude_md_panel = ClaudeMdPanel(on_notify_fn=self._project_vm.notify)
        self._tabs.addTab(self._claude_md_panel, "📌 CLAUDE.md")
        self._rules_panel = RulesPanel(on_notify_fn=self._project_vm.notify)
        self._tabs.addTab(self._rules_panel, "📐 규칙")

        # 고정 탭의 닫기 버튼 숨김
        tab_bar = self._tabs.tabBar()
        if tab_bar is not None:
            for index in _FIXED_TAB_INDEXES:
                tab_bar.setTabButton(index, tab_bar.ButtonPosition.RightSide, None)

        # 프로젝트 VM 변경 시 레지스트리 dim 갱신
        self._project_vm.add_listener(self._on_project_vm_changed)
        # 미저장 변경 감지 (A7) — **양 채널 모두** 등록해야 한다. notify("content")는
        # content 리스너만 부르므로(project_vm.notify) structure 한쪽만 등록하면
        # 본문 타이핑(body_documents 경로)이 통째로 새어 나간다.
        self._project_vm.add_listener(self._mark_dirty)
        self._project_vm.add_listener(self._mark_dirty, scope="content")

    def _setup_docks(self) -> None:
        self._registry_panel = RegistryPanel()
        registry_dock = QDockWidget("Registry")
        registry_dock.setWidget(self._registry_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, registry_dock)

        # 파일 독 패널 (WP-FR) — 프로젝트 옆 files/ 트리. _current_path 변경 시점
        # (저장/열기/새 프로젝트)마다 _sync_files_root가 루트를 재설정한다.
        # 레지스트리 **아래에** 배치(WP-SF 배치 개편, 사용자 확정) — 레지스트리가
        # 탭으로 컴팩트해졌으므로 좌측 열을 세로 스택으로 좁게 쓰고 에디터가
        # 가로 공간을 가져간다. 스킬별 파일은 스킬 에디터 우측 SkillFilesPanel.
        self._file_panel = FilePanel()
        file_dock = QDockWidget("플러그인 파일 (공용)")
        file_dock.setWidget(self._file_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, file_dock)
        self.splitDockWidget(registry_dock, file_dock, Qt.Orientation.Vertical)
        from daedalus.view.panels.file_panel import set_project_dir_provider
        from daedalus.view.widgets.markdown_editor import (
            set_files_root_provider,
            set_skill_files_root_provider,
        )
        set_files_root_provider(lambda: self._file_panel.files_root())
        set_skill_files_root_provider(lambda: self._file_panel.skill_files_root())
        set_project_dir_provider(
            lambda: str(Path(self._current_path).parent) if self._current_path else None
        )

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

            self._launch_cc_action = QAction("Claude Code 실행", self)
            self._launch_cc_action.setToolTip(
                "프로젝트 폴더에서 Claude Code를 연다 (MCP 서버 실행 중일 때)"
            )
            self._launch_cc_action.triggered.connect(self._launch_claude_code)
            tools_menu.addAction(self._launch_cc_action)

            tools_menu.addSeparator()

            cat_global = QAction("도구 카탈로그 (전역)...", self)
            cat_global.setToolTip(
                "~/.daedalus/catalogue/ — 모든 프로젝트에서 쓸 MCP·도구 후보"
            )
            cat_global.triggered.connect(self._open_global_catalogue)
            tools_menu.addAction(cat_global)

            cat_project = QAction("도구 카탈로그 (프로젝트)...", self)
            cat_project.setToolTip(
                "<프로젝트>/.daedalus/catalogue/ — 이 프로젝트 전용 후보 (전역을 덮음)"
            )
            cat_project.triggered.connect(self._open_project_catalogue)
            tools_menu.addAction(cat_project)

            global_hooks = QAction("전역 훅 폴더 열기...", self)
            global_hooks.setToolTip(
                "~/.daedalus/hooks/ — 모든 프로젝트에서 이름으로 참조할 수 있는 훅"
            )
            global_hooks.triggered.connect(self._open_global_hooks_dir)
            tools_menu.addAction(global_hooks)

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
        self._claude_md_panel.set_project(project)
        self._rules_panel.set_project(project)
        if self._fsm_scene is not None:
            self._fsm_scene.set_project(project)
        # HOOKS TagInput이 이 프로젝트의 hook_library 이름을 후보로 표시하도록 연결.
        # 전역 훅(A1)도 이름으로 참조할 수 있으므로 후보에 함께 낸다 — 목록에
        # 안 보이면 있는 줄 모르고, set_component_hooks가 거절하지 않는 이름이
        # 후보에서만 빠져 있으면 둘이 다른 말을 하는 셈이 된다.
        from daedalus.view.widgets.tag_input import set_hook_name_provider
        set_hook_name_provider(lambda: list(self.resolved_hooks()))
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
        # 변수 팝업의 빌드 타깃 제공자 — 팝업을 열 때마다 조회하므로 프로젝트
        # 속성에서 타깃을 바꾸면 즉시 반영된다(로컬 빌드는 ${CLAUDE_PLUGIN_ROOT}
        # 사용 불가 — 사용자 확정 매트릭스).
        from daedalus.view.editors.variable_loader import set_build_target_provider

        set_build_target_provider(
            lambda: getattr(self._project, "build_target", None)
        )
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

        # 4) 방금 로드한 상태는 미저장 변경이 아니다 (A7). 위 notify가 _mark_dirty를
        # 깨우므로 **로드 뒤에** 내려야 한다 — 호출자(open_path/new_project)가
        # 각자 내리게 하면 새 경로가 생길 때마다 빠뜨린다.
        self.mark_clean()

    # --- 훅 해소 (A1) ---

    def resolved_hooks(self) -> dict:
        """이름 → HookDef, 전역(`~/.daedalus/hooks/`) ← 프로젝트 순 (A1).

        **파일시스템을 읽는 지점은 여기 하나다.** 검증기와 컴파일러는 순수하게
        유지되고(같은 프로젝트가 검증한 사람의 홈에 따라 다른 결과를 내면 안
        된다), 해소된 사전을 이 메서드가 만들어 그쪽에 주입한다 — F7 검증,
        Ctrl+B 컴파일, MCP 도구가 전부 이것을 부른다.

        캐시하지 않는다 — 전역 폴더에 파일을 떨어뜨리고 곧바로 F7을 누르면
        반영되는 것이 기대 동작이고, 파일 몇 개짜리 glob이라 비용이 없다.
        """
        from daedalus.model.plugin.hook_store import resolve_hooks

        if self._project is None:
            return {}
        return resolve_hooks(self._project)

    def _open_global_hooks_dir(self) -> None:
        """도구 메뉴 — 전역 훅 폴더를 탐색기로 연다 (없으면 만든다)."""
        from daedalus.model.plugin.hook_store import global_hooks_dir

        hooks_dir = global_hooks_dir()
        hooks_dir.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(hooks_dir)))

    # --- 미저장 변경 (A7) ---

    def _mark_dirty(self) -> None:
        """편집이 일어났다 — 창 제목에 `*`를 붙인다.

        키스트로크마다 오는 content notify가 여기로 들어오므로, 이미 dirty면
        즉시 돌아가 setWindowTitle 재호출을 피한다.
        """
        if self._dirty:
            return
        self._dirty = True
        self._update_title()

    def mark_clean(self) -> None:
        """저장/로드 직후 — 미저장 변경 없음으로 표시하고 제목의 `*`를 지운다."""
        if not self._dirty:
            return
        self._dirty = False
        self._update_title()

    def confirm_discard_changes(self) -> bool:
        """미저장 변경이 있으면 저장 여부를 묻는다. 진행해도 되면 True.

        "저장 후 종료"를 골랐는데 저장이 실패하거나(경로 선택 취소 포함) 여전히
        dirty면 **종료를 막는다** — 저장하겠다고 답한 사용자의 변경을 그대로
        버리는 것이 이 기능이 막으려던 사고 그 자체다.
        """
        if not self._dirty or self._project is None:
            return True
        reply = QMessageBox.question(
            self,
            "저장하지 않은 변경",
            "저장하지 않은 변경이 있습니다.\n저장한 뒤 종료할까요?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            self._save_project()
            return not self._dirty
        return True  # Discard — 버리고 진행

    # --- 세션 입출력 위임 (실체는 view/session_io.SessionIO) ---

    def _sync_files_root(self) -> None:
        self._session_io.sync_files_root()

    def _update_title(self) -> None:
        self._session_io.update_title()

    def _save_to_path(self, path: str) -> bool:
        return self._session_io.save_to_path(path)

    def _carry_files_dir(self, new_file: str) -> int:
        return self._session_io.carry_files_dir(new_file)

    def _save_project(self) -> None:
        self._session_io.save_project()

    def _save_project_as(self) -> None:
        self._session_io.save_project_as()

    def project_has_content(self) -> bool:
        return self._session_io.project_has_content()

    def _new_project(self) -> None:
        self._session_io.new_project()

    def _prompt_build_target(self) -> BuildTarget | None:
        return self._session_io.prompt_build_target()

    def _edit_project_properties(self) -> None:
        self._session_io.edit_project_properties()

    def _open_project_dialog(self) -> None:
        self._session_io.open_project_dialog()

    def _open_file_dialog(self) -> None:
        self._session_io.open_file_dialog()

    def _export_package_dialog(self) -> None:
        self._session_io.export_package_dialog()

    def _import_package_dialog(self) -> None:
        self._session_io.import_package_dialog()

    def _remember_recent(self, path: str) -> None:
        self._session_io.remember_recent(path)

    def _rebuild_recent_menu(self) -> None:
        self._session_io.rebuild_recent_menu()

    # 순수 함수라 인스턴스가 필요 없다 — `MainWindow._recent_label(...)`로 직접 쓴다.
    _recent_label = staticmethod(recent_label)

    def _open_recent(self, path: str) -> None:
        self._session_io.open_recent(path)

    def _clear_recent(self) -> None:
        self._session_io.clear_recent()

    def open_path(self, path: str) -> bool:
        return self._session_io.open_path(path)

    # --- 컴파일 위임 (실체는 view/compile_actions.CompileActions) ---

    def _compile_project_dialog(self) -> None:
        self._compile_actions.compile_project_dialog()

    def _known_server_defs(self) -> dict[str, dict]:
        return self._compile_actions.known_server_defs()

    # --- MCP 서버 / Claude Code 실행 위임 (실체는 view/launch_actions.LaunchActions) ---

    def start_mcp_service(self, port: int | None = None) -> None:
        self._launch_actions.start_mcp_service(port)

    def _show_mcp_info(self) -> None:
        self._launch_actions.show_mcp_info()

    def _launch_claude_code(self) -> None:
        self._launch_actions.launch_claude_code()

    def _ensure_daedalus_mcp_json(self, work_dir: str) -> None:
        self._launch_actions.ensure_daedalus_mcp_json(work_dir)

    def _open_global_catalogue(self) -> None:
        """도구 메뉴 — 전역 카탈로그 폴더를 탐색기로 연다 (없으면 만든다)."""
        cat_dir = Path.home() / ".daedalus" / "catalogue"
        cat_dir.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cat_dir)))

    def _open_project_catalogue(self) -> None:
        """도구 메뉴 — 프로젝트 카탈로그 폴더를 탐색기로 연다 (없으면 만든다)."""
        if not self._current_path:
            self._status_label.setText("프로젝트를 먼저 저장하세요.")
            return
        cat_dir = Path(self._current_path).parent / ".daedalus" / "catalogue"
        cat_dir.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cat_dir)))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """미저장 변경을 확인한 뒤 닫고, 닫으면 MCP 서버도 함께 내린다 (A7).

        MCP/GUI 편집은 메모리에만 있으므로 확인 없이 닫으면 그대로 사라진다
        (실사고 3회). 취소를 고르면 `event.ignore()`로 창을 유지한다 — MCP
        서버도 내리지 않는다(닫지 않았으니 세션은 계속된다).
        """
        if not self.confirm_discard_changes():
            event.ignore()
            return
        self._launch_actions.stop_mcp_service()
        super().closeEvent(event)

    # --- 검증 위임 (실체는 view/validation_actions.ValidationActions) ---

    def _run_validation(self) -> None:
        self._validation_actions.run_validation()

    def _show_validation_dock(self) -> None:
        self._validation_actions.show_validation_dock()

    def _find_validation_dock(self) -> QDockWidget | None:
        return self._validation_actions.find_validation_dock()

    def _on_validation_item_activated(self, error: ValidationError) -> None:
        self._validation_actions.on_validation_item_activated(error)

    def show_component_findings(self, component: object) -> int:
        return self._validation_actions.show_component_findings(component)

    def _focus_in_project_canvas(self, subject: object) -> None:
        self._validation_actions.focus_in_project_canvas(subject)

    def _focus_in_agent_tab(self, agent_name: str, subject: object) -> None:
        self._validation_actions.focus_in_agent_tab(agent_name, subject)

    # --- 조회 / 동기화 ---

    def _skill_lookup(self, name: str) -> object | None:
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
        self._sync_agent_editors()
        self._sync_tab_titles()
        # 상주 패널은 자기 편집만 알므로, 바깥(MCP 등)에서 온 변경을 여기서
        # 반영한다 — 패널 자신이 발화한 notify는 각 패널이 알아서 건너뛴다.
        self._hook_panel.refresh_external()
        self._blackboard_panel.refresh_external()

    def _sync_agent_editors(self) -> None:
        """열린 AgentEditor 탭 동기화 훅 (WP-CT 이후 빈 자리).

        계약 패널 동기화가 유일한 일이었는데 패널이 퇴역해 지금은 할 일이 없다.
        에이전트 편집기에 외부 변경 반영이 다시 필요해지면 여기가 자리다.
        """

    def _sync_tab_titles(self) -> None:
        """열린 탭의 타이틀을 현재 컴포넌트 이름과 동기화한다.

        _open_tabs 키는 컴포넌트 id(str). 탭에 연결된 editor의 컴포넌트 이름을
        읽어 탭 텍스트가 달라졌으면 갱신한다. 키스트로크마다 notify가 오더라도
        문자열 비교로 갱신 여부를 판단하므로 비용이 낮다.
        """
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
        """레지스트리 우클릭 '삭제' → 확인 후 삭제 커맨드 실행."""
        if self._project is None:
            return

        comp_name = getattr(component, "name", str(component))

        # 참조 요약 수집 (간략 — validate 없이 빠른 사전 검사)
        ref_lines: list[str] = []
        if self._project is not None:
            from daedalus.model.fsm.state import SimpleState

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

        self.delete_component(component)
        self._status_label.setText(f"'{comp_name}' 삭제됨 (Ctrl+Z로 되돌릴 수 있습니다)")

    def delete_component(self, component: object) -> None:
        """컴포넌트 삭제 — 확인 다이얼로그 없이 커맨드로 실행한다 (A2).

        GUI 레지스트리 삭제와 MCP `delete_component`가 공유하는 실체다. 조작
        경로에 따라 Ctrl+Z가 듣고 안 듣고가 갈리면 협업 도구로 실격이다.

        **`_load_project_graph()`를 부르지 않는다** — 커맨드가 캔버스 VM을 직접
        떼어냈고, 여기서 모델로부터 VM을 다시 만들면 undo가 되돌려 놓을 VM 객체와
        캔버스에 있는 VM 객체가 서로 다른 물건이 되어(전이 VM이 사라진 노드 VM을
        가리킨다) 되돌린 그래프가 깨진다.
        """
        from daedalus.view.commands.component_commands import RemoveComponentCmd

        if self._project is None:
            return

        comp_id = getattr(component, "id", None)

        # 본문 문서 캐시 정리 — 삭제된 컴포넌트의 undo 이력을 들고 있을 이유가
        # 없다 (WP-BU). 되돌리면 본문 자체는 모델에 살아 돌아오고, 탭을 다시 열
        # 때 문서가 새로 만들어진다(본문 편집 이력만 잃는다).
        from daedalus.view.editors import body_documents
        body_documents.registry().discard(component)

        # 열린 탭 닫기
        if comp_id is not None and comp_id in self._open_tabs:
            self._close_tab(self._open_tabs[comp_id])

        # 레지스트리는 별도로 갱신하지 않는다 — execute의 notify가
        # _on_project_vm_changed → set_placed_ids → _rebuild를 태우고, 그 rebuild가
        # 프로젝트 목록을 처음부터 다시 읽으므로 undo 복원도 같은 경로로 반영된다.
        self._project_vm.execute(
            RemoveComponentCmd(self._project, self._project_vm, component)
        )

    # --- 탭 관리 ---

    def _open_component(self, component: object) -> None:
        """레지스트리에서 더블클릭 → SkillEditor/AgentEditor 탭 열기."""
        name = getattr(component, "name", None)
        comp_id = getattr(component, "id", None)
        if name is None or comp_id is None:
            return
        if comp_id in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[comp_id])
            return

        if isinstance(component, AgentDefinition):
            from daedalus.view.editors.agent_editor import AgentEditor
            editor = AgentEditor(
                component, on_notify_fn=self._project_vm.notify, project=self._project,
                project_vm=self._project_vm,
            )
            # AgentEditor._component_editor._fm.renamed → 이름 변경 처리
            fm = getattr(getattr(editor, "_component_editor", None), "_fm", None)
            if fm is not None and hasattr(fm, "renamed"):
                fm.renamed.connect(self._on_component_renamed)
            idx = self._tabs.addTab(editor, f"🤖 {name}")
            self._open_tabs[comp_id] = idx
            self._tabs.setCurrentIndex(idx)
        elif isinstance(component, (ProceduralSkill, DeclarativeSkill, TransferSkill, ReferenceSkill)):
            editor = SkillEditor(
                component, on_notify_fn=self._project_vm.notify,
                project_vm=self._project_vm,
            )
            # SkillEditor._editor._fm.renamed → 이름 변경 처리
            fm = getattr(getattr(editor, "_editor", None), "_fm", None)
            if fm is not None and hasattr(fm, "renamed"):
                fm.renamed.connect(self._on_component_renamed)
            idx = self._tabs.addTab(editor, name)
            self._open_tabs[comp_id] = idx
            self._tabs.setCurrentIndex(idx)

    def open_component_ports(self, component: object) -> None:
        """컴포넌트 편집 탭을 열고 출력 포트 패널로 포커스를 옮긴다 (A9-5).

        캔버스에서 "출력 포트 편집…"을 고른 사용자는 그 패널을 보려는 것이지
        탭이 열리기만 하면 되는 것이 아니다 — 우측 패널이 접혀 있거나 스크롤
        밖이면 열어도 못 찾는다.
        """
        self._open_component(component)
        comp_id = getattr(component, "id", None)
        if comp_id is None or comp_id not in self._open_tabs:
            return
        widget = self._tabs.widget(self._open_tabs[comp_id])
        panel = getattr(widget, "_transfer_on_panel", None)
        if panel is not None:
            panel.setFocus()
            panel.raise_()

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
        """에이전트 백킹 FSM — WP-AF 이후 형식상의 최소 기계.

        내부 FSM은 퇴역했다(절차는 본문, 결과 분기는 transfer_on). fsm 필드는
        WorkflowComponent 계약상 남아 있으므로 EntryPoint 하나짜리 빈 기계를
        준다 — 서술할 것이 없어 컴파일 산출에도 나타나지 않는다.
        """
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.pseudo import EntryPoint
        entry = EntryPoint(name="entry")
        return StateMachine(
            name=f"{name}_fsm",
            states=[entry],
            initial_state=entry,
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
            return  # 알 수 없는 종류 — 프로그램적 발화 방어
        name = self._ask_unique_name(self._COMPONENT_TITLES.get(kind, "새 컴포넌트"))
        if name is None:
            return
        factories = {
            "procedural": lambda: ProceduralSkill(fsm=self._make_fsm(name), name=name, description=""),
            "declarative": lambda: DeclarativeSkill(name=name, description=""),
            "transfer": lambda: TransferSkill(fsm=self._make_fsm(name), name=name, description=""),
            "reference": lambda: ReferenceSkill(name=name, description=""),
            "agent": lambda: AgentDefinition(
                fsm=self._make_agent_fsm(name), name=name, description="",
                transfer_on=[EventDef(name="done")],  # 기본 출력 포트 (WP-AF)
            ),  # type: ignore[arg-type]
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
            # Skill/Agent 편집기 — undo/redo는 project VM 기준 (WP-AF 이후
            # AgentEditor도 별도 그래프 VM이 없어 SkillEditor와 동일하다).
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

