from __future__ import annotations

import pytest
from daedalus.model.plugin.config import (
    ComponentConfig,
    SkillConfig,
    ProceduralSkillConfig,
    DeclarativeSkillConfig,
    AgentConfig,
    ForkAgentConfig,
    TransferSkillConfig,
    ForkSkillConfig,
    external_plugin_id_declared,
    is_external_skill_ref,
)
from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.enums import (
    ModelType,
    EffortLevel,
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
    # tri-state (A8) — 선언 기본값은 **미지정**이다(프론트매터 키 생략).
    assert c.disable_model_invocation is None
    assert c.user_invocable is None
    assert c.shell == SkillShell.BASH
    # fork 실행은 별도 종류다(2026-09-13) — 절차형은 context/agent를 갖지 않는다.
    assert not hasattr(c, "context")
    assert not hasattr(c, "agent")


def test_procedural_skill_config_custom():
    c = ProceduralSkillConfig(
        allowed_tools=["Bash", "Read"],
        model=ModelType.SONNET,
        effort=EffortLevel.HIGH,
        disable_model_invocation=True,
    )
    assert c.allowed_tools == ["Bash", "Read"]
    assert c.model == ModelType.SONNET


def test_fork_skill_config_is_abstract():
    """`ForkSkillConfig`는 추상이다 — background 값(= 종류)을 말하지 않는 fork는 없다."""
    import pytest

    with pytest.raises(TypeError):
        ForkSkillConfig()


def test_sync_and_async_fork_config_defaults():
    from daedalus.model.plugin.config import (
        AsyncForkSkillConfig,
        StepSkillConfig,
        SyncForkSkillConfig,
    )

    for cls, kind in ((SyncForkSkillConfig, "sync_fork"), (AsyncForkSkillConfig, "async_fork")):
        c = cls()
        assert c.kind == kind
        assert c.agent == "general-purpose"
        assert c.user_invocable is None
        assert isinstance(c, ForkSkillConfig)
        assert isinstance(c, StepSkillConfig)
        # fork config는 절차형 config의 하위가 아니다 — 형제다(계층 분리).
        assert not isinstance(c, ProceduralSkillConfig)
        assert cls(agent="Explore").agent == "Explore"


def test_declarative_skill_config():
    c = DeclarativeSkillConfig(user_invocable=False)
    assert c.user_invocable is False
    # tri-state (A8) — 지정하지 않은 쪽은 None(미지정)이다.
    assert c.disable_model_invocation is None


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


# --- WP-H: AgentConfig 감사 테스트 ---

def test_agent_config_no_initial_prompt_field():
    """본문 단일 진실은 AgentDefinition.body — initial_prompt 필드 부재 고정 (감사 2-5)."""
    import dataclasses
    names = {f.name for f in dataclasses.fields(AgentConfig)}
    assert "initial_prompt" not in names, "AgentConfig에 initial_prompt 필드가 잔존함"


def test_agent_config_mcp_servers_is_list_str():
    """mcp_servers는 list[str] (이름 참조 목록) — list[dict] 아님."""
    c = AgentConfig(mcp_servers=["server-a", "server-b"])
    assert c.mcp_servers == ["server-a", "server-b"]
    assert all(isinstance(s, str) for s in c.mcp_servers)


# --- TransferSkillConfig tests ---

def test_transfer_skill_config_defaults():
    cfg = TransferSkillConfig()
    assert cfg.kind == "transfer"
    assert cfg.disable_model_invocation is False
    assert cfg.user_invocable is False
    assert not hasattr(cfg, "context")
    assert cfg.shell == SkillShell.BASH


# --- WP-B: 외부 플러그인 스킬 참조 (플러그인:스킬, 사용자 확정 2026-09-19) ---


def test_is_external_skill_ref_by_colon():
    assert is_external_skill_ref("alpha:review") is True
    assert is_external_skill_ref("local-skill") is False
    assert is_external_skill_ref("") is False


def test_external_plugin_id_declared_exact_and_bare():
    assert external_plugin_id_declared("alpha", {"alpha"}) is True
    assert external_plugin_id_declared("alpha", {"alpha@mkt"}) is True
    assert external_plugin_id_declared("alpha@mkt", {"alpha"}) is True
    assert external_plugin_id_declared("alpha", {"beta@mkt"}) is False
    assert external_plugin_id_declared("alpha", set()) is False


def test_agent_config_base_name_refs_excludes_external_skill_refs():
    """`config.skills`의 name_refs(SKILLS)는 프로젝트 스킬 이름만 — 외부
    참조(콜론 포함)는 dangling_string_reference 오탐을 막기 위해 뺀다."""
    cfg = AgentConfig(skills=["local-a", "alpha:review", "local-b"])
    assert cfg.name_refs(Bucket.SKILLS) == ["local-a", "local-b"]
    assert cfg.name_refs(Bucket.AGENTS) == []


def test_agent_config_base_external_plugin_refs_extracts_bare_plugin_id():
    cfg = AgentConfig(skills=["local-a", "alpha:review", "beta@mkt:lint"])
    assert cfg.external_plugin_refs() == ["alpha", "beta@mkt"]


def test_agent_config_base_external_plugin_refs_skips_malformed():
    """빈 플러그인 부분·빈 스킬 이름은 형식이 깨진 참조라 건너뛴다."""
    cfg = AgentConfig(skills=[":review", "alpha:", "ok:skill"])
    assert cfg.external_plugin_refs() == ["ok"]


def test_agent_config_base_external_plugin_refs_ignores_empty_skills():
    cfg = AgentConfig()
    assert cfg.external_plugin_refs() == []


def test_fork_agent_config_shares_external_plugin_refs():
    """`ForkAgentConfig`도 `AgentConfigBase`를 상속하므로 같은 메서드를 쓴다."""
    cfg = ForkAgentConfig(skills=["alpha:review"])
    assert cfg.external_plugin_refs() == ["alpha"]


def test_component_config_default_external_plugin_refs_is_empty():
    """스킬 config는 이 메서드를 오버라이드하지 않는다 — 기본값 그대로."""
    cfg = ProceduralSkillConfig()
    assert cfg.external_plugin_refs() == []


