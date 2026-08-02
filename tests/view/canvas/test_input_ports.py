"""WP-IC Part B — 입력 포트 렌더 + 수렴 + 스냅 테스트."""
from __future__ import annotations

from PySide6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.view.canvas.canvas_view import FsmCanvasView
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


def test_input_port_count_matches_entry_paths(qapp):
    """포트 2개 스킬 placement의 입력 포트 수 = max(1, len(entry_paths))."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual", [EventDef("main"), EventDef("retry", color="#cc8844")])
    placement = SimpleState(name="dual", skill_ref=skill)
    svm = StateViewModel(model=placement, x=0, y=0)
    vm.state_vms.append(svm)
    scene._rebuild()

    node = scene._node_items[svm]
    assert len(node._input_event_defs()) == 2
    # 두 포트의 y좌표가 다르다 (기본 렌더 분리)
    y_main = node.input_port_scene_pos("main").y()
    y_retry = node.input_port_scene_pos("retry").y()
    assert y_main != y_retry


def test_input_port_labels_use_entry_path_names(qapp):
    """entry_paths 이름이 input_port_index로 조회 가능해야 한다(라벨 대칭 렌더의 전제)."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual2", [EventDef("main"), EventDef("retry")])
    placement = SimpleState(name="dual2", skill_ref=skill)
    svm = StateViewModel(model=placement, x=0, y=0)
    vm.state_vms.append(svm)
    scene._rebuild()

    node = scene._node_items[svm]
    assert node.input_port_index("main") == 0
    assert node.input_port_index("retry") == 1
    # 존재하지 않는 이름 → 기본(첫) 포트
    assert node.input_port_index("nope") == 0


def test_default_port_backward_compat_no_entry_paths(qapp):
    """entry_paths 빈 리스트 = 기본 포트 1개(암묵, 이름 없음) — 기존 렌더와 동일."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("solo")
    placement = SimpleState(name="solo", skill_ref=skill)
    svm = StateViewModel(model=placement, x=0, y=0)
    vm.state_vms.append(svm)
    scene._rebuild()

    node = scene._node_items[svm]
    assert len(node._input_event_defs()) == 0
    assert node.input_port_index("") == 0
    # 포트 1개 — local_pos가 어디든 스냅 결과는 빈 값(하위 호환)
    assert node.nearest_input_port_name(QPointF(0.0, 999.0)) == ""


def test_edges_same_target_port_converge_with_named_ports(qapp):
    """같은 target_port를 향하는 두 전이는 같은 점에 수렴한다(엔트리 경로가 있어도)."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual3", [EventDef("main"), EventDef("retry")])
    placement = SimpleState(name="dual3", skill_ref=skill)
    src_a = SimpleState(name="a")
    src_b = SimpleState(name="b")
    tvm = StateViewModel(model=placement, x=400, y=0)
    avm = StateViewModel(model=src_a, x=0, y=0)
    bvm = StateViewModel(model=src_b, x=0, y=200)
    vm.state_vms.extend([tvm, avm, bvm])

    t1 = TransitionViewModel(
        model=Transition(
            source=src_a, target=placement,
            trigger=CompletionEvent(name="done"), target_port="retry",
        ),
        source_vm=avm, target_vm=tvm,
    )
    t2 = TransitionViewModel(
        model=Transition(
            source=src_b, target=placement,
            trigger=CompletionEvent(name="done"), target_port="retry",
        ),
        source_vm=bvm, target_vm=tvm,
    )
    vm.transition_vms.extend([t1, t2])
    scene._rebuild()

    node = scene._node_items[tvm]
    pos1 = node.input_port_scene_pos(t1.model.target_port)
    pos2 = node.input_port_scene_pos(t2.model.target_port)
    pos_main = node.input_port_scene_pos("main")
    assert pos1 == pos2
    assert pos1 != pos_main


def test_transition_drag_snaps_to_nearest_port(qapp):
    """드롭 지점에서 가장 가까운 입력 포트에 스냅해 target_port를 기록한다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("dual4", [EventDef("main"), EventDef("retry")])
    placement = SimpleState(name="dual4", skill_ref=skill)
    src = SimpleState(name="src")
    tvm = StateViewModel(model=placement, x=300, y=0)
    svm = StateViewModel(model=src, x=0, y=0)
    vm.state_vms.extend([tvm, svm])
    scene._rebuild()
    view = FsmCanvasView(scene)

    node_t = scene._node_items[tvm]
    node_s = scene._node_items[svm]
    # "retry" 포트(index 1) 위치에 정확히 드롭
    drop_pt = node_t.input_port_scene_pos("retry")

    scene.begin_transition_drag(node_s, "done")
    scene.end_transition_drag(drop_pt)

    created = [t for t in vm.transition_vms if t.source_vm is svm and t.target_vm is tvm]
    assert len(created) == 1
    assert created[0].model.target_port == "retry"

    view.deleteLater()


def test_transition_drag_default_port_keeps_empty_target_port(qapp):
    """포트 1개(entry_paths 없음)인 노드에 드롭하면 target_port는 빈 값으로 유지된다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    skill = _make_skill("solo2")
    placement = SimpleState(name="solo2", skill_ref=skill)
    src = SimpleState(name="src2")
    tvm = StateViewModel(model=placement, x=300, y=0)
    svm = StateViewModel(model=src, x=0, y=0)
    vm.state_vms.extend([tvm, svm])
    scene._rebuild()
    view = FsmCanvasView(scene)

    node_t = scene._node_items[tvm]
    node_s = scene._node_items[svm]
    drop_pt = node_t.input_port_scene_pos("")

    scene.begin_transition_drag(node_s, "done")
    scene.end_transition_drag(drop_pt)

    created = [t for t in vm.transition_vms if t.source_vm is svm and t.target_vm is tvm]
    assert len(created) == 1
    assert created[0].model.target_port == ""

    view.deleteLater()
