from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.viewmodel.state_vm import StateViewModel

_BORDER_NORMAL = QColor("#4455aa")
_BORDER_SELECTED = QColor("#88aaff")
_FILL = QColor("#2a2a4a")
_HEADER_FILL = QColor("#334")
_TEXT_COLOR = QColor("#ddd")
_TEXT_SELECTED = QColor("#fff")
_SUBTEXT_COLOR = QColor("#888")
_PORT_COLOR = QColor("#4488ff")
_PORT_RADIUS = 7.0


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 SimpleState 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self.setPos(state_vm.x, state_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._drag_start_pos: QPointF | None = None
        self._dragging_connection = False

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    def _port_center(self) -> QPointF:
        """우측 중앙 포트 위치 (로컬 좌표)."""
        return QPointF(self._state_vm.width, self._state_vm.height / 2)

    def _in_port(self, local_pos: QPointF) -> bool:
        c = self._port_center()
        dx = local_pos.x() - c.x()
        dy = local_pos.y() - c.y()
        return (dx * dx + dy * dy) <= (_PORT_RADIUS * _PORT_RADIUS)

    def boundingRect(self) -> QRectF:
        w = self._state_vm.width
        h = self._state_vm.height
        return QRectF(0, 0, w + _PORT_RADIUS + 2, h)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        w = self._state_vm.width
        h = self._state_vm.height
        rect = QRectF(0, 0, w, h)
        selected = self.isSelected()
        border = _BORDER_SELECTED if selected else _BORDER_NORMAL

        # 본체
        painter.setPen(QPen(border, 2))
        painter.setBrush(QBrush(_FILL))
        painter.drawRoundedRect(rect, 8, 8)

        # 헤더
        header_h = 20.0
        header_rect = QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, header_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_HEADER_FILL))
        painter.drawRoundedRect(header_rect, 7, 7)
        painter.drawRect(
            QRectF(header_rect.x(), header_rect.y() + 10, header_rect.width(), header_h - 10)
        )

        painter.setPen(QPen(_SUBTEXT_COLOR))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            header_rect.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "SimpleState"
        )

        # 이름
        name_rect = QRectF(rect.x(), rect.y() + header_h, rect.width(), rect.height() - header_h)
        painter.setPen(QPen(_TEXT_SELECTED if selected else _TEXT_COLOR))
        font = QFont("Segoe UI", 11)
        if selected:
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, self._state_vm.model.name)

        # 연결 포트 (우측 중앙)
        painter.setPen(QPen(_BORDER_NORMAL, 1))
        painter.setBrush(QBrush(_PORT_COLOR))
        port = self._port_center()
        painter.drawEllipse(port, _PORT_RADIUS, _PORT_RADIUS)

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._in_port(event.pos())
        ):
            self._dragging_connection = True
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "begin_transition_drag"):
                sc.begin_transition_drag(self)
            event.accept()
            return
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_connection:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_transition_drag"):
                sc.update_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        sc: Any = self.scene()
        if self._dragging_connection:
            self._dragging_connection = False
            if sc is not None and hasattr(sc, "end_transition_drag"):
                sc.end_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            if sc is not None and hasattr(sc, "handle_node_moved"):
                sc.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
