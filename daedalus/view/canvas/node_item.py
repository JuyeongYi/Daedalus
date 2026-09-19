# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from functools import singledispatch

from daedalus.model.fsm.pseudo import (
    ENTRY_POINT_KIND,
    EXIT_POINT_KIND,
    ExitPoint,
)
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

#: **의사 상태(pseudo state)와 빈 노드**의 스타일 — 컴포넌트 종류가 아니다.
#: 종류별 스타일은 `view/kind_ui.KIND_UI`의 `node_style`이 소유한다(WP-7 ②) —
#: 예전에는 두 사실이 한 dict에 섞여 있어 새 종류가 빠져도 **빈 노드와 구분되지
#: 않는 기본 스타일**로 조용히 그려졌다(랩핑 스킬 회귀, 사용자 보고 2026-09-07).
#: 키는 **상태의 `kind`**다 — 모델이 스스로 말하는 종류 식별자라 뷰가 클래스를
#: 열거할 필요가 없다(WP-11: `isinstance(model, ExitPoint)` 사다리 소멸).
_PSEUDO_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    ENTRY_POINT_KIND:    ("#1a1a3a", "#4488ff", "▶ ENTRY",     ""),
    EXIT_POINT_KIND:     ("#2a1a1a", "#cc6666", "⏹ EXIT",      ""),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}


@singledispatch
def _pseudo_border(model: object, fallback: str) -> str:
    """의사 상태의 외곽선 색 — 색을 **모델이 들고 있는** 종류만 표를 덮어쓴다.

    폴백(표의 색)이 옳다: 색 필드가 없는 종류는 표가 정한 색으로 그린다.
    """
    return fallback


@_pseudo_border.register(ExitPoint)
def _(model: ExitPoint, fallback: str) -> str:
    # v1 출력 포트 표지의 잔재 — 포트 색을 사용자가 정할 수 있었다.
    return model.color

# 유저 발동 진입점(user_invocable 명시 true — 🚪 뱃지와 같은 기준)의 테두리 색.
# 종류 색(배경·헤더 글자)은 그대로 두고 **외곽선만** 바꾼다 — "어디서 사용자가
# 시작할 수 있는가"를 캔버스 전체에서 한눈에 찾게 한다(사용자 요청 2026-09-12).
_USER_ENTRY_BORDER = "#e0b030"


def node_border_color(model: object, kind_border: str) -> str:
    """노드 외곽선 색 — 유저 발동 진입점이면 전용 색, 아니면 종류 색."""
    from daedalus.view.actions.entrypoint import is_user_entry

    ref = getattr(model, "skill_ref", None)
    if ref is not None and is_user_entry(ref):
        return _USER_ENTRY_BORDER
    return kind_border


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
        """skill_ref의 **출력 포트** EventDef 목록 (WP-2d).

        종류마다 다른 속성(`output_event_defs` / `transfer_on`)을 `hasattr`로
        더듬던 자리다. 그러면 포트를 다른 이름으로 노출하는 종류가 생길 때
        캔버스에서 **포트 없는 노드**로 조용히 그려진다 — 이제 컴포넌트가
        선언한 `output_ports()` 하나만 묻는다(기본 구현은 빈 목록).
        """
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is None:
            return []
        return ref.output_ports()

    def _call_agent_defs(self) -> list[EventDef]:
        """call_agents EventDef 목록. 서브에이전트 FSM에서는 비활성."""
        if not self._show_call_agents:
            return []
        model = self._state_vm.model
        if not hasattr(model, "skill_ref"):
            return []
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is None:
            return []
        return ref.call_ports()

    def is_agent_call_event(self, event_name: str) -> bool:
        """event_name이 call_agent 포트인지 판별."""
        return any(e.name == event_name for e in self._call_agent_defs())

    def _output_events(self) -> list[str]:
        """출력 포트 이름 목록 — 높이 계산·포트 라벨 렌더가 쓴다.

        EventDef가 필요하면 `_event_defs()`를 쓴다 — 같은 `output_ports()`를
        본다(이름만 뽑는 자리와 정의가 필요한 자리가 서로 다른 답을 하면
        포트 수와 라벨이 어긋난다).
        """
        return [e.name for e in self._event_defs()]

    def set_ref_count(self, n: int) -> None:
        """하단 참조 포트 수 설정."""
        if self._ref_count != n:
            self._ref_count = n
            self.update()

    def _height(self) -> float:
        # 입력 포트는 항상 1개(WP-IP)이므로 출력 포트 수가 높이를 결정한다.
        n = max(1, len(self._output_events())) + len(self._call_agent_defs())
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
        return self._state_vm.model.kind == ENTRY_POINT_KIND

    def _is_exit_point(self) -> bool:
        return self._state_vm.model.kind == EXIT_POINT_KIND

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
        pseudo = _PSEUDO_STYLE.get(model.kind)
        if pseudo is not None:
            bg_str, border_str, header_label, icon = pseudo
            border_str = _pseudo_border(model, border_str)
        else:
            # 종류 스타일의 단일 진실은 `KIND_UI[kind].node_style`이다 — 상태
            # 노드가 아닌 종류(전이·참조·fork 에이전트)는 None이고, 그때만 빈
            # 노드와 같은 기본 스타일로 그린다.
            from daedalus.view.kind_ui import ui_for

            ref = model.skill_ref if hasattr(model, "skill_ref") else None  # type: ignore[union-attr]
            style = ui_for(ref).node_style if ref is not None else None
            bg_str, border_str, header_label, icon = style or _PSEUDO_STYLE[None]
        border_color = QColor(border_str)
        outline = QColor(node_border_color(model, border_str))
        active_border = outline.lighter(160) if self.isSelected() else outline

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

        # 입력 포트 (좌측) — 노드당 1개 고정 (WP-IP). (출처, 트리거)가 경로를
        # 특정하므로 도착 노드가 입력 포트를 이름으로 가르지 않는다.
        if not self._is_entry_point():
            iy = self._port_y(0, 1)
            painter.setPen(QPen(QColor("#333"), 1))
            painter.setBrush(QBrush(QColor("#888")))
            painter.drawEllipse(QPointF(0.0, iy), _PORT_R, _PORT_R)

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

    def input_port_scene_pos(self) -> QPointF:
        """입력 포트(노드당 1개, WP-IP) 위치 — 들어오는 모든 전이가 여기 수렴한다."""
        return self.mapToScene(QPointF(0.0, self._port_y(0, 1)))

    def _ref_port_x(self, i: int, n: int) -> float:
        """i번째 하단 참조 포트의 x좌표."""
        spacing = _W / (n + 1)
        return spacing * (i + 1)

    def ref_port_scene_pos(self, index: int = 0) -> QPointF:
        """하단 참조 포트의 씬 좌표."""
        n = max(1, self._ref_count)
        return self.mapToScene(QPointF(self._ref_port_x(index, n), self._height()))

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
            if sc is not None and hasattr(sc, "end_transition_drag"):
                sc.end_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.end_drag()
