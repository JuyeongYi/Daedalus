"""역직렬화 계약 — kind 다형성·config 짝 강제·미지 kind 거절 (2026-09-17).

`config.kind`가 매트릭스 키로 승격되면서 클래스는 더 이상 유일 심판이 아니다.
어긋난 조합이 파일에서 들어오면 산출이 두 가지 사실을 말하므로, 역직렬화가
짝을 강제하고 강등하면 경고를 낸다(원칙 1·5).
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.config import (
    AgentConfig,
    AsyncForkSkillConfig,
    DeclarativeSkillConfig,
    ForkAgentConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillShell,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import (
    _deser_config,
    _ser_config,
    deserialize_project,
    serialize_project,
)
from daedalus.model.serialize.deser_fsm import _Registry
from daedalus.model.serialize.deser_plugin import _deser_agent, _deser_skill


def _fsm(name: str = "m") -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name=name, states=[s], initial_state=s)


#: 구체 config 9종 — 종류마다 기본값과 다른 값을 넣어 왕복을 실제로 확인한다.
ALL_CONFIGS = [
    ProceduralSkillConfig(model=ModelType.OPUS, shell=SkillShell.POWERSHELL),
    SyncForkSkillConfig(agent="Explore", user_invocable=True),
    AsyncForkSkillConfig(agent="Plan", disable_model_invocation=False),
    WrappedSkillConfig(source="ext:skill", usage="reference", enabled=False),
    TransferSkillConfig(user_invocable=False, disable_model_invocation=True),
    DeclarativeSkillConfig(user_invocable=True),
    ReferenceSkillConfig(user_invocable=False),
    AgentConfig(
        tools=["Read"], permission_mode=PermissionMode.PLAN, max_turns=3,
        skills=["a"], mcp_servers=["m"], memory=MemoryScope.PROJECT,
        background=True, isolation=AgentIsolation.WORKTREE, color=AgentColor.RED,
    ),
    ForkAgentConfig(
        tools=["Read"], permission_mode=PermissionMode.PLAN, max_turns=3,
        skills=["a"], mcp_servers=["m"], memory=MemoryScope.PROJECT,
        color=AgentColor.CYAN,
    ),
]


@pytest.mark.parametrize("config", ALL_CONFIGS, ids=lambda c: c.kind)
def test_every_config_kind_roundtrips(config):
    again = _deser_config(_ser_config(config))
    assert type(again) is type(config)
    assert again == config


def test_fork_agent_config_never_carries_background_or_isolation():
    """파일에 남아 있어도 흡수하지 않는다 — 없는 개념의 잔재 금지."""
    data = _ser_config(ForkAgentConfig())
    assert "background" not in data
    assert "isolation" not in data
    data.update(background=True, isolation="worktree")
    cfg = _deser_config(data)
    assert type(cfg) is ForkAgentConfig
    assert not hasattr(cfg, "background")
    assert not hasattr(cfg, "isolation")


def test_retired_fork_config_kind_is_rejected():
    """마이그레이션을 거치지 않고 들어온 퇴역 키는 조용히 강등되지 않는다."""
    with pytest.raises(ValueError, match="fork"):
        _deser_config({"kind": "fork", "agent": "Explore"})


def test_missing_config_kind_means_unwritten_not_unknown():
    """kind 키 부재는 "미지"가 아니라 "미기재"다 — 호출자가 기본 config를 쓴다."""
    assert _deser_config({"model": "opus"}) is None


def test_unknown_skill_kind_is_rejected_not_demoted():
    """조용한 DeclarativeSkill 강등은 스킬 종류·본문을 통째로 바꿔 놓는다."""
    reg = _Registry()
    with pytest.raises(ValueError, match="nonsense"):
        _deser_skill({"kind": "nonsense", "name": "x"}, reg)


def test_unknown_agent_kind_is_rejected():
    reg = _Registry()
    with pytest.raises(ValueError, match="nonsense"):
        _deser_agent({"kind": "nonsense", "name": "x"}, reg)


def test_agent_kind_key_absent_means_workflow_agent():
    """구버전 파일에는 에이전트 kind 키가 없다 — 워크플로 에이전트로 읽는다."""
    reg = _Registry()
    agent = _deser_agent(
        {"name": "a", "fsm": {"name": "af", "states": [], "transitions": []}}, reg
    )
    assert type(agent) is AgentDefinition


def test_mismatched_config_kind_is_demoted_with_a_warning():
    """`procedural_skill` + `sync_fork` config는 산출이 두 사실을 말한다 — 경고 후 강등."""
    reg = _Registry()
    skill = _deser_skill(
        {
            "kind": "procedural_skill", "name": "x",
            "fsm": {"name": "f", "states": [], "transitions": []},
            "config": {"kind": "sync_fork", "agent": "Explore"},
        },
        reg,
    )
    assert type(skill) is ProceduralSkill
    assert type(skill.config) is ProceduralSkillConfig
    assert any("config 종류" in w and "'x'" in w for w in reg.warnings)


def test_mismatched_agent_config_kind_is_demoted_with_a_warning():
    reg = _Registry()
    agent = _deser_agent(
        {
            "kind": "fork_agent", "name": "fa",
            "config": {"kind": "agent", "background": True},
        },
        reg,
    )
    assert type(agent) is ForkAgent
    assert type(agent.config) is ForkAgentConfig
    assert any("config 종류" in w for w in reg.warnings)


def test_project_with_every_component_kind_roundtrips():
    project = PluginProject(
        name="p",
        skills=[
            ProceduralSkill(fsm=_fsm(), name="p1", description="d"),
            SyncForkSkill(
                fsm=_fsm(), name="sf", description="d",
                config=SyncForkSkillConfig(agent="Explore"),
            ),
            AsyncForkSkill(
                fsm=_fsm(), name="af", description="d",
                config=AsyncForkSkillConfig(agent="Plan"),
            ),
            TransferSkill(fsm=_fsm(), name="t", description="d"),
            DeclarativeSkill(name="dc", description="d"),
            ReferenceSkill(name="r", description="d"),
        ],
        agents=[
            AgentDefinition(fsm=_fsm(), name="a", description="d"),
            ForkAgent(name="fa", description="d", body="Do it."),
        ],
    )
    warnings: list[str] = []
    again = deserialize_project(serialize_project(project), collect_warnings=warnings)
    assert warnings == []
    assert [type(s) for s in again.skills] == [type(s) for s in project.skills]
    assert [type(a) for a in again.agents] == [type(a) for a in project.agents]
    assert again.agents[1].body == "Do it."


def test_fork_agent_record_has_no_graph_derived_keys():
    """fork 에이전트 dict에는 fsm·포트·배치 키가 아예 없다."""
    project = PluginProject(name="p", agents=[ForkAgent(name="fa", description="d")])
    record = serialize_project(project)["agents"][0]
    for key in (
        "fsm", "transfer_on", "call_agents", "execution_policy",
        "reference_placements", "graph_layout", "edge_layout",
    ):
        assert key not in record, key


def test_v1_migration_keeps_a_fork_skill_agent():
    """`migrate_skill_context`의 `agent` 팝이 살아 있는 필드를 지우면 안 된다."""
    data = {
        "format": 1,
        "name": "p",
        "skills": [{
            "kind": "sync_fork_skill", "id": "s1", "name": "scout",
            "config": {"kind": "sync_fork", "agent": "Explore"},
            "fsm": {"name": "f", "states": [], "transitions": []},
        }],
        "agents": [],
    }
    project = deserialize_project(data)
    assert project.skills[0].config.agent == "Explore"
