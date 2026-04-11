from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QRectF, Qt
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
        self._drag_start_pos = None

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._state_vm.width, self._state_vm.height)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        rect = self.boundingRect()
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

    def mousePressEvent(self, event) -> None:
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            scene: Any = self.scene()
            if scene is not None and hasattr(scene, "handle_node_moved"):
                scene.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
