from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    DelegationDef,
    DispatchMode,
    DynamicWorkflowDef,
    PhaseSpec,
    TeammateSpec,
    TeamSpawnDef,
    WaitMode,
)
from daedalus.model.project import PluginProject


def _make_agent(name: str = "worker") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name=f"{name}_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )
    return AgentDefinition(fsm=fsm, name=name, description="")


def test_delegation_def_is_abstract():
    with pytest.raises(TypeError):
        DelegationDef(name="x", description="")  # type: ignore[abstract]


def test_team_spawn_def_defaults():
    d = TeamSpawnDef(name="review_team", description="")
    assert d.kind == "team_spawn"
    assert d.wait_mode is WaitMode.WAIT
    assert d.teammates == []


def test_team_spawn_def_with_teammates():
    agent = _make_agent()
    d = TeamSpawnDef(
        name="t", description="",
        teammates=[TeammateSpec(agent_ref=agent, count=3, role_note="리뷰 담당")],
        wait_mode=WaitMode.FIRE_AND_FORGET,
    )
    assert d.teammates[0].agent_ref is agent
    assert d.teammates[0].count == 3
    assert d.wait_mode is WaitMode.FIRE_AND_FORGET


def test_dynamic_workflow_def_defaults():
    d = DynamicWorkflowDef(name="audit", description="")
    assert d.kind == "dynamic_workflow"
    assert d.objective == ""
    assert d.phases == []


def test_dynamic_workflow_def_with_phases():
    agent = _make_agent()
    d = DynamicWorkflowDef(
        name="audit", description="", objective="저장소 감사",
        phases=[
            PhaseSpec(title="분석", detail="차원별 리뷰"),
            PhaseSpec(title="검증", agent_ref=agent),
        ],
    )
    assert d.phases[0].agent_ref is None
    assert d.phases[1].agent_ref is agent


def test_agora_dispatch_def_defaults():
    d = AgoraDispatchDef(name="notify", description="")
    assert d.kind == "agora_dispatch"
    assert d.mode is DispatchMode.DISPATCH
    assert d.target == ""
    assert d.msgtype == ""
    assert d.payload_note == ""


def test_agora_dispatch_broadcast():
    d = AgoraDispatchDef(
        name="announce", description="",
        mode=DispatchMode.BROADCAST, msgtype="status_update",
        payload_note="진행률을 담아라",
    )
    assert d.mode is DispatchMode.BROADCAST


def test_all_defs_are_plugin_components():
    from daedalus.model.plugin.base import PluginComponent
    for d in (
        TeamSpawnDef(name="a", description=""),
        DynamicWorkflowDef(name="b", description=""),
        AgoraDispatchDef(name="c", description=""),
    ):
        assert isinstance(d, (PluginComponent, DelegationDef))
        assert isinstance(d, DelegationDef)


def test_project_holds_delegations():
    p = PluginProject(name="proj")
    assert p.delegations == []
    d = TeamSpawnDef(name="t", description="")
    p.delegations.append(d)
    assert p.delegations == [d]
