from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from daedalus.view.canvas.draggable import DraggableItemMixin
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.commands.transition_commands import MoveWaypointCmd
from daedalus.view.viewmodel.state_vm import TransitionViewModel

_EDGE_COLOR = QColor("#6674cc")
_EDGE_SELECTED = QColor("#88aaff")
_EDGE_TRANSFER = QColor("#88aacc")   # Transfer Skill 할당 엣지
_ARROW_SIZE = 8.0
_ARROW_SPACING = 320.0   # 화살표 간격 (px)
_EDGE_WIDTH = 4.0        # 기본 두께
_EDGE_WIDTH_TRANSFER = 5.0  # Transfer Skill 할당 시 두께
_HIT_WIDTH = 12.0        # 마우스 클릭 히트 영역

# WP-ER — 경유점(waypoint) 핸들
_HANDLE_R = 5.0
_HANDLE_COLOR = QColor("#88aaff")     # 선택 엣지 색과 통일 (핸들은 엣지 선택 중에만 표시)
_HANDLE_BORDER = QColor("#222222")
_HANDLE_IDLE_OPACITY = 0.35  # 엣지 비선택 시 — 숨기면 그랩을 잃으므로 흐리게만
_SEGMENT_SAMPLES = 24  # 최근접 구간 판정용 곡선 샘플 수
_PORT_TANGENT_MIN = 60.0  # 포트 진출입 접선 최소 길이 (수평 진입 인상 유지)


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
        self._handles: list[WaypointHandleItem] = []
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

    def _route_points(self) -> list[QPointF]:
        """소스 포트 → 경유점들 → 타깃 포트 순의 경로 통과점 목록."""
        trigger = self._transition_vm.model.trigger
        event_name = trigger.name if trigger is not None else "done"

        is_agent_call = self._source_node.is_agent_call_event(event_name)
        src_pt = self._source_node.output_port_scene_pos(event_name, is_agent_call)
        target_port = self._transition_vm.model.target_port
        tgt_pt = self._target_node.input_port_scene_pos(target_port)

        waypoints = self._transition_vm.waypoints
        return [src_pt] + [QPointF(x, y) for x, y in waypoints] + [tgt_pt]

    def update_path(self) -> None:
        """출력/입력 포트 위치 기반 베지어 경로.

        WP-IC: 입력 포트 위치는 target_port(이름) 기준으로 조회한다 —
        같은 target_port를 향하는 여러 전이는 자연히 한 점에 수렴한다.

        WP-ER: transition_vm.waypoints가 있으면 소스 포트 → 경유점들 → 타깃
        포트 순으로 잇는다. 경유점이 없으면 기존 렌더와 완전히 동일하다(하위 호환).
        """
        self.prepareGeometryChange()
        points = self._route_points()

        if len(points) == 2:
            path = QPainterPath(points[0])
            self._add_curve_segment(path, points[0], points[1])
        else:
            path = self._waypoint_path(points)
        self.setPath(path)
        self._sync_handles()

    @staticmethod
    def _waypoint_path(points: list[QPointF]) -> QPainterPath:
        """경유점을 지나는 매끄러운 경로.

        포트 규칙(출력은 오른쪽으로 나가고 입력은 왼쪽으로 들어온다)은 **양 끝
        구간에만** 적용하고, 중간 경유점에서는 진행 방향 접선(Catmull-Rom)을
        쓴다. 경유점마다 포트 규칙을 적용하면 매 구간이 오른쪽으로 나갔다
        왼쪽으로 되돌아오는 S자 루프가 되어 경로가 스파게티가 된다.
        """
        n = len(points)
        tangents: list[QPointF] = []
        for i, p in enumerate(points):
            if i == 0:
                # 소스 포트 — 수평 오른쪽으로 진출
                k = max(abs(points[1].x() - p.x()) * 0.5, _PORT_TANGENT_MIN)
                tangents.append(QPointF(k, 0.0))
            elif i == n - 1:
                # 타깃 포트 — 수평 왼쪽에서 진입
                k = max(abs(p.x() - points[i - 1].x()) * 0.5, _PORT_TANGENT_MIN)
                tangents.append(QPointF(k, 0.0))
            else:
                d = points[i + 1] - points[i - 1]
                tangents.append(QPointF(d.x() * 0.5, d.y() * 0.5))

        path = QPainterPath(points[0])
        for i in range(n - 1):
            p1, p2 = points[i], points[i + 1]
            t1, t2 = tangents[i], tangents[i + 1]
            ctrl1 = QPointF(p1.x() + t1.x() / 3.0, p1.y() + t1.y() / 3.0)
            ctrl2 = QPointF(p2.x() - t2.x() / 3.0, p2.y() - t2.y() / 3.0)
            path.cubicTo(ctrl1, ctrl2, p2)
        return path

    @staticmethod
    def _add_curve_segment(path: QPainterPath, p1: QPointF, p2: QPointF) -> None:
        """p1(현재 경로 끝점)에서 p2까지 기존 스타일의 베지어 구간을 잇는다."""
        if p2.x() < p1.x():
            # 역방향 — 더 크게 휘어짐
            dx = abs(p2.x() - p1.x()) * 0.8 + 80
            ctrl1 = QPointF(p1.x() + dx, p1.y())
            ctrl2 = QPointF(p2.x() - dx, p2.y())
        else:
            dx = abs(p2.x() - p1.x()) * 0.5
            ctrl1 = QPointF(p1.x() + dx, p1.y())
            ctrl2 = QPointF(p2.x() - dx, p2.y())
        path.cubicTo(ctrl1, ctrl2, p2)

    # --- WP-ER 경유점 편집 ---

    def handle_at(self, index: int) -> "WaypointHandleItem | None":
        """index에 해당하는 경유점 핸들 아이템 반환 (WP-DM).

        scene.handle_waypoint_moved가 handle_items_moved에 위임할 때 쓴다.
        범위 밖이면 None.
        """
        if 0 <= index < len(self._handles):
            return self._handles[index]
        return None

    def nearest_segment_index(self, scene_pos: QPointF) -> int:
        """scene_pos에 가장 가까운 구간의 0-based 인덱스.

        구간 i는 route_points()[i] → route_points()[i+1]. 반환값은 그대로
        transition_vm.waypoints.insert(index, ...)에 쓸 수 있는 삽입 위치다
        (구간 i에 삽입 = waypoints[i] 앞에 삽입, 경로 순서가 보존된다).
        """
        points = self._route_points()
        best_index = 0
        best_dist: float | None = None
        for i in range(len(points) - 1):
            seg_path = QPainterPath(points[i])
            self._add_curve_segment(seg_path, points[i], points[i + 1])
            for s in range(_SEGMENT_SAMPLES + 1):
                pt = seg_path.pointAtPercent(s / _SEGMENT_SAMPLES)
                dx = pt.x() - scene_pos.x()
                dy = pt.y() - scene_pos.y()
                dist = dx * dx + dy * dy
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_index = i
        return best_index

    def update_waypoint_preview(self, index: int, pos: QPointF) -> None:
        """드래그 중 실시간 미리보기 — undo 커맨드 없이 vm에 직접 반영.

        노드 드래그 중 update_edges_for_node가 하는 역할과 동일한 결의 실시간
        갱신. 커밋(undo 가능)은 release 시 scene.handle_waypoint_moved가 한다.
        """
        waypoints = self._transition_vm.waypoints
        if 0 <= index < len(waypoints):
            waypoints[index] = (pos.x(), pos.y())
        self.update_path()

    def _sync_handles(self) -> None:
        """자식 핸들 아이템 개수·위치·표시 여부를 transition_vm.waypoints와 동기화.

        엣지가 선택된 동안에만 표시(캔버스 잡음 방지). 핸들 객체는 재사용되고
        매번 enumerate로 인덱스를 다시 매기므로, 추가/제거로 인한 순서 변화에도
        항상 올바른 위치에 정렬된다.
        """
        waypoints = self._transition_vm.waypoints
        while len(self._handles) < len(waypoints):
            handle = WaypointHandleItem(self, len(self._handles))
            handle.setParentItem(self)
            self._handles.append(handle)
        while len(self._handles) > len(waypoints):
            handle = self._handles.pop()
            handle.setParentItem(None)
            sc = handle.scene()
            if sc is not None:
                sc.removeItem(handle)

        # 핸들은 **항상 표시**하고, 엣지 비선택 시에는 흐리게만 그린다.
        # setVisible(False)로 숨기면 Qt가 마우스 그랩과 선택 가능성까지 잃는데,
        # press 시점에는 선택 상태가 아직 갱신되기 전이라 "선택됐을 때만 표시"
        # 조건으로는 이 순서 문제를 피할 수 없다 — 숨기는 순간 드래그가 죽고,
        # 우회하려 super를 건너뛰면 Qt가 드래그 기준 좌표를 잃어 다음 이동이
        # 왼쪽 위로 튄다(사용자 보고 2건이 같은 뿌리였다). 투명도는 마우스
        # 처리에 영향을 주지 않으므로 잡음만 줄이고 기능은 지킨다.
        active = self.isSelected() or any(h.isSelected() for h in self._handles)
        for i, handle in enumerate(self._handles):
            handle.set_index(i)
            pt = QPointF(*waypoints[i])
            if handle.pos() != pt:
                handle.setPos(pt)
            handle.setVisible(True)
            handle.setOpacity(1.0 if active else _HANDLE_IDLE_OPACITY)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._sync_handles()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event) -> None:
        """더블클릭 — 클릭 지점에 가장 가까운 구간에 경유점 삽입."""
        if event is None:
            return
        sc: Any = self.scene()
        if sc is not None and hasattr(sc, "handle_edge_double_clicked"):
            sc.handle_edge_double_clicked(self, event.scenePos())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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


class WaypointHandleItem(DraggableItemMixin, QGraphicsEllipseItem):
    """엣지 경유점(waypoint) 편집 핸들 — 소유 엣지가 선택된 동안에만 표시.

    TransitionEdgeItem의 자식 아이템(setParentItem)으로, 엣지 자신은 절대
    이동하지 않으므로(pos()가 항상 원점) 자식 로컬 좌표 == 씬 좌표다.
    드래그는 Qt 기본 ItemIsMovable로 처리하고, itemChange로 실시간 미리보기를
    반영하며, release 시 scene.handle_items_moved(WP-DM)로 undo 가능한 커맨드를
    커밋한다(TransitionEdgeItem/ReferenceNodeItem 드래그 관례와 동일).
    """

    def __init__(self, edge: TransitionEdgeItem, index: int) -> None:
        super().__init__(-_HANDLE_R, -_HANDLE_R, _HANDLE_R * 2, _HANDLE_R * 2)
        self._edge = edge
        self._index = index
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(2)
        self.setBrush(QBrush(_HANDLE_COLOR))
        self.setPen(QPen(_HANDLE_BORDER, 1))
        self.setVisible(False)

    @property
    def edge(self) -> TransitionEdgeItem:
        return self._edge

    @property
    def index(self) -> int:
        return self._index

    def set_index(self, index: int) -> None:
        self._index = index

    def vm_position(self) -> QPointF:
        """WP-DM — DraggableItemMixin 구현. 인덱스가 범위 밖이면(방어) pos() 반환."""
        waypoints = self._edge.transition_vm.waypoints
        if 0 <= self._index < len(waypoints):
            return QPointF(*waypoints[self._index])
        return self.pos()

    def make_move_command(self, old: QPointF, new: QPointF) -> MoveWaypointCmd:
        """WP-DM — DraggableItemMixin 구현."""
        return MoveWaypointCmd(
            self._edge.transition_vm, self._index,
            old_x=old.x(), old_y=old.y(),
            new_x=new.x(), new_y=new.y(),
        )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # update_waypoint_preview → update_path → _sync_handles의 setPos가
            # 이 itemChange로 되돌아오는 재진입은 좌표 수렴으로 2단계에서 멈춘다
            # (의도된 설계 — 리뷰 확인).
            self._edge.update_waypoint_preview(self._index, self.pos())
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # 핸들 선택 변화도 표시 조건에 반영 — 엣지 선택이 풀린 뒤에도
            # 선택된 핸들은 남아야 드래그·Delete 대상이 유지된다.
            self._edge._sync_handles()
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        if event is None:
            return
        # super를 반드시 호출한다 — Qt가 여기서 드래그 기준 좌표를 기록하므로,
        # 우회하면 다음 이동이 스테일 오프셋으로 계산돼 아이템이 화면 왼쪽 위로
        # 튄다(사용자 보고). 선택이 풀려도 _sync_handles가 "핸들 자신이 선택됨"
        # 조건으로 핸들을 계속 표시하므로 그랩은 유지된다.
        self.begin_drag()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event is None:
            return
        super().mouseReleaseEvent(event)
        self.end_drag()
