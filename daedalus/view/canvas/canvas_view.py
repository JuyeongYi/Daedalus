# daedalus/view/canvas/canvas_view.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QColor,
    QWheelEvent,
    QResizeEvent,
)
from PyQt6.QtWidgets import QGraphicsView, QWidget

from daedalus.view.canvas.scene import FsmScene

# 줌 범위 상수
_MIN_ZOOM = 0.05   # 5%
_MAX_ZOOM = 8.0    # 800%
_MINIMAP_THRESHOLD = 0.25  # 이 배율 이하에서 미니맵 표시

_MINIMAP_W = 200
_MINIMAP_H = 140
_MINIMAP_MARGIN = 8


class _MiniMap(QGraphicsView):
    """씬 전체를 축소 표시하는 미니맵 오버레이 (메인 뷰 하단 우측)."""

    def __init__(self, scene: FsmScene, parent: QWidget) -> None:
        super().__init__(scene, parent)
        self.setFixedSize(_MINIMAP_W, _MINIMAP_H)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet(
            "background: rgba(18, 18, 42, 220); border: 1px solid #334;"
        )
        self._main_view: FsmCanvasView | None = None

    def set_main_view(self, view: FsmCanvasView) -> None:
        self._main_view = view

    def fit_to_items(self) -> None:
        sc = self.scene()
        if sc is None:
            return
        rect = sc.itemsBoundingRect()
        if rect.isEmpty():
            rect = sc.sceneRect()
        self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def drawForeground(self, painter: QPainter | None, rect) -> None:  # type: ignore[override]
        """메인 뷰의 현재 화면 영역을 파란 테두리로 표시."""
        if painter is None or self._main_view is None:
            return
        vp = self._main_view.viewport()
        if vp is None:
            return
        vp_scene_rect = self._main_view.mapToScene(vp.rect()).boundingRect()
        pen = QPen(QColor("#4488ff"), 0)  # cosmetic pen (width=0 → 1px)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(vp_scene_rect)


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

        # 미니맵 오버레이 — viewport의 자식 위젯
        vp = self.viewport()
        self._minimap: _MiniMap | None = None
        if vp is not None:
            self._minimap = _MiniMap(scene, vp)
            self._minimap.set_main_view(self)
            self._minimap.hide()

    def fit_to_content(self) -> None:
        """노드 영역에 뷰를 맞춤."""
        sc = self.scene()
        if sc is None:
            return
        rect = sc.itemsBoundingRect()
        if rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-80, -80, 80, 80), Qt.AspectRatioMode.KeepAspectRatio)

    # --- 드롭 ---

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

    # --- 줌 (제한 있음) ---

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current_zoom = self.transform().m11()
        new_zoom = current_zoom * factor
        if new_zoom < _MIN_ZOOM:
            factor = _MIN_ZOOM / current_zoom
        elif new_zoom > _MAX_ZOOM:
            factor = _MAX_ZOOM / current_zoom
        if abs(factor - 1.0) > 1e-9:
            self.scale(factor, factor)
        self._update_minimap()

    # --- 미니맵 ---

    def _update_minimap(self) -> None:
        if self._minimap is None:
            return
        zoom = self.transform().m11()
        visible = zoom < _MINIMAP_THRESHOLD
        self._minimap.setVisible(visible)
        if visible:
            self._minimap.fit_to_items()
            self._reposition_minimap()

    def _reposition_minimap(self) -> None:
        if self._minimap is None:
            return
        vp = self.viewport()
        if vp is None:
            return
        x = vp.width() - _MINIMAP_W - _MINIMAP_MARGIN
        y = vp.height() - _MINIMAP_H - _MINIMAP_MARGIN
        self._minimap.move(x, y)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._reposition_minimap()

    # --- 패닝 ---

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
            # 미니맵 viewport 인디케이터 갱신
            if self._minimap is not None and self._minimap.isVisible():
                self._minimap.viewport().update() if self._minimap.viewport() else None
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
