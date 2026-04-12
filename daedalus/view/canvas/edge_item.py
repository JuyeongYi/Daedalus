from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.viewmodel.state_vm import TransitionViewModel

_EDGE_COLOR = QColor("#6674cc")
_EDGE_SELECTED = QColor("#88aaff")
_ARROW_SIZE = 8.0


class TransitionEdgeItem(QGraphicsPathItem):
    """두 StateNodeItem을 연결하는 전이 화살표."""

    def __init__(
        self,
        transition_vm: TransitionViewModel,
        source_node: StateNodeItem,
        target_node: StateNodeItem,
    ) -> None:
        super().__init__()
        self._transition_vm = transition_vm
        self._source_node = source_node
        self._target_node = target_node
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)
        self.update_path()

    @property
    def transition_vm(self) -> TransitionViewModel:
        return self._transition_vm

    @property
    def source_node(self) -> StateNodeItem:
        return self._source_node

    @property
    def target_node(self) -> StateNodeItem:
        return self._target_node

    def update_path(self) -> None:
        """출력/입력 포트 위치 기반 베지어 경로."""
        trigger = self._transition_vm.model.trigger
        event_name = trigger.name if trigger is not None else "done"

        src_pt = self._source_node.output_port_scene_pos(event_name)
        tgt_pt = self._target_node.input_port_scene_pos()

        if tgt_pt.x() < src_pt.x():
            # 역방향 — 더 크게 휘어짐
            dx = abs(tgt_pt.x() - src_pt.x()) * 0.8 + 80
            ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
            ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())
        else:
            dx = abs(tgt_pt.x() - src_pt.x()) * 0.5
            ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
            ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())

        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)
        self.setPath(path)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        color = _EDGE_SELECTED if self.isSelected() else _EDGE_COLOR
        painter.setPen(QPen(color, 2))
        painter.drawPath(self.path())

        # 화살표 머리
        path = self.path()
        if path.isEmpty():
            return
        end_pt = path.pointAtPercent(1.0)
        tangent_pt = path.pointAtPercent(0.95)
        dx = end_pt.x() - tangent_pt.x()
        dy = end_pt.y() - tangent_pt.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            dx /= length
            dy /= length
            left = QPointF(
                end_pt.x() - _ARROW_SIZE * dx + _ARROW_SIZE * 0.5 * dy,
                end_pt.y() - _ARROW_SIZE * dy - _ARROW_SIZE * 0.5 * dx,
            )
            right = QPointF(
                end_pt.x() - _ARROW_SIZE * dx - _ARROW_SIZE * 0.5 * dy,
                end_pt.y() - _ARROW_SIZE * dy + _ARROW_SIZE * 0.5 * dx,
            )
            arrow = QPolygonF([end_pt, left, right])
            painter.setBrush(color)
            painter.setPen(QPen(color))
            painter.drawPolygon(arrow)
