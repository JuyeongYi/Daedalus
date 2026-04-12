# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.viewmodel.state_vm import StateViewModel

_W = 160.0          # 노드 본체 너비
_HEADER_H = 20.0    # 헤더 높이
_PORT_R = 6.0       # 포트 원 반지름
_PORT_SPACING = 22.0  # 출력 포트 간 수직 간격
_PORT_PAD = 12.0    # 포트 영역 상하 패딩
_LABEL_W = 44.0     # 출력 포트 레이블 너비

# skill kind → (배경, 테두리, 헤더 텍스트, 아이콘)
_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "PROCEDURAL", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}

_PORT_COLORS: dict[str, QColor] = {
    "done":  QColor("#4488ff"),
    "error": QColor("#cc3333"),
}
_PORT_DEFAULT_COLOR = QColor("#cc8800")


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 스킬/에이전트 노드."""

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
        self._drag_event_name: str | None = None
        self._sync_height()

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    # --- 치수 ---

    def _output_events(self) -> list[str]:
        ref = self._state_vm.model.skill_ref
        if ref is not None and hasattr(ref, "output_events"):
            return list(ref.output_events)
        return []

    def _height(self) -> float:
        n = max(1, len(self._output_events()))
        port_area = _PORT_SPACING * n + _PORT_PAD * 2
        return _HEADER_H + max(44.0, port_area)

    def _output_port_y(self, i: int, n: int) -> float:
        body_h = self._height() - _HEADER_H
        spacing = body_h / (n + 1)
        return _HEADER_H + spacing * (i + 1)

    def _sync_height(self) -> None:
        new_h = self._height()
        if self._state_vm.height != new_h:
            self.prepareGeometryChange()
            self._state_vm.height = new_h

    def update_from_model(self) -> None:
        """output_events 변경 후 호출 — 높이/포트 재계산."""
        self._sync_height()
        self.update()

    # --- QGraphicsItem ---

    def boundingRect(self) -> QRectF:
        h = self._height()
        return QRectF(-_PORT_R * 2 - 2, 0, _W + _PORT_R * 2 + 2 + _LABEL_W, h)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        ref = self._state_vm.model.skill_ref
        kind = ref.kind if ref is not None else None
        bg_str, border_str, header_label, icon = _TYPE_STYLE.get(kind, _TYPE_STYLE[None])
        border_color = QColor(border_str)
        active_border = border_color.lighter(160) if self.isSelected() else border_color

        h = self._height()
        events = self._output_events() or ["done"]
        n = len(events)

        # 본체
        body_rect = QRectF(0, 0, _W, h)
        painter.setPen(QPen(active_border, 2))
        painter.setBrush(QBrush(QColor(bg_str)))
        painter.drawRoundedRect(body_rect, 7, 7)

        # 헤더
        header_rect = QRectF(1, 1, _W - 2, _HEADER_H - 1)
        hdr_bg = QColor(bg_str).darker(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(hdr_bg))
        painter.drawRoundedRect(header_rect, 6, 6)
        painter.drawRect(QRectF(1, 10, _W - 2, _HEADER_H - 11))

        painter.setPen(QPen(border_color.lighter(130)))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            header_rect.adjusted(6, 0, -20, 0),
            Qt.AlignmentFlag.AlignVCenter, header_label,
        )
        if icon:
            painter.drawText(
                header_rect.adjusted(0, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                icon,
            )

        # 이름
        name_rect = QRectF(4, _HEADER_H, _W - 8, h - _HEADER_H - 12)
        text_color = QColor("#eee") if self.isSelected() else QColor("#ccc")
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 11)
        if self.isSelected():
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, self._state_vm.model.name)

        # 서브텍스트
        subtext_rect = QRectF(4, h - 12, _W - 8, 12)
        painter.setPen(QPen(border_color.lighter(80)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(subtext_rect, Qt.AlignmentFlag.AlignCenter, kind or "state")

        # 입력 포트 (좌측 중앙)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#888")))
        painter.drawEllipse(QPointF(0.0, h / 2), _PORT_R, _PORT_R)

        # 출력 포트 (우측, 이벤트별)
        for i, event_name in enumerate(events):
            y = self._output_port_y(i, n)
            port_color = _PORT_COLORS.get(event_name, _PORT_DEFAULT_COLOR)
            painter.setPen(QPen(QColor("#111"), 1))
            painter.setBrush(QBrush(port_color))
            painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
            lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W - 4, 14)
            painter.setPen(QPen(port_color.lighter(140)))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, event_name)

    # --- 포트 씬 좌표 ---

    def output_port_scene_pos(self, event_name: str) -> QPointF:
        events = self._output_events() or ["done"]
        n = len(events)
        try:
            i = events.index(event_name)
        except ValueError:
            i = 0
        return self.mapToScene(QPointF(_W, self._output_port_y(i, n)))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0.0, self._height() / 2))

    # --- 히트 테스트 ---

    def _get_output_port_event(self, local_pos: QPointF) -> str | None:
        events = self._output_events() or ["done"]
        n = len(events)
        hit_r = _PORT_R * 1.8
        for i, name in enumerate(events):
            y = self._output_port_y(i, n)
            dx = local_pos.x() - _W
            dy = local_pos.y() - y
            if dx * dx + dy * dy <= hit_r * hit_r:
                return name
        return None

    def is_input_port(self, local_pos: QPointF) -> bool:
        h = self._height()
        dy = local_pos.y() - h / 2
        return local_pos.x() <= _PORT_R * 2 and abs(dy) <= _PORT_R * 2

    # --- 마우스 이벤트 ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event_name = self._get_output_port_event(event.pos())
            if event_name is not None:
                self._dragging_connection = True
                self._drag_event_name = event_name
                sc: Any = self.scene()
                if sc is not None and hasattr(sc, "begin_transition_drag"):
                    sc.begin_transition_drag(self, event_name)
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
            self._drag_event_name = None
            if sc is not None and hasattr(sc, "end_transition_drag"):
                sc.end_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            if sc is not None and hasattr(sc, "handle_node_moved"):
                sc.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
