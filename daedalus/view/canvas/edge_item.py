from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.viewmodel.state_vm import TransitionViewModel

_EDGE_COLOR = QColor("#6674cc")
_EDGE_SELECTED = QColor("#88aaff")
_EDGE_TRANSFER = QColor("#88aacc")   # Transfer Skill 할당 엣지
_ARROW_SIZE = 8.0
_ARROW_SPACING = 320.0   # 화살표 간격 (px)
_EDGE_WIDTH = 4.0        # 기본 두께
_EDGE_WIDTH_TRANSFER = 5.0  # Transfer Skill 할당 시 두께
_HIT_WIDTH = 12.0        # 마우스 클릭 히트 영역


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
        self._input_index: int = 0
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

    def set_input_index(self, index: int) -> None:
        self._input_index = index

    def update_path(self) -> None:
        """출력/입력 포트 위치 기반 베지어 경로."""
        self.prepareGeometryChange()
        trigger = self._transition_vm.model.trigger
        event_name = trigger.name if trigger is not None else "done"

        is_agent_call = self._source_node.is_agent_call_event(event_name)
        src_pt = self._source_node.output_port_scene_pos(event_name, is_agent_call)
        tgt_pt = self._target_node.input_port_scene_pos(self._input_index)

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

    def shape(self) -> QPainterPath:
        """히트 영역을 시각적 두께보다 넓게 설정해 우클릭 편의성 향상."""
        stroker = QPainterPathStroker()
        stroker.setWidth(_HIT_WIDTH)
        return stroker.createStroke(self.path())

    def boundingRect(self) -> QRectF:
        rect = super().boundingRect()
        if self._transition_vm.model.skill_ref is not None:
            # 라벨이 경로 바운딩 박스를 벗어날 수 있으므로 여유 확장
            rect = rect.adjusted(-10, -20, 100, 10)
        return rect

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        skill_ref = self._transition_vm.model.skill_ref
        has_skill = skill_ref is not None

        if self.isSelected():
            color = _EDGE_SELECTED
        elif has_skill:
            color = _EDGE_TRANSFER
        else:
            color = _EDGE_COLOR

        width = _EDGE_WIDTH_TRANSFER if has_skill else _EDGE_WIDTH
        painter.setPen(QPen(color, width))
        painter.drawPath(self.path())

        # 화살표 — 경로 중간 구간에 일정 간격으로 배치 (최소 1개 보장)
        path = self.path()
        if path.isEmpty():
            return
        total = path.length()
        margin = _ARROW_SIZE * 2
        if total < margin * 2:
            return
        painter.setBrush(color)
        painter.setPen(QPen(color))
        if total < _ARROW_SPACING + margin:
            # 짧은 경로 — 중간 지점에 1개
            mid_t = path.percentAtLength(total * 0.5)
            mid_back = path.percentAtLength(max(0.0, total * 0.5 - _ARROW_SIZE))
            self._draw_arrow(painter, path.pointAtPercent(mid_back), path.pointAtPercent(mid_t))
        else:
            dist = _ARROW_SPACING
            while dist < total - margin:
                t = path.percentAtLength(dist)
                t_back = path.percentAtLength(max(0.0, dist - _ARROW_SIZE))
                self._draw_arrow(painter, path.pointAtPercent(t_back), path.pointAtPercent(t))
                dist += _ARROW_SPACING

        # Transfer Skill 라벨
        if has_skill:
            mid = path.pointAtPercent(0.5)
            label = f"⚡ {skill_ref.name}"
            painter.setPen(QPen(QColor("#88aacc")))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QPointF(mid.x() + 4, mid.y() - 4), label)

    @staticmethod
    def _draw_arrow(painter: QPainter, from_pt: QPointF, to_pt: QPointF) -> None:
        dx = to_pt.x() - from_pt.x()
        dy = to_pt.y() - from_pt.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-6:
            return
        dx /= length
        dy /= length
        left = QPointF(
            to_pt.x() - _ARROW_SIZE * dx + _ARROW_SIZE * 0.5 * dy,
            to_pt.y() - _ARROW_SIZE * dy - _ARROW_SIZE * 0.5 * dx,
        )
        right = QPointF(
            to_pt.x() - _ARROW_SIZE * dx - _ARROW_SIZE * 0.5 * dy,
            to_pt.y() - _ARROW_SIZE * dy + _ARROW_SIZE * 0.5 * dx,
        )
        painter.drawPolygon(QPolygonF([to_pt, left, right]))
