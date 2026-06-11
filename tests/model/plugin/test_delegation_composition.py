"""CompositionMode 모델 + 검증 + 직렬화 라운드트립 테스트."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DelegationDef,
    DynamicWorkflowDef,
    TeamSpawnDef,
    TeammateSpec,
    WaitMode,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


def _make_agent(name: str = "worker") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name=f"{name}_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )
    return AgentDefinition(fsm=fsm, name=name, description="")


def _machine_with(*states):
    sm = StateMachine(name="m", states=list(states), initial_state=states[0])
    return sm


# ─────────────────────── CompositionMode 기본값 ───────────────────────

def test_composition_mode_default_is_explicit():
    d = TeamSpawnDef(name="t", description="")
    assert d.composition is CompositionMode.EXPLICIT
    assert d.guidance == ""


def test_composition_mode_explicit_value():
    assert CompositionMode.EXPLICIT.value == "explicit"
    assert CompositionMode.GUIDED.value == "guided"


def test_delegation_def_guided_mode():
    d = DynamicWorkflowDef(
        name="w", description="",
        composition=CompositionMode.GUIDED,
        guidance="본문 참고",
    )
    assert d.composition is CompositionMode.GUIDED
    assert d.guidance == "본문 참고"


# ─────────────────────── empty_delegation GUIDED 미경고 ───────────────────────

def test_guided_team_spawn_no_teammates_no_warning():
    """GUIDED 모드 TeamSpawn은 팀원 0명이어도 경고하지 않는다."""
    d = TeamSpawnDef(name="t", description="", composition=CompositionMode.GUIDED)
    s = SimpleState(name="t_node", skill_ref=d)
    errors = Validator.validate(_machine_with(s))
    assert not any(e.rule == "empty_delegation" for e in errors)


def test_guided_dynamic_workflow_empty_objective_no_warning():
    """GUIDED 모드 DynamicWorkflow는 objective 빈 값이어도 경고하지 않는다."""
    d = DynamicWorkflowDef(name="w", description="", composition=CompositionMode.GUIDED)
    s = SimpleState(name="w_node", skill_ref=d)
    errors = Validator.validate(_machine_with(s))
    assert not any(e.rule == "empty_delegation" for e in errors)


def test_agora_dispatch_empty_msgtype_always_warns_regardless_of_mode():
    """AgoraDispatch msgtype 경고는 GUIDED 모드에도 유지된다."""
    d_guided = AgoraDispatchDef(name="a", description="", composition=CompositionMode.GUIDED)
    s = SimpleState(name="a_node", skill_ref=d_guided)
    errors = Validator.validate(_machine_with(s))
    assert any(e.rule == "empty_delegation" for e in errors)


def test_explicit_team_spawn_no_teammates_still_warns():
    """EXPLICIT(기본값) TeamSpawn은 팀원 0명이면 여전히 경고한다."""
    d = TeamSpawnDef(name="t", description="", composition=CompositionMode.EXPLICIT)
    s = SimpleState(name="t_node", skill_ref=d)
    errors = Validator.validate(_machine_with(s))
    assert any(e.rule == "empty_delegation" for e in errors)


def test_explicit_dynamic_workflow_empty_objective_still_warns():
    """EXPLICIT(기본값) DynamicWorkflow는 objective 빈 값이면 여전히 경고한다."""
    d = DynamicWorkflowDef(name="w", description="", composition=CompositionMode.EXPLICIT)
    s = SimpleState(name="w_node", skill_ref=d)
    errors = Validator.validate(_machine_with(s))
    assert any(e.rule == "empty_delegation" for e in errors)


# ─────────────────────── unregistered_delegation ───────────────────────

def _make_simple_project() -> PluginProject:
    """proc_skill을 가진 기본 프로젝트."""
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.model.fsm.section import EventDef

    s = SimpleState(name="start")
    fsm = StateMachine(name="fsm", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm, name="proc", description="",
        transfer_on=[EventDef(name="done")],
    )
    return PluginProject(name="p", skills=[skill])


def test_unregistered_delegation_detected():
    """배치된 DelegationDef가 project.delegations에 없으면 unregistered_delegation 경고."""
    project = _make_simple_project()
    deleg = TeamSpawnDef(name="orphan-team", description="")
    # delegations에 등록하지 않고 FSM에만 배치
    node = SimpleState(name="d_node", skill_ref=deleg)
    project.skills[0].fsm.states.append(node)

    errors = Validator.validate_project(project)
    assert any(e.rule == "unregistered_delegation" for e in errors)


def test_registered_delegation_not_detected():
    """배치된 DelegationDef가 project.delegations에 있으면 경고 없다."""
    project = _make_simple_project()
    deleg = TeamSpawnDef(name="registered-team", description="")
    project.delegations.append(deleg)  # 등록
    node = SimpleState(name="d_node", skill_ref=deleg)
    project.skills[0].fsm.states.append(node)

    errors = Validator.validate_project(project)
    assert not any(e.rule == "unregistered_delegation" for e in errors)


def test_unregistered_delegation_not_detected_when_not_placed():
    """project.delegations에 등록만 하고 배치 안 하면 경고 없다."""
    project = _make_simple_project()
    deleg = TeamSpawnDef(name="unused-team", description="")
    project.delegations.append(deleg)  # 등록만

    errors = Validator.validate_project(project)
    assert not any(e.rule == "unregistered_delegation" for e in errors)


# ─────────────────────── 직렬화 라운드트립 ───────────────────────

def _roundtrip(p: PluginProject) -> PluginProject:
    data = serialize_project(p)
    return deserialize_project(data)


def test_composition_mode_roundtrip_explicit():
    d = TeamSpawnDef(name="t", description="", composition=CompositionMode.EXPLICIT)
    p = PluginProject(name="P", delegations=[d])
    p2 = _roundtrip(p)
    assert p2.delegations[0].composition is CompositionMode.EXPLICIT


def test_composition_mode_roundtrip_guided():
    d = DynamicWorkflowDef(
        name="w", description="",
        composition=CompositionMode.GUIDED,
        guidance="힌트 텍스트",
    )
    p = PluginProject(name="P", delegations=[d])
    p2 = _roundtrip(p)
    assert p2.delegations[0].composition is CompositionMode.GUIDED
    assert p2.delegations[0].guidance == "힌트 텍스트"


def test_agora_dispatch_composition_roundtrip():
    d = AgoraDispatchDef(
        name="a", description="", msgtype="msg",
        composition=CompositionMode.GUIDED, guidance="payload 참고",
    )
    p = PluginProject(name="P", delegations=[d])
    p2 = _roundtrip(p)
    assert p2.delegations[0].composition is CompositionMode.GUIDED
    assert p2.delegations[0].guidance == "payload 참고"


def test_missing_composition_field_defaults_to_explicit():
    """구버전 JSON(composition 필드 없음)은 EXPLICIT으로 복원된다."""
    d = TeamSpawnDef(name="t", description="")
    p = PluginProject(name="P", delegations=[d])
    data = serialize_project(p)
    # composition 필드를 제거하여 구버전 시뮬레이션
    for deleg in data["delegations"]:
        deleg.pop("composition", None)
        deleg.pop("guidance", None)
    p2 = deserialize_project(data)
    assert p2.delegations[0].composition is CompositionMode.EXPLICIT
    assert p2.delegations[0].guidance == ""
