# daedalus/view/editor_tabs.py
"""탭 배선 — 고정 탭 구축 · 컴포넌트 편집 탭 열기/닫기/제목 동기화 (WP-7 ①).

`MainWindow`의 협력 객체다(Mixin 아님, WP-RF-3e 관례). `app.py`가 1,072줄로
분해 예산(~800줄)을 넘겨 있었고, 그중 **탭에 관한 것 전부**가 한 덩어리로
떨어져 나올 수 있었다 — 중앙 위젯(고정 탭 6개) 구축, 컴포넌트 편집 탭의
수명주기(열기·닫기·제목 동기화·프론트매터 재구축·포트 포커스), 탭 전환이
좌우하는 undo 스택 배선이다.

**이동만이다(WP-7 ①).** 로직은 한 줄도 바뀌지 않았고, `app.py`에는 같은
이름의 한 줄 위임 메서드가 남는다 — 테스트와 MCP 도구가
`window._open_component(...)`처럼 창의 내부 메서드를 직접 부르기 때문이다.
상태(`_tabs`/`_open_tabs`/`_fsm_scene`/고정 패널들)의 단일 진실은 계속
윈도우에 있고, 이 객체는 그것을 복제하지 않고 `self._w.<attr>`로 직접 읽고 쓴다.

종류별 편집기 선택(`_open_component`)은 WP-7 ②에서 `view/kind_ui.py`의
`KIND_UI[kind].editor_factory`로 바뀐다 — 여기서는 옮기기만 한다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QTabWidget

from daedalus.model.plugin.enums import BuildTarget

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow

_FSM_TAB_INDEX = 0  # 프로젝트 FSM 캔버스는 항상 탭 0
_BLACKBOARD_TAB_INDEX = 1  # 블랙보드 편집 탭은 항상 탭 1 (WP-BB — 닫기 불가 고정 탭)
_HOOK_TAB_INDEX = 2  # 훅 라이브러리 탭은 항상 탭 2 (WP-HK — 닫기 불가 고정 탭)
_CLAUDE_MD_TAB_INDEX = 3  # .claude/CLAUDE.md 구역 탭 (WP-WD — 닫기 불가 고정 탭)
_RULES_TAB_INDEX = 4  # .claude/rules/ 탭 (WP-WD — 닫기 불가 고정 탭)
_SETTINGS_TAB_INDEX = 5  # 작업 폴더 settings 탭 (WP-WS — 닫기 불가 고정 탭)
# 고정 탭 = 컴포넌트 에디터가 아닌 상주 탭. 새 에디터는 이 뒤에 붙는다.
_FIXED_TAB_INDEXES = (
    _FSM_TAB_INDEX, _BLACKBOARD_TAB_INDEX, _HOOK_TAB_INDEX,
    _CLAUDE_MD_TAB_INDEX, _RULES_TAB_INDEX, _SETTINGS_TAB_INDEX,
)
# LOCAL 빌드 전용 탭 — 산출이 작업 폴더 .claude/로만 나가는 표면(WP-WD/WP-WS).
# 마켓플레이스 프로젝트에서는 setTabVisible로 숨긴다(제거가 아니라 숨김 —
# 인덱스가 보존돼야 _open_tabs/고정 인덱스 체계가 흔들리지 않는다).
_LOCAL_ONLY_TAB_INDEXES = (
    _CLAUDE_MD_TAB_INDEX, _RULES_TAB_INDEX, _SETTINGS_TAB_INDEX,
)
_LAST_FIXED_TAB_INDEX = max(_FIXED_TAB_INDEXES)

# 설정 위젯 유휴 프리웜 지연(ms) — 창이 뜨고 잠시 뒤 미리 구축해 첫 탭 진입의
# ~0.8s 동기 구축 멈춤(실측)을 사용자가 클릭하기 전 유휴 시점으로 옮긴다.
_SETTINGS_PREWARM_MS = 800


def _tab_prefix(component: object) -> str:
    """컴포넌트 편집 탭의 아이콘 접두 — 종류가 한눈에 보이게.

    스킬은 접두가 없고(대다수), 워크플로 에이전트 🤖 / fork 에이전트 🧩다.
    탭 텍스트 동기화(`sync_tab_titles`)와 탭 생성이 **같은 함수**를 써야
    이름 변경 때 접두가 사라지지 않는다.

    **한 줄 파사드다**(WP-7 ②): 실체는 뷰의 종류 표 `KIND_UI[kind].tab_prefix`다.
    """
    from daedalus.view.kind_ui import ui_for

    return ui_for(component).tab_prefix


class EditorTabs:
    """탭 구축 + 컴포넌트 편집 탭 수명주기를 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    # --- 초기화 ---

    def setup_central(self) -> None:
        w = self._w
        from daedalus.view.canvas.canvas_view import FsmCanvasView
        from daedalus.view.canvas.scene import FsmScene

        w._tabs = QTabWidget()
        w._tabs.setTabsClosable(True)
        w._tabs.tabCloseRequested.connect(w._close_tab)
        # currentChanged는 _setup_docks() 완료 후 _connect_signals()에서 연결
        w.setCentralWidget(w._tabs)

        # 프로젝트 FSM 캔버스 — 항상 탭 0, 닫을 수 없음
        w._fsm_scene = FsmScene(w._project_vm, skill_lookup=w._skill_lookup)
        fsm_view = FsmCanvasView(w._fsm_scene)
        w._fsm_scene.selectionChanged.connect(w._on_scene_selection)
        w._tabs.addTab(fsm_view, "Project FSM")

        # 블랙보드 편집 탭 — 항상 탭 1, 닫을 수 없음 (WP-BB)
        from daedalus.view.editors.blackboard_editor import BlackboardPanel
        w._blackboard_panel = BlackboardPanel(on_notify_fn=w._project_vm.notify)
        w._tabs.addTab(w._blackboard_panel, "🗂 블랙보드")

        # 훅 라이브러리 탭 — 항상 탭 2, 닫을 수 없음 (WP-HK).
        # 모달 다이얼로그였다가 상주 탭이 됐다: CC 훅은 이벤트 31종 × 핸들러 5종의
        # 3단 구조라 모달 폼으로는 다룰 수 없다.
        from daedalus.view.editors.hook_panel import HookLibraryPanel
        w._hook_panel = HookLibraryPanel(on_notify_fn=w._project_vm.notify)
        w._tabs.addTab(w._hook_panel, "🪝 훅")

        # 작업 폴더 문서 — 항상 탭 3·4, 닫을 수 없음 (WP-WD). CLAUDE.md와 규칙을
        # 한 탭에 목록으로 묶지 않고 각각 최상위로 둔 것은 사용자 확정이다 —
        # CLAUDE.md는 하나뿐이고 규칙은 여럿이라 성격이 다르다.
        from daedalus.view.editors.workspace_editor import ClaudeMdPanel, RulesPanel
        w._claude_md_panel = ClaudeMdPanel(on_notify_fn=w._project_vm.notify)
        w._tabs.addTab(w._claude_md_panel, "📌 CLAUDE.md")
        w._rules_panel = RulesPanel(on_notify_fn=w._project_vm.notify)
        w._tabs.addTab(w._rules_panel, "📐 규칙")

        # 작업 폴더 settings 탭 — 항상 탭 5, 닫을 수 없음 (WP-WS, LOCAL 전용 표시).
        # 편집기 실체는 external/ 서브모듈 위젯(훅 카테고리 제외 — 훅 정본은
        # hook_library)이고 패널은 모델 배선 어댑터다.
        from daedalus.view.editors.workspace_settings_panel import (
            WorkspaceSettingsPanel,
        )
        w._workspace_settings_panel = WorkspaceSettingsPanel(
            on_notify_fn=w._project_vm.notify
        )
        w._tabs.addTab(w._workspace_settings_panel, "⚙ 설정")

        # 고정 탭의 닫기 버튼 숨김
        tab_bar = w._tabs.tabBar()
        if tab_bar is not None:
            for index in _FIXED_TAB_INDEXES:
                tab_bar.setTabButton(index, tab_bar.ButtonPosition.RightSide, None)

        # 프로젝트 VM 변경 시 레지스트리 dim 갱신
        w._project_vm.add_listener(w._on_project_vm_changed)
        # 미저장 변경 감지 — **양 채널 모두** 등록해야 한다. notify("content")는
        # content 리스너만 부르므로(project_vm.notify) structure 한쪽만 등록하면
        # 본문 타이핑(body_documents 경로)이 통째로 새어 나간다.
        w._project_vm.add_listener(w._mark_dirty)
        w._project_vm.add_listener(w._mark_dirty, scope="content")

    def schedule_settings_prewarm(self) -> None:
        """설정 위젯 유휴 프리웜 (WP-WS).

        스키마 구동 위젯의 첫 구축이 ~0.8s(실측) 동기 멈춤이라, 창이 화면에
        보이는 유휴 시점에 미리 만들어 둔다. **isVisible 가드가 핵심** —
        창을 띄우지 않는 테스트 스위트(수백 개 MainWindow)에서는 절대
        발동하지 않아야 지연 생성의 목적(스위트 속도)이 지켜진다.
        LOCAL 프로젝트에서만 — 마켓 프로젝트는 탭 자체가 숨어 있다.
        """
        w = self._w
        if not w.isVisible():
            return
        project = w._project
        if project is not None and getattr(project, "build_target", None) is not BuildTarget.LOCAL:
            return
        from PySide6.QtCore import QTimer

        def _prewarm(window=w) -> None:
            if not window.isVisible():
                return
            panel = getattr(window, "_workspace_settings_panel", None)
            if panel is not None:
                panel.ensure_editor()

        QTimer.singleShot(_SETTINGS_PREWARM_MS, _prewarm)

    # --- 탭 표시 / 제목 ---

    def on_project_vm_changed(self) -> None:
        w = self._w
        w._registry_panel.set_placed_ids(w._get_placed_ids())
        w._sync_tab_titles()
        # 상주 패널은 자기 편집만 알므로, 바깥(MCP 등)에서 온 변경을 여기서
        # 반영한다 — 패널 자신이 발화한 notify는 각 패널이 알아서 건너뛴다.
        w._hook_panel.refresh_external()
        w._blackboard_panel.refresh_external()
        w._workspace_settings_panel.refresh_external()
        w._refresh_target_dependent_tabs()

    def refresh_target_dependent_tabs(self) -> None:
        """LOCAL 전용 탭(CLAUDE.md·규칙·설정)의 표시를 빌드 타깃에 맞춘다.

        setTabVisible은 탭을 **제거하지 않고 숨긴다** — 인덱스가 보존돼
        고정 탭 체계(_FIXED_TAB_INDEXES·_open_tabs)가 흔들리지 않는다.
        프로젝트가 없으면 보인다(빈 상태에서 표면을 숨기면 기능 발견이 안 된다).
        """
        w = self._w
        project = w._project
        local = (
            project is None
            or getattr(project, "build_target", None) is BuildTarget.LOCAL
        )
        tab_bar = w._tabs.tabBar()
        if tab_bar is None:
            return
        for index in _LOCAL_ONLY_TAB_INDEXES:
            tab_bar.setTabVisible(index, local)

    def sync_tab_titles(self) -> None:
        """열린 탭의 타이틀을 현재 컴포넌트 이름과 동기화한다.

        _open_tabs 키는 컴포넌트 id(str). 탭에 연결된 editor의 컴포넌트 이름을
        읽어 탭 텍스트가 달라졌으면 갱신한다. 키스트로크마다 notify가 오더라도
        문자열 비교로 갱신 여부를 판단하므로 비용이 낮다.
        """
        w = self._w
        for comp_id, tab_idx in w._open_tabs.items():
            widget = w._tabs.widget(tab_idx)
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
            current_text = w._tabs.tabText(tab_idx)
            expected = f"{_tab_prefix(comp)}{name}"
            if current_text != expected:
                w._tabs.setTabText(tab_idx, expected)

    # --- 컴포넌트 편집 탭 ---

    def open_component(self, component: object) -> None:
        """레지스트리에서 더블클릭 → 종류가 선언한 편집기 탭 열기.

        **종류별 클래스 전수 열거가 있던 자리다**(V14): `isinstance(component,
        (StepSkill, DeclarativeSkill, …))` 튜플에 빠진 종류는 예외도 안 내고
        **탭이 그냥 안 열렸다**. 이제 종류가 자기 편집기를 선언한다
        (`KIND_UI[kind].editor_factory`) — 없는 종류는 시끄럽게 실패한다.
        """
        from daedalus.view.kind_ui import ui_for

        w = self._w
        name = getattr(component, "name", None)
        comp_id = getattr(component, "id", None)
        if name is None or comp_id is None:
            return
        if comp_id in w._open_tabs:
            w._tabs.setCurrentIndex(w._open_tabs[comp_id])
            return

        ui = ui_for(component)
        editor = ui.editor_factory(
            component, on_notify_fn=w._project_vm.notify, project=w._project,
            project_vm=w._project_vm,
        )
        # 편집기의 프론트매터 패널 renamed → 이름 변경 처리. 패널이 걸린 속성
        # 이름은 편집기마다 다르다(SkillEditor._editor / AgentEditor._component_editor)
        # — `rebuild_component_frontmatter`와 **같은 조회**를 쓴다.
        inner = getattr(editor, "_editor", None) or getattr(
            editor, "_component_editor", None
        )
        fm = getattr(inner, "_fm", None)
        if fm is not None and hasattr(fm, "renamed"):
            fm.renamed.connect(w._on_component_renamed)
        idx = w._tabs.addTab(editor, f"{ui.tab_prefix}{name}")
        w._open_tabs[comp_id] = idx
        w._tabs.setCurrentIndex(idx)

    def rebuild_component_frontmatter(self, component: object) -> None:
        """열려 있는 편집 탭의 프론트매터 폼을 현재 종류로 다시 만든다. 없으면 무동작.

        종류 전환(`convert_skill_kind`)은 `__class__`와 config를 통째로 바꾸므로
        열려 있던 폼은 **다른 종류의 표**로 그려진 스테일 위젯이 된다 — 사라진
        필드를 그대로 편집할 수 있고, 새로 생긴 필드는 보이지 않는다. "탭을
        닫았다 여세요"라고 안내하는 대신 여기서 다시 만든다.

        `renamed` 재연결이 여기 있는 이유는 원래 배선이 여기(`open_component`)에
        있기 때문이다 — 새 폼이 이름 변경을 알리지 못하면 참조 갱신이 끊긴다.
        """
        w = self._w
        comp_id = getattr(component, "id", None)
        if comp_id is None or comp_id not in w._open_tabs:
            return
        widget = w._tabs.widget(w._open_tabs[comp_id])
        editor = getattr(widget, "_editor", None) or getattr(
            widget, "_component_editor", None
        )
        rebuild = getattr(editor, "rebuild_frontmatter", None)
        if not callable(rebuild):
            return
        fm = rebuild()
        fm.renamed.connect(w._on_component_renamed)

    def open_component_ports(self, component: object) -> None:
        """컴포넌트 편집 탭을 열고 출력 포트 패널로 포커스를 옮긴다 (A9-5).

        캔버스에서 "출력 포트 편집…"을 고른 사용자는 그 패널을 보려는 것이지
        탭이 열리기만 하면 되는 것이 아니다 — 우측 패널이 접혀 있거나 스크롤
        밖이면 열어도 못 찾는다.
        """
        w = self._w
        w._open_component(component)
        comp_id = getattr(component, "id", None)
        if comp_id is None or comp_id not in w._open_tabs:
            return
        widget = w._tabs.widget(w._open_tabs[comp_id])
        panel = getattr(widget, "_transfer_on_panel", None)
        if panel is not None:
            panel.setFocus()
            panel.raise_()

    def close_tab(self, index: int) -> None:
        w = self._w
        if index in _FIXED_TAB_INDEXES:
            return  # Project FSM / 블랙보드 / 훅은 닫을 수 없음
        widget = w._tabs.widget(index)
        name = next((n for n, i in w._open_tabs.items() if i == index), None)
        if name:
            del w._open_tabs[name]
        w._tabs.removeTab(index)
        w._open_tabs = {
            n: (i if i < index else i - 1) for n, i in w._open_tabs.items()
        }
        if widget is not None:
            # closeEvent 발화 (AgentEditor의 씬 리스너 해제 등) + Qt 메모리 정리
            widget.close()
            widget.deleteLater()

    # --- 탭 전환 · undo 스택 배선 ---

    def on_tab_changed(self, index: int) -> None:
        w = self._w
        if not w._initialized:
            return

        w._active_stack.remove_listener(w._update_undo_redo)

        if index == _FSM_TAB_INDEX:
            # Project FSM 캔버스
            w._active_stack = w._project_vm.command_stack
            w._active_notify = w._project_vm.notify
            w._history_panel.set_stack(
                w._project_vm.command_stack, on_goto=w._project_vm.notify
            )
            w._property_panel.set_project_vm(w._project_vm)
            w._script_panel.set_stack(w._project_vm.command_stack)
        else:
            # Skill/Agent 편집기 — undo/redo는 project VM 기준 (WP-AF 이후
            # AgentEditor도 별도 그래프 VM이 없어 SkillEditor와 동일하다).
            w._active_stack = w._project_vm.command_stack
            w._active_notify = w._project_vm.notify
            w._history_panel.set_stack(
                w._project_vm.command_stack, on_goto=w._project_vm.notify
            )
            w._script_panel.set_stack(w._project_vm.command_stack)
            w._property_panel.clear()

        w._active_stack.add_listener(w._update_undo_redo)
        w._update_undo_redo()

    def on_scene_selection(self) -> None:
        from daedalus.view.canvas.edge_item import TransitionEdgeItem
        from daedalus.view.canvas.node_item import StateNodeItem

        w = self._w
        if w._fsm_scene is None:
            return
        try:
            selected = w._fsm_scene.selectedItems()
        except RuntimeError:
            # 씬의 C++ 객체가 이미 파괴된 뒤 지연 발화된 시그널 — 무시
            # (agent_editor._on_graph_selection과 동일 가드).
            return
        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, StateNodeItem):
                w._property_panel.show_state(item.state_vm)
            elif isinstance(item, TransitionEdgeItem):
                w._property_panel.show_transition(item.transition_vm)
        else:
            w._property_panel.clear()

    def update_undo_redo(self) -> None:
        w = self._w
        stack = w._active_stack
        w._undo_action.setEnabled(stack.can_undo)
        w._redo_action.setEnabled(stack.can_redo)
        w._undo_action.setText(
            f"Undo: {stack.history[-1].description}" if stack.can_undo else "Undo"
        )
        w._redo_action.setText(
            f"Redo: {stack.redo_history[0].description}" if stack.can_redo else "Redo"
        )

    def undo(self) -> None:
        self._w._active_stack.undo()
        self._w._active_notify()

    def redo(self) -> None:
        self._w._active_stack.redo()
        self._w._active_notify()
