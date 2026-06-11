"""EdgeItem / RefEdgeItem 렌더·갱신 경로 스모크 (offscreen QImage paint).

paint()가 예외 없이 그려지는지, update_path()가 경로를 구성하는지 확인한다.
실제 픽셀 값은 검증하지 않고, 렌더 파이프라인이 크래시 없이 도는지에 집중.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ReferenceSkill, TransferSkill
from daedalus.model.fsm.machine import StateMachine
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.ref_edge_item import ReferenceEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.ref_node_item import ReferenceNodeItem
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
    TransitionViewModel,
)


def _paint_item(item) -> None:
    """아이템을 offscreen QImage에 그려 paint() 경로를 강제 실행한다."""
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    try:
        item.paint(painter, None, None)
    finally:
        painter.end()


def _make_nodes():
    a = StateNodeItem(StateViewModel(model=SimpleState(name="a"), x=0, y=0))
    b = StateNodeItem(StateViewModel(model=SimpleState(name="b"), x=120, y=40))
    return a, b


def test_transition_edge_paint_smoke(qapp):
    a, b = _make_nodes()
    model = Transition(source=a.state_vm.model, target=b.state_vm.model,
                       trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=a.state_vm, target_vm=b.state_vm)
    edge = TransitionEdgeItem(tvm, a, b)
    edge.update_path()
    assert not edge.path().isEmpty()
    _paint_item(edge)  # 크래시 없이 렌더


def test_transition_edge_with_transfer_skill_label_paint(qapp):
    """Transfer Skill 라벨 분기까지 포함해 paint."""
    a, b = _make_nodes()
    s = SimpleState(name="start")
    ts = TransferSkill(
        fsm=StateMachine(name="f", states=[s], initial_state=s),
        name="logit", description="",
    )
    model = Transition(source=a.state_vm.model, target=b.state_vm.model,
                       trigger=CompletionEvent(name="done"), skill_ref=ts)
    tvm = TransitionViewModel(model=model, source_vm=a.state_vm, target_vm=b.state_vm)
    edge = TransitionEdgeItem(tvm, a, b)
    edge.update_path()
    _paint_item(edge)


def test_transition_edge_selected_paint(qapp):
    a, b = _make_nodes()
    model = Transition(source=a.state_vm.model, target=b.state_vm.model,
                       trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=a.state_vm, target_vm=b.state_vm)
    edge = TransitionEdgeItem(tvm, a, b)
    edge.setSelected(True)
    edge.update_path()
    _paint_item(edge)


def test_transition_edge_update_path_recomputes_on_move(qapp):
    """타깃 노드 이동 후 update_path → 경로 종점이 갱신된다."""
    a, b = _make_nodes()
    model = Transition(source=a.state_vm.model, target=b.state_vm.model,
                       trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=a.state_vm, target_vm=b.state_vm)
    edge = TransitionEdgeItem(tvm, a, b)
    edge.update_path()
    end_before = edge.path().pointAtPercent(1.0)
    b.setPos(400, 300)
    edge.update_path()
    end_after = edge.path().pointAtPercent(1.0)
    assert end_before != end_after, "노드 이동 후 경로 종점이 갱신되어야 한다"


def test_reference_edge_paint_smoke(qapp):
    src = StateNodeItem(StateViewModel(model=SimpleState(name="s"), x=0, y=0))
    ref_skill = ReferenceSkill(name="DocRef", description="")
    ref_node = ReferenceNodeItem(ReferenceViewModel(model=ref_skill, x=0, y=200))
    lvm = ReferenceLinkViewModel(state_vm=src.state_vm, reference_vm=ref_node.ref_vm)
    edge = ReferenceEdgeItem(lvm, src, ref_node)
    edge.update_path()
    assert not edge.path().isEmpty()
    _paint_item(edge)


def test_reference_edge_selected_paint(qapp):
    src = StateNodeItem(StateViewModel(model=SimpleState(name="s"), x=0, y=0))
    ref_skill = ReferenceSkill(name="DocRef", description="")
    ref_node = ReferenceNodeItem(ReferenceViewModel(model=ref_skill, x=0, y=200))
    lvm = ReferenceLinkViewModel(state_vm=src.state_vm, reference_vm=ref_node.ref_vm)
    edge = ReferenceEdgeItem(lvm, src, ref_node)
    edge.setSelected(True)
    edge.update_path()
    _paint_item(edge)
