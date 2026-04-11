from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.commands.base import MacroCommand
from daedalus.view.commands.state_commands import CreateStateCmd, DeleteStateCmd, MoveStateCmd
from daedalus.view.commands.transition_commands import CreateTransitionCmd, DeleteTransitionCmd
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel

_BG_COLOR = QColor("#12122a")


class FsmScene(QGraphicsScene):
    """FSM 노드 편집 씬."""

    def __init__(self, project_vm: ProjectViewModel) -> None:
        super().__init__()
        self._project_vm = project_vm
        self._node_items: dict[StateViewModel, StateNodeItem] = {}
        self._edge_items: dict[TransitionViewModel, TransitionEdgeItem] = {}
        self._state_counter = 0
        self.setBackgroundBrush(_BG_COLOR)
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._connecting = False
        self._connect_source: StateNodeItem | None = None

        self._project_vm.add_listener(self._rebuild)

    def close(self) -> None:
        """씬 종료 시 ProjectViewModel 리스너를 해제."""
        self._project_vm.remove_listener(self._rebuild)

    def _rebuild(self) -> None:
        """ProjectViewModel과 씬 아이템을 동기화."""
        # 제거된 상태
        for vm in list(self._node_items):
            if vm not in self._project_vm.state_vms:
                self.removeItem(self._node_items.pop(vm))
        # 추가된 상태
        for vm in self._project_vm.state_vms:
            if vm not in self._node_items:
                item = StateNodeItem(vm)
                self.addItem(item)
                self._node_items[vm] = item
            else:
                self._node_items[vm].setPos(vm.x, vm.y)
        # 제거된 전이
        for tvm in list(self._edge_items):
            if tvm not in self._project_vm.transition_vms:
                self.removeItem(self._edge_items.pop(tvm))
        # 추가된 전이
        for tvm in self._project_vm.transition_vms:
            if tvm not in self._edge_items:
                src = self._node_items.get(tvm.source_vm)
                tgt = self._node_items.get(tvm.target_vm)
                if src and tgt:
                    edge = TransitionEdgeItem(tvm, src, tgt)
                    self.addItem(edge)
                    self._edge_items[tvm] = edge
        # 경로 업데이트
        for edge in self._edge_items.values():
            edge.update_path()

    def handle_node_moved(
        self, node: StateNodeItem, old_pos: QPointF, new_pos: QPointF
    ) -> None:
        cmd = MoveStateCmd(
            node.state_vm,
            old_x=old_pos.x(), old_y=old_pos.y(),
            new_x=new_pos.x(), new_y=new_pos.y(),
        )
        self._project_vm.execute(cmd)

    # --- 컨텍스트 메뉴 ---

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        if event is None:
            return
        pos = event.scenePos()
        item = self.itemAt(pos, self.views()[0].transform()) if self.views() else None
        menu = QMenu()

        if isinstance(item, StateNodeItem):
            delete_act = menu.addAction(f"'{item.state_vm.model.name}' 삭제")
            connect_act = menu.addAction("전이 시작")
            chosen = menu.exec(event.screenPos())
            if chosen == delete_act:
                self._delete_state(item.state_vm)
            elif chosen == connect_act:
                self._connecting = True
                self._connect_source = item
        elif isinstance(item, TransitionEdgeItem):
            delete_act = menu.addAction("전이 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self._delete_transition(item.transition_vm)
        else:
            add_act = menu.addAction("상태 추가")
            if menu.exec(event.screenPos()) == add_act:
                self._create_state(pos)

    def _create_state(self, pos: QPointF) -> None:
        self._state_counter += 1
        model = SimpleState(name=f"State_{self._state_counter}")
        vm = StateViewModel(model=model, x=pos.x(), y=pos.y())
        self._project_vm.execute(CreateStateCmd(self._project_vm, vm))

    def _delete_state(self, state_vm: StateViewModel) -> None:
        transitions = self._project_vm.get_transitions_for(state_vm)
        children = [DeleteTransitionCmd(self._project_vm, t) for t in transitions]
        children.append(DeleteStateCmd(self._project_vm, state_vm))
        self._project_vm.execute(
            MacroCommand(children=children, description=f"상태 '{state_vm.model.name}' 삭제")
        )

    def _delete_transition(self, tvm: TransitionViewModel) -> None:
        self._project_vm.execute(DeleteTransitionCmd(self._project_vm, tvm))

    # --- 전이 생성 (클릭 모드) ---

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if self._connecting and event.button() == Qt.MouseButton.RightButton:
            self._connecting = False
            self._connect_source = None
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if self._connecting and self._connect_source:
            target = (
                self.itemAt(event.scenePos(), self.views()[0].transform())
                if self.views()
                else None
            )
            if isinstance(target, StateNodeItem) and target is not self._connect_source:
                src_vm = self._connect_source.state_vm
                tgt_vm = target.state_vm
                model = Transition(source=src_vm.model, target=tgt_vm.model)
                tvm = TransitionViewModel(model=model, source_vm=src_vm, target_vm=tgt_vm)
                self._project_vm.execute(CreateTransitionCmd(self._project_vm, tvm))
            self._connecting = False
            self._connect_source = None
            return
        super().mouseReleaseEvent(event)

    # --- 키보드 ---

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        if event.key() == Qt.Key.Key_Delete:
            for item in list(self.selectedItems()):
                if isinstance(item, StateNodeItem):
                    self._delete_state(item.state_vm)
                elif isinstance(item, TransitionEdgeItem):
                    self._delete_transition(item.transition_vm)
            return
        super().keyPressEvent(event)
