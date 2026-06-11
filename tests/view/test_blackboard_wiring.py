"""WP-N ④ Blackboard parent 배선 — 컴포넌트 생성 경로 검증."""
from __future__ import annotations

from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def test_register_component_wires_blackboard_parent(qapp):
    """새 스킬 등록 시 fsm.blackboard.parent가 프로젝트 블랙보드를 가리킨다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.skill import ProceduralSkill

    window = MainWindow()
    project = PluginProject(name="p")
    window.set_project(project)

    s = SimpleState(name="start")
    fsm = StateMachine(name="s_fsm", states=[s], initial_state=s)
    skill = ProceduralSkill(fsm=fsm, name="my-skill", description="")
    assert skill.fsm.blackboard.parent is None  # 생성 직후엔 미연결

    window._register_component(skill)

    assert skill.fsm.blackboard.parent is project.blackboard
    window.close()


def test_register_agent_wires_blackboard_parent(qapp):
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    from daedalus.model.plugin.agent import AgentDefinition

    window = MainWindow()
    project = PluginProject(name="p")
    window.set_project(project)

    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(name="a_fsm", states=[entry, done],
                       initial_state=entry, final_states=[done])
    agent = AgentDefinition(fsm=fsm, name="my-agent", description="")
    window._register_component(agent)

    assert agent.fsm.blackboard.parent is project.blackboard
    window.close()


def test_agent_editor_local_skill_wires_blackboard_parent(qapp, monkeypatch):
    """에이전트 로컬 스킬 생성 시 fsm.blackboard.parent가
    소유 에이전트 FSM 블랙보드를 가리킨다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.view.editors import agent_editor as ae_module
    from daedalus.view.editors.agent_editor import AgentEditor

    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(name="a_fsm", states=[entry, done],
                       initial_state=entry, final_states=[done])
    agent = AgentDefinition(fsm=fsm, name="my-agent", description="")
    editor = AgentEditor(agent)

    # 이름 입력 다이얼로그 우회
    monkeypatch.setattr(
        ae_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("local-tool", True)),
    )
    editor._on_add_local_skill("procedural")

    assert len(agent.skills) == 1
    local = agent.skills[0]
    assert local.name == "local-tool"
    assert local.fsm.blackboard.parent is agent.fsm.blackboard
    editor.close()
