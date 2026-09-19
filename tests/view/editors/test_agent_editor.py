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


def test_output_ports_come_from_transfer_on(qapp):
    """캔버스 포트 소스 — transfer_on이 단일 진실이다."""
    agent = _make_agent(transfer_on=[EventDef(name="ok"), EventDef(name="fail")])
    assert [e.name for e in agent.output_ports()] == ["ok", "fail"]


def test_exit_points_do_not_feed_output_ports():
    """RF-1b — ExitPoint 폴백은 삭제됐다. transfer_on이 비면 출력 포트도 없다
    (v1 파일의 ExitPoint 승계는 로드 마이그레이션 소관 — serialize._migrate_v1)."""
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="f", states=[entry, done], initial_state=entry, final_states=[done],
    )
    agent = AgentDefinition(fsm=fsm, name="legacy", description="")
    assert agent.transfer_on == []
    assert agent.output_ports() == []


# ---------------------------------------------------------------------------
# fork 에이전트 — 포트 대신 "사용하는 fork 스킬" 목록 (WP-FK2 D)
# ---------------------------------------------------------------------------

def _fork_project(fork_agent_name: str = "helper", used_by: tuple[str, ...] = ()):
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.agent import ForkAgent
    from daedalus.model.plugin.config import SyncForkSkillConfig
    from daedalus.model.plugin.skill import SyncForkSkill
    from daedalus.model.project import PluginProject

    agent = ForkAgent(name=fork_agent_name, description="fork 실행 기반")
    skills = []
    for name in used_by:
        s = SimpleState(name="s")
        skills.append(
            SyncForkSkill(
                fsm=StateMachine(name=f"{name}_fsm", states=[s], initial_state=s),
                name=name, description="d",
                config=SyncForkSkillConfig(agent=fork_agent_name),
            )
        )
    return agent, PluginProject(name="p", skills=skills, agents=[agent])


def test_fork_agent_editor_lists_the_fork_skills_using_it(qapp):
    """산출("## Invocation Contract")·삭제 확인·MCP와 **같은 유도 함수**를 쓴다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent, project = _fork_project(used_by=("scout", "audit"))
    editor = AgentEditor(agent, project=project)

    panel = editor._fork_users_panel
    assert panel is not None
    names = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert names == ["audit", "scout"]  # 정렬 — 결정적
    # isHidden — 창을 띄우지 않은 헤드리스에서 isVisible은 항상 False다.
    assert panel._empty_label.isHidden() is True
    assert panel._list.isHidden() is False


def test_fork_agent_editor_says_when_nobody_uses_it(qapp):
    """아무도 부르지 않는 fork 에이전트는 산출은 되지만 죽은 코드다 — 말해 준다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent, project = _fork_project()
    editor = AgentEditor(agent, project=project)

    panel = editor._fork_users_panel
    assert panel._list.count() == 0
    assert panel._list.isHidden() is True
    assert panel._empty_label.isHidden() is False


def test_fork_users_panel_refreshes_from_the_model(qapp):
    """다른 탭에서 fork 스킬의 agent를 바꾼 뒤 돌아오면 반영돼야 한다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent, project = _fork_project(used_by=("scout",))
    editor = AgentEditor(agent, project=project)
    project.skills[0].config.agent = "general-purpose"
    editor._fork_users_panel.refresh()
    assert editor._fork_users_panel._list.count() == 0


def test_workflow_agent_editor_has_no_fork_users_panel(qapp):
    """워크플로 에이전트는 fork 에이전트가 될 수 없다 — 이 목록 자체가 없다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    editor = AgentEditor(_make_agent())
    assert editor._fork_users_panel is None
    assert editor._callers_panel is not None


def test_agent_editor_port_panels_follow_the_placement_declaration(qapp):
    """포트 패널 게이트는 **배치 선언**이다 — 종류 열거가 아니다 (WP-2d).

    스킬 편집기와 같은 술어(`is_state_placeable`)를 쓴다. 종류로 물으면 새
    에이전트 종류가 `PLACEMENT=STATE`를 선언해도 포트 편집기를 조용히 잃고,
    GUI에서 `transfer_on`을 만들 길이 없어진다(스킬 쪽에서 실제로 났던 버그).
    """
    from daedalus.view.editors.agent_editor import AgentEditor
    from daedalus.view.editors.skill_editor import _TransferOnPanel

    workflow = AgentEditor(_make_agent())
    assert len(workflow.findChildren(_TransferOnPanel)) == 2  # 출력 포트 + 호출 포트

    fork_agent, project = _fork_project()
    fork = AgentEditor(fork_agent, project=project)
    assert fork.findChildren(_TransferOnPanel) == []
