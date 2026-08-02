"""위임 노드 씬 테스트: drop, 중복 배치 허용, fsm 동기화."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    DelegationDef,
    DynamicWorkflowDef,
    TeamSpawnDef,
)
from daedalus.view.canvas.scene import AgentFsmScene, FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _make_agent_fsm() -> StateMachine:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm",
        states=[entry, done],
        initial_state=entry,
        final_states=[done],
    )


def _make_deleg(kind: str = "team_spawn") -> DelegationDef:
    factories = {
        "team_spawn": lambda: TeamSpawnDef(name="my-team", description=""),
        "dynamic_workflow": lambda: DynamicWorkflowDef(name="my-wf", description=""),
        "agora_dispatch": lambda: AgoraDispatchDef(name="my-agora", description=""),
    }
    return factories[kind]()


# ─────────────────────── drop → SimpleState.skill_ref ───────────────────────

def test_drop_delegation_creates_node(qapp):
    """DelegationDef drop → SimpleState가 생성되고 skill_ref가 정의를 가리킨다."""
    vm = ProjectViewModel()
    deleg = _make_deleg("team_spawn")
    scene = FsmScene(vm, skill_lookup=lambda n: deleg if n == deleg.name else None)
    scene.drop_skill(deleg.name, QPointF(100, 100))

    assert len(vm.state_vms) == 1
    node_model = vm.state_vms[0].model
    assert isinstance(node_model, SimpleState)
    assert node_model.skill_ref is deleg


def test_drop_delegation_syncs_to_agent_fsm(qapp):
    """AgentFsmScene에서 drop 시 agent.fsm.states에도 추가된다."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    deleg = _make_deleg("dynamic_workflow")
    scene = AgentFsmScene(
        vm, agent_fsm=fsm,
        skill_lookup=lambda n: deleg if n == deleg.name else None,
    )
    scene.drop_skill(deleg.name, QPointF(50, 50))

    placed = [s for s in fsm.states if getattr(s, "skill_ref", None) is deleg]
    assert len(placed) == 1


def test_drop_delegation_fsm_sync_undo(qapp):
    """drop 후 undo 시 fsm.states에서 제거된다."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    deleg = _make_deleg("agora_dispatch")
    scene = AgentFsmScene(
        vm, agent_fsm=fsm,
        skill_lookup=lambda n: deleg if n == deleg.name else None,
    )
    scene.drop_skill(deleg.name, QPointF(50, 50))
    assert any(getattr(s, "skill_ref", None) is deleg for s in fsm.states)

    vm.command_stack.undo()
    assert not any(getattr(s, "skill_ref", None) is deleg for s in fsm.states)


# ─────────────────────── 중복 배치 허용 ───────────────────────

def test_delegation_allows_duplicate_drop(qapp):
    """같은 DelegationDef를 두 번 drop해도 두 노드 모두 생성된다 (중복 배치 허용)."""
    vm = ProjectViewModel()
    deleg = _make_deleg("team_spawn")
    scene = FsmScene(vm, skill_lookup=lambda n: deleg if n == deleg.name else None)

    scene.drop_skill(deleg.name, QPointF(100, 100))
    scene.drop_skill(deleg.name, QPointF(200, 100))

    placed = [svm for svm in vm.state_vms if getattr(svm.model, "skill_ref", None) is deleg]
    assert len(placed) == 2, "DelegationDef는 같은 정의를 2회 배치 가능해야 한다"


def test_skill_duplicate_guard_still_works(qapp):
    """일반 ProceduralSkill은 여전히 중복 배치 불가."""
    from daedalus.model.fsm.section import EventDef
    from daedalus.model.plugin.skill import ProceduralSkill

    s = SimpleState(name="start")
    skill = ProceduralSkill(
        fsm=StateMachine(name="f", states=[s], initial_state=s),
        name="proc", description="",
        transfer_on=[EventDef(name="done")],
    )
    vm = ProjectViewModel()
    scene = FsmScene(vm, skill_lookup=lambda n: skill if n == "proc" else None)

    scene.drop_skill("proc", QPointF(100, 100))
    scene.drop_skill("proc", QPointF(200, 100))

    placed = [svm for svm in vm.state_vms if getattr(svm.model, "skill_ref", None) is skill]
    assert len(placed) == 1, "ProceduralSkill 중복 가드는 여전히 동작해야 한다"
