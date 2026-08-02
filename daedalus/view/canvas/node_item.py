# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.view.canvas.draggable import DraggableItemMixin
from daedalus.view.canvas.node_badges import badges_for, state_access_badges
from daedalus.view.commands.state_commands import MoveStateCmd
from daedalus.view.viewmodel.state_vm import StateViewModel

_W = 160.0
_HEADER_H = 20.0
_PORT_R = 6.0
_PORT_SPACING = 22.0
_PORT_PAD = 12.0

_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    # 헤더 라벨 "PROCEDURAL"은 형용사라 어색 — 배치는 플러그인 FSM의 상태이므로
    # STATE로 표기 (사용자 확정). 종류 구분은 색·아이콘이 담당.
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "STATE", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    "team_spawn":        ("#1a1a2a", "#7755aa", "DELEGATION",  "👥"),
    "dynamic_workflow":  ("#1a2a2a", "#4a88aa", "DELEGATION",  "🔀"),
    "agora_dispatch":    ("#1a1a2a", "#aa7744", "DELEGATION",  "🛰"),
    "entry_point":       ("#1a1a3a", "#4488ff", "▶ ENTRY",     ""),
    "exit_point":        ("#2a1a1a", "#cc6666", "⏹ EXIT",      ""),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}


class StateNodeItem(DraggableItemMixin, QGraphicsItem):
    """캔버스 위의 스킬/에이전트 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None,
        show_call_agents: bool = True,
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self._ref_count: int = 0  # 하단 참조 포트 수
        self._show_call_agents = show_call_agents
        self.setPos(state_vm.x, state_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._dragging_connection = False
        self._drag_event_name: str | None = None
        self._sync_height()

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    def vm_position(self) -> QPointF:
        """WP-DM — DraggableItemMixin 구현."""
        return QPointF(self._state_vm.x, self._state_vm.y)

    def make_move_command(self, old: QPointF, new: QPointF) -> MoveStateCmd:
        """WP-DM — DraggableItemMixin 구현."""
        return MoveStateCmd(
            self._state_vm,
            old_x=old.x(), old_y=old.y(),
            new_x=new.x(), new_y=new.y(),
        )

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

    def _input_event_defs(self) -> list[EventDef]:
        """WP-IC — skill_ref.entry_paths에서 EventDef 목록 반환.

        빈 리스트 = 기본 포트 1개(암묵, 이름 없음) — 기존 렌더와 호환.
        """
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is None:
            return []
        if hasattr(ref, "entry_paths"):
            return list(ref.entry_paths)  # type: ignore[union-attr]
        return []

    def set_ref_count(self, n: int) -> None:
        """하단 참조 포트 수 설정."""
        if self._ref_count != n:
            self._ref_count = n
            self.update()

    def _height(self) -> float:
        n_out = max(1, len(self._output_events())) + len(self._call_agent_defs())
        n_in = max(1, len(self._input_event_defs()))
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
        return QRectF(-_PORT_R * 2 - 2, 0, _W + _PORT_R * 4, h + extra_bottom)

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

        # 이름 — 헤더 바로 아래, 상단 가운데
        name_rect = QRectF(4, _HEADER_H + 2, _W - 8, 20)
        text_color = QColor("#eee") if self.isSelected() else QColor("#ccc")
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 11)
        if self.isSelected():
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._state_vm.model.name)

        # 뱃지 행 (프론트매터 enum/bool 시각화 + WP-BB 상태 접근 선언)
        ref_for_badge = model.skill_ref if hasattr(model, "skill_ref") else model  # type: ignore[union-attr]
        badge_list = badges_for(ref_for_badge) + state_access_badges(model)
        if badge_list:
            badge_text = " ".join(emoji for emoji, _ in badge_list)
            badge_rect = QRectF(4, _HEADER_H + 22, _W - 8, 16)
            painter.setPen(QPen(QColor("#ddaa44")))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, badge_text)
        # 뱃지가 전부 사라진 노드의 잔존 툴팁도 함께 갱신
        self.setToolTip("\n".join(f"{emoji} {tip}" for emoji, tip in badge_list))

        # 입력 포트 (좌측) — WP-IC: entry_paths 기반, 라벨은 출력 포트와 대칭
        # (포트 오른쪽·본체 안, 좌측 정렬, EventDef.color 사용).
        if not self._is_entry_point():
            in_defs = self._input_event_defs()
            n_in = max(1, len(in_defs))
            for ii in range(n_in):
                iy = self._port_y(ii, n_in)
                port_color = QColor(in_defs[ii].color) if in_defs else QColor("#888")
                painter.setPen(QPen(QColor("#333"), 1))
                painter.setBrush(QBrush(port_color))
                painter.drawEllipse(QPointF(0.0, iy), _PORT_R, _PORT_R)
                if in_defs:
                    lbl_rect = QRectF(_PORT_R + 6, iy - 7, _W - _PORT_R - 10, 14)
                    painter.setPen(QPen(port_color.lighter(140)))
                    painter.setFont(QFont("Segoe UI", 7))
                    painter.drawText(
                        lbl_rect,
                        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                        in_defs[ii].name,
                    )

        # 출력 포트 — transfer_on + call_agent
        if not self._is_exit_point():
            event_defs = self._event_defs()
            if not event_defs:
                event_defs = [EventDef("done", color="#4488ff")]
            agent_defs = self._call_agent_defs()
            n_total = len(event_defs) + len(agent_defs)
            # transfer_on 포트 — 라벨은 포트 왼쪽(본체 안), 우측 정렬
            for i, edef in enumerate(event_defs):
                y = self._output_port_y(i, n_total)
                port_color = QColor(edef.color)
                painter.setPen(QPen(QColor("#111"), 1))
                painter.setBrush(QBrush(port_color))
                painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
                lbl_rect = QRectF(4, y - 7, _W - _PORT_R - 6, 14)
                painter.setPen(QPen(port_color.lighter(140)))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, edef.name)
            # call_agent 포트 — 라벨은 포트 왼쪽(본체 안), 우측 정렬
            for j, adef in enumerate(agent_defs):
                y = self._output_port_y(len(event_defs) + j, n_total)
                port_color = QColor(adef.color)
                painter.setPen(QPen(QColor("#111"), 1))
                painter.setBrush(QBrush(port_color))
                painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
                lbl_rect = QRectF(4, y - 7, _W - _PORT_R - 6, 14)
                painter.setPen(QPen(port_color.lighter(140)))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"🤖 {adef.name}")

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

    def output_port_index(self, event_name: str, is_agent_call: bool = False) -> int:
        """이벤트 이름 + agent_call 여부로 정확한 포트 인덱스 반환."""
        events = self._output_events() or ["done"]
        if is_agent_call:
            agent_names = [e.name for e in self._call_agent_defs()]
            try:
                j = agent_names.index(event_name)
            except ValueError:
                j = 0
            return len(events) + j
        try:
            return events.index(event_name)
        except ValueError:
            return 0

    def output_port_scene_pos(self, event_name: str, is_agent_call: bool = False) -> QPointF:
        n = len(self._all_output_names())
        i = self.output_port_index(event_name, is_agent_call)
        return self.mapToScene(QPointF(_W, self._output_port_y(i, n)))

    def input_port_index(self, port_name: str = "") -> int:
        """WP-IC — port_name → entry_paths 인덱스.

        target_port가 빈 값이거나 entry_paths에 없는 이름이면 기본(첫) 포트(0).
        """
        paths = self._input_event_defs()
        if not paths or not port_name:
            return 0
        names = [p.name for p in paths]
        try:
            return names.index(port_name)
        except ValueError:
            return 0

    def input_port_scene_pos(self, port_name: str = "") -> QPointF:
        """WP-IC — 이름으로 입력 포트 위치 조회. 같은 port_name은 같은 점에 수렴한다."""
        n = max(1, len(self._input_event_defs()))
        i = self.input_port_index(port_name)
        return self.mapToScene(QPointF(0.0, self._port_y(i, n)))

    def nearest_input_port_name(self, local_pos: QPointF) -> str:
        """WP-IC — 드롭 지점(local 좌표)에서 가장 가까운 입력 포트 이름으로 스냅.

        선언된 entry_paths가 없으면 빈 값(기본 포트, 하위 호환). 선언이 1개라도
        있으면 그 이름을 기록한다 — 1개 선언이 no-op이 되지 않게 (리뷰 지적 d).
        """
        paths = self._input_event_defs()
        if not paths:
            return ""
        n = len(paths)
        best_i = 0
        best_dist: float | None = None
        for i in range(n):
            y = self._port_y(i, n)
            dist = abs(local_pos.y() - y)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_i = i
        return paths[best_i].name

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

    def _get_output_port_event(self, local_pos: QPointF) -> tuple[str, bool] | None:
        """클릭 위치에 해당하는 (event_name, is_agent_call) 반환."""
        if self._is_exit_point():
            return None
        events = self._all_output_names()
        n_transfer = len(self._output_events() or ["done"])
        n = len(events)
        hit_r = _PORT_R * 2.0
        for i, name in enumerate(events):
            y = self._output_port_y(i, n)
            dx = local_pos.x() - _W
            dy = local_pos.y() - y
            if dx * dx + dy * dy <= hit_r * hit_r:
                return (name, i >= n_transfer)
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
            hit = self._get_output_port_event(event.pos())
            if hit is not None:
                event_name, is_agent_call = hit
                self._dragging_connection = True
                self._drag_event_name = event_name
                sc: Any = self.scene()
                if sc is not None and hasattr(sc, "begin_transition_drag"):
                    sc.begin_transition_drag(self, event_name, is_agent_call)
                event.accept()
                return
        self.begin_drag()
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
        self.end_drag()
