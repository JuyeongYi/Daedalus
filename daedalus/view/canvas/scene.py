# daedalus/view/canvas/scene.py
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QKeyEvent, QPen
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QInputDialog,
    QMenu,
    QMessageBox,
)

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ReferenceSkill, TransferSkill
from daedalus.view.canvas.draggable import DraggableItemMixin
from daedalus.view.canvas.edge_item import TransitionEdgeItem, WaypointHandleItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.ref_edge_item import ReferenceEdgeItem
from daedalus.view.canvas.ref_node_item import ReferenceNodeItem
from daedalus.view.commands.base import Command, MacroCommand
from daedalus.view.commands.reference_commands import (
    CreateRefCmd,
    CreateRefLinkCmd,
    DeleteRefCmd,
    DeleteRefLinkCmd,
)
from daedalus.view.commands.state_commands import CreateStateCmd, DeleteStateCmd
from daedalus.view.commands.transition_commands import (
    AddSkillToProjectCmd,
    AddWaypointCmd,
    ClearWaypointsCmd,
    CreateTransitionCmd,
    DeleteTransitionCmd,
    MoveWaypointCmd,
    RemoveWaypointCmd,
    SetTransitionSkillRefCmd,
)
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
    TransitionViewModel,
)

from daedalus.model.project import PluginProject

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel

_BG_COLOR = QColor("#12122a")
_DRAG_LINE_COLOR = QColor("#4488ff")

# 캔버스 이동 범위 — 좁으면 노드를 그 밖으로 옮길 수도, 스크롤할 수도 없다.
# 넉넉히 시작하고 노드가 가장자리에 접근하면 _grow_scene_rect가 확장한다(단조 증가 —
# 축소하면 스크롤 위치가 튄다).
_INITIAL_SCENE_RECT = QRectF(-20000, -20000, 40000, 40000)
_SCENE_MARGIN = 4000.0  # 아이템 경계에서 확보할 여백


class FsmScene(QGraphicsScene):
    """FSM 노드 편집 씬."""

    node_double_clicked = Signal(object)  # skill_ref

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
        self._ref_node_items: dict[ReferenceViewModel, ReferenceNodeItem] = {}
        self._ref_edge_items: dict[ReferenceLinkViewModel, ReferenceEdgeItem] = {}
        self._state_counter = 0
        self._target_fsm: StateMachine | None = None  # AgentFsmScene만 설정 — 모델 동기화 대상
        self._drag_positions: dict[DraggableItemMixin, QPointF] = {}  # WP-DM 드래그 시작 스냅샷
        self.setBackgroundBrush(_BG_COLOR)
        self.setSceneRect(_INITIAL_SCENE_RECT)

        self._connecting = False
        self._connect_source: StateNodeItem | None = None
        self._connect_event: str | None = None
        self._connect_is_agent_call: bool = False
        self._drag_line: QGraphicsLineItem | None = None

        self._ref_connecting = False
        self._ref_connect_source: ReferenceNodeItem | None = None
        self._ref_drag_line: QGraphicsLineItem | None = None

        self._project_vm.add_listener(self._rebuild)

    def _create_node_item(self, vm: StateViewModel) -> StateNodeItem:
        return StateNodeItem(vm)

    def close(self) -> None:
        self._project_vm.remove_listener(self._rebuild)

    def _rebuild(self) -> None:
        for vm in list(self._node_items):
            if vm not in self._project_vm.state_vms:
                self.removeItem(self._node_items.pop(vm))
        for vm in self._project_vm.state_vms:
            if vm not in self._node_items:
                item = self._create_node_item(vm)
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
        self._rebuild_refs()
        self.grow_scene_rect()

    def grow_scene_rect(self) -> None:
        """아이템이 가장자리에 접근하면 씬 범위를 넓힌다 (확장 전용).

        범위가 고정이면 노드를 그 밖으로 옮길 수도, 그쪽으로 스크롤할 수도 없다.
        축소는 하지 않는다 — 스크롤 위치가 튀기 때문.
        """
        items_rect = self.itemsBoundingRect()
        if items_rect.isEmpty():
            return
        needed = items_rect.adjusted(
            -_SCENE_MARGIN, -_SCENE_MARGIN, _SCENE_MARGIN, _SCENE_MARGIN,
        )
        current = self.sceneRect()
        if not current.contains(needed):
            self.setSceneRect(current.united(needed))

    def update_edges_for_node(self, node: StateNodeItem) -> None:
        """노드 드래그 중 연결된 엣지 경로를 실시간 갱신."""
        for edge in self._edge_items.values():
            if edge.source_node is node or edge.target_node is node:
                edge.update_path()
        for edge in self._ref_edge_items.values():
            if edge.source_node is node:
                edge.update_path()
        self.grow_scene_rect()

    # --- 드래그 이동 (WP-DM) ---

    def snapshot_drag_positions(self) -> None:
        """드래그 시작(press) 시점 — 선택된 모든 draggable의 vm 좌표를 미리 기록.

        WaypointHandleItem처럼 pos() 변경이 실시간으로 모델(waypoints)을
        미리보기 갱신하는 아이템은, release 시점에 vm_position()을 다시 읽으면
        이미 새 값으로 갱신돼 있어 old/new 차이를 판정할 수 없다 — press
        시점 스냅샷으로 해결한다.
        """
        self._drag_positions = {
            item: item.vm_position()
            for item in self.selectedItems()
            if isinstance(item, DraggableItemMixin)
        }

    def clear_drag_positions(self) -> None:
        """드래그 스냅샷 폐기 — 이동 없이 끝난 클릭 등에서 호출.

        스냅샷을 남겨두면 _rebuild()로 파괴된 아이템 참조를 다음 press까지
        붙잡는다. begin_drag()가 매 press마다 dict를 통째로 재할당하므로
        정확성 문제는 없지만, 수명주기를 대칭으로 닫아 둔다.
        """
        self._drag_positions = {}

    def handle_items_moved(
        self, grabbed: DraggableItemMixin, old_pos: QPointF, new_pos: QPointF
    ) -> None:
        """드래그 릴리스 단일 진입점(WP-DM).

        Qt는 선택된 이동 가능 아이템을 전부 화면에서 함께 옮기지만, release
        이벤트는 잡은(grabbed) 아이템 하나에만 배달된다 — 이 메서드가 선택된
        모든 draggable을 모아 하나의 undo 단위로 묶어 그 비대칭을 흡수하는
        단일 진입점이다. 아이템 타입 분기는 두지 않는다 — 커맨드 생성 지식은
        각 아이템의 make_move_command()에 있고, 씬은 수집·묶기만 한다.
        """
        items: list[DraggableItemMixin] = [
            item for item in self.selectedItems()
            if isinstance(item, DraggableItemMixin)
        ]
        if grabbed not in items:
            items.append(grabbed)

        snapshot = self._drag_positions
        cmds: list[Command] = []
        for item in items:
            if item is grabbed:
                old, new = old_pos, new_pos
            else:
                # 함께 드래그된(passenger) 아이템 — press 시점 스냅샷을 우선
                # 쓰고(WaypointHandleItem 등 실시간 미리보기로 vm이 이미
                # 갱신됐을 수 있는 아이템 대응), 스냅샷이 없으면(직접 호출 등)
                # vm_position()으로 폴백한다.
                old = snapshot.get(item, item.vm_position())
                new = item.pos()
                if old == new:
                    continue
            cmd = item.make_move_command(old, new)
            if cmd is not None:
                cmds.append(cmd)
        self._drag_positions = {}

        if not cmds:
            return
        if len(cmds) == 1:
            self._project_vm.execute(cmds[0])
        else:
            self._project_vm.execute(MacroCommand(
                children=cmds,
                description="캔버스 다중 이동",
            ))

    def handle_node_moved(
        self, node: StateNodeItem, old_pos: QPointF, new_pos: QPointF
    ) -> None:
        """노드 드래그 release — WP-DM: handle_items_moved에 위임(시그니처
        유지, 기존 호출부·테스트 호환)."""
        self.handle_items_moved(node, old_pos, new_pos)

    # --- 엣지 경유점 (WP-ER) ---

    def handle_edge_double_clicked(self, edge: TransitionEdgeItem, scene_pos: QPointF) -> None:
        """엣지 더블클릭 — 클릭 지점에 가장 가까운 구간에 경유점 삽입. undo 가능."""
        index = edge.nearest_segment_index(scene_pos)
        self._project_vm.execute(
            AddWaypointCmd(edge.transition_vm, index, scene_pos.x(), scene_pos.y())
        )

    def handle_waypoint_moved(
        self,
        edge: TransitionEdgeItem,
        index: int,
        old_pos: QPointF,
        new_pos: QPointF,
    ) -> None:
        """경유점 핸들 드래그 release — WP-DM: handle_items_moved에 위임(시그니처
        유지, 기존 호출부·테스트 호환)."""
        handle = edge.handle_at(index)
        if handle is not None:
            self.handle_items_moved(handle, old_pos, new_pos)
            return
        # 방어적 폴백 — 인덱스가 어긋난 경우 기존 단일 커맨드 경로 유지
        self._project_vm.execute(
            MoveWaypointCmd(
                edge.transition_vm, index,
                old_x=old_pos.x(), old_y=old_pos.y(),
                new_x=new_pos.x(), new_y=new_pos.y(),
            )
        )

    def remove_waypoint(self, edge: TransitionEdgeItem, index: int) -> None:
        """경유점 하나 제거 — undo 가능."""
        self._project_vm.execute(RemoveWaypointCmd(edge.transition_vm, index))

    def clear_waypoints(self, edge: TransitionEdgeItem) -> None:
        """전이의 경유점을 모두 제거(직선 복원) — undo 가능."""
        self._project_vm.execute(ClearWaypointsCmd(edge.transition_vm))

    # --- 전이 드래그 ---

    def begin_transition_drag(self, source: StateNodeItem, event_name: str, is_agent_call: bool = False) -> None:
        self._connecting = True
        self._connect_source = source
        self._connect_event = event_name
        self._connect_is_agent_call = is_agent_call
        line = QGraphicsLineItem()
        pen = QPen(_DRAG_LINE_COLOR, 2, Qt.PenStyle.DashLine)
        line.setPen(pen)
        self.addItem(line)
        self._drag_line = line

    def update_transition_drag(self, scene_pos: QPointF) -> None:
        if self._drag_line is not None and self._connect_source is not None:
            event_name = self._connect_event or "done"
            src_pt = self._connect_source.output_port_scene_pos(event_name, self._connect_is_agent_call)
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
                event_name = self._connect_event or "done"
                src_ref = getattr(src_vm.model, "skill_ref", None)
                tgt_ref = getattr(tgt_vm.model, "skill_ref", None)
                is_agent_call = self._connect_is_agent_call
                tgt_is_agent = isinstance(tgt_ref, AgentDefinition)
                # 에이전트 노드 입력 ← call_agent 포트만 허용
                if tgt_is_agent and not is_agent_call:
                    self._connecting = False
                    self._connect_source = None
                    self._connect_event = None
                    return
                # call_agent 포트 → 에이전트 노드만 허용
                if is_agent_call and not tgt_is_agent:
                    self._connecting = False
                    self._connect_source = None
                    self._connect_event = None
                    return
                # 같은 (source, target, event) 조합이 이미 존재하면 무시
                duplicate = any(
                    t.source_vm is src_vm
                    and t.target_vm is tgt_vm
                    and t.model.trigger is not None
                    and t.model.trigger.name == event_name
                    for t in self._project_vm.transition_vms
                )
                if not duplicate:
                    # 입력 포트는 노드당 하나(WP-IP) — 도착점 지정 없이 연결한다.
                    model = Transition(
                        source=src_vm.model,
                        target=tgt_vm.model,
                        trigger=CompletionEvent(name=event_name),
                    )
                    tvm = TransitionViewModel(
                        model=model, source_vm=src_vm, target_vm=tgt_vm
                    )
                    # WP-CT — 계약 카드 자동 생성은 퇴역했다. 호출 계약은
                    # 컴파일러가 그래프(호출 포트 + 전이)에서 유도한다.
                    self._project_vm.execute(
                        CreateTransitionCmd(self._project_vm, tvm, fsm=self._target_fsm)
                    )

        self._connecting = False
        self._connect_source = None
        self._connect_event = None
        self._connect_is_agent_call = False

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
        model = node.state_vm.model
        if not hasattr(model, "skill_ref"):
            return
        ref = model.skill_ref  # type: ignore[union-attr]
        if ref is not None:
            self.node_double_clicked.emit(ref)
            return
        # 컴포넌트가 붙지 않은 빈 노드 — 열 편집기가 없다. 아무 반응도 없으면
        # 고장으로 읽히므로, 빈 노드에서 유일하게 편집할 것인 이름을 연다.
        self.rename_state_interactive(node.state_vm)

    def rename_state_interactive(self, state_vm) -> None:
        """노드 이름 변경 다이얼로그. undo 가능."""
        from daedalus.view.commands.state_commands import RenameStateCmd

        view = self.views()[0] if self.views() else None
        old = state_vm.model.name
        new_name, ok = QInputDialog.getText(view, "노드 이름 변경", "이름:", text=old)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old:
            return
        # 같은 머신에 동명 상태가 둘이면 컴파일·직렬화에서 서로를 가린다
        # (duplicate_state_name 경고). 여기서 미리 막는다.
        others = {
            svm.model.name for svm in self._project_vm.state_vms if svm is not state_vm
        }
        if new_name in others:
            QMessageBox.warning(view, "이름 중복", f"'{new_name}' 노드가 이미 있습니다.")
            return
        self._project_vm.execute(RenameStateCmd(state_vm, old, new_name))

    # --- Registry 드롭 ---

    def drop_skill(self, skill_name: str, scene_pos: QPointF) -> None:
        if self._skill_lookup is None:
            return
        skill = self._skill_lookup(skill_name)
        if skill is None:
            return
        # 참조 스킬은 별도 처리 (여러 인스턴스 허용)
        if isinstance(skill, ReferenceSkill):
            self.drop_reference_skill(skill_name, scene_pos)
            return
        # DeclarativeSkill / TransferSkill은 FSM 노드로 배치 불가 (edge-only)
        if isinstance(skill, (DeclarativeSkill, TransferSkill)):
            return
        for svm in self._project_vm.state_vms:
            if hasattr(svm.model, "skill_ref") and svm.model.skill_ref is skill:  # type: ignore[union-attr]
                return  # 이미 배치됨
        self._state_counter += 1
        model = SimpleState(name=skill.name, skill_ref=skill)  # type: ignore[arg-type,union-attr]
        vm = StateViewModel(model=model, x=scene_pos.x(), y=scene_pos.y())
        self._project_vm.execute(CreateStateCmd(self._project_vm, vm, fsm=self._target_fsm))

    # --- 컨텍스트 메뉴 ---

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        if event is None:
            return
        pos = event.scenePos()
        item = self.itemAt(pos, self.views()[0].transform()) if self.views() else None
        menu = QMenu()
        if isinstance(item, StateNodeItem):
            from daedalus.model.fsm.pseudo import EntryPoint as _EP
            if isinstance(item.state_vm.model, _EP):
                # 프로젝트 그래프 시작점(EntryPoint)은 삭제 불가 — 안내만.
                act = menu.addAction("삭제 불가 (워크플로 시작점)")
                if act is not None:
                    act.setEnabled(False)
                menu.exec(event.screenPos())
                return
            # 진입점 프리셋 (A8) — 스킬 placement에만. 실체는
            # view/actions/entrypoint.py이고 여기는 호출부일 뿐이다.
            # 노드 메뉴는 항목이 많아 exec 반환값 비교 대신 **디스패치 표**를
            # 쓴다 — 항목이 늘 때마다 elif 사슬이 길어지면 어느 분기가 어느
            # 항목인지 눈으로 짝지어야 한다.
            dispatch: dict = {}
            entry_actions = self._add_entry_preset_menu(menu, item.state_vm)
            for act, preset in entry_actions.items():
                dispatch[act] = (
                    lambda vm=item.state_vm, p=preset: self._apply_entry_preset(vm, p)
                )
            dispatch.update(self._add_component_actions_menu(menu, item.state_vm))
            delete_act = menu.addAction(f"'{item.state_vm.model.name}' 삭제")
            dispatch[delete_act] = lambda vm=item.state_vm: self._delete_state(vm)

            chosen = menu.exec(event.screenPos())
            handler = dispatch.get(chosen) if chosen is not None else None
            if handler is not None:
                handler()
        elif isinstance(item, ReferenceNodeItem):
            name = getattr(item.ref_vm.model, "name", "?")
            delete_act = menu.addAction(f"참조 '{name}' 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self.delete_reference_node(item.ref_vm)
        elif isinstance(item, ReferenceEdgeItem):
            delete_act = menu.addAction("참조 연결 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self.delete_reference_link(item.link_vm)
        elif isinstance(item, TransitionEdgeItem):
            self._handle_transition_edge_menu(menu, item, pos, event.screenPos())
        elif isinstance(item, WaypointHandleItem):
            self._handle_waypoint_handle_menu(menu, item, event.screenPos())
        else:
            add_act = menu.addAction("빈 상태 추가")
            if menu.exec(event.screenPos()) == add_act:
                self._create_state(pos)

    # --- 진입점 프리셋 (A8) — 실체는 view/actions/entrypoint.py ---

    def _add_entry_preset_menu(self, menu: QMenu, state_vm: StateViewModel) -> dict:
        """"진입점 설정" 서브메뉴를 붙이고 {QAction: EntryPreset}을 돌려준다.

        프리셋을 지원하지 않는 노드(에이전트·빈 상태·FIXED 종류 스킬)에는
        **메뉴를 만들지 않는다** — 눌러도 아무 일도 일어나지 않는 항목은
        없느니만 못하다.
        """
        from daedalus.view.actions.entrypoint import (
            ENTRY_PRESETS,
            current_entry_preset,
            supports_entry_presets,
        )

        component = getattr(state_vm.model, "skill_ref", None)
        if component is None or not supports_entry_presets(component):
            return {}

        submenu = menu.addMenu("진입점 설정")
        if submenu is None:
            return {}
        submenu.setToolTipsVisible(True)
        current = current_entry_preset(component)
        mapping: dict = {}
        for spec in ENTRY_PRESETS:
            act = submenu.addAction(spec.label)
            if act is None:
                continue
            act.setToolTip(spec.description)
            act.setCheckable(True)
            act.setChecked(spec.preset is current)
            mapping[act] = spec.preset
        menu.addSeparator()
        return mapping

    def _apply_entry_preset(self, state_vm: StateViewModel, preset) -> None:
        from daedalus.view.actions.entrypoint import apply_entry_preset

        component = getattr(state_vm.model, "skill_ref", None)
        if component is not None:
            apply_entry_preset(self._project_vm, component, preset)

    # --- 컴포넌트 공통 액션 (A9-1/2/3) — 실체는 view/actions/ ---

    def main_window(self):
        """이 씬이 놓인 최상위 창. 없으면 None.

        씬은 MainWindow를 참조하지 않는다(캔버스가 창을 알 이유가 없다) —
        다이얼로그 부모나 프로젝트 수준 액션이 필요할 때만 뷰를 통해 거슬러
        올라간다. 뷰가 아직 붙지 않은 헤드리스 생성 경로에서는 None이다.
        """
        views = self.views()
        return views[0].window() if views else None

    def _add_component_actions_menu(self, menu: QMenu, state_vm: StateViewModel) -> dict:
        """스킬/에이전트 placement 공통 항목 — 미리보기·모델/effort·관련 경고.

        {QAction: 무인자 콜러블} 디스패치 표를 돌려준다. placement가 아닌
        노드(빈 상태)에는 아무것도 붙이지 않는다.
        """
        from daedalus.view.actions import model_effort as me

        component = getattr(state_vm.model, "skill_ref", None)
        if component is None:
            return {}

        dispatch: dict = {}

        preview_act = menu.addAction("컴파일 미리보기…")
        if preview_act is not None:
            preview_act.setToolTip("이 컴포넌트가 어떤 파일로 나가는지 — 파일은 쓰지 않는다")
            dispatch[preview_act] = lambda c=component: self._show_preview(c)

        if me.supports_model_effort(component):
            model_menu = menu.addMenu("모델 지정")
            if model_menu is not None:
                current = me.current_model(component)
                for model, label in me.MODEL_CHOICES:
                    act = model_menu.addAction(label)
                    if act is None:
                        continue
                    act.setCheckable(True)
                    act.setChecked(current is model)
                    dispatch[act] = (
                        lambda c=component, m=model: me.set_model(self._project_vm, c, m)
                    )
            effort_menu = menu.addMenu("effort 지정")
            if effort_menu is not None:
                current_effort = me.current_effort(component)
                for effort, label in me.EFFORT_CHOICES:
                    act = effort_menu.addAction(label)
                    if act is None:
                        continue
                    act.setCheckable(True)
                    act.setChecked(current_effort is effort)
                    dispatch[act] = (
                        lambda c=component, e=effort: me.set_effort(self._project_vm, c, e)
                    )

        warn_act = menu.addAction("관련 경고 보기")
        if warn_act is not None:
            dispatch[warn_act] = lambda c=component: self._show_component_findings(c)

        dispatch.update(self._add_agent_actions_menu(menu, component))

        menu.addSeparator()
        return dispatch

    # --- 에이전트 전용 (A9-4/5) ---

    def _add_agent_actions_menu(self, menu: QMenu, component: object) -> dict:
        """에이전트 placement에만 붙는 항목 — 호출자 목록 / 출력 포트 편집."""
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.view.actions.agent_links import callers_of

        if not isinstance(component, AgentDefinition):
            return {}

        dispatch: dict = {}
        callers = callers_of(component, self._project)
        callers_menu = menu.addMenu("호출자 목록")
        if callers_menu is not None:
            callers_menu.setToolTipsVisible(True)
            if not callers:
                act = callers_menu.addAction("(없음)")
                if act is not None:
                    act.setEnabled(False)
            for ref in callers:
                act = callers_menu.addAction(ref.label)
                if act is None:
                    continue
                if ref.description:
                    act.setToolTip(ref.description)
                dispatch[act] = lambda r=ref: self._focus_state(r.source_state)

        ports_act = menu.addAction("출력 포트 편집…")
        if ports_act is not None:
            dispatch[ports_act] = lambda c=component: self._open_ports(c)
        return dispatch

    def _focus_state(self, state: object) -> None:
        """그 상태의 노드를 캔버스에서 선택·센터링한다 (검증 결과 점프와 같은 경로)."""
        window = self.main_window()
        if hasattr(window, "_focus_in_project_canvas"):
            window._focus_in_project_canvas(state)

    def _open_ports(self, component: object) -> None:
        window = self.main_window()
        if hasattr(window, "open_component_ports"):
            window.open_component_ports(component)

    def _show_preview(self, component: object) -> None:
        from daedalus.view.actions.preview import show_preview_dialog

        window = self.main_window()
        resolved = window.resolved_hooks() if hasattr(window, "resolved_hooks") else None
        show_preview_dialog(
            window, component, project=self._project, resolved_hooks=resolved,
        )

    def _show_component_findings(self, component: object) -> None:
        window = self.main_window()
        if hasattr(window, "show_component_findings"):
            window.show_component_findings(component)

    def _handle_transition_edge_menu(
        self, menu: QMenu, item: TransitionEdgeItem, scene_pos: QPointF, screen_pos
    ) -> None:
        """전이 엣지 컨텍스트 메뉴 — On Transfer 스킬 설정/해제/생성 + 삭제 + 경유점.

        FsmScene와 AgentFsmScene 양쪽에서 공유하는 템플릿. 스킬 목록/생성
        정책 차이는 _get_transfer_skills / _create_and_assign_transfer_skill
        오버라이드로 흡수한다.
        """
        tvm = item.transition_vm
        transition = tvm.model

        transfer_menu = menu.addMenu("On Transfer 스킬 설정")
        transfer_skills = self._get_transfer_skills()
        skill_actions: dict[QAction, object] = {}
        if transfer_menu is not None:
            for ts in transfer_skills:
                act = transfer_menu.addAction(f"⚡ {ts.name}")
                if act is not None:
                    skill_actions[act] = ts
            if transfer_skills:
                transfer_menu.addSeparator()
        new_act = (
            transfer_menu.addAction("새 Transfer Skill 생성...")
            if transfer_menu is not None else None
        )

        unset_act = None
        if transition.skill_ref is not None:
            unset_act = menu.addAction(
                f"On Transfer 스킬 해제 ({transition.skill_ref.name})"
            )

        add_wp_act = menu.addAction("경유점 추가")
        clear_wp_act = menu.addAction("경유점 모두 제거") if tvm.waypoints else None

        delete_act = menu.addAction("전이 삭제")

        chosen = menu.exec(screen_pos)
        if chosen is None:
            return
        if chosen == delete_act:
            self._delete_transition(tvm)
        elif chosen == new_act:
            self._create_and_assign_transfer_skill(tvm)
        elif chosen == unset_act:
            self._project_vm.execute(SetTransitionSkillRefCmd(tvm, None))
        elif chosen == add_wp_act:
            self.handle_edge_double_clicked(item, scene_pos)
        elif chosen == clear_wp_act:
            self.clear_waypoints(item)
        elif chosen in skill_actions:
            self._project_vm.execute(
                SetTransitionSkillRefCmd(tvm, skill_actions[chosen])
            )

    def _handle_waypoint_handle_menu(
        self, menu: QMenu, item: WaypointHandleItem, screen_pos
    ) -> None:
        """경유점 핸들 우클릭 메뉴 — 제거 하나."""
        remove_act = menu.addAction("경유점 제거")
        if menu.exec(screen_pos) == remove_act:
            self.remove_waypoint(item.edge, item.index)

    def _create_state(self, pos: QPointF) -> None:
        self._state_counter += 1
        model = SimpleState(name=f"State_{self._state_counter}")
        vm = StateViewModel(model=model, x=pos.x(), y=pos.y())
        self._project_vm.execute(CreateStateCmd(self._project_vm, vm, fsm=self._target_fsm))

    def _delete_state(self, state_vm: StateViewModel) -> None:
        from daedalus.model.fsm.pseudo import EntryPoint as _EP
        # EntryPoint(워크플로 시작점)는 삭제 불가 — 모든 경로에서 방어.
        if isinstance(state_vm.model, _EP):
            return
        transitions = self._project_vm.get_transitions_for(state_vm)
        children: list[Command] = []
        # WP-CT — 계약 카드 정리는 퇴역했다(카드 자체가 없다). 전이만 함께 지운다.
        for t in transitions:
            children.append(DeleteTransitionCmd(self._project_vm, t, fsm=self._target_fsm))
        children.append(DeleteStateCmd(self._project_vm, state_vm, fsm=self._target_fsm))
        self._project_vm.execute(
            MacroCommand(children=children, description=f"상태 '{state_vm.model.name}' 삭제")
        )

    def _delete_transition(self, tvm: TransitionViewModel) -> None:
        self._project_vm.execute(
            DeleteTransitionCmd(self._project_vm, tvm, fsm=self._target_fsm)
        )

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        # 프로젝트 캔버스의 노드/전이를 정식 FSM(project.graph)에 동기화하도록 배선
        # (버그 3: 각 노드가 정식 상태여야 한다). AgentFsmScene은 _target_fsm을
        # 에이전트 FSM으로 별도 설정하므로 이 메서드를 거치지 않는다.
        self._target_fsm = project.graph

    def _get_transfer_skills(self) -> list:
        """프로젝트에서 TransferSkill 목록을 반환."""
        if self._project is None:
            return []
        return [s for s in self._project.skills if isinstance(s, TransferSkill)]

    def _create_and_assign_transfer_skill(self, tvm: TransitionViewModel) -> None:
        """새 TransferSkill을 생성하고 transition에 할당 (undo 가능)."""
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
        self._project_vm.execute(MacroCommand(
            children=[
                AddSkillToProjectCmd(self._project, skill),
                SetTransitionSkillRefCmd(tvm, skill),
            ],
            description=f"Transfer Skill '{name}' 생성 및 설정",
        ))

    # --- 참조 스킬 ---

    def _rebuild_refs(self) -> None:
        """참조 노드 + 참조 엣지 동기화."""
        pvm = self._project_vm
        # 참조 노드
        for rvm in list(self._ref_node_items):
            if rvm not in pvm.reference_vms:
                self.removeItem(self._ref_node_items.pop(rvm))
        for rvm in pvm.reference_vms:
            if rvm not in self._ref_node_items:
                item = ReferenceNodeItem(rvm)
                self.addItem(item)
                self._ref_node_items[rvm] = item
            else:
                self._ref_node_items[rvm].setPos(rvm.x, rvm.y)
        # 참조 엣지
        for lvm in list(self._ref_edge_items):
            if lvm not in pvm.reference_links:
                self.removeItem(self._ref_edge_items.pop(lvm))
        for lvm in pvm.reference_links:
            if lvm not in self._ref_edge_items:
                src_node = self._node_items.get(lvm.state_vm)
                ref_node = self._ref_node_items.get(lvm.reference_vm)
                if src_node and ref_node:
                    edge = ReferenceEdgeItem(lvm, src_node, ref_node)
                    self.addItem(edge)
                    self._ref_edge_items[lvm] = edge
        self._sync_ref_ports()
        for edge in self._ref_edge_items.values():
            edge.update_path()

    def _sync_ref_ports(self) -> None:
        """각 노드의 하단 참조 포트 수와 엣지별 index 할당."""
        src_groups: dict[StateNodeItem, list[ReferenceEdgeItem]] = defaultdict(list)
        for edge in self._ref_edge_items.values():
            src_groups[edge.source_node].append(edge)
        for node in self._node_items.values():
            edges = src_groups.get(node, [])
            node.set_ref_count(len(edges))
            for i, edge in enumerate(edges):
                edge.set_port_index(i)

    def update_ref_edges_for_node(self, node: ReferenceNodeItem) -> None:
        """참조 노드 드래그 중 연결선 갱신."""
        for edge in self._ref_edge_items.values():
            if edge.ref_node is node:
                edge.update_path()

    def _get_ref_placements(self) -> list:
        """모델의 reference_placements 리스트 반환 (project 또는 agent)."""
        if self._project is not None:
            return self._project.reference_placements
        return []

    def drop_reference_skill(self, skill_name: str, scene_pos: QPointF) -> None:
        """참조 스킬을 캔버스에 드롭 — 여러 인스턴스 허용. undo 가능."""
        if self._skill_lookup is None:
            return
        skill = self._skill_lookup(skill_name)
        if not isinstance(skill, ReferenceSkill):
            return
        rvm = ReferenceViewModel(model=skill, x=scene_pos.x(), y=scene_pos.y())
        cmd = CreateRefCmd(
            self._project_vm, rvm,
            sync_fn=self._sync_refs_to_model,
        )
        self._project_vm.execute(cmd)

    def create_reference_link(
        self, state_vm: StateViewModel, ref_vm: ReferenceViewModel
    ) -> None:
        """상태 노드 → 참조 노드 연결 생성 (같은 스킬 중복 방지). undo 가능."""
        ref_skill = ref_vm.model
        duplicate = any(
            l.state_vm is state_vm and l.reference_vm.model is ref_skill
            for l in self._project_vm.reference_links
        )
        if not duplicate:
            lvm = ReferenceLinkViewModel(state_vm=state_vm, reference_vm=ref_vm)
            cmd = CreateRefLinkCmd(
                self._project_vm, lvm,
                sync_fn=self._sync_refs_to_model,
            )
            self._project_vm.execute(cmd)

    def delete_reference_node(self, ref_vm: ReferenceViewModel) -> None:
        """참조 노드 + 연결된 링크 삭제. undo 가능."""
        cmd = DeleteRefCmd(
            self._project_vm, ref_vm,
            sync_fn=self._sync_refs_to_model,
        )
        self._project_vm.execute(cmd)

    def delete_reference_link(self, lvm: ReferenceLinkViewModel) -> None:
        """참조 링크 삭제. undo 가능."""
        cmd = DeleteRefLinkCmd(
            self._project_vm, lvm,
            sync_fn=self._sync_refs_to_model,
        )
        self._project_vm.execute(cmd)

    def handle_ref_node_moved(
        self, ref_node: ReferenceNodeItem, old_pos: QPointF, new_pos: QPointF
    ) -> None:
        """참조 노드 드래그 release — WP-DM: handle_items_moved에 위임(시그니처
        유지, 기존 호출부·테스트 호환)."""
        self.handle_items_moved(ref_node, old_pos, new_pos)

    def _sync_refs_to_model(self) -> None:
        """뷰 모델 → 모델 동기화. 위치 + 연결 정보를 모델에 반영 (sync 모듈 위임)."""
        from daedalus.view.canvas.sync import sync_refs_to_model
        sync_refs_to_model(self._project_vm, self._get_ref_placements())

    def begin_ref_link_drag(self, ref_node: ReferenceNodeItem) -> None:
        """참조 노드 상단 포트에서 드래그 시작."""
        self._ref_connecting = True
        self._ref_connect_source = ref_node
        line = QGraphicsLineItem()
        line.setPen(QPen(QColor("#66aaaa"), 2, Qt.PenStyle.DashLine))
        self.addItem(line)
        self._ref_drag_line = line

    def update_ref_link_drag(self, scene_pos: QPointF) -> None:
        if self._ref_drag_line is not None and self._ref_connect_source is not None:
            src_pt = self._ref_connect_source.top_port_scene_pos()
            self._ref_drag_line.setLine(
                src_pt.x(), src_pt.y(), scene_pos.x(), scene_pos.y(),
            )

    def end_ref_link_drag(
        self, ref_node: ReferenceNodeItem, scene_pos: QPointF
    ) -> None:
        if self._ref_drag_line is not None:
            self.removeItem(self._ref_drag_line)
            self._ref_drag_line = None

        if self._ref_connecting and self._ref_connect_source is not None:
            # 드롭 위치에 StateNodeItem이 있는지 확인
            target = self._state_node_at(scene_pos)
            if target is not None:
                self.create_reference_link(target.state_vm, ref_node.ref_vm)

        self._ref_connecting = False
        self._ref_connect_source = None

    def _state_node_at(self, scene_pos: QPointF) -> StateNodeItem | None:
        """scene_pos 위치의 StateNodeItem 반환."""
        view_transform = self.views()[0].transform() if self.views() else None
        for item in self.items(scene_pos) if view_transform is None else self.items(scene_pos):
            if isinstance(item, StateNodeItem):
                return item
        return None

    def handle_ref_node_double_clicked(self, node: ReferenceNodeItem) -> None:
        ref = node.ref_vm.model
        if ref is not None:
            self.node_double_clicked.emit(ref)

    # --- 키보드 ---

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        if event.key() == Qt.Key.Key_Delete:
            selected = list(self.selectedItems())
            # 경유점 핸들이 선택돼 있으면 그것만 처리하고 끝낸다 — 핸들은 엣지가
            # 선택된 동안에만 보이므로, 엣지 삭제 분기까지 타면 Delete 한 번에
            # 전이 전체가 함께 지워진다 (리뷰 결함 2).
            handles = [i for i in selected if isinstance(i, WaypointHandleItem)]
            if handles:
                for h in sorted(handles, key=lambda i: i.index, reverse=True):
                    self.remove_waypoint(h.edge, h.index)
                return
            # 1패스: 노드 삭제 (연결 전이는 MacroCommand로 함께 삭제됨)
            for item in selected:
                if isinstance(item, StateNodeItem):
                    self._delete_state(item.state_vm)
            # 2패스: 엣지 — 노드 삭제로 이미 제거된 전이는 중복 커맨드 금지
            for item in selected:
                if isinstance(item, TransitionEdgeItem):
                    if item.transition_vm in self._project_vm.transition_vms:
                        self._delete_transition(item.transition_vm)
                elif isinstance(item, ReferenceNodeItem):
                    self.delete_reference_node(item.ref_vm)
                elif isinstance(item, ReferenceEdgeItem):
                    self.delete_reference_link(item.link_vm)
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


class AgentFsmScene(FsmScene):
    """에이전트 서브그래프 전용 씬.

    - EntryPoint: 삭제 불가, 컨텍스트 메뉴 비활성
    - ExitPoint: 이름변경/색상변경/삭제(마지막 1개 제외) 가능
    - 빈 공간: 빈 상태 추가 / ExitPoint 추가
    """

    def __init__(
        self,
        project_vm: ProjectViewModel,
        agent_fsm: StateMachine,
        skill_lookup: Callable[[str], object] | None = None,
        agent_ref_placements: list | None = None,
    ) -> None:
        super().__init__(project_vm, skill_lookup=skill_lookup)
        self._agent_fsm = agent_fsm
        self._target_fsm = agent_fsm
        self._agent_ref_placements: list = agent_ref_placements if agent_ref_placements is not None else []

    def _create_node_item(self, vm: StateViewModel) -> StateNodeItem:
        return StateNodeItem(vm, show_call_agents=False)

    def _get_ref_placements(self) -> list:
        return self._agent_ref_placements

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        if event is None:
            return
        pos = event.scenePos()
        item = self.itemAt(pos, self.views()[0].transform()) if self.views() else None
        menu = QMenu()

        if isinstance(item, StateNodeItem):
            from daedalus.model.fsm.pseudo import EntryPoint as _EP, ExitPoint as _XP
            model = item.state_vm.model

            if isinstance(model, _EP):
                act = menu.addAction("삭제 불가 (EntryPoint)")
                if act is not None:
                    act.setEnabled(False)
                menu.exec(event.screenPos())

            elif isinstance(model, _XP):
                rename_act = menu.addAction(f"'{model.name}' 이름 변경")
                color_act = menu.addAction("색상 변경")
                exit_count = sum(
                    1 for s in self._agent_fsm.states
                    if isinstance(s, _XP)
                )
                del_act = menu.addAction(f"'{model.name}' 삭제")
                if del_act is not None and exit_count <= 1:
                    del_act.setEnabled(False)
                chosen = menu.exec(event.screenPos())
                if chosen is None:
                    return
                if chosen == rename_act:
                    self._rename_exit_point(model)
                elif chosen == color_act:
                    self._change_exit_point_color(model)
                elif chosen == del_act and exit_count > 1:
                    self._delete_exit_point(item.state_vm, model)

            else:
                delete_act = menu.addAction(f"'{model.name}' 삭제")
                if menu.exec(event.screenPos()) == delete_act:
                    self._delete_state(item.state_vm)

        elif isinstance(item, ReferenceNodeItem):
            ref_name = getattr(item.ref_vm.model, "name", "?")
            del_ref_act = menu.addAction(f"참조 '{ref_name}' 삭제")
            if menu.exec(event.screenPos()) == del_ref_act:
                self.delete_reference_node(item.ref_vm)

        elif isinstance(item, ReferenceEdgeItem):
            del_link_act = menu.addAction("참조 연결 삭제")
            if menu.exec(event.screenPos()) == del_link_act:
                self.delete_reference_link(item.link_vm)

        elif isinstance(item, TransitionEdgeItem):
            self._handle_transition_edge_menu(menu, item, pos, event.screenPos())

        elif isinstance(item, WaypointHandleItem):
            self._handle_waypoint_handle_menu(menu, item, event.screenPos())

        else:
            add_exit_act = menu.addAction("ExitPoint 추가")
            if menu.exec(event.screenPos()) == add_exit_act:
                self._create_exit_point(pos)

    def _create_exit_point(self, pos: QPointF) -> None:
        from daedalus.model.fsm.pseudo import ExitPoint as _XP
        from daedalus.view.commands.exit_point_commands import AddExitPointCmd
        # 중복 이름 방지
        existing = {s.name for s in self._agent_fsm.states}
        name = "exit"
        counter = 1
        while name in existing:
            name = f"exit_{counter}"
            counter += 1
        ep = _XP(name=name)
        vm = StateViewModel(model=ep, x=pos.x(), y=pos.y())
        self._project_vm.execute(MacroCommand(
            children=[
                AddExitPointCmd(self._agent_fsm, ep),
                CreateStateCmd(self._project_vm, vm),
            ],
            description=f"ExitPoint '{name}' 추가",
        ))

    def _rename_exit_point(self, model) -> None:
        from daedalus.view.commands.exit_point_commands import RenameExitPointCmd
        view = self.views()[0] if self.views() else None
        new_name, ok = QInputDialog.getText(
            view, "ExitPoint 이름 변경", "이름:", text=model.name
        )
        if not (ok and new_name.strip() and new_name.strip() != model.name):
            return
        new_name = new_name.strip()
        existing = {s.name for s in self._agent_fsm.states if s is not model}
        if new_name in existing:
            QMessageBox.warning(view, "이름 중복", f"'{new_name}' 이름이 이미 존재합니다.")
            return
        self._project_vm.execute(RenameExitPointCmd(model, model.name, new_name))

    def _change_exit_point_color(self, model) -> None:
        from daedalus.view.commands.exit_point_commands import ChangeExitPointColorCmd
        from daedalus.view.editors.skill_editor import _ColorPickerPopup
        from PySide6.QtGui import QCursor

        view = self.views()[0] if self.views() else None
        popup = _ColorPickerPopup(parent=view)

        def _on_color(new_color: str) -> None:
            if new_color != model.color:
                self._project_vm.execute(
                    ChangeExitPointColorCmd(model, model.color, new_color)
                )
            popup.deleteLater()

        popup.color_selected.connect(_on_color)
        popup.move(QCursor.pos())
        popup.show()

    def _delete_exit_point(self, state_vm: StateViewModel, model) -> None:
        from daedalus.view.commands.exit_point_commands import DeleteExitPointCmd
        transitions = self._project_vm.get_transitions_for(state_vm)
        children: list[Command] = [
            DeleteTransitionCmd(self._project_vm, t, fsm=self._target_fsm) for t in transitions
        ]
        children.append(DeleteExitPointCmd(self._agent_fsm, model))
        children.append(DeleteStateCmd(self._project_vm, state_vm))
        self._project_vm.execute(MacroCommand(
            children=children,
            description=f"ExitPoint '{model.name}' 삭제",
        ))

    def _delete_state(self, state_vm: StateViewModel) -> None:
        """EntryPoint는 삭제 불가 — 모든 코드 경로에서 방어."""
        from daedalus.model.fsm.pseudo import EntryPoint as _EP
        if isinstance(state_vm.model, _EP):
            return
        super()._delete_state(state_vm)

    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is None:
            return
        if event.key() == Qt.Key.Key_Delete:
            from daedalus.model.fsm.pseudo import EntryPoint as _EP, ExitPoint as _XP
            selected = list(self.selectedItems())
            # 경유점 핸들 우선 처리 — 프로젝트 캔버스와 동일 (리뷰 결함 2)
            handles = [i for i in selected if isinstance(i, WaypointHandleItem)]
            if handles:
                for h in sorted(handles, key=lambda i: i.index, reverse=True):
                    self.remove_waypoint(h.edge, h.index)
                return
            # 1패스: 노드 삭제 (연결 전이는 MacroCommand로 함께 삭제됨)
            for item in selected:
                if isinstance(item, StateNodeItem):
                    model = item.state_vm.model
                    if isinstance(model, _EP):
                        continue  # EntryPoint 삭제 불가
                    if isinstance(model, _XP):
                        # 매 반복마다 재계산 — 다중 선택 시 마지막 ExitPoint 보호
                        exit_count = sum(
                            1 for s in self._agent_fsm.states if isinstance(s, _XP)
                        )
                        if exit_count <= 1:
                            continue  # 마지막 ExitPoint 삭제 불가
                        self._delete_exit_point(item.state_vm, model)
                    else:
                        self._delete_state(item.state_vm)
            # 2패스: 엣지 — 노드 삭제로 이미 제거된 전이는 중복 커맨드 금지
            for item in selected:
                if isinstance(item, TransitionEdgeItem):
                    if item.transition_vm in self._project_vm.transition_vms:
                        self._delete_transition(item.transition_vm)
                elif isinstance(item, ReferenceNodeItem):
                    self.delete_reference_node(item.ref_vm)
                elif isinstance(item, ReferenceEdgeItem):
                    self.delete_reference_link(item.link_vm)
            return
        super().keyPressEvent(event)
