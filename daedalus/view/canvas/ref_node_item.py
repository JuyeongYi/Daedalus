# daedalus/view/canvas/ref_node_item.py
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.viewmodel.state_vm import ReferenceViewModel

_W = 160.0
_H = 48.0
_HEADER_H = 18.0
_PORT_R = 6.0

_BG = QColor("#1a2a2a")
_BORDER = QColor("#66aaaa")
_HEADER_LABEL = "📖 REFERENCE"


class ReferenceNodeItem(QGraphicsItem):
    """참조 스킬 노드 — 컴팩트 카드, 상단 포트, 점선 테두리."""

    def __init__(
        self, ref_vm: ReferenceViewModel, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._ref_vm = ref_vm
        self.setPos(ref_vm.x, ref_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._drag_start_pos: QPointF | None = None
        self._dragging_link = False

    @property
    def ref_vm(self) -> ReferenceViewModel:
        return self._ref_vm

    def boundingRect(self) -> QRectF:
        return QRectF(-_PORT_R, -_PORT_R, _W + _PORT_R * 2, _H + _PORT_R * 2)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        border = _BORDER.lighter(160) if self.isSelected() else _BORDER

        # 본체 — 점선 테두리
        body = QRectF(0, 0, _W, _H)
        pen = QPen(border, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(_BG))
        painter.drawRoundedRect(body, 7, 7)

        # 헤더
        hdr = QRectF(1, 1, _W - 2, _HEADER_H - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_BG.darker(140)))
        painter.drawRoundedRect(hdr, 6, 6)
        painter.drawRect(QRectF(1, 9, _W - 2, _HEADER_H - 10))

        painter.setPen(QPen(border.lighter(130)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(hdr.adjusted(6, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, _HEADER_LABEL)

        # 이름
        name = getattr(self._ref_vm.model, "name", "?")
        text_color = QColor("#eee") if self.isSelected() else QColor("#ccc")
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 9)
        if self.isSelected():
            font.setBold(True)
        painter.setFont(font)
        name_rect = QRectF(4, _HEADER_H, _W - 8, _H - _HEADER_H)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, name)

        # 상단 포트 (중앙)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(_BORDER))
        painter.drawEllipse(QPointF(_W / 2, 0), _PORT_R, _PORT_R)

    def top_port_scene_pos(self) -> QPointF:
        """상단 포트의 씬 좌표."""
        return self.mapToScene(QPointF(_W / 2, 0))

    def is_top_port(self, local_pos: QPointF) -> bool:
        """local_pos가 상단 포트 위인지 판정."""
        dx = local_pos.x() - _W / 2
        dy = local_pos.y()
        hit_r = _PORT_R * 2
        return dx * dx + dy * dy <= hit_r * hit_r

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_ref_edges_for_node"):
                sc.update_ref_edges_for_node(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_top_port(event.pos()):
                self._dragging_link = True
                sc: Any = self.scene()
                if sc is not None and hasattr(sc, "begin_ref_link_drag"):
                    sc.begin_ref_link_drag(self)
                event.accept()
                return
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event is None:
            return
        if self._dragging_link:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_ref_link_drag"):
                sc.update_ref_link_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event is None:
            return
        if self._dragging_link:
            self._dragging_link = False
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "end_ref_link_drag"):
                sc.end_ref_link_drag(self, self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            self._ref_vm.x = self.pos().x()
            self._ref_vm.y = self.pos().y()
        self._drag_start_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event is None:
            return
        sc: Any = self.scene()
        if sc is not None and hasattr(sc, "handle_ref_node_double_clicked"):
            sc.handle_ref_node_double_clicked(self)
        event.accept()
