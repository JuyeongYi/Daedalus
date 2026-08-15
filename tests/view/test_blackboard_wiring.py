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


def test_legacy_local_skill_blackboard_parent_survives_load(qapp):
    """WP-AF — 로컬 스킬 생성 UI는 퇴역했지만, 기존 파일의 로컬 스킬은
    역직렬화가 blackboard.parent를 소유 에이전트 FSM으로 재연결한다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.model.project import PluginProject
    from daedalus.model.serialize import deserialize_project, serialize_project

    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="a_fsm", states=[entry], initial_state=entry)
    start_state = SimpleState(name="start")
    local_fsm = StateMachine(
        name="local_fsm", states=[start_state], initial_state=start_state,
    )
    local = ProceduralSkill(fsm=local_fsm, name="local-tool", description="")
    agent = AgentDefinition(fsm=fsm, name="my-agent", description="", skills=[local])

    loaded = deserialize_project(
        serialize_project(PluginProject(name="p", agents=[agent]))
    )
    restored = loaded.agents[0]
    assert restored.skills[0].fsm.blackboard.parent is restored.fsm.blackboard
