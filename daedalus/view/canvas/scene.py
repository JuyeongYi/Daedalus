# daedalus/view/canvas/scene.py
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QKeyEvent, QPen
from PyQt6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.commands.base import Command, MacroCommand
from daedalus.view.commands.state_commands import CreateStateCmd, DeleteStateCmd, MoveStateCmd
from daedalus.view.commands.transition_commands import CreateTransitionCmd, DeleteTransitionCmd
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

from daedalus.model.project import PluginProject

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel

_BG_COLOR = QColor("#12122a")
_DRAG_LINE_COLOR = QColor("#4488ff")


class FsmScene(QGraphicsScene):
    """FSM 노드 편집 씬."""

    node_double_clicked = pyqtSignal(object)  # skill_ref

    def __init__(
        self,
        project_vm: ProjectViewModel,
        skill_lookup: Callable[[str], object] | None = None,
    ) -> None:
        super().__init__()
        self._project_vm = project_vm
        self._skill_lookup = skill_lookup
        self._project: PluginProject | None = None  # set via set_project()
        self._node_items: dict[StateViewModel, StateNodeItem] = {}
        self._edge_items: dict[TransitionViewModel, TransitionEdgeItem] = {}
        self._state_counter = 0
        self.setBackgroundBrush(_BG_COLOR)
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._connecting = False
        self._connect_source: StateNodeItem | None = None
        self._connect_event: str | None = None
        self._drag_line: QGraphicsLineItem | None = None

        self._project_vm.add_listener(self._rebuild)

    def close(self) -> None:
        self._project_vm.remove_listener(self._rebuild)

    def _rebuild(self) -> None:
        for vm in list(self._node_items):
            if vm not in self._project_vm.state_vms:
                self.removeItem(self._node_items.pop(vm))
        for vm in self._project_vm.state_vms:
            if vm not in self._node_items:
                item = StateNodeItem(vm)
                self.addItem(item)
                self._node_items[vm] = item
            else:
                self._node_items[vm].setPos(vm.x, vm.y)
                self._node_items[vm].update_from_model()
        for tvm in list(self._edge_items):
            if tvm not in self._project_vm.transition_vms:
                self.removeItem(self._edge_items.pop(tvm))
        for tvm in self._project_vm.transition_vms:
            if tvm not in self._edge_items:
                src = self._node_items.get(tvm.source_vm)
                tgt = self._node_items.get(tvm.target_vm)
                if src and tgt:
                    edge = TransitionEdgeItem(tvm, src, tgt)
                    self.addItem(edge)
                    self._edge_items[tvm] = edge
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

    # --- 전이 드래그 ---

    def begin_transition_drag(self, source: StateNodeItem, event_name: str) -> None:
        self._connecting = True
        self._connect_source = source
        self._connect_event = event_name
        line = QGraphicsLineItem()
        pen = QPen(_DRAG_LINE_COLOR, 2, Qt.PenStyle.DashLine)
        line.setPen(pen)
        self.addItem(line)
        self._drag_line = line

    def update_transition_drag(self, scene_pos: QPointF) -> None:
        if self._drag_line is not None and self._connect_source is not None:
            event_name = self._connect_event or "done"
            src_pt = self._connect_source.output_port_scene_pos(event_name)
            self._drag_line.setLine(
                src_pt.x(), src_pt.y(),
                scene_pos.x(), scene_pos.y(),
            )

    def end_transition_drag(self, scene_pos: QPointF) -> None:
        if self._drag_line is not None:
            self.removeItem(self._drag_line)
            self._drag_line = None

        if self._connecting and self._connect_source is not None:
            target = self._item_at_input_port(scene_pos)
            if target is not None and target is not self._connect_source:
                src_vm = self._connect_source.state_vm
                tgt_vm = target.state_vm
                model = Transition(
                    source=src_vm.model,
                    target=tgt_vm.model,
                    trigger=CompletionEvent(name=self._connect_event or "done"),
                )
                tvm = TransitionViewModel(
                    model=model, source_vm=src_vm, target_vm=tgt_vm
                )
                self._project_vm.execute(CreateTransitionCmd(self._project_vm, tvm))

        self._connecting = False
        self._connect_source = None
        self._connect_event = None

    def _item_at_input_port(self, scene_pos: QPointF) -> StateNodeItem | None:
        view_transform = self.views()[0].transform() if self.views() else None
        item = (
            self.itemAt(scene_pos, view_transform)
            if view_transform is not None else None
        )
        if isinstance(item, StateNodeItem):
            local = item.mapFromScene(scene_pos)
            if item.is_input_port(local):
                return item
        return None

    def handle_node_double_clicked(self, node: StateNodeItem) -> None:
        ref = node.state_vm.model.skill_ref
        if ref is not None:
            self.node_double_clicked.emit(ref)

    # --- Registry 드롭 ---

    def drop_skill(self, skill_name: str, scene_pos: QPointF) -> None:
        if self._skill_lookup is None:
            return
        skill = self._skill_lookup(skill_name)
        if skill is None:
            return
        # DeclarativeSkill은 FSM 노드로 배치 불가
        from daedalus.model.plugin.skill import DeclarativeSkill
        if isinstance(skill, DeclarativeSkill):
            return
        for svm in self._project_vm.state_vms:
            if svm.model.skill_ref is skill:
                return  # 이미 배치됨
        self._state_counter += 1
        model = SimpleState(name=skill.name, skill_ref=skill)
        vm = StateViewModel(model=model, x=scene_pos.x(), y=scene_pos.y())
        self._project_vm.execute(CreateStateCmd(self._project_vm, vm))

    # --- 컨텍스트 메뉴 ---

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        if event is None:
            return
        pos = event.scenePos()
        item = self.itemAt(pos, self.views()[0].transform()) if self.views() else None
        menu = QMenu()
        if isinstance(item, StateNodeItem):
            delete_act = menu.addAction(f"'{item.state_vm.model.name}' 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self._delete_state(item.state_vm)
        elif isinstance(item, TransitionEdgeItem):
            tvm = item.transition_vm
            transition = tvm.model

            # On Transfer 스킬 서브메뉴
            transfer_menu = menu.addMenu("On Transfer 스킬 설정")
            transfer_skills = self._get_transfer_skills()
            skill_actions: dict[QAction, object] = {}
            for ts in transfer_skills:
                act = transfer_menu.addAction(f"⚡ {ts.name}")
                skill_actions[act] = ts
            if transfer_skills:
                transfer_menu.addSeparator()
            new_act = transfer_menu.addAction("새 Transfer Skill 생성...")

            # 스킬 해제 (현재 연결된 경우만)
            unset_act = None
            if transition.skill_ref is not None:
                unset_act = menu.addAction(f"On Transfer 스킬 해제 ({transition.skill_ref.name})")

            delete_act = menu.addAction("전이 삭제")

            chosen = menu.exec(event.screenPos())
            if chosen is None:
                return
            if chosen == delete_act:
                self._delete_transition(tvm)
            elif chosen == new_act:
                self._create_and_assign_transfer_skill(transition)
            elif chosen == unset_act:
                transition.skill_ref = None
                self._project_vm.notify()
            elif chosen in skill_actions:
                transition.skill_ref = skill_actions[chosen]
                self._project_vm.notify()
        else:
            add_act = menu.addAction("빈 상태 추가")
            if menu.exec(event.screenPos()) == add_act:
                self._create_state(pos)

    def _create_state(self, pos: QPointF) -> None:
        self._state_counter += 1
        model = SimpleState(name=f"State_{self._state_counter}")
        vm = StateViewModel(model=model, x=pos.x(), y=pos.y())
        self._project_vm.execute(CreateStateCmd(self._project_vm, vm))

    def _delete_state(self, state_vm: StateViewModel) -> None:
        transitions = self._project_vm.get_transitions_for(state_vm)
        children: list[Command] = [DeleteTransitionCmd(self._project_vm, t) for t in transitions]
        children.append(DeleteStateCmd(self._project_vm, state_vm))
        self._project_vm.execute(
            MacroCommand(children=children, description=f"상태 '{state_vm.model.name}' 삭제")
        )

    def _delete_transition(self, tvm: TransitionViewModel) -> None:
        self._project_vm.execute(DeleteTransitionCmd(self._project_vm, tvm))

    def set_project(self, project: PluginProject) -> None:
        self._project = project

    def _get_transfer_skills(self) -> list:
        """프로젝트에서 TransferSkill 목록을 반환."""
        from daedalus.model.plugin.skill import TransferSkill
        if self._project is None:
            return []
        return [s for s in self._project.skills if isinstance(s, TransferSkill)]

    def _create_and_assign_transfer_skill(self, transition: object) -> None:
        """새 TransferSkill을 생성하고 transition에 할당."""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        from daedalus.model.plugin.skill import TransferSkill
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState
        if self._project is None:
            return
        existing = {s.name for s in self._project.skills} | {a.name for a in self._project.agents}
        view = self.views()[0] if self.views() else None
        while True:
            name, ok = QInputDialog.getText(view, "새 Transfer Skill", "이름:")
            if not ok or not name.strip():
                return
            name = name.strip()
            if name in existing:
                QMessageBox.warning(view, "이름 중복", f"'{name}' 이름이 이미 존재합니다.")
                continue
            break
        s = SimpleState(name="start")
        fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
        skill = TransferSkill(fsm=fsm, name=name, description="")
        self._project.skills.append(skill)
        transition.skill_ref = skill
        self._project_vm.notify()

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

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if self._connecting and event.button() == Qt.MouseButton.RightButton:
            if self._drag_line is not None:
                self.removeItem(self._drag_line)
                self._drag_line = None
            self._connecting = False
            self._connect_source = None
            self._connect_event = None
            return
        super().mousePressEvent(event)
