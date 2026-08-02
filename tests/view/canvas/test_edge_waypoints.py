"""WP-ER Part D-2/D-3 — 엣지 경유점(waypoint) 렌더 + 상호작용.

렌더: 경유점이 있으면 경로가 그 점을 통과(최근접 거리 ≈ 0)하고, 경유점이
없으면 기존 렌더 공식과 완전히 동일(하위 호환)함을 고정한다.
상호작용: 더블클릭 삽입, 핸들 드래그 커밋, 제거/모두 제거, undo,
저장→로드 왕복 보존을 검증한다.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.view.app import MainWindow
from daedalus.view.canvas.edge_item import TransitionEdgeItem, WaypointHandleItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.commands.transition_commands import (
    AddWaypointCmd,
    ClearWaypointsCmd,
    MoveWaypointCmd,
    RemoveWaypointCmd,
)
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_nodes():
    a = StateNodeItem(StateViewModel(model=SimpleState(name="a"), x=0, y=0))
    b = StateNodeItem(StateViewModel(model=SimpleState(name="b"), x=300, y=0))
    return a, b


def _make_edge(waypoints=None):
    a, b = _make_nodes()
    model = Transition(source=a.state_vm.model, target=b.state_vm.model,
                       trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(
        model=model, source_vm=a.state_vm, target_vm=b.state_vm,
        waypoints=list(waypoints) if waypoints else [],
    )
    edge = TransitionEdgeItem(tvm, a, b)
    return edge, tvm, a, b


def _min_dist_to_path(path, pt: QPointF, samples: int = 4000) -> float:
    best = None
    for s in range(samples + 1):
        p = path.pointAtPercent(s / samples)
        dx = p.x() - pt.x()
        dy = p.y() - pt.y()
        d = (dx * dx + dy * dy) ** 0.5
        if best is None or d < best:
            best = d
    return best


# ─────────────────────── 렌더 (Part D-2) ───────────────────────


def test_edge_without_waypoints_matches_original_formula(qapp):
    """경유점 없으면 기존 단일 구간 베지어 공식과 완전히 동일한 경로."""
    edge, tvm, a, b = _make_edge()
    edge.update_path()

    src_pt = a.output_port_scene_pos("done", False)
    tgt_pt = b.input_port_scene_pos("")
    dx = abs(tgt_pt.x() - src_pt.x()) * 0.5
    ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
    ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())

    from PySide6.QtGui import QPainterPath
    expected = QPainterPath(src_pt)
    expected.cubicTo(ctrl1, ctrl2, tgt_pt)

    actual = edge.path()
    assert actual.pointAtPercent(0.0) == expected.pointAtPercent(0.0)
    assert actual.pointAtPercent(0.5) == expected.pointAtPercent(0.5)
    assert actual.pointAtPercent(1.0) == expected.pointAtPercent(1.0)
    assert abs(actual.length() - expected.length()) < 1e-6


def test_edge_with_waypoint_path_passes_through_it(qapp):
    """경유점이 있으면 경로가 그 점을 통과한다(최근접 거리 ≈ 0)."""
    edge, tvm, a, b = _make_edge(waypoints=[(150.0, -80.0)])
    edge.update_path()
    dist = _min_dist_to_path(edge.path(), QPointF(150.0, -80.0))
    assert dist < 0.5


def test_edge_with_multiple_waypoints_passes_through_all(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(80.0, 60.0), (220.0, -60.0)])
    edge.update_path()
    path = edge.path()
    assert _min_dist_to_path(path, QPointF(80.0, 60.0)) < 0.5
    assert _min_dist_to_path(path, QPointF(220.0, -60.0)) < 0.5


# ─────────────────────── 핸들 표시/숨김 ───────────────────────


def test_handles_hidden_when_edge_not_selected(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(100.0, 50.0)])
    assert len(edge._handles) == 1
    assert edge._handles[0].isVisible() is False


def test_handles_visible_when_edge_selected(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(100.0, 50.0)])
    edge.setSelected(True)
    assert edge._handles[0].isVisible() is True
    edge.setSelected(False)
    assert edge._handles[0].isVisible() is False


def test_handle_position_matches_waypoint(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(123.0, 45.0)])
    handle = edge._handles[0]
    assert (handle.pos().x(), handle.pos().y()) == (123.0, 45.0)


# ─────────────────────── 상호작용: nearest_segment_index ───────────────────────


def test_nearest_segment_index_no_waypoints_is_zero(qapp):
    edge, tvm, a, b = _make_edge()
    assert edge.nearest_segment_index(QPointF(150.0, 0.0)) == 0


def test_nearest_segment_index_picks_closer_segment(qapp):
    """경유점 하나 존재 시, 두 구간(src→wp, wp→tgt) 중 가까운 쪽을 고른다."""
    edge, tvm, a, b = _make_edge(waypoints=[(150.0, 0.0)])
    # src(0,~) 쪽에 가까운 클릭 → 구간 0
    idx_near_src = edge.nearest_segment_index(QPointF(20.0, 0.0))
    assert idx_near_src == 0
    # tgt(300,~) 쪽에 가까운 클릭 → 구간 1
    idx_near_tgt = edge.nearest_segment_index(QPointF(280.0, 0.0))
    assert idx_near_tgt == 1


# ─────────────────────── 커맨드: undo 가능 ───────────────────────


def test_add_waypoint_cmd_insert_and_undo(qapp):
    edge, tvm, a, b = _make_edge()
    cmd = AddWaypointCmd(tvm, 0, 111.0, 222.0)
    cmd.execute()
    assert tvm.waypoints == [(111.0, 222.0)]
    cmd.undo()
    assert tvm.waypoints == []


def test_move_waypoint_cmd_and_undo(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(10.0, 20.0)])
    cmd = MoveWaypointCmd(tvm, 0, old_x=10.0, old_y=20.0, new_x=99.0, new_y=88.0)
    cmd.execute()
    assert tvm.waypoints[0] == (99.0, 88.0)
    cmd.undo()
    assert tvm.waypoints[0] == (10.0, 20.0)


def test_remove_waypoint_cmd_and_undo(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(10.0, 20.0), (30.0, 40.0)])
    cmd = RemoveWaypointCmd(tvm, 0)
    cmd.execute()
    assert tvm.waypoints == [(30.0, 40.0)]
    cmd.undo()
    assert tvm.waypoints == [(10.0, 20.0), (30.0, 40.0)]


def test_clear_waypoints_cmd_and_undo(qapp):
    edge, tvm, a, b = _make_edge(waypoints=[(10.0, 20.0), (30.0, 40.0)])
    cmd = ClearWaypointsCmd(tvm)
    cmd.execute()
    assert tvm.waypoints == []
    cmd.undo()
    assert tvm.waypoints == [(10.0, 20.0), (30.0, 40.0)]


# ─────────────────────── 씬 레벨: 더블클릭/핸들 드래그/undo 스택 ───────────────────────


def _make_scene_with_edge():
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=300, y=0)
    vm.state_vms.extend([avm, bvm])
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    vm.transition_vms.append(tvm)
    vm.notify()
    edge = scene._edge_items[tvm]
    return scene, vm, tvm, edge


def test_scene_handle_edge_double_clicked_inserts_via_undo_stack(qapp):
    scene, vm, tvm, edge = _make_scene_with_edge()
    scene.handle_edge_double_clicked(edge, QPointF(50.0, 5.0))
    assert len(tvm.waypoints) == 1
    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    assert tvm.waypoints == []


def test_scene_handle_waypoint_moved_commits_undoable(qapp):
    scene, vm, tvm, edge = _make_scene_with_edge()
    scene.handle_edge_double_clicked(edge, QPointF(50.0, 5.0))
    old_pos = QPointF(*tvm.waypoints[0])
    new_pos = QPointF(60.0, 90.0)
    scene.handle_waypoint_moved(edge, 0, old_pos, new_pos)
    assert tvm.waypoints[0] == (60.0, 90.0)
    vm.command_stack.undo()
    assert tvm.waypoints[0] == (old_pos.x(), old_pos.y())


def test_scene_remove_waypoint_undoable(qapp):
    scene, vm, tvm, edge = _make_scene_with_edge()
    scene.handle_edge_double_clicked(edge, QPointF(50.0, 5.0))
    scene.remove_waypoint(edge, 0)
    assert tvm.waypoints == []
    vm.command_stack.undo()
    assert len(tvm.waypoints) == 1


def test_scene_clear_waypoints_undoable(qapp):
    scene, vm, tvm, edge = _make_scene_with_edge()
    scene.handle_edge_double_clicked(edge, QPointF(50.0, 5.0))
    scene.handle_edge_double_clicked(edge, QPointF(250.0, 5.0))
    assert len(tvm.waypoints) == 2
    scene.clear_waypoints(edge)
    assert tvm.waypoints == []
    vm.command_stack.undo()
    assert len(tvm.waypoints) == 2


def test_waypoint_handle_item_drag_updates_preview(qapp):
    """WaypointHandleItem.itemChange가 드래그 중 tvm.waypoints를 실시간 갱신."""
    scene, vm, tvm, edge = _make_scene_with_edge()
    scene.handle_edge_double_clicked(edge, QPointF(50.0, 5.0))
    handle = edge._handles[0]
    handle.setPos(QPointF(77.0, 33.0))
    assert tvm.waypoints[0] == (77.0, 33.0)


# ─────────────────────── 저장→로드 왕복 (Part D-3) ───────────────────────


def _mk_proc(name):
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name=name, description=f"{name}.")


def test_waypoints_survive_save_load_round_trip(qapp, tmp_path):
    a = _mk_proc("a")
    b = _mk_proc("b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    t = Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    project.graph.transitions.append(t)

    window = MainWindow()
    window.set_project(project)
    tvm = window._project_vm.transition_vms[0]
    tvm.waypoints.append((123.0, 45.0))
    tvm.waypoints.append((222.0, -33.0))

    dst = tmp_path / "p.daedalus.json"
    window._save_to_path(str(dst))
    window.close()

    data = json.loads(dst.read_text(encoding="utf-8"))
    assert data["edge_layout"][t.id] == [[123.0, 45.0], [222.0, -33.0]]

    project2 = deserialize_project(data)
    window2 = MainWindow()
    window2.set_project(project2)
    tvm2 = window2._project_vm.transition_vms[0]
    assert tvm2.waypoints == [(123.0, 45.0), (222.0, -33.0)]
    window2.close()


# ── 리뷰 반영: 실제 Qt 이벤트 경로 회귀 (결함 1·2 잠금) ──
# QTest.mouseMove는 buttons 상태를 싣지 않으므로 합성 QMouseEvent로
# buttons=LeftButton을 명시해 view.viewport()에 전달한다 (리뷰어 레시피).


def _send_mouse(view, type_, scene_pos, *, button, buttons):
    from PySide6.QtCore import QPointF as _QPointF, Qt  # noqa: F401
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    vp_pos = view.mapFromScene(scene_pos)
    ev = QMouseEvent(
        type_, _QPointF(vp_pos),
        _QPointF(view.viewport().mapToGlobal(vp_pos)),
        button, buttons, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), ev)


def _view_scene_with_waypoint(qapp):
    """뷰 + 씬 + 경유점 1개짜리 전이. (view, scene, vm, tvm, edge, handle 스캔용)"""
    from PySide6.QtWidgets import QGraphicsView

    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    b = StateViewModel(model=SimpleState(name="b"), x=400, y=0)
    vm.state_vms.extend([a, b])
    tvm = TransitionViewModel(
        model=Transition(source=a.model, target=b.model,
                         trigger=CompletionEvent(name="done")),
        source_vm=a, target_vm=b,
    )
    tvm.waypoints.append((300.0, 150.0))
    vm.transition_vms.append(tvm)
    scene._rebuild()
    view = QGraphicsView(scene)
    view.resize(800, 600)
    view.show()
    qapp.processEvents()
    return view, scene, vm, tvm


def test_handle_drag_via_real_mouse_events(qapp):
    """핸들 press가 엣지 선택을 해제하지 않고, 드래그가 실제로 동작한다 (결함 1)."""
    from PySide6.QtCore import QEvent, QPointF as _QP, Qt

    view, scene, vm, tvm = _view_scene_with_waypoint(qapp)
    edge = scene._edge_items[tvm]
    edge.setSelected(True)
    qapp.processEvents()

    handle_pos = _QP(300.0, 150.0)
    target_pos = _QP(340.0, 90.0)

    _send_mouse(view, QEvent.Type.MouseButtonPress, handle_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton)
    assert edge.isSelected(), "핸들 press가 엣지 선택을 해제하면 안 된다"
    _send_mouse(view, QEvent.Type.MouseMove, target_pos,
                button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.LeftButton)
    _send_mouse(view, QEvent.Type.MouseButtonRelease, target_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)
    qapp.processEvents()

    wx, wy = tvm.waypoints[0]
    assert abs(wx - 340.0) < 2.0 and abs(wy - 90.0) < 2.0, f"드래그 미반영: {tvm.waypoints}"
    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    wx2, wy2 = tvm.waypoints[0]
    assert abs(wx2 - 300.0) < 0.01 and abs(wy2 - 150.0) < 0.01
    view.hide()


def test_delete_on_handle_removes_waypoint_not_transition(qapp):
    """핸들이 선택된 상태의 Delete는 경유점만 제거한다 — 전이는 무사 (결함 2)."""
    from PySide6.QtCore import QEvent, QPointF as _QP, Qt
    from PySide6.QtTest import QTest

    view, scene, vm, tvm = _view_scene_with_waypoint(qapp)
    edge = scene._edge_items[tvm]
    edge.setSelected(True)
    qapp.processEvents()

    handle_pos = _QP(300.0, 150.0)
    _send_mouse(view, QEvent.Type.MouseButtonPress, handle_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton)
    _send_mouse(view, QEvent.Type.MouseButtonRelease, handle_pos,
                button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)
    qapp.processEvents()

    QTest.keyClick(view.viewport(), Qt.Key.Key_Delete)
    qapp.processEvents()

    assert tvm.waypoints == []
    assert tvm in vm.transition_vms, "Delete가 전이까지 지우면 안 된다"
    view.hide()
