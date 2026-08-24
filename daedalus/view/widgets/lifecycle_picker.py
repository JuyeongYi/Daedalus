# daedalus/view/widgets/lifecycle_picker.py
"""훅 이벤트 라이프사이클 피커 — QGraphicsScene 네이티브 (A10).

이벤트가 31종이라 콤보에서 고르면 "이게 언제 도는 건데?"를 알 수 없다. CC 훅
라이프사이클 다이어그램을 그대로 보여 주고 **박스를 클릭해 고르게** 한다.

**SVG를 렌더하지 않는다.** 원본(`hooks-lifecycle-dark.svg`)의 좌표·색을 아래
`_LAYOUT` 테이블로 옮겼다 — 그래야 박스마다 hover·클릭·툴팁·현재 선택 강조를
붙일 수 있고, 이벤트가 늘거나 줄면 **테스트가 깨져 갱신을 강제**한다
(`_LAYOUT` 키 집합 == `set(HookEvent)`).

원본 다이어그램에서 **한 박스에 두세 이벤트가 묶여 있던 것들**
(`PostToolUse / PostToolUseFailure` 등)은 여기서 이벤트별로 쪼갰다 — 전체
footprint와 색은 그대로 두되, 클릭 대상이 하나의 이벤트로 정해져야 하기
때문이다. 묶여 있으면 어느 쪽을 고른 것인지 정할 수 없다.

**재사용 위젯이다.** 훅 패널의 버튼은 이 다이얼로그를 열고 결과를 콤보에
반영하는 호출부일 뿐이고, 이벤트를 고르는 다른 표면이 생기면 같은 것을 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
)

from daedalus.model.plugin.hook import (
    NO_MATCHER_EVENTS,
    UNDOCUMENTED_EVENTS,
    HookEvent,
)

# ─────────────────────── 팔레트 (SVG 원본 그대로) ───────────────────────

BACKGROUND = "#1A1A1A"
_ARROW = "#C4C4C4"

#: (채움, 테두리) — 박스 그룹별 색.
_STYLE_START = ("#336448", "#8FBF97")     # SessionStart
_STYLE_PLAIN = ("#3C3C3C", "#505050")     # 루프 밖 주 흐름
_STYLE_LOOP = ("#5A4E22", "#D4A27F")      # AGENTIC LOOP 안
_STYLE_STOP = ("#5C3232", "#E0A0A0")      # Stop 계열
_STYLE_SIDE = ("#1A1A1A", "#757575")      # 좌측 사이드(점선)
_STYLE_TOOL = ("#6AABD2", "#4A8DB8")      # [tool executes] — 장식, 클릭 불가

_GROUP_TURN = "#4A8DB8"
_GROUP_LOOP = "#D4A27F"

CANVAS_W = 520
CANVAS_H = 1228


@dataclass(frozen=True)
class _Box:
    """이벤트 하나의 박스 — SVG 좌표 그대로."""

    x: float
    y: float
    w: float
    h: float
    label: str
    style: tuple[str, str]
    #: 좌측 사이드 박스는 점선 테두리 + 작은 글씨.
    dashed: bool = False
    #: 부제(원본의 회색 두 번째 줄).
    subtitle: str = ""

    @property
    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.w, self.h)


#: 이벤트 → 박스. **키 집합이 HookEvent 전체와 정확히 일치해야 한다**
#: (`tests/view/widgets/test_lifecycle_picker.py`가 고정 — 이벤트가 늘거나
#: 줄면 그 테스트가 깨져 다이어그램 갱신을 강제한다).
_LAYOUT: dict[HookEvent, _Box] = {
    # 좌측 사이드 (opt-in / async / 환경 반응)
    HookEvent.SETUP: _Box(15, 25, 115, 42, "Setup", _STYLE_SIDE, True, "(Opt-in)"),
    HookEvent.USER_PROMPT_EXPANSION: _Box(
        15, 98, 127, 42, "UserPromptExpansion", _STYLE_SIDE, True, "(slash commands)",
    ),
    HookEvent.PERMISSION_DENIED: _Box(
        15, 283, 115, 42, "PermissionDenied", _STYLE_SIDE, True, "(auto-mode deny)",
    ),
    HookEvent.ELICITATION: _Box(
        15, 332, 115, 42, "Elicitation", _STYLE_SIDE, True, "(MCP input)",
    ),
    HookEvent.ELICITATION_RESULT: _Box(
        15, 380, 115, 42, "ElicitationResult", _STYLE_SIDE, True, "(MCP input)",
    ),
    HookEvent.NOTIFICATION: _Box(
        15, 818, 115, 42, "Notification", _STYLE_SIDE, True, "(Async)",
    ),
    HookEvent.CONFIG_CHANGE: _Box(
        15, 872, 115, 42, "ConfigChange", _STYLE_SIDE, True, "(Async)",
    ),
    HookEvent.WORKTREE_CREATE: _Box(
        15, 926, 115, 42, "WorktreeCreate", _STYLE_SIDE, True, "(Isolation)",
    ),
    HookEvent.WORKTREE_REMOVE: _Box(
        15, 980, 115, 42, "WorktreeRemove", _STYLE_SIDE, True, "(Teardown)",
    ),
    # 원본이 한 박스에 세 줄로 묶어 둔 환경 반응 3종 — 이벤트별로 쪼갠다.
    HookEvent.CWD_CHANGED: _Box(15, 1034, 115, 18, "CwdChanged", _STYLE_SIDE, True),
    HookEvent.FILE_CHANGED: _Box(15, 1052, 115, 18, "FileChanged", _STYLE_SIDE, True),
    HookEvent.DIRECTORY_ADDED: _Box(
        15, 1070, 115, 18, "DirectoryAdded", _STYLE_SIDE, True,
    ),
    HookEvent.INSTRUCTIONS_LOADED: _Box(
        15, 1107, 115, 42, "InstructionsLoaded", _STYLE_SIDE, True, "(Async)",
    ),
    HookEvent.MESSAGE_DISPLAY: _Box(
        15, 1161, 115, 42, "MessageDisplay", _STYLE_SIDE, True, "(Display)",
    ),
    # 주 흐름 세로 열
    HookEvent.SESSION_START: _Box(160, 25, 190, 42, "SessionStart", _STYLE_START),
    HookEvent.USER_PROMPT_SUBMIT: _Box(
        160, 98, 190, 42, "UserPromptSubmit", _STYLE_PLAIN,
    ),
    HookEvent.PRE_TOOL_USE: _Box(160, 210, 190, 42, "PreToolUse", _STYLE_LOOP),
    HookEvent.PERMISSION_REQUEST: _Box(
        160, 283, 190, 42, "PermissionRequest", _STYLE_LOOP,
    ),
    # 원본 "PostToolUse / PostToolUseFailure" 한 박스(x=110 w=290)를 반씩.
    HookEvent.POST_TOOL_USE: _Box(110, 429, 145, 42, "PostToolUse", _STYLE_LOOP),
    HookEvent.POST_TOOL_USE_FAILURE: _Box(
        255, 429, 145, 42, "PostToolUseFailure", _STYLE_LOOP,
    ),
    HookEvent.POST_TOOL_BATCH: _Box(160, 502, 190, 42, "PostToolBatch", _STYLE_LOOP),
    # 원본 "SubagentStart / SubagentStop" 한 박스(x=115 w=280)를 반씩.
    HookEvent.SUBAGENT_START: _Box(115, 575, 140, 42, "SubagentStart", _STYLE_LOOP),
    HookEvent.SUBAGENT_STOP: _Box(255, 575, 140, 42, "SubagentStop", _STYLE_LOOP),
    HookEvent.TASK_CREATED: _Box(160, 648, 190, 42, "TaskCreated", _STYLE_LOOP),
    HookEvent.TASK_COMPLETED: _Box(160, 721, 190, 42, "TaskCompleted", _STYLE_LOOP),
    # 원본 "Stop / StopFailure" 한 박스(x=160 w=190)를 반씩.
    HookEvent.STOP: _Box(160, 810, 95, 42, "Stop", _STYLE_STOP),
    HookEvent.STOP_FAILURE: _Box(255, 810, 95, 42, "StopFailure", _STYLE_STOP),
    HookEvent.TEAMMATE_IDLE: _Box(160, 883, 190, 42, "TeammateIdle", _STYLE_PLAIN),
    HookEvent.PRE_COMPACT: _Box(160, 956, 190, 42, "PreCompact", _STYLE_PLAIN),
    HookEvent.POST_COMPACT: _Box(160, 1029, 190, 42, "PostCompact", _STYLE_PLAIN),
    HookEvent.SESSION_END: _Box(160, 1102, 190, 42, "SessionEnd", _STYLE_PLAIN),
}

#: 그룹 테두리 — (rect, 색, 라벨 줄들, 라벨 좌상단).
_GROUPS: tuple[tuple[QRectF, str, tuple[str, ...], tuple[float, float]], ...] = (
    (QRectF(44, 88, 420, 775), _GROUP_TURN, ("EACH", "TURN"), (69, 772)),
    (QRectF(60, 158, 380, 610), _GROUP_LOOP, ("AGENTIC", "LOOP"), (85, 172)),
)

#: 이벤트가 아닌 장식 박스 — 클릭 불가.
_TOOL_BOX = _Box(160, 356, 190, 42, "[tool executes]", _STYLE_TOOL)

#: 주 흐름 세로 화살표 — (x, y1, y2).
_FLOW_ARROWS: tuple[tuple[float, float, float], ...] = (
    (255, 67, 96), (255, 140, 182), (255, 252, 281), (255, 325, 354),
    (255, 398, 427), (255, 471, 500), (255, 544, 573), (255, 617, 646),
    (255, 690, 719), (255, 763, 808), (255, 852, 881), (255, 925, 954),
    (255, 998, 1027), (255, 1071, 1100),
)

#: 피드백 루프 — (꺾은선 점들, 색, 점선 여부, 라벨/라벨 위치).
_FEEDBACK: tuple[tuple[tuple[tuple[float, float], ...], str, bool, str, tuple[float, float]], ...] = (
    (((350, 742), (410, 742), (410, 231), (362, 231)), _GROUP_LOOP, False, "", (0, 0)),
    (((350, 831), (450, 831), (450, 119), (362, 119)), _GROUP_TURN, False, "", (0, 0)),
    (
        ((350, 1123), (475, 1123), (475, 46), (362, 46)),
        "#E0E0E0", True, "resumed sessions", (483, 556),
    ),
)

#: 좌측 사이드 박스 → 주 흐름을 잇는 짧은 점선 (x1,y1,x2,y2, 화살표가 왼쪽인가).
_SIDE_LINKS: tuple[tuple[float, float, float, float, bool], ...] = (
    (130, 46, 160, 46, False),     # Setup → SessionStart
    (160, 119, 138, 119, True),    # UserPromptSubmit → UserPromptExpansion
    (160, 304, 126, 304, True),    # PermissionRequest → PermissionDenied
    (130, 377, 160, 377, False),   # Elicitation → [tool executes]
)


def event_tooltip(event: HookEvent) -> str:
    """박스 툴팁 — 이벤트 값 + matcher 지원 여부 + 문서화 여부.

    matcher를 받지 않는 이벤트에 matcher를 넣어 두면 설정한 사람은 걸린 줄
    알지만 CC는 무시한다 — 고르는 자리에서 미리 알린다.
    """
    lines = [event.value]
    if event in NO_MATCHER_EVENTS:
        lines.append("matcher 없음 — 이 이벤트는 matcher를 받지 않습니다")
    else:
        lines.append("matcher 지원")
    if event in UNDOCUMENTED_EVENTS:
        lines.append("공식 문서에 없음 (스키마에만 존재)")
    return "\n".join(lines)


class _EventBoxItem(QGraphicsItem):
    """클릭 가능한 이벤트 박스."""

    def __init__(self, event: HookEvent, box: _Box, is_current: bool) -> None:
        super().__init__()
        self._event = event
        self._box = box
        self._current = is_current
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(event_tooltip(event))

    @property
    def event_value(self) -> HookEvent:
        return self._event

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt override)
        return QRectF(0, 0, self._box.w, self._box.h)

    def paint(self, painter, option, widget=None) -> None:  # noqa: D102
        fill, border = self._box.style
        pen = QPen(QColor(border))
        # 현재 선택은 굵은 테두리, hover는 밝은 테두리 — 둘 다면 굵고 밝게.
        pen.setWidth(3 if self._current else (2 if self._hover else 1))
        if self._hover:
            pen.setColor(QColor("#FFFFFF"))
        if self._box.dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(fill)))
        painter.drawRoundedRect(self.boundingRect(), 6, 6)

        small = self._box.dashed
        font = QFont()
        font.setPointSize(8 if small else 9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#C4C4C4" if small else "#F5F5F5")))
        if self._box.subtitle:
            rect = self.boundingRect()
            top = QRectF(rect.x(), rect.y(), rect.width(), rect.height() * 0.6)
            bottom = QRectF(
                rect.x(), rect.y() + rect.height() * 0.55,
                rect.width(), rect.height() * 0.45,
            )
            painter.drawText(top, Qt.AlignmentFlag.AlignCenter, self._box.label)
            sub = QFont()
            sub.setPointSize(7)
            painter.setFont(sub)
            painter.setPen(QPen(QColor("#9A9A9A")))
            painter.drawText(bottom, Qt.AlignmentFlag.AlignCenter, self._box.subtitle)
        else:
            painter.drawText(
                self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self._box.label,
            )

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        scene = self.scene()
        if scene is not None and hasattr(scene, "pick"):
            scene.pick(self._event)
        event.accept()


class HookLifecycleScene(QGraphicsScene):
    """다이어그램 씬 — 박스 클릭 시 `picked`를 발화한다."""

    picked = Signal(object)  # HookEvent

    def __init__(self, current: HookEvent | None = None) -> None:
        super().__init__()
        self.setSceneRect(0, 0, CANVAS_W, CANVAS_H)
        self.setBackgroundBrush(QBrush(QColor(BACKGROUND)))
        self._items: dict[HookEvent, _EventBoxItem] = {}
        self._draw_groups()
        self._draw_arrows()
        self._draw_decoration()
        self._draw_events(current)

    # --- 조회 (테스트/호출부) ---

    def item_for(self, event: HookEvent) -> _EventBoxItem | None:
        return self._items.get(event)

    def pick(self, event: HookEvent) -> None:
        self.picked.emit(event)

    # --- 렌더 ---

    def _draw_groups(self) -> None:
        for rect, color, label_lines, (lx, ly) in _GROUPS:
            pen = QPen(QColor(color))
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            self.addRect(rect, pen)
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            for i, line in enumerate(label_lines):
                text = self.addText(line, font)
                text.setDefaultTextColor(QColor(color))
                text.setPos(lx, ly + i * 15)

    def _draw_arrows(self) -> None:
        pen = QPen(QColor(_ARROW))
        pen.setWidth(2)
        for x, y1, y2 in _FLOW_ARROWS:
            self.addLine(x, y1, x, y2 - 12, pen)
            self._arrow_head(x, y2, _ARROW)

        for points, color, dashed, label, (lx, ly) in _FEEDBACK:
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            fpen = QPen(QColor(color))
            fpen.setWidth(2)
            if dashed:
                fpen.setStyle(Qt.PenStyle.DashLine)
            self.addPath(path, fpen)
            # 마지막 구간은 왼쪽으로 향한다 — 화살촉도 왼쪽.
            end = points[-1]
            self._arrow_head_left(end[0] - 12, end[1], color)
            if label:
                font = QFont()
                font.setPointSize(8)
                text = self.addText(label, font)
                text.setDefaultTextColor(QColor("#C4C4C4"))
                text.setPos(lx, ly)

        side_pen = QPen(QColor("#757575"))
        side_pen.setWidth(1)
        side_pen.setStyle(Qt.PenStyle.DashLine)
        for x1, y1, x2, y2, points_left in _SIDE_LINKS:
            self.addLine(x1, y1, x2, y2, side_pen)
            if points_left:
                self._arrow_head_left(x2, y2, "#757575")
            else:
                self._arrow_head_right(x2, y2, "#757575")

    def _arrow_head(self, x: float, y: float, color: str) -> None:
        poly = QPolygonF([
            _pt(x - 7, y - 12), _pt(x, y), _pt(x + 7, y - 12),
        ])
        self.addPolygon(poly, QPen(Qt.PenStyle.NoPen), QBrush(QColor(color)))

    def _arrow_head_left(self, x: float, y: float, color: str) -> None:
        poly = QPolygonF([_pt(x + 12, y - 7), _pt(x, y), _pt(x + 12, y + 7)])
        self.addPolygon(poly, QPen(Qt.PenStyle.NoPen), QBrush(QColor(color)))

    def _arrow_head_right(self, x: float, y: float, color: str) -> None:
        poly = QPolygonF([_pt(x - 12, y - 7), _pt(x, y), _pt(x - 12, y + 7)])
        self.addPolygon(poly, QPen(Qt.PenStyle.NoPen), QBrush(QColor(color)))

    def _draw_decoration(self) -> None:
        """[tool executes] — 이벤트가 아니라 장식이다(클릭 불가)."""
        fill, border = _TOOL_BOX.style
        pen = QPen(QColor(border))
        pen.setWidth(1)
        self.addRect(_TOOL_BOX.rect, pen, QBrush(QColor(fill)))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        text = self.addText(_TOOL_BOX.label, font)
        text.setDefaultTextColor(QColor("#2C2C2C"))
        bounds = text.boundingRect()
        text.setPos(
            _TOOL_BOX.x + (_TOOL_BOX.w - bounds.width()) / 2,
            _TOOL_BOX.y + (_TOOL_BOX.h - bounds.height()) / 2,
        )

    def _draw_events(self, current: HookEvent | None) -> None:
        for event, box in _LAYOUT.items():
            item = _EventBoxItem(event, box, event is current)
            item.setPos(box.x, box.y)
            self.addItem(item)
            self._items[event] = item


def _pt(x: float, y: float):
    from PySide6.QtCore import QPointF

    return QPointF(x, y)


class HookLifecycleDialog(QDialog):
    """라이프사이클에서 이벤트를 고르는 다이얼로그.

    고르면 `event_selected`를 발화하고 곧바로 accept한다 — 확인 버튼을 한 번 더
    누르게 하면 "골랐는데 아무 일도 안 일어나는" 순간이 생긴다.
    """

    event_selected = Signal(object)  # HookEvent

    def __init__(self, current: HookEvent | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("훅 라이프사이클 — 이벤트 선택")
        self.resize(600, 800)
        self._selected: HookEvent | None = None

        lay = QVBoxLayout(self)
        hint = QLabel(
            "박스를 클릭해 이벤트를 고르세요. 현재 선택은 굵은 테두리로 표시됩니다."
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self._scene = HookLifecycleScene(current)
        self._scene.picked.connect(self._on_picked)
        view = QGraphicsView(self._scene)
        view.setRenderHints(view.renderHints())
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(view, 1)
        self._view = view

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @property
    def selected(self) -> HookEvent | None:
        return self._selected

    def _on_picked(self, event: HookEvent) -> None:
        self._selected = event
        self.event_selected.emit(event)
        self.accept()
