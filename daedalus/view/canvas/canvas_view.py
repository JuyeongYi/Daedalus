# daedalus/view/canvas/canvas_view.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QGraphicsView

from daedalus.view.canvas.scene import FsmScene


class FsmCanvasView(QGraphicsView):
    """pan/zoom + 레지스트리 드롭 수신 캔버스 뷰."""

    def __init__(self, scene: FsmScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAcceptDrops(True)
        self._panning = False
        self._pan_start = None

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event is not None and event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent | None) -> None:
        if event is None or not event.mimeData().hasText():
            return
        skill_name = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        sc = self.scene()
        if isinstance(sc, FsmScene):
            sc.drop_skill(skill_name, scene_pos)
        event.acceptProposedAction()

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar is not None:
                h_bar.setValue(h_bar.value() - int(delta.x()))
            if v_bar is not None:
                v_bar.setValue(v_bar.value() - int(delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)
