"""FsmScene이 _target_fsm(project.graph) 모델을 동기화하는지 검증.

WP-AF로 에이전트 내부 FSM(AgentFsmScene)이 퇴역해, _target_fsm이 배선되는
씬은 프로젝트 캔버스 하나뿐이다 — 동기화 메커니즘 자체는 그대로이므로
같은 시나리오를 project.graph 기준으로 검증한다.
"""
from PySide6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.project import PluginProject
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_scene(skill_lookup=None):
    vm = ProjectViewModel()
    project = PluginProject(name="p")
    scene = FsmScene(vm, skill_lookup=skill_lookup)
    scene.set_project(project)
    return vm, project.graph, scene


def test_create_state_syncs_to_target_fsm(qapp):
    vm, fsm, scene = _make_scene()
    scene._create_state(QPointF(50, 60))

    created = [s for s in fsm.states if s.name == "State_1"]
    assert len(created) == 1, "캔버스에서 만든 상태가 project.graph.states에 있어야 한다"

    vm.command_stack.undo()
    assert not any(s.name == "State_1" for s in fsm.states)


def test_delete_state_syncs_to_target_fsm(qapp):
    vm, fsm, scene = _make_scene()
    state = SimpleState(name="victim")
    fsm.states.append(state)
    svm = StateViewModel(model=state, x=0, y=0)
    vm.state_vms.append(svm)

    scene._delete_state(svm)
    assert state not in fsm.states

    vm.command_stack.undo()
    assert state in fsm.states


def test_delete_transition_syncs_to_target_fsm(qapp):
    vm, fsm, scene = _make_scene()
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm.states.extend([a, b])
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    fsm.transitions.append(model)
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=100, y=0)
    vm.state_vms.extend([avm, bvm])
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    vm.transition_vms.append(tvm)

    scene._delete_transition(tvm)
    assert model not in fsm.transitions

    vm.command_stack.undo()
    assert model in fsm.transitions


def test_scene_without_project_does_not_touch_fsm(qapp):
    """set_project를 거치지 않은 씬은 _target_fsm=None — VM에만 반영된다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    assert scene._target_fsm is None
    scene._create_state(QPointF(0, 0))
    assert len(vm.state_vms) == 1  # VM에만 추가, 크래시 없음


# --- 봉합 3: 노드+엣지 동시 삭제 중복 커맨드 방지 ---


def _delete_key_event():
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
    )


def test_node_and_edge_simultaneous_delete_restores_single_transition(qapp):
    """노드+연결 엣지 동시 선택 삭제 → undo → 전이가 정확히 1개만 복원."""
    vm, fsm, scene = _make_scene()
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm.states.extend([a, b])
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=200, y=0)
    vm.state_vms.extend([avm, bvm])

    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    fsm.transitions.append(model)
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    vm.transition_vms.append(tvm)
    vm.notify()  # scene rebuild → 아이템 생성

    node_item = scene._node_items[avm]
    edge_item = scene._edge_items[tvm]
    node_item.setSelected(True)
    edge_item.setSelected(True)

    scene.keyPressEvent(_delete_key_event())

    assert tvm not in vm.transition_vms
    assert model not in fsm.transitions
    # 중복 DeleteTransitionCmd 없이 단일 복합 커맨드 1개만 쌓여야 한다
    assert len(vm.command_stack.history) == 1, (
        f"커맨드가 1개여야 하는데 {len(vm.command_stack.history)}개"
    )

    while vm.command_stack.can_undo:
        vm.command_stack.undo()
    assert sum(1 for t in vm.transition_vms if t is tvm) == 1, (
        "undo 후 전이 vm이 정확히 1개만 복원되어야 한다"
    )
    assert sum(1 for t in fsm.transitions if t is model) == 1


# --- 봉합 4: 다중 선택 드래그 스냅백 ---


def test_multi_drag_updates_all_vm_coords(qapp):
    """두 노드 동시 드래그 → 둘 다 vm 좌표가 신좌표, undo 시 둘 다 구좌표."""
    vm, fsm, scene = _make_scene()
    a = SimpleState(name="aa")
    b = SimpleState(name="bb")
    fsm.states.extend([a, b])
    avm = StateViewModel(model=a, x=0.0, y=0.0)
    bvm = StateViewModel(model=b, x=200.0, y=0.0)
    vm.state_vms.extend([avm, bvm])
    vm.notify()  # scene rebuild → 아이템 생성

    node_a = scene._node_items[avm]
    node_b = scene._node_items[bvm]
    node_a.setSelected(True)
    node_b.setSelected(True)

    # Qt 드래그 시뮬레이션: 두 아이템 모두 (50, 60)만큼 이동된 상태
    node_a.setPos(50.0, 60.0)
    node_b.setPos(250.0, 60.0)

    # release 핸들러 — node_a가 트리거
    scene.handle_node_moved(node_a, QPointF(0.0, 0.0), QPointF(50.0, 60.0))

    assert (avm.x, avm.y) == (50.0, 60.0), "트리거 노드 vm 좌표가 신좌표여야 한다"
    assert (bvm.x, bvm.y) == (250.0, 60.0), "동반 이동 노드 vm 좌표도 신좌표여야 한다"

    vm.command_stack.undo()
    assert (avm.x, avm.y) == (0.0, 0.0), "undo 후 트리거 노드가 구좌표여야 한다"
    assert (bvm.x, bvm.y) == (200.0, 0.0), "undo 후 동반 이동 노드도 구좌표여야 한다"


def test_add_transition_vm_identity_duplicate_guard(qapp):
    """add_transition_vm은 동일 인스턴스 중복 추가를 거부한다."""
    vm = ProjectViewModel()
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    avm = StateViewModel(model=a)
    bvm = StateViewModel(model=b)
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)

    vm.add_transition_vm(tvm)
    vm.add_transition_vm(tvm)
    assert sum(1 for t in vm.transition_vms if t is tvm) == 1
