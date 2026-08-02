# tests/view/canvas/test_drag_move.py
"""WP-DM — 캔버스 드래그 이동 로직 통합.

이동 가능한 아이템 3종(StateNodeItem/ReferenceNodeItem/WaypointHandleItem)이
공통 믹스인(DraggableItemMixin) + 씬 단일 진입점(handle_items_moved)을 통해
일관되게 동작하는지 검증한다.

실측으로 확인한 정확한 고장 메커니즘(master): 세 아이템 모두 mouseMoveEvent에서
super()를 호출하므로 드래그 "도중"에는 Qt가 선택된 모든 이동 가능 아이템을
이미 정상적으로 함께 옮긴다 — 이 단계는 버그가 아니다. 진짜 고장은 release
"이후"다: release 이벤트가 잡은(grabbed) 아이템 하나에만 배달되므로, 구
handle_node_moved/handle_ref_node_moved는 그 하나만 커맨드로 만들어 vm.x/y를
갱신한다. 그 직후 `_project_vm.execute()` → notify → 씬 `_rebuild()`가
`item.setPos(vm.x, vm.y)`로 화면 좌표를 vm 기준으로 재계산하는데, 커맨드를
못 받은 함께-드래그된(passenger) 아이템은 vm.x/y가 갱신된 적이 없어 원래
좌표로 스냅백된다 — "무엇을 잡았느냐에 따라 튕기는 대상이 달라지는" 증상.

따라서 검증은 반드시 release 완료(+ qapp.processEvents()) 후, **vm 좌표**
(StateViewModel.x/y, ReferenceViewModel.x/y, project.reference_placements,
TransitionViewModel.waypoints)로 해야 한다 — 화면 좌표(item.pos())나 드래그
"도중" 상태를 검사하면 이 스냅백 버그가 있어도 통과해버린다(Qt가 이미 다
옮겨놨으므로). 합성 setPos()/핸들러 직접 호출로도 이 release-이후 경로를
재현할 수 없으므로, 반드시 실제 QMouseEvent를 뷰포트에 보내는 방식으로
press→move→release 전체를 거친다(tests/view/canvas/test_canvas_interaction.py,
test_edge_waypoints.py의 _send_mouse 패턴 참조 — 합성 이벤트가 실제 경로를
우회해 통과한 전례가 있다).

교차검증: 이 테스트들을 WP-DM 이전(master, eeea4b0) 캔버스 코드에 그대로
돌려 정확히 이 스냅백 패턴으로 실패하는 것을 확인했다 — 예를 들어 상태
노드를 잡으면 함께 선택된 레퍼런스 노드(r1)만 원좌표에 고정되고, 레퍼런스
노드를 잡으면 상태 노드(a)와 다른 레퍼런스 노드(r2)가 원좌표에 고정된다.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ReferenceSkill
from daedalus.model.project import PluginProject
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.commands.base import MacroCommand
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import (
    ReferenceViewModel,
    StateViewModel,
    TransitionViewModel,
)

_TOL = 1.0  # 픽셀 라운딩 허용 오차


def _send_mouse(view, type_, scene_pos, *, button, buttons):
    vp_pos = view.mapFromScene(scene_pos)
    ev = QMouseEvent(
        type_, QPointF(vp_pos), QPointF(view.viewport().mapToGlobal(vp_pos)),
        button, buttons, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), ev)


def _drag(view, start_scene_pos, end_scene_pos):
    """press → move → release, 실제 QMouseEvent 경로로."""
    _send_mouse(view, QEvent.Type.MouseButtonPress, start_scene_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton)
    _send_mouse(view, QEvent.Type.MouseMove, end_scene_pos,
                button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.LeftButton)
    _send_mouse(view, QEvent.Type.MouseButtonRelease, end_scene_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)


def _make_mixed_scene(qapp):
    """상태 노드 2 + 참조 노드 2 + 웨이포인트 1을 가진 씬 — 전부 선택된 채로 반환.

    반환: (view, scene, vm, project, a, b, r1, r2, tvm, edge, handle)
    """
    project = PluginProject(name="p")
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene.set_project(project)

    a = StateViewModel(model=SimpleState(name="a"), x=0.0, y=0.0)
    b = StateViewModel(model=SimpleState(name="b"), x=400.0, y=0.0)
    vm.state_vms.extend([a, b])

    r1 = ReferenceViewModel(model=ReferenceSkill(name="ref1", description=""), x=800.0, y=0.0)
    r2 = ReferenceViewModel(model=ReferenceSkill(name="ref2", description=""), x=1100.0, y=0.0)
    vm.reference_vms.extend([r1, r2])

    tvm = TransitionViewModel(
        model=Transition(source=a.model, target=b.model, trigger=CompletionEvent(name="done")),
        source_vm=a, target_vm=b,
    )
    tvm.waypoints.append((200.0, 300.0))
    vm.transition_vms.append(tvm)

    scene._rebuild()
    scene._sync_refs_to_model()  # project.reference_placements 초기 시드

    view = FsmCanvasView(scene)
    view.resize(1600, 900)
    view.show()
    qapp.processEvents()

    edge = scene._edge_items[tvm]
    handle = edge._handles[0]

    node_a = scene._node_items[a]
    node_b = scene._node_items[b]
    ref1_item = scene._ref_node_items[r1]
    ref2_item = scene._ref_node_items[r2]
    for item in (node_a, node_b, ref1_item, ref2_item, handle):
        item.setSelected(True)
    qapp.processEvents()

    return view, scene, vm, project, a, b, r1, r2, tvm, edge, handle


def _current_positions(a, b, r1, r2, tvm):
    return {
        "a": (a.x, a.y),
        "b": (b.x, b.y),
        "r1": (r1.x, r1.y),
        "r2": (r2.x, r2.y),
        "wp": tvm.waypoints[0],
    }


# ─────────────────────── 1. 혼합 다중 선택 — 잡은 대상 무관 동일 결과 ───────────────────────


def test_mixed_drag_grab_state_node_moves_all(qapp):
    view, scene, vm, project, a, b, r1, r2, tvm, edge, handle = _make_mixed_scene(qapp)
    node_a = scene._node_items[a]
    before = _current_positions(a, b, r1, r2, tvm)

    start = node_a.mapToScene(QPointF(20, 20))
    end = start + QPointF(80.0, 50.0)
    _drag(view, start, end)
    qapp.processEvents()

    after = _current_positions(a, b, r1, r2, tvm)
    dx, dy = 80.0, 50.0
    for key in ("a", "b", "r1", "r2", "wp"):
        ox, oy = before[key]
        nx, ny = after[key]
        assert abs((nx - ox) - dx) < _TOL and abs((ny - oy) - dy) < _TOL, (
            f"{key}가 잡은 노드와 같은 델타로 이동하지 않음: {before[key]} → {after[key]}"
        )

    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    assert _current_positions(a, b, r1, r2, tvm) == before, "1회 undo로 전부 복원되지 않았다"
    view.hide()


def test_mixed_drag_grab_reference_node_moves_all(qapp):
    view, scene, vm, project, a, b, r1, r2, tvm, edge, handle = _make_mixed_scene(qapp)
    ref1_item = scene._ref_node_items[r1]
    before = _current_positions(a, b, r1, r2, tvm)

    start = ref1_item.mapToScene(QPointF(20, 30))
    end = start + QPointF(-60.0, 40.0)
    _drag(view, start, end)
    qapp.processEvents()

    after = _current_positions(a, b, r1, r2, tvm)
    dx, dy = -60.0, 40.0
    for key in ("a", "b", "r1", "r2", "wp"):
        ox, oy = before[key]
        nx, ny = after[key]
        assert abs((nx - ox) - dx) < _TOL and abs((ny - oy) - dy) < _TOL, (
            f"{key}가 잡은 참조 노드와 같은 델타로 이동하지 않음: {before[key]} → {after[key]}"
        )

    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    assert _current_positions(a, b, r1, r2, tvm) == before, "1회 undo로 전부 복원되지 않았다"
    view.hide()


def test_mixed_drag_grab_waypoint_moves_all(qapp):
    view, scene, vm, project, a, b, r1, r2, tvm, edge, handle = _make_mixed_scene(qapp)
    before = _current_positions(a, b, r1, r2, tvm)

    start = QPointF(*tvm.waypoints[0])
    end = start + QPointF(30.0, -70.0)
    _drag(view, start, end)
    qapp.processEvents()

    after = _current_positions(a, b, r1, r2, tvm)
    dx, dy = 30.0, -70.0
    for key in ("a", "b", "r1", "r2", "wp"):
        ox, oy = before[key]
        nx, ny = after[key]
        assert abs((nx - ox) - dx) < _TOL and abs((ny - oy) - dy) < _TOL, (
            f"{key}가 잡은 웨이포인트와 같은 델타로 이동하지 않음: {before[key]} → {after[key]}"
        )

    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    assert _current_positions(a, b, r1, r2, tvm) == before, "1회 undo로 전부 복원되지 않았다"
    view.hide()


# ─────────────────────── 3. 레퍼런스 모델 동기화 ───────────────────────


def test_mixed_drag_syncs_reference_placements_and_undo_restores(qapp):
    view, scene, vm, project, a, b, r1, r2, tvm, edge, handle = _make_mixed_scene(qapp)
    node_a = scene._node_items[a]

    orig_placements = {p.skill_name: (p.x, p.y) for p in project.reference_placements}
    assert orig_placements == {"ref1": (800.0, 0.0), "ref2": (1100.0, 0.0)}

    start = node_a.mapToScene(QPointF(20, 20))
    end = start + QPointF(45.0, -15.0)
    _drag(view, start, end)
    qapp.processEvents()

    new_placements = {p.skill_name: (p.x, p.y) for p in project.reference_placements}
    for name in ("ref1", "ref2"):
        ox, oy = orig_placements[name]
        nx, ny = new_placements[name]
        assert abs((nx - ox) - 45.0) < _TOL and abs((ny - oy) - (-15.0)) < _TOL, (
            f"project.reference_placements['{name}']가 갱신되지 않음: {orig_placements[name]} → {new_placements[name]}"
        )

    vm.command_stack.undo()
    restored = {p.skill_name: (p.x, p.y) for p in project.reference_placements}
    assert restored == orig_placements, "undo 후 project.reference_placements가 복원되지 않았다"
    view.hide()


# ─────────────────────── 4. 단일 선택 회귀 ───────────────────────


def test_single_selection_drag_produces_single_command_not_macro(qapp):
    """아이템 하나만 선택해 드래그하면 기존과 동일하게 단일 커맨드가 쌓인다."""
    project = PluginProject(name="p")
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene.set_project(project)

    a = StateViewModel(model=SimpleState(name="a"), x=0.0, y=0.0)
    b = StateViewModel(model=SimpleState(name="b"), x=400.0, y=0.0)
    vm.state_vms.extend([a, b])
    scene._rebuild()

    view = FsmCanvasView(scene)
    view.resize(900, 700)
    view.show()
    qapp.processEvents()

    node_a = scene._node_items[a]
    # b는 선택하지 않는다 — 단일 선택 시나리오.
    start = node_a.mapToScene(QPointF(20, 20))
    end = start + QPointF(70.0, 40.0)
    _drag(view, start, end)
    qapp.processEvents()

    assert len(vm.command_stack.history) == 1, "단일 드래그는 커맨드 1개만 쌓여야 한다"
    cmd = vm.command_stack.history[0]
    assert not isinstance(cmd, MacroCommand), "단일 선택 드래그가 MacroCommand로 묶이면 안 된다"
    assert (a.x, a.y) != (0.0, 0.0)
    assert (b.x, b.y) == (400.0, 0.0), "선택되지 않은 노드는 움직이면 안 된다"

    vm.command_stack.undo()
    assert (a.x, a.y) == (0.0, 0.0)
    view.hide()
