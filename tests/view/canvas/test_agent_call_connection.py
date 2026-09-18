"""캔버스에서 에이전트 → 에이전트 연결 (2026-09-12).

CC가 서브에이전트 중첩 스폰을 허용하면서 에이전트도 호출 포트(call_agents)를
갖는다. 여기서 고정하는 것은 **GUI 드래그 경로**다 — 모델·MCP가 되는데 캔버스에서
안 되면 사용자에게는 "안 되는 기능"이다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel


def _agent(name: str, calls: list[str] | None = None) -> AgentDefinition:
    entry = EntryPoint(name="s")
    return AgentDefinition(
        fsm=StateMachine(name=f"{name}_fsm", states=[entry], initial_state=entry),
        name=name, description="",
        transfer_on=[EventDef("done")],
        call_agents=[EventDef(c) for c in (calls or [])],
    )


def _scene_with(vm: ProjectViewModel, project=None) -> FsmScene:
    scene = FsmScene(vm)
    if project is not None:
        scene.set_project(project)  # 백킹 머신 배선 — 없으면 모델에 동기화되지 않는다
    # 뷰는 **씬에 매어 둔다** — 지역 변수로 버리면 GC가 가져가 `scene.views()`가
    # 비고, 드롭 히트 판정이 조용히 실패한다(다른 테스트의 할당량에 따라
    # 결과가 달라지는 유령 실패가 된다 — 2026-09-19 실측).
    scene._test_view = FsmCanvasView(scene)
    scene._rebuild()
    return scene


def test_agent_node_renders_call_port(qapp):
    """에이전트 노드에도 호출 포트가 그려지고 호출 포트로 히트 판정된다."""
    vm = ProjectViewModel()
    lead = _agent("lead", calls=["probe"])
    svm = StateViewModel(model=SimpleState(name="lead", skill_ref=lead), x=0, y=0)
    vm.state_vms.append(svm)
    scene = _scene_with(vm)

    node = scene._node_items[svm]
    port = node.output_port_scene_pos("probe", True)
    assert node._get_output_port_event(node.mapFromScene(port)) == ("probe", True)


def test_drag_from_agent_call_port_to_agent_creates_transition(qapp):
    """에이전트의 호출 포트 → 다른 에이전트 노드로 드래그하면 전이가 생긴다."""
    lead, scout = _agent("lead", calls=["probe"]), _agent("scout")
    project = PluginProject(name="p", agents=[lead, scout])
    n_lead = SimpleState(name="lead", skill_ref=lead)
    n_scout = SimpleState(name="scout", skill_ref=scout)
    project.graph.states += [n_lead, n_scout]
    vm = ProjectViewModel()
    s_lead = StateViewModel(model=n_lead, x=0, y=0)
    s_scout = StateViewModel(model=n_scout, x=400, y=0)
    vm.state_vms += [s_lead, s_scout]
    scene = _scene_with(vm, project)

    src_item, tgt_item = scene._node_items[s_lead], scene._node_items[s_scout]
    scene.begin_transition_drag(src_item, "probe", True)
    drop = tgt_item.input_port_scene_pos()
    scene.end_transition_drag(QPointF(drop.x() + 1, drop.y()))

    assert len(vm.transition_vms) == 1
    tvm = vm.transition_vms[0]
    assert tvm.source_vm is s_lead and tvm.target_vm is s_scout
    assert tvm.model.trigger is not None and tvm.model.trigger.name == "probe"
    # 그래프(백킹 머신)에도 들어가야 저장·컴파일·검증이 본다
    assert tvm.model in project.graph.transitions


def test_agent_output_port_cannot_target_agent(qapp):
    """출력 포트(transfer_on)로는 에이전트에 닿을 수 없다 — 호출 포트만 허용."""
    vm = ProjectViewModel()
    lead, scout = _agent("lead", calls=["probe"]), _agent("scout")
    s_lead = StateViewModel(model=SimpleState(name="lead", skill_ref=lead), x=0, y=0)
    s_scout = StateViewModel(model=SimpleState(name="scout", skill_ref=scout), x=400, y=0)
    vm.state_vms += [s_lead, s_scout]
    scene = _scene_with(vm)

    scene.begin_transition_drag(scene._node_items[s_lead], "done", False)
    drop = scene._node_items[s_scout].input_port_scene_pos()
    scene.end_transition_drag(QPointF(drop.x() + 1, drop.y()))
    assert vm.transition_vms == []


def test_skill_call_port_still_works(qapp):
    """기존 경로(스킬 → 에이전트)가 그대로여야 한다."""
    entry = EntryPoint(name="s")
    skill = ProceduralSkill(
        fsm=StateMachine(name="f", states=[entry], initial_state=entry),
        name="init", description="",
        transfer_on=[EventDef("done")], call_agents=[EventDef("delegate")],
    )
    vm = ProjectViewModel()
    agent = _agent("worker")
    s_skill = StateViewModel(model=SimpleState(name="init", skill_ref=skill), x=0, y=0)
    s_agent = StateViewModel(model=SimpleState(name="worker", skill_ref=agent), x=400, y=0)
    vm.state_vms += [s_skill, s_agent]
    scene = _scene_with(vm)

    scene.begin_transition_drag(scene._node_items[s_skill], "delegate", True)
    drop = scene._node_items[s_agent].input_port_scene_pos()
    scene.end_transition_drag(QPointF(drop.x() + 1, drop.y()))
    assert len(vm.transition_vms) == 1
