# daedalus/view/canvas/scene.py
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QKeyEvent, QPen
from PyQt6.QtWidgets import (
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
from daedalus.model.fsm.section import Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.ref_edge_item import ReferenceEdgeItem
from daedalus.view.canvas.ref_node_item import ReferenceNodeItem
from daedalus.view.commands.base import Command, MacroCommand
from daedalus.view.commands.section_commands import AddSectionCmd, RemoveSectionCmd
from daedalus.view.commands.state_commands import CreateStateCmd, DeleteStateCmd, MoveStateCmd
from daedalus.view.commands.transition_commands import (
    AddSkillToProjectCmd,
    CreateTransitionCmd,
    DeleteTransitionCmd,
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
        self._ref_node_items: dict[ReferenceViewModel, ReferenceNodeItem] = {}
        self._ref_edge_items: dict[ReferenceLinkViewModel, ReferenceEdgeItem] = {}
        self._state_counter = 0
        self.setBackgroundBrush(_BG_COLOR)
        self.setSceneRect(-2000, -2000, 4000, 4000)

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
        self._sync_input_ports()
        for edge in self._edge_items.values():
            edge.update_path()
        self._rebuild_refs()

    def _sync_input_ports(self) -> None:
        """각 노드의 incoming edge 수와 edge별 input index를 할당."""
        target_groups: dict[StateNodeItem, list[TransitionEdgeItem]] = defaultdict(list)
        for edge in self._edge_items.values():
            target_groups[edge.target_node].append(edge)
        for node in self._node_items.values():
            edges = target_groups.get(node, [])
            edges.sort(key=lambda e: (
                e.transition_vm.source_vm.model.name,
                e.transition_vm.model.trigger.name if e.transition_vm.model.trigger else "",
            ))
            node.set_input_count(len(edges))
            for i, edge in enumerate(edges):
                edge.set_input_index(i)

    def update_edges_for_node(self, node: StateNodeItem) -> None:
        """노드 드래그 중 연결된 엣지 경로를 실시간 갱신."""
        for edge in self._edge_items.values():
            if edge.source_node is node or edge.target_node is node:
                edge.update_path()
        for edge in self._ref_edge_items.values():
            if edge.source_node is node:
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
                    model = Transition(
                        source=src_vm.model,
                        target=tgt_vm.model,
                        trigger=CompletionEvent(name=event_name),
                    )
                    tvm = TransitionViewModel(
                        model=model, source_vm=src_vm, target_vm=tgt_vm
                    )
                    cmds: list[Command] = [CreateTransitionCmd(self._project_vm, tvm)]
                    # call_agent 연결 시 caller/callee 양쪽에 섹션 강제 생성
                    if is_agent_call and tgt_is_agent:
                        sec_cmds = self._make_agent_call_section_cmds(src_ref, tgt_ref, event_name)
                        cmds.extend(sec_cmds)
                    if len(cmds) == 1:
                        self._project_vm.execute(cmds[0])
                    else:
                        self._project_vm.execute(MacroCommand(
                            children=cmds,
                            description=f"에이전트 호출 '{event_name}→{tgt_vm.model.name}' 연결",
                        ))

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
            tvm = item.transition_vm
            transition = tvm.model

            # On Transfer 스킬 서브메뉴
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
            new_act = transfer_menu.addAction("새 Transfer Skill 생성...") if transfer_menu is not None else None  # type: ignore[assignment]

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
                self._create_and_assign_transfer_skill(tvm)
            elif chosen == unset_act:
                self._project_vm.execute(SetTransitionSkillRefCmd(tvm, None))
            elif chosen in skill_actions:
                self._project_vm.execute(
                    SetTransitionSkillRefCmd(tvm, skill_actions[chosen])
                )
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
        ref = getattr(state_vm.model, "skill_ref", None)
        # 에이전트 노드 삭제 시: caller_contracts가 있으면 경고 + 정리
        if isinstance(ref, AgentDefinition) and ref.caller_contracts:
            view = self.views()[0] if self.views() else None
            result = QMessageBox.warning(
                view,
                "에이전트 노드 삭제",
                f"'{ref.name}'에 연결된 입력 프로시저 정보가 있습니다.\n"
                "삭제하면 저장된 입력 프로시저 정보가 모두 사라집니다.\n\n계속하시겠습니까?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if result != QMessageBox.StandardButton.Ok:
                return

        transitions = self._project_vm.get_transitions_for(state_vm)
        children: list[Command] = []
        # 연결된 전이의 caller_contracts 섹션 정리
        for t in transitions:
            src_ref = getattr(t.source_vm.model, "skill_ref", None)
            tgt_ref = getattr(t.target_vm.model, "skill_ref", None)
            trigger = t.model.trigger
            event_name = trigger.name if trigger is not None else ""
            if isinstance(src_ref, ProceduralSkill) and isinstance(tgt_ref, AgentDefinition):
                children.extend(self._find_agent_call_section_cmds(src_ref, tgt_ref, event_name))
            children.append(DeleteTransitionCmd(self._project_vm, t))
        children.append(DeleteStateCmd(self._project_vm, state_vm))
        self._project_vm.execute(
            MacroCommand(children=children, description=f"상태 '{state_vm.model.name}' 삭제")
        )

    def _delete_transition(self, tvm: TransitionViewModel) -> None:
        src_ref = getattr(tvm.source_vm.model, "skill_ref", None)
        tgt_ref = getattr(tvm.target_vm.model, "skill_ref", None)
        trigger = tvm.model.trigger
        event_name = trigger.name if trigger is not None else ""
        if isinstance(src_ref, ProceduralSkill) and isinstance(tgt_ref, AgentDefinition):
            sec_cmds = self._find_agent_call_section_cmds(src_ref, tgt_ref, event_name)
            cmds: list[Command] = sec_cmds + [DeleteTransitionCmd(self._project_vm, tvm)]
            self._project_vm.execute(MacroCommand(
                children=cmds,
                description=f"에이전트 호출 '{event_name}→{tgt_ref.name}' 삭제",
            ))
        else:
            self._project_vm.execute(DeleteTransitionCmd(self._project_vm, tvm))

    # --- call_agent 섹션 관리 ---

    @staticmethod
    def _callee_section_title(skill_name: str, event_name: str) -> str:
        return f"caller: {skill_name} ({event_name})"

    def _make_agent_call_section_cmds(
        self, src_ref: object, tgt_ref: object, event_name: str
    ) -> list[Command]:
        """call_agent 연결 시 에이전트 측 caller_contracts에 섹션 추가."""
        cmds: list[Command] = []
        if not isinstance(src_ref, ProceduralSkill) or not isinstance(tgt_ref, AgentDefinition):
            return cmds
        callee_title = self._callee_section_title(src_ref.name, event_name)
        if not any(s.title == callee_title for s in tgt_ref.caller_contracts):
            cmds.append(AddSectionCmd(
                tgt_ref.caller_contracts,
                Section(title=callee_title, content=""),
            ))
        return cmds

    def _find_agent_call_section_cmds(
        self, src_ref: object, tgt_ref: object, event_name: str
    ) -> list[Command]:
        """call_agent 삭제 시 에이전트 측 caller_contracts에서 섹션 제거."""
        cmds: list[Command] = []
        if not isinstance(src_ref, ProceduralSkill) or not isinstance(tgt_ref, AgentDefinition):
            return cmds
        callee_title = self._callee_section_title(src_ref.name, event_name)
        for sec in tgt_ref.caller_contracts:
            if sec.title == callee_title:
                cmds.append(RemoveSectionCmd(tgt_ref.caller_contracts, sec))
                break
        return cmds

    def set_project(self, project: PluginProject) -> None:
        self._project = project

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
        """참조 스킬을 캔버스에 드롭 — 여러 인스턴스 허용."""
        from daedalus.model.project import ReferencePlacement
        if self._skill_lookup is None:
            return
        skill = self._skill_lookup(skill_name)
        if not isinstance(skill, ReferenceSkill):
            return
        rvm = ReferenceViewModel(model=skill, x=scene_pos.x(), y=scene_pos.y())
        self._project_vm.reference_vms.append(rvm)
        # 모델 동기화
        self._get_ref_placements().append(
            ReferencePlacement(skill_name=skill_name, x=scene_pos.x(), y=scene_pos.y())
        )
        self._project_vm.notify()

    def create_reference_link(
        self, state_vm: StateViewModel, ref_vm: ReferenceViewModel
    ) -> None:
        """상태 노드 → 참조 노드 연결 생성 (같은 스킬 중복 방지)."""
        ref_skill = ref_vm.model
        duplicate = any(
            l.state_vm is state_vm and l.reference_vm.model is ref_skill
            for l in self._project_vm.reference_links
        )
        if not duplicate:
            lvm = ReferenceLinkViewModel(state_vm=state_vm, reference_vm=ref_vm)
            self._project_vm.reference_links.append(lvm)
            # 모델 동기화
            self._sync_refs_to_model()
            self._project_vm.notify()

    def delete_reference_node(self, ref_vm: ReferenceViewModel) -> None:
        """참조 노드 + 연결된 링크 삭제."""
        self._project_vm.reference_links = [
            l for l in self._project_vm.reference_links if l.reference_vm is not ref_vm
        ]
        if ref_vm in self._project_vm.reference_vms:
            self._project_vm.reference_vms.remove(ref_vm)
        self._sync_refs_to_model()
        self._project_vm.notify()

    def delete_reference_link(self, lvm: ReferenceLinkViewModel) -> None:
        if lvm in self._project_vm.reference_links:
            self._project_vm.reference_links.remove(lvm)
            self._sync_refs_to_model()
            self._project_vm.notify()

    def _sync_refs_to_model(self) -> None:
        """뷰 모델 → 모델 동기화. 위치 + 연결 정보를 모델에 반영."""
        from daedalus.model.project import ReferencePlacement
        placements = self._get_ref_placements()
        placements.clear()
        for rvm in self._project_vm.reference_vms:
            skill_name = getattr(rvm.model, "name", "")
            connected = [
                l.state_vm.model.name
                for l in self._project_vm.reference_links
                if l.reference_vm is rvm
            ]
            placements.append(ReferencePlacement(
                skill_name=skill_name, x=rvm.x, y=rvm.y,
                connected_states=connected,
            ))

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
            for item in list(self.selectedItems()):
                if isinstance(item, StateNodeItem):
                    self._delete_state(item.state_vm)
                elif isinstance(item, TransitionEdgeItem):
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
        agent_skills: list | None = None,
        agent_ref_placements: list | None = None,
    ) -> None:
        super().__init__(project_vm, skill_lookup=skill_lookup)
        self._agent_fsm = agent_fsm
        self._agent_skills: list = agent_skills if agent_skills is not None else []
        self._agent_ref_placements: list = agent_ref_placements if agent_ref_placements is not None else []

    def _create_node_item(self, vm: StateViewModel) -> StateNodeItem:
        return StateNodeItem(vm, show_call_agents=False)

    def _get_ref_placements(self) -> list:
        return self._agent_ref_placements

    def _get_transfer_skills(self) -> list:
        """에이전트 로컬 Transfer 스킬 목록."""
        return [s for s in self._agent_skills if isinstance(s, TransferSkill)]

    def _create_and_assign_transfer_skill(self, tvm: TransitionViewModel) -> None:
        """로컬 Transfer 스킬 생성 후 전이에 할당."""
        existing = {s.name for s in self._agent_skills}
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
        self._agent_skills.append(skill)
        self._project_vm.execute(SetTransitionSkillRefCmd(tvm, skill))

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
            del_trans_act = menu.addAction("전이 삭제")
            chosen = menu.exec(event.screenPos())
            if chosen is None:
                return
            if chosen == del_trans_act:
                self._delete_transition(tvm)
            elif chosen == new_act:
                self._create_and_assign_transfer_skill(tvm)
            elif chosen == unset_act:
                self._project_vm.execute(SetTransitionSkillRefCmd(tvm, None))
            elif chosen in skill_actions:
                self._project_vm.execute(
                    SetTransitionSkillRefCmd(tvm, skill_actions[chosen])
                )

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
        from PyQt6.QtGui import QCursor

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
            DeleteTransitionCmd(self._project_vm, t) for t in transitions
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
            for item in list(self.selectedItems()):
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
                elif isinstance(item, TransitionEdgeItem):
                    self._delete_transition(item.transition_vm)
                elif isinstance(item, ReferenceNodeItem):
                    self.delete_reference_node(item.ref_vm)
                elif isinstance(item, ReferenceEdgeItem):
                    self.delete_reference_link(item.link_vm)
            return
        super().keyPressEvent(event)
