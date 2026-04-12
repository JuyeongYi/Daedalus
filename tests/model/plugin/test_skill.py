from __future__ import annotations

import pytest
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.skill import Skill, ProceduralSkill, DeclarativeSkill
from daedalus.model.plugin.config import ProceduralSkillConfig, DeclarativeSkillConfig
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def test_plugin_component_is_abstract():
    with pytest.raises(TypeError):
        PluginComponent(name="x", description="y")


def test_skill_is_abstract():
    with pytest.raises(TypeError):
        Skill(name="x", description="y")


def test_procedural_skill():
    s1 = SimpleState(name="start")
    sm = StateMachine(name="flow", initial_state=s1, states=[s1])
    skill = ProceduralSkill(
        name="deploy",
        description="배포 스킬",
        fsm=sm,
        config=ProceduralSkillConfig(),
    )
    assert skill.name == "deploy"
    assert skill.fsm is sm
    assert skill.fsm.blackboard is not None
    assert isinstance(skill, Skill)
    assert isinstance(skill, WorkflowComponent)
    assert isinstance(skill, PluginComponent)


def test_procedural_skill_mro():
    mro_names = [c.__name__ for c in ProceduralSkill.__mro__]
    assert mro_names.index("Skill") < mro_names.index("PluginComponent")
    assert "WorkflowComponent" in mro_names


def test_declarative_skill():
    skill = DeclarativeSkill(
        name="api-conventions",
        description="API 컨벤션",
        content="RESTful 패턴을 사용하라.",
        config=DeclarativeSkillConfig(),
    )
    assert skill.name == "api-conventions"
    assert skill.content == "RESTful 패턴을 사용하라."
    assert isinstance(skill, Skill)
    assert not isinstance(skill, WorkflowComponent)


def _make_fsm():
    from daedalus.model.fsm.state import SimpleState as _SS
    from daedalus.model.fsm.machine import StateMachine as _SM
    s = _SS(name="s")
    return _SM(name="f", states=[s], initial_state=s)


def test_procedural_skill_output_events_default():
    fsm = _make_fsm()
    skill = ProceduralSkill(fsm=fsm, name="S", description="d")
    assert skill.output_events == ["done"]


def test_procedural_skill_output_events_custom():
    fsm = _make_fsm()
    skill = ProceduralSkill(
        fsm=fsm, name="S", description="d",
        output_events=["done", "error", "retry"],
    )
    assert skill.output_events == ["done", "error", "retry"]
