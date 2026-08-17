"""FsmScene 내부 메커니즘 직접 테스트 — _rebuild diff, 전이 드래그, 입력 포트 정렬.

기존 test_scene_fsm_sync.py가 커버하지 않는 잔여 공백을 채운다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.scene import AgentFsmScene, FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_agent_fsm() -> StateMachine:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )


# ---------------------------------------------------------------------------
# _rebuild diff 동기화
# ---------------------------------------------------------------------------

def test_rebuild_adds_node_items_for_new_vms(qapp):
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    b = StateViewModel(model=SimpleState(name="b"), x=100, y=0)
    vm.state_vms.extend([a, b])

    scene._rebuild()
    assert len(scene._node_items) == 2
    assert a in scene._node_items and b in scene._node_items


def test_rebuild_removes_node_items_for_dropped_vms(qapp):
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    b = StateViewModel(model=SimpleState(name="b"), x=100, y=0)
    vm.state_vms.extend([a, b])
    scene._rebuild()
    assert len(scene._node_items) == 2

    vm.state_vms.remove(b)
    scene._rebuild()
    assert len(scene._node_items) == 1
    assert a in scene._node_items
    assert b not in scene._node_items


def test_rebuild_is_idempotent_reuses_items(qapp):
    """동일 VM 집합으로 두 번 _rebuild → 아이템 객체가 재사용된다(재생성 아님)."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    vm.state_vms.append(a)
    scene._rebuild()
    item_first = scene._node_items[a]
    scene._rebuild()
    assert scene._node_items[a] is item_first, "diff 동기화는 아이템을 재생성하지 않는다"


def test_rebuild_updates_position_from_model(qapp):
    """VM 좌표 변경 후 _rebuild → 노드 아이템 위치가 갱신된다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    vm.state_vms.append(a)
    scene._rebuild()
    a.x, a.y = 55.0, 66.0
    scene._rebuild()
    item = scene._node_items[a]
    assert (item.pos().x(), item.pos().y()) == (55.0, 66.0)


def test_rebuild_adds_and_removes_edge_items(qapp):
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    b = StateViewModel(model=SimpleState(name="b"), x=200, y=0)
    vm.state_vms.extend([a, b])
    model = Transition(source=a.model, target=b.model, trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=a, target_vm=b)
    vm.transition_vms.append(tvm)

    scene._rebuild()
    assert tvm in scene._edge_items

    vm.transition_vms.remove(tvm)
    scene._rebuild()
    assert tvm not in scene._edge_items


# ---------------------------------------------------------------------------
# WP-IP — 입력 포트 수렴 (노드당 1개)
# ---------------------------------------------------------------------------

def test_edges_to_same_target_converge(qapp):
    """같은 타깃으로 들어오는 엣지 2개는 같은 점(단일 입력 포트)에 수렴한다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    t = StateViewModel(model=SimpleState(name="t"), x=400, y=0)
    z = StateViewModel(model=SimpleState(name="zsrc"), x=0, y=0)
    a = StateViewModel(model=SimpleState(name="asrc"), x=0, y=100)
    vm.state_vms.extend([t, z, a])
    tz = TransitionViewModel(
        model=Transition(source=z.model, target=t.model, trigger=CompletionEvent(name="done")),
        source_vm=z, target_vm=t,
    )
    ta = TransitionViewModel(
        model=Transition(source=a.model, target=t.model, trigger=CompletionEvent(name="done")),
        source_vm=a, target_vm=t,
    )
    vm.transition_vms.extend([tz, ta])

    scene._rebuild()

    edge_z = scene._edge_items[tz]
    edge_a = scene._edge_items[ta]
    # 서로 다른 두 엣지의 **실제 렌더 경로 끝점**이 한 점에 수렴해야 한다
    # (리뷰 지적: 같은 함수를 두 번 부르는 동어반복 단언은 어떤 회귀도 못 잡음)
    end_z = edge_z.path().currentPosition()
    end_a = edge_a.path().currentPosition()
    assert end_z == end_a


# ---------------------------------------------------------------------------
# begin/end_transition_drag — 포트→포트 전이 생성
# ---------------------------------------------------------------------------

def test_transition_drag_creates_transition(qapp):
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    view = FsmCanvasView(scene)  # self.views() 비어있지 않게

    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm.states.extend([a, b])
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=300, y=0)
    vm.state_vms.extend([avm, bvm])
    vm.notify()

    node_b = scene._node_items[bvm]
    drop_pt = node_b.input_port_scene_pos()

    scene.begin_transition_drag(scene._node_items[avm], "done")
    assert scene._connecting is True
    scene.update_transition_drag(drop_pt)
    scene.end_transition_drag(drop_pt)

    assert scene._connecting is False
    # a→b 전이가 생성되어 모델/VM에 반영
    created = [t for t in vm.transition_vms if t.source_vm is avm and t.target_vm is bvm]
    assert len(created) == 1, "포트→포트 드래그로 전이가 1개 생성되어야 한다"
    assert any(t.source is a and t.target is b for t in fsm.transitions)

    view.deleteLater()


def test_transition_drag_to_self_is_rejected(qapp):
    """같은 노드의 입력 포트에 드롭하면 전이를 만들지 않는다."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    view = FsmCanvasView(scene)

    a = SimpleState(name="a")
    fsm.states.append(a)
    avm = StateViewModel(model=a, x=0, y=0)
    vm.state_vms.append(avm)
    vm.notify()

    node_a = scene._node_items[avm]
    drop_pt = node_a.input_port_scene_pos()

    scene.begin_transition_drag(node_a, "done")
    scene.end_transition_drag(drop_pt)

    assert not any(t.source_vm is avm and t.target_vm is avm for t in vm.transition_vms)
    view.deleteLater()


def test_transition_drag_empty_drop_cancels(qapp):
    """빈 공간에 드롭하면 전이 없이 드래그만 종료된다."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    view = FsmCanvasView(scene)

    a = SimpleState(name="a")
    fsm.states.append(a)
    avm = StateViewModel(model=a, x=0, y=0)
    vm.state_vms.append(avm)
    vm.notify()

    before = len(vm.transition_vms)
    scene.begin_transition_drag(scene._node_items[avm], "done")
    scene.end_transition_drag(QPointF(-999, -999))  # 빈 공간

    assert scene._connecting is False
    assert len(vm.transition_vms) == before
    view.deleteLater()
