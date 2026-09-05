# daedalus/view/canvas/draggable.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF

if TYPE_CHECKING:
    from daedalus.view.commands.base import Command


class DraggableItemMixin:
    """캔버스에서 드래그 이동 가능한 아이템의 공통 로직 (WP-DM).

    러버밴드 등으로 다중 선택된 상태에서 Qt는 선택된 이동 가능(ItemIsMovable)
    아이템을 전부 화면에서 함께 움직이지만, mousePressEvent/mouseReleaseEvent는
    실제로 마우스를 잡은(grabbed) 아이템 하나에만 배달된다. 이 믹스인은 그
    비대칭을 흡수하는 공통 드래그 수명주기를 제공한다 — 서브클래스는 자신의
    mousePressEvent에서 begin_drag()를, mouseReleaseEvent에서 end_drag()를
    호출한다(단, 두 이벤트 모두 super() 호출은 그대로 유지해야 한다 — Qt가
    거기서 드래그 기준 좌표를 기록하므로, 우회하면 다음 드래그가 스테일
    오프셋으로 계산돼 아이템이 화면 왼쪽 위로 튄다).

    ABC를 쓰지 않는다 — Qt 메타클래스와 충돌한다. 서브클래스가 구현해야 할
    메서드는 NotImplementedError를 던지는 평범한 메서드로 대체한다. 믹스인은
    항상 QGraphicsItem 계열 앞에 둔다: `class Foo(DraggableItemMixin, QGraphicsItem)`.
    """

    _drag_origin: QPointF | None = None

    def begin_drag(self) -> None:
        """현재 pos()를 드래그 시작 좌표로 기록 + 씬에 다중 선택 스냅샷 요청.

        스냅샷이 필요한 이유: WaypointHandleItem처럼 pos() 변경이 실시간으로
        모델을 미리보기 갱신하는 아이템(update_waypoint_preview 참조)은,
        release 시점에 vm_position()을 다시 읽으면 이미 새 값으로 갱신돼 있어
        old/new 차이를 판정할 수 없다 — 드래그 시작(press) 시점에 선택된
        모든 draggable의 vm 좌표를 미리 떠 둔다.
        """
        self._drag_origin = self.pos()  # type: ignore[attr-defined]
        sc: Any = self.scene()  # type: ignore[attr-defined]
        if sc is not None and hasattr(sc, "snapshot_drag_positions"):
            sc.snapshot_drag_positions()

    def end_drag(self) -> None:
        """release — 시작 좌표가 있고 실제로 움직였으면 scene.handle_items_moved 위임.

        씬이 없거나 handle_items_moved를 제공하지 않으면 fallback_apply_move로
        대체한다(예: ReferenceNodeItem의 "씬 없는 환경" 폴백).
        """
        origin = self._drag_origin
        self._drag_origin = None
        sc: Any = self.scene()  # type: ignore[attr-defined]
        new_pos = self.pos() if origin is not None else None  # type: ignore[attr-defined]
        if origin is None or origin == new_pos:
            # 이동 없이 끝난 클릭 — 스냅샷 수명주기를 대칭으로 닫는다.
            if sc is not None and hasattr(sc, "clear_drag_positions"):
                sc.clear_drag_positions()
            return
        if sc is not None and hasattr(sc, "handle_items_moved"):
            sc.handle_items_moved(self, origin, new_pos)
        else:
            self.fallback_apply_move(new_pos)

    def vm_position(self) -> QPointF:
        """VM(모델)에 저장된 현재 좌표 — 화면 좌표(pos())가 아니라.

        함께 드래그된(passenger) 아이템의 "구 위치" 판정에 쓰인다.
        서브클래스가 반드시 구현.
        """
        raise NotImplementedError

    def make_move_command(self, old: QPointF, new: QPointF) -> "Command | None":
        """자기 타입에 맞는 이동 커맨드 생성. 만들 수 없으면 None.

        서브클래스가 반드시 구현.
        """
        raise NotImplementedError

    def fallback_apply_move(self, new: QPointF) -> None:
        """씬이 없거나 handle_items_moved 미제공 시 기본 동작 — no-op.

        ReferenceNodeItem이 기존 "씬 없을 때 ref_vm.x/y 직접 설정" 폴백을
        유지하는 데 오버라이드한다.
        """
        return None
