# daedalus/view/app.py
"""Daedalus 메인 윈도우 골격 (WP-RF-3e).

윈도우가 직접 갖는 것은 **탭·독·메뉴 배선과 컴포넌트 편집 진입**뿐이다.
세션 입출력·컴파일·실행·검증·그래프 왕복·컴포넌트 수명주기는 각각
협력 객체(Mixin 아님)가 맡는다:

| 협력 객체 | 모듈 | 담당 |
|---|---|---|
| `SessionIO` | `view/session_io.py` | 저장/열기/최근 목록/패키지(.ddpj) |
| `CompileActions` | `view/compile_actions.py` | Ctrl+B 컴파일 + 서버 정의 주입 |
| `LaunchActions` | `view/launch_actions.py` | MCP 서버 수명주기 · Claude Code 실행 |
| `ValidationActions` | `view/validation_actions.py` | F7 검증 · 결과 항목 노드 포커스 |
| `GraphIO` | `view/graph_io.py` | 프로젝트 그래프 ↔ 캔버스 VM · 레이아웃 저장 |
| `ComponentActions` | `view/component_actions.py` | 컴포넌트 생성 · 이름 변경 · 삭제 |

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
    QInputDialog,  # noqa: F401 — 테스트가 이 모듈 경로로 다이얼로그를 몽키패치한다
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
)

from daedalus.model.project import PluginProject
from daedalus.model.validation import ValidationError
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.compile_actions import CompileActions
from daedalus.view.component_actions import ComponentActions
from daedalus.view.graph_io import GraphIO
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

#: 고정 탭 인덱스·탭 접두는 `view/editor_tabs.py`가 소유한다 (WP-7 ①).
#: 테스트·협력 객체가 `daedalus.view.app`에서 이 이름들을 임포트하므로
#: **같은 객체**를 재-export한다 (복제 금지 — 두 벌이 되면 인덱스가 갈린다).
from daedalus.view.editor_tabs import (  # noqa: E402
    _BLACKBOARD_TAB_INDEX,  # noqa: F401
    _CLAUDE_MD_TAB_INDEX,  # noqa: F401
    _FIXED_TAB_INDEXES,  # noqa: F401
    _FSM_TAB_INDEX,  # noqa: F401
    _HOOK_TAB_INDEX,  # noqa: F401
    _LAST_FIXED_TAB_INDEX,
    _LOCAL_ONLY_TAB_INDEXES,  # noqa: F401
    _RULES_TAB_INDEX,  # noqa: F401
    _SETTINGS_TAB_INDEX,  # noqa: F401
    _tab_prefix,  # noqa: F401
    EditorTabs,
)

class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._current_path: str | None = None  # 현재 저장 경로 (.daedalus.json)
        # 폴더형 템플릿의 동봉 폴더 — 첫 저장 시 files/·skill-files/ 복사 원천.
        # SessionIO(new_project/open_path/carry_template_assets)가 관리한다.
        self._pending_template_assets: Path | None = None
        # 미저장 변경 플래그 — notify 양 채널 리스너가 True로 올리고,
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
        self._graph_io = GraphIO(self)
        self._component_actions = ComponentActions(self)
        self._editor_tabs = EditorTabs(self)

        self._setup_central()
        self._setup_docks()
        self._setup_menus()
        self._setup_statusbar()
        self._initialized = True
        self._connect_signals()

    # --- 초기화 ---

    def _setup_central(self) -> None:
        self._editor_tabs.setup_central()

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
            # Ctrl+N 하나가 통합 다이얼로그(출발점 빈|템플릿 + 빌드 타깃)를
            # 연다 — 별도 "템플릿에서 새 프로젝트" 항목은 통합으로 흡수됐다
            # (사용자 확정).
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

            tpl_action = QAction("템플릿으로 저장…", self)
            tpl_action.setToolTip(
                "현재 프로젝트를 ~/.daedalus/templates/에 시작 템플릿으로 저장한다 "
                "— 새 프로젝트 목록에 뜨고 재설치해도 남는다"
            )
            tpl_action.triggered.connect(self._save_as_template_dialog)
            file_menu.addAction(tpl_action)

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

            wrap_catalog_action = QAction("외부 플러그인 카탈로그...", self)
            wrap_catalog_action.setToolTip(
                "등록된 마켓플레이스 폴더의 외부 플러그인을 체크로 사용 "
                "선언한다 — 빌드가 의존성을 자동 배선 (WP-WR)"
            )
            wrap_catalog_action.triggered.connect(self._show_wrap_catalog)
            tools_menu.addAction(wrap_catalog_action)

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
        self._registry_panel.component_preview_requested.connect(self._on_preview_component)
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
        self._workspace_settings_panel.set_project(project)
        self._refresh_target_dependent_tabs()
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
        # 에이전트 MCP_SERVERS TagInput 후보 (WP-WR) — 사용 선언된 외부
        # 플러그인이 동봉 .mcp.json으로 제공하는 서버 ∪ 프로젝트
        # mcp_server_defs 이름. tools 후보에는 넣지 않는다(개별 도구 목록
        # 미지원 — 사용자 확정).
        from daedalus.view.widgets.tag_input import set_mcp_server_candidate_provider

        def _mcp_server_candidates(p=project) -> list[str]:
            from daedalus.model.plugin.wrap_catalog import used_plugin_mcp_servers

            names = set(used_plugin_mcp_servers(p))
            names.update(getattr(p, "mcp_server_defs", None) or {})
            return sorted(names)

        set_mcp_server_candidate_provider(_mcp_server_candidates)
        # fork 에이전트 피커 후보 (2026-09-13) — MCP 검증과 같은 함수.
        from daedalus.view.actions.fork_skill import fork_agent_choices
        from daedalus.view.widgets.tag_input import set_fork_agent_choice_provider

        set_fork_agent_choice_provider(lambda p=project: fork_agent_choices(p))
        # 변수 팝업의 빌드 타깃 제공자 — 팝업을 열 때마다 조회하므로 프로젝트
        # 속성에서 타깃을 바꾸면 즉시 반영된다(로컬 빌드는 ${CLAUDE_PLUGIN_ROOT}
        # 사용 불가 — 사용자 확정 매트릭스).
        from daedalus.view.editors.variable_loader import set_build_target_provider

        set_build_target_provider(
            lambda: getattr(self._project, "build_target", None)
        )
        # 프로젝트 그래프(워크플로 백킹 머신) → 캔버스 VM 재구성 (버그 1: 저장된
        # 노드 연결 복원). placement 노드 + 전이를 graph_layout 좌표로 배치한다
        # (WP-EP: EntryPoint는 그리지 않음).
        self._graph_io.load_project_graph()

    # --- 레이아웃 저장 (GraphIO 위임) ---

    def _save_graph_layout(self) -> None:
        self._graph_io.save_graph_layout()

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
        # (notify는 set_project → GraphIO.load_project_graph 끝에서 1회 발화 — 중복 금지)
        self.set_project(project)

        # 4) 방금 로드한 상태는 미저장 변경이 아니다. 위 notify가 _mark_dirty를
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

    # --- 미저장 변경 ---

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

    def _save_project(self) -> None:
        self._session_io.save_project()

    def _save_project_as(self) -> None:
        self._session_io.save_project_as()

    def project_has_content(self) -> bool:
        return self._session_io.project_has_content()

    def _new_project(self) -> None:
        self._session_io.new_project()

    def _edit_project_properties(self) -> None:
        self._session_io.edit_project_properties()

    def _open_project_dialog(self) -> None:
        self._session_io.open_project_dialog()

    def _open_file_dialog(self) -> None:
        self._session_io.open_file_dialog()

    def _save_as_template_dialog(self) -> None:
        self._session_io.save_as_template_dialog()

    def _export_package_dialog(self) -> None:
        self._session_io.export_package_dialog()

    def _import_package_dialog(self) -> None:
        self._session_io.import_package_dialog()

    def _rebuild_recent_menu(self) -> None:
        self._session_io.rebuild_recent_menu()

    # 순수 함수라 인스턴스가 필요 없다 — `MainWindow._recent_label(...)`로 직접 쓴다.
    _recent_label = staticmethod(recent_label)

    def open_path(self, path: str) -> bool:
        return self._session_io.open_path(path)

    # --- 컴파일 위임 (실체는 view/compile_actions.CompileActions) ---

    def _compile_project_dialog(self) -> None:
        self._compile_actions.compile_project_dialog()

    def compile_inputs(self) -> dict:
        """컴파일 환경 주입 인자 — Ctrl+B와 MCP `compile_check`가 공유한다 (G3)."""
        return self._compile_actions.compile_inputs()

    # --- MCP 서버 / Claude Code 실행 위임 (실체는 view/launch_actions.LaunchActions) ---

    def start_mcp_service(self, port: int | None = None) -> None:
        self._launch_actions.start_mcp_service(port)

    def _show_mcp_info(self) -> None:
        self._launch_actions.show_mcp_info()

    def _launch_claude_code(self) -> None:
        self._launch_actions.launch_claude_code()

    def _open_global_catalogue(self) -> None:
        """도구 메뉴 — 전역 카탈로그 폴더를 탐색기로 연다 (없으면 만든다)."""
        cat_dir = Path.home() / ".daedalus" / "catalogue"
        cat_dir.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cat_dir)))

    def _show_wrap_catalog(self) -> None:
        """도구 메뉴 — 외부 플러그인 카탈로그 창 (WP-WR, D2)."""
        from daedalus.view.editors.wrap_catalog_dialog import WrapCatalogDialog

        WrapCatalogDialog(self).exec()

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

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self._schedule_settings_prewarm()

    def _schedule_settings_prewarm(self) -> None:
        self._editor_tabs.schedule_settings_prewarm()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """미저장 변경을 확인한 뒤 닫고, 닫으면 MCP 서버도 함께 내린다.

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

    def _on_validation_item_activated(self, error: ValidationError) -> None:
        self._validation_actions.on_validation_item_activated(error)

    def show_component_findings(self, component: object) -> int:
        return self._validation_actions.show_component_findings(component)

    def _on_preview_component(self, component: object) -> None:
        """레지스트리 우클릭 → 컴파일 미리보기 — 캔버스 메뉴와 같은 실체(A9-1).

        트랜스퍼 스킬은 캔버스 노드가 아니라 엣지에 붙어 placement 메뉴가
        닿지 않으므로(사용자 보고) 레지스트리가 전 컴포넌트 공통 진입점이다.
        """
        from daedalus.view.actions.preview import show_preview_dialog

        show_preview_dialog(
            self, component, project=self._project,
            resolved_hooks=self.resolved_hooks(),
        )

    def _focus_in_project_canvas(self, subject: object) -> None:
        self._validation_actions.focus_in_project_canvas(subject)

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
        self._editor_tabs.on_project_vm_changed()

    def _refresh_target_dependent_tabs(self) -> None:
        self._editor_tabs.refresh_target_dependent_tabs()

    def _sync_tab_titles(self) -> None:
        self._editor_tabs.sync_tab_titles()

    # --- 컴포넌트 이름 변경 ---

    def _on_component_renamed(self, component: object, old_name: str, new_name: str) -> None:
        self._component_actions.on_component_renamed(component, old_name, new_name)

    # --- 컴포넌트 삭제 ---

    def _on_delete_component(self, component: object) -> None:
        self._component_actions.on_delete_component(component)

    def delete_component(self, component: object) -> None:
        """컴포넌트 삭제 (A2) — MCP `delete_component`가 직접 부르는 표면."""
        self._component_actions.delete_component(component)

    # --- 탭 관리 (EditorTabs 위임) ---
    #
    # 탭 배선의 실체는 `view/editor_tabs.py`에 있다 (WP-7 ①) — 테스트·MCP
    # 도구가 창의 이 이름들을 직접 부르므로 여기에는 위임만 남는다.

    def _open_component(self, component: object) -> None:
        self._editor_tabs.open_component(component)

    def rebuild_component_frontmatter(self, component: object) -> None:
        self._editor_tabs.rebuild_component_frontmatter(component)

    def open_component_ports(self, component: object) -> None:
        self._editor_tabs.open_component_ports(component)

    # --- 컴포넌트 생성 (ComponentActions 위임) ---
    #
    # 캔버스 컨텍스트 메뉴(context_menus)와 actions/creation, MCP 도구가 아래
    # 이름들을 창에서 직접 부른다 — 실체는 협력 객체에 있고 여기에는 위임만 남는다.

    #: 종류 → 다이얼로그 제목 (단일 진실은 ComponentActions).
    _COMPONENT_TITLES = ComponentActions._COMPONENT_TITLES

    def _make_fsm(self, name: str) -> object:
        return self._component_actions.make_fsm(name)

    def _make_agent_fsm(self, name: str) -> object:
        return self._component_actions.make_agent_fsm(name)

    def _register_component(self, component: object) -> None:
        self._component_actions.register_component(component)

    def _on_new_component(self, kind: str) -> None:
        self._component_actions.on_new_component(kind)

    def _close_tab(self, index: int) -> None:
        self._editor_tabs.close_tab(index)

    def _on_tab_changed(self, index: int) -> None:
        self._editor_tabs.on_tab_changed(index)

    def _on_scene_selection(self) -> None:
        self._editor_tabs.on_scene_selection()

    def _update_undo_redo(self) -> None:
        self._editor_tabs.update_undo_redo()

    def _undo(self) -> None:
        self._editor_tabs.undo()

    def _redo(self) -> None:
        self._editor_tabs.redo()
