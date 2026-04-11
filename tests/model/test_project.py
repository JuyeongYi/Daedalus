from __future__ import annotations

from daedalus.model.project import PluginProject
from daedalus.model.plugin.skill import ProceduralSkill, DeclarativeSkill
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig, DeclarativeSkillConfig, AgentConfig
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def test_plugin_project_empty():
    proj = PluginProject(name="my-plugin")
    assert proj.name == "my-plugin"
    assert proj.skills == []
    assert proj.agents == []


def test_plugin_project_with_components():
    s1 = SimpleState(name="s1")
    sm = StateMachine(name="flow", initial_state=s1, states=[s1])

    proc_skill = ProceduralSkill(
        name="deploy",
        description="배포",
        fsm=sm,
        config=ProceduralSkillConfig(),
    )
    decl_skill = DeclarativeSkill(
        name="conventions",
        description="컨벤션",
        content="...",
        config=DeclarativeSkillConfig(),
    )
    agent = AgentDefinition(
        name="reviewer",
        description="리뷰어",
        fsm=sm,
        config=AgentConfig(),
    )

    proj = PluginProject(
        name="my-plugin",
        skills=[proc_skill, decl_skill],
        agents=[agent],
    )
    assert len(proj.skills) == 2
    assert len(proj.agents) == 1
    assert isinstance(proj.skills[0], ProceduralSkill)
    assert isinstance(proj.skills[1], DeclarativeSkill)
