"""AgentEditor — 본문 + 포트, 스킬 편집기와 같은 레벨 (WP-AF).

내부 FSM(그래프 탭·로컬 스킬·EntryPoint/ExitPoint 편집)은 퇴역했다. 절차는
본문 산문이 담고, 결과 분기는 transfer_on(출력 포트)이 담는다.
"""
from __future__ import annotations

from PySide6.QtWidgets import QTabWidget

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import AgentDefinition


def _make_agent(transfer_on: list[EventDef] | None = None):
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="test_fsm", states=[entry], initial_state=entry)
    return AgentDefinition(
        fsm=fsm, name="test-agent", description="테스트",
        transfer_on=transfer_on if transfer_on is not None else [EventDef(name="done")],
    )


def test_agent_editor_smoke(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor

    AgentEditor(_make_agent())


def test_agent_editor_has_no_tabs(qapp):
    """그래프/컨텐츠 탭 구조는 퇴역 — 컨텐츠 편집기가 곧 에디터 전체다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    editor = AgentEditor(_make_agent())
    assert editor.findChild(QTabWidget) is None


def test_agent_editor_changed_signal(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor

    editor = AgentEditor(_make_agent())
    assert hasattr(editor, "agent_changed")


def test_agent_editor_has_component_editor(qapp):
    """스킬 편집기와 같은 얼굴 — ComponentEditor(프론트매터 + 본문)."""
    from daedalus.view.editors.agent_editor import AgentEditor
    from daedalus.view.editors.component_editor import ComponentEditor

    editor = AgentEditor(_make_agent())
    assert editor.findChild(ComponentEditor) is not None


def test_transfer_on_panel_edits_agent_output_ports(qapp):
    """출력 포트 패널이 agent.transfer_on을 직접 편집한다 — ExitPoint 승계."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent = _make_agent()
    editor = AgentEditor(agent)
    panel = editor._transfer_on_panel
    assert panel._transfer_on is agent.transfer_on  # 같은 리스트를 편집해야 반영된다


def test_entry_paths_panel_edits_agent_entry_paths(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor

    agent = _make_agent()
    editor = AgentEditor(agent)
    assert editor._entry_paths_panel._transfer_on is agent.entry_paths


def test_output_events_come_from_transfer_on(qapp):
    """캔버스 포트 소스 — transfer_on이 단일 진실이다."""
    agent = _make_agent(transfer_on=[EventDef(name="ok"), EventDef(name="fail")])
    assert agent.output_events == ["ok", "fail"]


def test_legacy_exit_points_still_feed_output_events():
    """transfer_on이 빈 구버전 객체는 ExitPoint 폴백 — 메모리 내 호환."""
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="f", states=[entry, done], initial_state=entry, final_states=[done],
    )
    agent = AgentDefinition(fsm=fsm, name="legacy", description="")
    assert agent.transfer_on == []
    assert agent.output_events == ["done"]
