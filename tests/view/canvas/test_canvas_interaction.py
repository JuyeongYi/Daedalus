# tests/view/canvas/test_canvas_interaction.py
"""캔버스 기본 상호작용 — 러버밴드 다중 선택·다중 이동·씬 범위 확장.

사용자 보고: ① 노드 다중 선택 및 드래그가 안 됨(setDragMode가 NoDrag라
러버밴드 자체가 없었다) ② FSM 창 최대 이동 범위가 너무 작음(sceneRect 고정).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QGraphicsView

from daedalus.model.fsm.state import SimpleState
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel


def _send(view, type_, scene_pos, *, button, buttons):
    vp = view.mapFromScene(scene_pos)
    ev = QMouseEvent(
        type_, QPointF(vp), QPointF(view.viewport().mapToGlobal(vp)),
        button, buttons, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), ev)


def _two_node_view(qapp):
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    a = StateViewModel(model=SimpleState(name="a"), x=0, y=0)
    b = StateViewModel(model=SimpleState(name="b"), x=200, y=0)
    vm.state_vms.extend([a, b])
    scene._rebuild()
    view = FsmCanvasView(scene)
    view.resize(900, 700)
    view.show()
    qapp.processEvents()
    return view, scene, vm, a, b


def test_view_uses_rubber_band_drag(qapp):
    view, _scene, _vm, _a, _b = _two_node_view(qapp)
    assert view.dragMode() == QGraphicsView.DragMode.RubberBandDrag
    view.hide()


def test_rubber_band_selects_multiple_nodes(qapp):
    """빈 영역 드래그로 여러 노드를 한 번에 선택한다."""
    view, scene, _vm, _a, _b = _two_node_view(qapp)
    _send(view, QEvent.Type.MouseButtonPress, QPointF(-80, -80),
          button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton)
    _send(view, QEvent.Type.MouseMove, QPointF(400, 200),
          button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.LeftButton)
    _send(view, QEvent.Type.MouseButtonRelease, QPointF(400, 200),
          button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)
    qapp.processEvents()
    assert len(scene.selectedItems()) == 2
    view.hide()


def test_multi_selection_drag_moves_all_as_one_undo(qapp):
    """다중 선택 상태에서 하나를 끌면 전부 이동하고 1 undo로 되돌아간다."""
    view, scene, vm, a, b = _two_node_view(qapp)
    for item in scene._node_items.values():
        item.setSelected(True)
    qapp.processEvents()

    _send(view, QEvent.Type.MouseButtonPress, QPointF(20, 20),
          button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton)
    _send(view, QEvent.Type.MouseMove, QPointF(120, 90),
          button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.LeftButton)
    _send(view, QEvent.Type.MouseButtonRelease, QPointF(120, 90),
          button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton)
    qapp.processEvents()

    assert (a.x, a.y) != (0, 0), "잡은 노드가 안 움직였다"
    assert (b.x, b.y) != (200, 0), "함께 선택된 노드가 안 움직였다"
    assert vm.command_stack.can_undo
    vm.command_stack.undo()
    assert (a.x, a.y) == (0, 0) and (b.x, b.y) == (200, 0), "1 undo로 복원되지 않았다"
    view.hide()


def test_scene_rect_is_large_and_grows(qapp):
    """씬 범위가 넉넉하고, 아이템이 가장자리에 접근하면 확장된다."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    initial = scene.sceneRect()
    assert initial.width() >= 40000 and initial.height() >= 40000

    far = StateViewModel(model=SimpleState(name="far"), x=19500, y=19500)
    vm.state_vms.append(far)
    scene._rebuild()
    grown = scene.sceneRect()
    assert grown.right() > initial.right(), "먼 노드를 담도록 확장되지 않았다"
    assert grown.contains(initial), "확장이 기존 범위를 잃었다 (축소 금지)"
