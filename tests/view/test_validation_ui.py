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
