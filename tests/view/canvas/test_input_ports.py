"""입력 포트 — 노드당 항상 1개 (WP-IP).

입력 포트 선언(entry_paths)과 전이의 도착 포트 지정(target_port)은 필드째
사라졌다(RF-1b): (출처, 트리거)가 경로를 특정하므로 도착 노드가 입력 포트를
이름으로 가를 이유가 없다. 들어오는 전이는 전부 한 점으로 수렴한다.
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


def _make_skill(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name=name, description="")


def test_input_port_is_single(qapp):
    """입력 포트는 노드당 1개 — 위치 조회는 항상 같은 점이다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual")
    placement = SimpleState(name="dual", skill_ref=skill)
    svm = StateViewModel(model=placement, x=0, y=0)
    vm.state_vms.append(svm)
    scene._rebuild()

    node = scene._node_items[svm]
    assert node.input_port_scene_pos() == node.input_port_scene_pos()


def test_all_incoming_edges_converge_on_single_port(qapp):
    """출처가 달라도 도착점은 같은 입력 포트다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = _make_skill("a")
    b = _make_skill("b")
    tgt = _make_skill("tgt")
    sa = StateViewModel(model=SimpleState(name="a", skill_ref=a), x=0, y=0)
    sb = StateViewModel(model=SimpleState(name="b", skill_ref=b), x=0, y=200)
    st = StateViewModel(model=SimpleState(name="tgt", skill_ref=tgt), x=400, y=100)
    vm.state_vms += [sa, sb, st]
    t1 = Transition(
        source=sa.model, target=st.model, trigger=CompletionEvent(name="done"),
    )
    t2 = Transition(
        source=sb.model, target=st.model, trigger=CompletionEvent(name="done"),
    )
    vm.transition_vms += [
        TransitionViewModel(model=t1, source_vm=sa, target_vm=st),
        TransitionViewModel(model=t2, source_vm=sb, target_vm=st),
    ]
    scene._rebuild()

    node = scene._node_items[st]
    e1 = scene._edge_items[vm.transition_vms[0]]
    e2 = scene._edge_items[vm.transition_vms[1]]
    assert e1.path().pointAtPercent(1.0) == e2.path().pointAtPercent(1.0)
    assert e1.path().pointAtPercent(1.0) == node.input_port_scene_pos()


def test_new_transition_has_no_target_port_field(qapp):
    """드래그 연결로 만든 전이에 도착 포트 지정 자체가 없다 (WP-IP/RF-1b)."""
    from PySide6.QtCore import QPointF

    from daedalus.view.canvas.canvas_view import FsmCanvasView

    vm = ProjectViewModel()
    scene = FsmScene(vm)
    view = FsmCanvasView(scene)  # self.views()가 비어 있으면 드롭 판정 불가
    src = _make_skill("src")
    src.transfer_on = [EventDef("done")]
    tgt = _make_skill("tgt2")
    s_src = StateViewModel(model=SimpleState(name="src", skill_ref=src), x=0, y=0)
    s_tgt = StateViewModel(model=SimpleState(name="tgt2", skill_ref=tgt), x=400, y=0)
    vm.state_vms += [s_src, s_tgt]
    scene._rebuild()

    src_item = scene._node_items[s_src]
    tgt_item = scene._node_items[s_tgt]
    scene.begin_transition_drag(src_item, "done")
    drop = tgt_item.input_port_scene_pos()
    scene.end_transition_drag(QPointF(drop.x() + 1, drop.y()))

    assert len(vm.transition_vms) == 1
    assert not hasattr(vm.transition_vms[0].model, "target_port")
