from __future__ import annotations

import pytest
from daedalus.model.plugin.config import (
    SkillConfig,
    ProceduralSkillConfig,
    DeclarativeSkillConfig,
    AgentConfig,
)
from daedalus.model.plugin.enums import (
    ModelType,
    EffortLevel,
    SkillContext,
    SkillShell,
    PermissionMode,
    MemoryScope,
    AgentIsolation,
    AgentColor,
)


def test_skill_config_is_abstract():
    with pytest.raises(TypeError):
        SkillConfig()


def test_procedural_skill_config_defaults():
    c = ProceduralSkillConfig()
    assert c.argument_hint is None
    assert c.allowed_tools == []
    assert c.model == ModelType.INHERIT
    assert c.effort is None
    assert c.disable_model_invocation is False
    assert c.user_invocable is True
    assert c.context == SkillContext.INLINE
    assert c.agent is None
    assert c.shell == SkillShell.BASH


def test_procedural_skill_config_custom():
    c = ProceduralSkillConfig(
        allowed_tools=["Bash", "Read"],
        model=ModelType.SONNET,
        effort=EffortLevel.HIGH,
        disable_model_invocation=True,
        context=SkillContext.FORK,
        agent="Explore",
    )
    assert c.allowed_tools == ["Bash", "Read"]
    assert c.model == ModelType.SONNET
    assert c.context == SkillContext.FORK
    assert c.agent == "Explore"


def test_declarative_skill_config():
    c = DeclarativeSkillConfig(user_invocable=False)
    assert c.user_invocable is False
    assert c.disable_model_invocation is False


def test_agent_config_defaults():
    c = AgentConfig()
    assert c.tools is None
    assert c.disallowed_tools is None
    assert c.model == ModelType.INHERIT
    assert c.permission_mode == PermissionMode.DEFAULT
    assert c.max_turns is None
    assert c.skills == []
    assert c.mcp_servers is None
    assert c.hooks is None
    assert c.memory is None
    assert c.background is False
    assert c.isolation == AgentIsolation.NONE
    assert c.color is None
    assert c.initial_prompt is None


def test_agent_config_custom():
    c = AgentConfig(
        tools=["Read", "Grep", "Glob"],
        model=ModelType.HAIKU,
        permission_mode=PermissionMode.DONT_ASK,
        memory=MemoryScope.PROJECT,
        color=AgentColor.BLUE,
    )
    assert c.tools == ["Read", "Grep", "Glob"]
    assert c.model == ModelType.HAIKU
    assert c.memory == MemoryScope.PROJECT
    assert c.color == AgentColor.BLUE
