"""ValidationPanel 통합 테스트 — F7 액션, 검증 흐름 (WP-J)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _make_clean_project() -> PluginProject:
    """검증 위반이 없는 최소 프로젝트."""
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    skill = DeclarativeSkill(name="my-skill", description="d")
    project = PluginProject(name="p", skills=[skill])
    return project


def _make_violating_project() -> PluginProject:
    """duplicate_component_name 위반이 포함된 프로젝트."""
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    skill1 = ProceduralSkill(fsm=fsm, name="dup-skill", description="a")
    # 다른 FSM 객체로도 same name → duplicate_component_name
    s2 = SimpleState(name="start2")
    fsm2 = StateMachine(name="f2", initial_state=s2, states=[s2])
    skill2 = ProceduralSkill(fsm=fsm2, name="dup-skill", description="b")
    return PluginProject(name="p", skills=[skill1, skill2])


# ---------------------------------------------------------------------------
# F7 액션 존재 + 단축키
# ---------------------------------------------------------------------------

def test_validate_action_exists(qapp):
    """'프로젝트 검증' 액션이 존재한다."""
    window = MainWindow()
    assert hasattr(window, "_validate_action")
    assert window._validate_action.text() == "프로젝트 검증"
    window.close()


def test_validate_action_shortcut_f7(qapp):
    """검증 액션의 단축키가 F7이다."""
    window = MainWindow()
    shortcut = window._validate_action.shortcut()
    # QKeySequence("F7")와 비교
    assert shortcut == QKeySequence(Qt.Key.Key_F7)
    window.close()


# ---------------------------------------------------------------------------
# F7 trigger → ValidationPanel 갱신
# ---------------------------------------------------------------------------

def test_f7_trigger_updates_validation_panel(qapp):
    """F7 실행 시 위반이 있으면 ValidationPanel에 항목이 생긴다."""
    window = MainWindow()
    project = _make_violating_project()
    window.set_project(project)

    window._run_validation()
    assert window._validation_panel._table.rowCount() > 0
    window.close()


def test_f7_trigger_clean_project_shows_no_errors(qapp):
    """위반이 없는 프로젝트 검증 시 ValidationPanel이 비어 있다."""
    window = MainWindow()
    project = _make_clean_project()
    window.set_project(project)

    window._run_validation()
    # 위반 0건 (unreachable_state 경고는 스킬 FSM 없으므로 발생 안 함)
    rows = window._validation_panel._table.rowCount()
    # 'my-skill'은 DeclarativeSkill → FSM 없음 → 머신 수준 검사 없음
    assert rows == 0
    window.close()


def test_f7_trigger_updates_statusbar(qapp):
    """F7 실행 시 상태바가 '검증: 오류/경고' 형식으로 갱신된다."""
    window = MainWindow()
    project = _make_violating_project()
    window.set_project(project)

    window._run_validation()
    text = window._status_label.text()
    assert "검증:" in text
    window.close()


def test_f7_no_project_shows_message(qapp):
    """프로젝트가 없을 때 F7은 상태바 안내만 출력하고 크래시가 없다."""
    window = MainWindow()
    # _project는 None
    window._run_validation()
    assert "프로젝트가 없습니다" in window._status_label.text()
    window.close()


# ---------------------------------------------------------------------------
# 더블클릭 → 노드 포커스
# ---------------------------------------------------------------------------

def _make_agent_with_violation() -> tuple[PluginProject, AgentDefinition]:
    """에이전트 FSM 내부에 duplicate_state_name 위반(subject=상태)을 가진 프로젝트.

    주의: AgentEditor._migrate_fsm은 skill_ref 없는 SimpleState를 제거하므로,
    위반 상태에 skill_ref를 부여해 탭 오픈 후에도 위반이 유지되게 한다.
    """
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")

    def _local_skill(name: str) -> ProceduralSkill:
        s = SimpleState(name="s")
        fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
        return ProceduralSkill(fsm=fsm, name=name, description="d")

    sk1 = _local_skill("tool-a")
    sk2 = _local_skill("tool-b")
    node1 = SimpleState(name="task", skill_ref=sk1)
    node2 = SimpleState(name="task", skill_ref=sk2)  # 동명 → duplicate_state_name
    fsm = StateMachine(
        name="af", states=[entry, done, node1, node2],
        initial_state=entry, final_states=[done],
    )
    agent = AgentDefinition(fsm=fsm, name="worker", description="d")
    agent.skills.extend([sk1, sk2])
    project = PluginProject(name="p", agents=[agent])
    return project, agent


def test_focus_agent_tab_open_selects_node(qapp):
    """에이전트 탭이 열려 있을 때 더블클릭 → 탭 전환 + 노드 선택.

    회귀 가드: _focus_in_agent_tab이 AgentEditor의 실제 뷰 속성(_canvas_view)을
    참조하는지 — 잘못된 속성명이어도 select는 되므로 속성 실존까지 확인한다.
    """
    from daedalus.view.editors.agent_editor import AgentEditor

    window = MainWindow()
    project, agent = _make_agent_with_violation()
    window.set_project(project)

    # 에이전트 탭 열기
    window._open_component(agent)
    widget = window._tabs.currentWidget()
    assert isinstance(widget, AgentEditor)
    # 회귀 가드: _focus_in_agent_tab이 조회하는 속성이 실존해야 한다
    assert getattr(widget, "_canvas_view", None) is not None

    # 검증 실행 → duplicate_state_name 에러 획득
    window._run_validation()
    errors = [
        e for e in window._validation_panel._errors
        if e.rule == "duplicate_state_name"
    ]
    assert len(errors) == 1
    error = errors[0]
    assert error.path and error.path[0] == "agent:worker"

    # 프로젝트 탭으로 이동 후 더블클릭 시뮬레이션
    window._tabs.setCurrentIndex(0)
    window._on_validation_item_activated(error)

    # 에이전트 탭으로 전환되었는지
    assert window._tabs.currentWidget() is widget
    # 해당 노드가 씬에서 선택되었는지 (identity 기준)
    selected_models = [
        svm.model
        for svm, item in widget._graph_scene._node_items.items()
        if item.isSelected()
    ]
    assert any(m is error.subject for m in selected_models)
    window.close()


def test_focus_agent_tab_closed_shows_statusbar_hint(qapp):
    """에이전트 탭이 닫혀 있으면 상태바 안내만 출력한다 (탭 자동 오픈 금지)."""
    window = MainWindow()
    project, agent = _make_agent_with_violation()
    window.set_project(project)

    window._run_validation()
    errors = [
        e for e in window._validation_panel._errors
        if e.rule == "duplicate_state_name"
    ]
    assert len(errors) == 1

    tab_count_before = window._tabs.count()
    window._on_validation_item_activated(errors[0])

    assert window._tabs.count() == tab_count_before, "탭 자동 오픈 금지"
    assert "worker" in window._status_label.text()
    assert "탭을 열어" in window._status_label.text()
    window.close()
