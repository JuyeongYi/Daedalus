# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.view.viewmodel.state_vm import StateViewModel

_W = 160.0
_HEADER_H = 20.0
_PORT_R = 6.0
_PORT_SPACING = 22.0
_PORT_PAD = 12.0
_LABEL_W = 44.0

_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "PROCEDURAL", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    "entry_point":       ("#1a1a3a", "#4488ff", "▶ ENTRY",     ""),
    "exit_point":        ("#2a1a1a", "#cc6666", "⏹ EXIT",      ""),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 스킬/에이전트 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None,
        show_call_agents: bool = True,
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self._input_count: int = 1
        self._ref_count: int = 0  # 하단 참조 포트 수
        self._show_call_agents = show_call_agents
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

    def _event_defs(self) -> list[EventDef]:
        """skill_ref에서 EventDef 목록 반환.

        AgentDefinition은 output_event_defs 프로퍼티를,
        ProceduralSkill은 transfer_on 필드를 사용한다.
        """
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is None:
            return []
        if hasattr(ref, "output_event_defs"):
            return list(ref.output_event_defs)  # type: ignore[union-attr]
        if hasattr(ref, "transfer_on"):
            return list(ref.transfer_on)  # type: ignore[union-attr]
        return []

    def _call_agent_defs(self) -> list[EventDef]:
        """call_agents EventDef 목록. 서브에이전트 FSM에서는 비활성."""
        if not self._show_call_agents:
            return []
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is not None and hasattr(ref, "call_agents"):
            return list(ref.call_agents)  # type: ignore[union-attr]
        return []

    def is_agent_call_event(self, event_name: str) -> bool:
        """event_name이 call_agent 포트인지 판별."""
        return any(e.name == event_name for e in self._call_agent_defs())

    def _output_events(self) -> list[str]:
        """하위 호환용 — 이벤트 이름 목록만 반환."""
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is not None and hasattr(ref, "output_events"):
            return list(ref.output_events)  # type: ignore[union-attr]
        return []

    def set_input_count(self, n: int) -> None:
        """Scene이 incoming edge 수를 알려줄 때 호출."""
        if self._input_count != n:
            self._input_count = max(1, n)
            self._sync_height()

    def set_ref_count(self, n: int) -> None:
        """하단 참조 포트 수 설정."""
        if self._ref_count != n:
            self._ref_count = n
            self.update()

    def _height(self) -> float:
        n_out = max(1, len(self._output_events())) + len(self._call_agent_defs())
        n_in = max(1, self._input_count)
        n = max(n_out, n_in)
        port_area = _PORT_SPACING * n + _PORT_PAD * 2
        return _HEADER_H + max(44.0, port_area)

    def _port_y(self, i: int, n: int) -> float:
        """i번째 포트(입력/출력 공용)의 y좌표."""
        body_h = self._height() - _HEADER_H
        spacing = body_h / (n + 1)
        return _HEADER_H + spacing * (i + 1)

    def _output_port_y(self, i: int, n: int) -> float:
        return self._port_y(i, n)

    def _is_entry_point(self) -> bool:
        return isinstance(self._state_vm.model, EntryPoint)

    def _is_exit_point(self) -> bool:
        return isinstance(self._state_vm.model, ExitPoint)

    def _sync_height(self) -> None:
        new_h = self._height()
        if self._state_vm.height != new_h:
            self.prepareGeometryChange()
            self._state_vm.height = new_h

    def update_from_model(self) -> None:
        self._sync_height()
        self.update()

    def boundingRect(self) -> QRectF:
        h = self._height()
        extra_bottom = _PORT_R * 2 if self._ref_count > 0 else 0
        return QRectF(-_PORT_R * 2 - 2, 0, _W + _PORT_R * 2 + 2 + _LABEL_W, h + extra_bottom)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        model = self._state_vm.model
        kind: str | None = None
        if isinstance(model, ExitPoint):
            bg_str, _, header_label, icon = _TYPE_STYLE["exit_point"]
            border_str = model.color
            kind = "exit_point"
        elif isinstance(model, EntryPoint):
            bg_str, border_str, header_label, icon = _TYPE_STYLE["entry_point"]
            kind = "entry_point"
        else:
            ref = model.skill_ref if hasattr(model, "skill_ref") else None  # type: ignore[union-attr]
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

        # 입력 포트 (좌측)
        if not self._is_entry_point():
            n_in = max(1, self._input_count)
            painter.setPen(QPen(QColor("#333"), 1))
            painter.setBrush(QBrush(QColor("#888")))
            for ii in range(n_in):
                iy = self._port_y(ii, n_in)
                painter.drawEllipse(QPointF(0.0, iy), _PORT_R, _PORT_R)

        # 출력 포트 — transfer_on + call_agent
        if not self._is_exit_point():
            event_defs = self._event_defs()
            if not event_defs:
                event_defs = [EventDef("done", color="#4488ff")]
            agent_defs = self._call_agent_defs()
            n_total = len(event_defs) + len(agent_defs)
            # transfer_on 포트
            for i, edef in enumerate(event_defs):
                y = self._output_port_y(i, n_total)
                port_color = QColor(edef.color)
                painter.setPen(QPen(QColor("#111"), 1))
                painter.setBrush(QBrush(port_color))
                painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
                lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W - 4, 14)
                painter.setPen(QPen(port_color.lighter(140)))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, edef.name)
            # call_agent 포트 (🤖 아이콘)
            for j, adef in enumerate(agent_defs):
                y = self._output_port_y(len(event_defs) + j, n_total)
                port_color = QColor(adef.color)
                painter.setPen(QPen(QColor("#111"), 1))
                painter.setBrush(QBrush(port_color))
                painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
                lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W + 8, 14)
                painter.setPen(QPen(port_color.lighter(140)))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, f"🤖{adef.name}")

        # 하단 참조 포트
        if self._ref_count > 0 and not self._is_entry_point() and not self._is_exit_point():
            painter.setPen(QPen(QColor("#333"), 1))
            painter.setBrush(QBrush(QColor("#66aaaa")))
            for ri in range(self._ref_count):
                rx = self._ref_port_x(ri, self._ref_count)
                painter.drawEllipse(QPointF(rx, h), _PORT_R, _PORT_R)

    def _all_output_names(self) -> list[str]:
        """transfer_on + call_agent 이벤트 이름 통합 목록."""
        names = self._output_events() or ["done"]
        names = list(names) + [e.name for e in self._call_agent_defs()]
        return names

    def output_port_scene_pos(self, event_name: str) -> QPointF:
        events = self._all_output_names()
        n = len(events)
        try:
            i = events.index(event_name)
        except ValueError:
            i = 0
        return self.mapToScene(QPointF(_W, self._output_port_y(i, n)))

    def input_port_scene_pos(self, index: int = 0) -> QPointF:
        n = max(1, self._input_count)
        return self.mapToScene(QPointF(0.0, self._port_y(index, n)))

    def _ref_port_x(self, i: int, n: int) -> float:
        """i번째 하단 참조 포트의 x좌표."""
        spacing = _W / (n + 1)
        return spacing * (i + 1)

    def ref_port_scene_pos(self, index: int = 0) -> QPointF:
        """하단 참조 포트의 씬 좌표."""
        n = max(1, self._ref_count)
        return self.mapToScene(QPointF(self._ref_port_x(index, n), self._height()))

    def is_bottom_port(self, local_pos: QPointF) -> bool:
        """local_pos가 하단 참조 포트 근처인지 판정."""
        if self._is_entry_point() or self._is_exit_point():
            return False
        h = self._height()
        if abs(local_pos.y() - h) > _PORT_R * 2:
            return False
        return 0 <= local_pos.x() <= _W

    def _get_output_port_event(self, local_pos: QPointF) -> str | None:
        if self._is_exit_point():
            return None
        events = self._all_output_names()
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
        if self._is_entry_point():
            return False
        if local_pos.x() > _PORT_R * 2:
            return False
        h = self._height()
        return _HEADER_H <= local_pos.y() <= h

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_edges_for_node"):
                sc.update_edges_for_node(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if event is None:
            return
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
        if event is None:
            return
        if self._dragging_connection:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_transition_drag"):
                sc.update_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event is None:
            return
        sc: Any = self.scene()
        if sc is not None and hasattr(sc, "handle_node_double_clicked"):
            sc.handle_node_double_clicked(self)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event is None:
            return
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
