from __future__ import annotations

import pytest
from daedalus.model.plugin.config import (
    ComponentConfig,
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


def test_component_config_is_abstract():
    with pytest.raises(TypeError):
        ComponentConfig()


def test_skill_config_is_abstract():
    with pytest.raises(TypeError):
        SkillConfig()


def test_procedural_skill_config_defaults():
    c = ProceduralSkillConfig()
    assert c.model == ModelType.INHERIT
    assert c.effort is None
    assert c.hooks is None
    assert c.argument_hint is None
    assert c.allowed_tools == []
    assert c.paths is None
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
    assert c.model == ModelType.INHERIT
    assert c.effort is None
    assert c.hooks is None
    assert c.tools is None
    assert c.disallowed_tools is None
    assert c.permission_mode == PermissionMode.DEFAULT
    assert c.max_turns is None
    assert c.skills == []
    assert c.mcp_servers is None
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


def test_component_config_shared_fields():
    """ComponentConfig 공통 필드가 모든 서브클래스에서 동작하는지 확인."""
    proc = ProceduralSkillConfig(model=ModelType.OPUS, effort=EffortLevel.MAX)
    agent = AgentConfig(model=ModelType.OPUS, effort=EffortLevel.MAX)
    assert proc.model == agent.model
    assert proc.effort == agent.effort


# --- TransferSkillConfig, FieldSpec, FIELD_REGISTRY tests ---

def test_transfer_skill_config_defaults():
    from daedalus.model.plugin.config import TransferSkillConfig
    cfg = TransferSkillConfig()
    assert cfg.kind == "transfer"
    assert cfg.disable_model_invocation is False
    assert cfg.user_invocable is False
    assert cfg.context == SkillContext.INLINE
    assert cfg.shell == SkillShell.BASH


def test_field_spec_dataclass():
    from daedalus.model.plugin.config import FieldSpec
    fs = FieldSpec(label="model", widget_type="combo", attr="model", choices=["a", "b"])
    assert fs.label == "model"
    assert fs.widget_type == "combo"
    assert fs.attr == "model"
    assert fs.choices == ["a", "b"]
    assert fs.default_enabled is False


def test_field_registry_has_all_kinds():
    from daedalus.model.plugin.config import FIELD_REGISTRY
    assert "procedural" in FIELD_REGISTRY
    assert "declarative" in FIELD_REGISTRY
    assert "transfer" in FIELD_REGISTRY
    assert "agent" in FIELD_REGISTRY


def test_field_registry_procedural_fields():
    from daedalus.model.plugin.config import FIELD_REGISTRY
    attrs = [f.attr for f in FIELD_REGISTRY["procedural"]]
    assert "model" in attrs
    assert "effort" in attrs
    assert "context" in attrs
    assert "shell" in attrs
    assert "disable_model_invocation" in attrs
    assert "user_invocable" in attrs
    assert "argument_hint" in attrs
    assert "allowed_tools" in attrs
    assert "paths" in attrs


def test_field_registry_transfer_fields():
    from daedalus.model.plugin.config import FIELD_REGISTRY
    attrs = [f.attr for f in FIELD_REGISTRY["transfer"]]
    assert "model" in attrs
    assert "context" in attrs
    assert "shell" in attrs
    assert "disable_model_invocation" in attrs
    # transfer에는 user_invocable, argument_hint 없음
    assert "user_invocable" not in attrs
    assert "argument_hint" not in attrs


def test_field_registry_declarative_fields():
    from daedalus.model.plugin.config import FIELD_REGISTRY
    attrs = [f.attr for f in FIELD_REGISTRY["declarative"]]
    assert "model" in attrs
    assert "effort" in attrs
    assert "argument_hint" in attrs
    # declarative에는 context, shell 없음
    assert "context" not in attrs
    assert "shell" not in attrs


def test_field_registry_agent_fields():
    from daedalus.model.plugin.config import FIELD_REGISTRY
    attrs = [f.attr for f in FIELD_REGISTRY["agent"]]
    assert "model" in attrs
    assert "effort" in attrs
    assert "permission_mode" in attrs
    assert "max_turns" in attrs
