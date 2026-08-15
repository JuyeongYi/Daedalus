"""입력 포트 — WP-IP 이후 항상 기본 1개.

entry_paths 선언은 퇴역했다: (출처, 트리거)가 경로를 특정하므로 도착 노드가
입력 포트를 이름으로 가를 이유가 없다. legacy 파일에 선언이 남아 있어도
렌더는 기본 포트 하나이고, 전이는 전부 그 한 점으로 수렴한다.
"""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_skill(name: str, entry_paths: list[EventDef] | None = None) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(
        fsm=fsm, name=name, description="",
        entry_paths=entry_paths or [],
    )


def test_input_port_is_always_single_even_with_legacy_declarations(qapp):
    """legacy entry_paths가 남아 있어도 입력 포트는 기본 1개다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual", [EventDef("main"), EventDef("retry")])
    placement = SimpleState(name="dual", skill_ref=skill)
    svm = StateViewModel(model=placement, x=0, y=0)
    vm.state_vms.append(svm)
    scene._rebuild()

    node = scene._node_items[svm]
    assert node._input_event_defs() == []
    # 이름 조회는 전부 기본 포트 한 점으로 수렴한다
    assert node.input_port_scene_pos("main") == node.input_port_scene_pos("retry")
    assert node.input_port_scene_pos("") == node.input_port_scene_pos("main")


def test_all_incoming_edges_converge_on_default_port(qapp):
    """legacy target_port가 서로 달라도 도착점은 같은 기본 포트다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = _make_skill("a")
    b = _make_skill("b")
    tgt = _make_skill("tgt", [EventDef("p1"), EventDef("p2")])
    sa = StateViewModel(model=SimpleState(name="a", skill_ref=a), x=0, y=0)
    sb = StateViewModel(model=SimpleState(name="b", skill_ref=b), x=0, y=200)
    st = StateViewModel(model=SimpleState(name="tgt", skill_ref=tgt), x=400, y=100)
    vm.state_vms += [sa, sb, st]
    t1 = Transition(
        source=sa.model, target=st.model,
        trigger=CompletionEvent(name="done"), target_port="p1",
    )
    t2 = Transition(
        source=sb.model, target=st.model,
        trigger=CompletionEvent(name="done"), target_port="p2",
    )
    vm.transition_vms += [
        TransitionViewModel(model=t1, source_vm=sa, target_vm=st),
        TransitionViewModel(model=t2, source_vm=sb, target_vm=st),
    ]
    scene._rebuild()

    node = scene._node_items[st]
    assert node.input_port_scene_pos("p1") == node.input_port_scene_pos("p2")


def test_new_transition_records_no_target_port(qapp):
    """드래그 연결이 target_port를 기록하지 않는다 (WP-IP)."""
    from PySide6.QtCore import QPointF

    from daedalus.view.canvas.canvas_view import FsmCanvasView

    vm = ProjectViewModel()
    scene = FsmScene(vm)
    view = FsmCanvasView(scene)  # self.views()가 비어 있으면 드롭 판정 불가
    src = _make_skill("src")
    src.transfer_on = [EventDef("done")]
    tgt = _make_skill("tgt2", [EventDef("declared")])
    s_src = StateViewModel(model=SimpleState(name="src", skill_ref=src), x=0, y=0)
    s_tgt = StateViewModel(model=SimpleState(name="tgt2", skill_ref=tgt), x=400, y=0)
    vm.state_vms += [s_src, s_tgt]
    scene._rebuild()

    src_item = scene._node_items[s_src]
    tgt_item = scene._node_items[s_tgt]
    scene.begin_transition_drag(src_item, "done")
    drop = tgt_item.input_port_scene_pos("")
    scene.end_transition_drag(QPointF(drop.x() + 1, drop.y()))

    assert len(vm.transition_vms) == 1
    assert vm.transition_vms[0].model.target_port == ""
