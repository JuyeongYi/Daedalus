# daedalus/view/canvas/ref_edge_item.py
"""참조 스킬 연결선 — 상하 방향, Transfer Skill 부여 불가."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.ref_node_item import ReferenceNodeItem
from daedalus.view.viewmodel.state_vm import ReferenceLinkViewModel

_COLOR = QColor("#66aaaa")
_COLOR_SELECTED = QColor("#88dddd")
_WIDTH = 2.0
_HIT_WIDTH = 10.0


class ReferenceEdgeItem(QGraphicsPathItem):
    """StateNodeItem 하단 포트 → ReferenceNodeItem 상단 포트 연결."""

    def __init__(
        self,
        link_vm: ReferenceLinkViewModel,
        source_node: StateNodeItem,
        ref_node: ReferenceNodeItem,
        port_index: int = 0,
    ) -> None:
        super().__init__()
        self._link_vm = link_vm
        self._source_node = source_node
        self._ref_node = ref_node
        self._port_index = port_index
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-2)
        self.update_path()

    @property
    def link_vm(self) -> ReferenceLinkViewModel:
        return self._link_vm

    @property
    def source_node(self) -> StateNodeItem:
        return self._source_node

    @property
    def ref_node(self) -> ReferenceNodeItem:
        return self._ref_node

    def set_port_index(self, index: int) -> None:
        self._port_index = index

    def update_path(self) -> None:
        self.prepareGeometryChange()
        src_pt = self._source_node.ref_port_scene_pos(self._port_index)
        tgt_pt = self._ref_node.top_port_scene_pos()

        # 수직 베지어 — 아래로 내려가는 곡선
        dy = abs(tgt_pt.y() - src_pt.y()) * 0.4
        ctrl1 = QPointF(src_pt.x(), src_pt.y() + dy)
        ctrl2 = QPointF(tgt_pt.x(), tgt_pt.y() - dy)

        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)
        self.setPath(path)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_HIT_WIDTH)
        return stroker.createStroke(self.path())

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        color = _COLOR_SELECTED if self.isSelected() else _COLOR
        pen = QPen(color, _WIDTH, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawPath(self.path())
