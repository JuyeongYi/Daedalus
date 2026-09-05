"""tests/view/test_component_mgmt_ui.py — WP-S 컴포넌트 관리 UX 뷰 테스트."""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view import app as app_module
from daedalus.view.app import MainWindow
from daedalus.view.panels.registry_panel import RegistryPanel
# 고정 상주 탭 개수(Project FSM / 블랙보드 / 훅) — 탭이 늘어도 테스트가 따라간다
from daedalus.view.app import _FIXED_TAB_INDEXES
_FIXED_TAB_COUNT = len(_FIXED_TAB_INDEXES)


def _stub_build_target_dialog(monkeypatch, choice: str = "마켓플레이스 플러그인") -> None:
    """새 프로젝트 통합 다이얼로그를 "빈 프로젝트 + 지정 타깃"으로 스텁.

    모달을 헤드리스에서 띄우지 않는 봉합선은 SessionIO.exec_new_project_dialog다
    (구 QInputDialog.getItem 스텁의 후임 — 통합 다이얼로그 도입으로 교체)."""
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.view.editors.project_properties import BUILD_TARGET_LABELS
    from daedalus.view.session_io import SessionIO
    target = next(t for t, label in BUILD_TARGET_LABELS if label == choice)
    monkeypatch.setattr(
        SessionIO, "exec_new_project_dialog", lambda self: (None, target)
    )


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}_fsm", initial_state=s, states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="")


def _make_agent(name: str) -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name=f"{name}_fsm",
        initial_state=entry,
        states=[entry, done],
        final_states=[done],
    )
    return AgentDefinition(fsm=fsm, name=name, description="")


# ---------------------------------------------------------------------------
# 새 프로젝트 (Ctrl+N)
# ---------------------------------------------------------------------------

class TestNewProject:
    def test_new_project_loads_empty_project(self, qapp, monkeypatch):
        window = MainWindow()
        # 기존에 스킬이 있는 프로젝트 로드
        proj = PluginProject(name="existing")
        proj.skills.append(_make_proc("skill1"))
        window.set_project(proj)

        # 비어있지 않은 프로젝트 → _new_project 직접 호출 (확인 다이얼로그 없이 내부 호출)
        # 테스트에서 QMessageBox 없이 확인: 빈 프로젝트일 때 새 프로젝트 동작
        empty_proj = PluginProject(name="empty")
        window.set_project(empty_proj)
        _stub_build_target_dialog(monkeypatch)
        window._new_project()  # 빈 프로젝트 → 확인 다이얼로그 없이 새 프로젝트 생성

        assert window._project is not None
        assert len(window._project.skills) == 0
        assert len(window._project.agents) == 0
        # graph는 EntryPoint만 있어야 함
        assert len(window._project.graph.states) == 1
        window.close()

    def test_new_project_clears_tabs(self, qapp, monkeypatch):
        window = MainWindow()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        window.set_project(proj)
        window._open_component(skill)  # 탭 열기

        assert window._tabs.count() == _FIXED_TAB_COUNT + 1  # 고정 탭 + skill 탭

        # 빈 프로젝트로 만든 후 새 프로젝트
        empty_proj = PluginProject(name="empty")
        window.set_project(empty_proj)
        _stub_build_target_dialog(monkeypatch)
        window._new_project()  # 빈 → 새 프로젝트 (확인 다이얼로그 없음)

        assert window._tabs.count() == _FIXED_TAB_COUNT  # 고정 탭만
        window.close()

    def test_new_project_resets_current_path(self, qapp, monkeypatch):
        window = MainWindow()
        window._current_path = "some/path.json"

        empty_proj = PluginProject(name="empty")
        window.set_project(empty_proj)
        _stub_build_target_dialog(monkeypatch)
        window._new_project()

        assert window._current_path is None
        window.close()


# ---------------------------------------------------------------------------
# 탭 타이틀 동기화
# ---------------------------------------------------------------------------

class TestTabTitleSync:
    def test_tab_title_updated_on_notify(self, qapp):
        """notify 발생 시 _sync_tab_titles가 탭 텍스트를 최신 이름으로 갱신한다."""
        window = MainWindow()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        window.set_project(proj)
        window._open_component(skill)

        # 탭 타이틀 초기 확인
        skill_tab_idx = window._open_tabs[skill.id]
        assert window._tabs.tabText(skill_tab_idx) == "my-skill"

        # 이름 직접 변경 후 notify 발화 (시그널 경로 없이 모델만 변경)
        skill.name = "renamed-skill"
        window._project_vm.notify()

        assert window._tabs.tabText(skill_tab_idx) == "renamed-skill"
        window.close()

    def test_agent_tab_title_updated_on_notify(self, qapp):
        window = MainWindow()
        proj = PluginProject(name="p")
        agent = _make_agent("my-agent")
        proj.agents.append(agent)
        window.set_project(proj)
        window._open_component(agent)

        agent_tab_idx = window._open_tabs[agent.id]
        assert window._tabs.tabText(agent_tab_idx) == "🤖 my-agent"

        agent.name = "new-agent"
        window._project_vm.notify()

        assert window._tabs.tabText(agent_tab_idx) == "🤖 new-agent"
        window.close()


# ---------------------------------------------------------------------------
# 중복 이름 거부
# ---------------------------------------------------------------------------

class TestDuplicateNameRejection:
    def test_rename_rejected_when_duplicate(self, qapp, monkeypatch):
        """_on_component_renamed: 중복 이름이면 원본 이름으로 원복."""
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **kw: None))

        window = MainWindow()
        proj = PluginProject(name="p")
        skill_a = _make_proc("skill-a")
        skill_b = _make_proc("skill-b")
        proj.skills.extend([skill_a, skill_b])
        window.set_project(proj)

        # skill-b를 skill-a 이름으로 변경 시도 (중복) — 원복 확인
        window._on_component_renamed(skill_b, "skill-b", "skill-a")
        assert skill_b.name == "skill-b"  # 원복 확인
        window.close()

    def test_rename_succeeds_when_unique(self, qapp):
        window = MainWindow()
        proj = PluginProject(name="p")
        skill = _make_proc("foo")
        proj.skills.append(skill)
        window.set_project(proj)

        window._on_component_renamed(skill, "foo", "bar")
        assert skill.name == "bar"
        window.close()


# ---------------------------------------------------------------------------
# 레지스트리 컨텍스트 메뉴 시그널
# ---------------------------------------------------------------------------

class TestRegistryDeleteSignal:
    def test_delete_signal_emitted(self, qapp):
        """RegistryPanel.component_delete_requested 시그널이 발화된다."""
        panel = RegistryPanel()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        panel.set_project(proj)

        received: list[object] = []
        panel.component_delete_requested.connect(lambda c: received.append(c))

        # _RegistrySection.delete_requested → panel.component_delete_requested 연결 확인
        # 직접 시그널 발화로 연결 여부 검증
        proc_section = panel._sections["procedural"]
        proc_section.delete_requested.emit(skill)

        assert len(received) == 1
        assert received[0] is skill


# ---------------------------------------------------------------------------
# 삭제 핸들러 (view 정리)
# ---------------------------------------------------------------------------

class TestDeleteHandler:
    def test_delete_removes_component_and_closes_tab(self, qapp):
        """_on_delete_component: 탭이 열려 있으면 닫히고 프로젝트에서 제거된다."""
        window = MainWindow()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        window.set_project(proj)
        window._open_component(skill)

        assert window._tabs.count() == _FIXED_TAB_COUNT + 1  # 고정 탭 + skill 탭
        assert skill.id in window._open_tabs

        # QMessageBox 없이 직접 모델/뷰 정리 메서드를 호출
        # (확인 다이얼로그는 UI 테스트 범위 밖)
        from daedalus.model.project import remove_component
        comp_id = skill.id
        remove_component(window._project, skill)

        # 탭 닫기
        if comp_id in window._open_tabs:
            window._close_tab(window._open_tabs[comp_id])

        assert skill not in window._project.skills
        assert window._tabs.count() == _FIXED_TAB_COUNT  # 고정 탭만
        window.close()



class TestRegistryPreviewSignal:
    """레지스트리 우클릭 컴파일 미리보기 — 트랜스퍼 스킬은 캔버스 노드가 없어
    placement 메뉴가 닿지 않으므로(사용자 보고) 레지스트리가 공통 진입점이다."""

    def test_preview_signal_emitted(self, qapp):
        panel = RegistryPanel()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        panel.set_project(proj)

        received: list[object] = []
        panel.component_preview_requested.connect(lambda c: received.append(c))
        panel._sections["procedural"].preview_requested.emit(skill)

        assert received == [skill]

    def test_window_handler_opens_preview_dialog(self, qapp, monkeypatch):
        """window 배선 — 시그널이 show_preview_dialog(공용 실체)로 흐른다."""
        from daedalus.view.actions import preview as preview_mod
        from daedalus.view.app import MainWindow

        win = MainWindow()
        proj = PluginProject(name="p")
        skill = _make_proc("my-skill")
        proj.skills.append(skill)
        win.load_project(proj)

        calls: list[tuple] = []
        monkeypatch.setattr(
            preview_mod, "show_preview_dialog",
            lambda parent, component, project=None, resolved_hooks=None:
                calls.append((component, project)),
        )
        win._registry_panel.component_preview_requested.emit(skill)

        assert calls == [(skill, proj)]
        win.close()
