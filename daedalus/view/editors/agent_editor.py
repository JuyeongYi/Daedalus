# daedalus/view/editors/agent_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.project import PluginProject

from daedalus.view.panels.registry_panel import _RegistrySection


class AgentEditor(QWidget):
    """AgentDefinition 편집기 — Graph / Content(+Config) 탭."""

    agent_changed = pyqtSignal()

    def __init__(
        self,
        agent: AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        project: PluginProject | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent
        self._on_notify_fn = on_notify_fn
        self._project = project

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        root_lay.addWidget(self._tabs)

        # Tab 0: Graph
        graph_tab = self._build_graph_tab()
        self._tabs.addTab(graph_tab, "📐 Graph")

        # Tab 1: Content + Config (SkillEditor와 동일한 UX)
        content_tab = self._build_content_tab()
        self._tabs.addTab(content_tab, "📝 Content")

        # ComponentEditor handles initial section selection internally

    # ------------------------------------------------------------------ #
    # Tab builders                                                          #
    # ------------------------------------------------------------------ #

    def _build_graph_tab(self) -> QWidget:
        """Graph 탭: Procedural/Transfer 레지스트리(좌) + FsmCanvasView(우)."""
        from daedalus.view.canvas.canvas_view import FsmCanvasView
        from daedalus.view.canvas.scene import AgentFsmScene
        from daedalus.view.viewmodel.project_vm import ProjectViewModel

        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 좌측 사이드바: Procedural + Transfer 레지스트리
        sidebar = QWidget()
        sidebar.setMinimumWidth(130)
        sidebar_lay = QVBoxLayout(sidebar)
        sidebar_lay.setContentsMargins(0, 0, 0, 0)
        sidebar_lay.setSpacing(2)

        self._proc_section = _RegistrySection("⚙ PROCEDURAL", QColor("#88cc88"))
        self._proc_section.add_requested.connect(lambda: self._on_add_local_skill("procedural"))
        self._proc_section.item_double_clicked.connect(self._open_local_skill)
        sidebar_lay.addWidget(self._proc_section)

        self._transfer_section = _RegistrySection("⚡ TRANSFER", QColor("#88aacc"), no_place=True)
        self._transfer_section.add_requested.connect(lambda: self._on_add_local_skill("transfer"))
        self._transfer_section.item_double_clicked.connect(self._open_local_skill)
        sidebar_lay.addWidget(self._transfer_section)

        self._ref_section = _RegistrySection("📖 REFERENCE (global)", QColor("#66aaaa"))
        self._ref_section.item_double_clicked.connect(self._open_local_skill)
        sidebar_lay.addWidget(self._ref_section)

        sidebar_lay.addStretch(1)
        splitter.addWidget(sidebar)

        # 캔버스 (우측)
        self._graph_vm = ProjectViewModel()
        self._graph_vm.add_listener(self._on_model_changed)
        self._graph_scene = AgentFsmScene(
            self._graph_vm,
            agent_fsm=self._agent.fsm,
            skill_lookup=self._local_skill_lookup,
            agent_skills=self._agent.skills,
            agent_ref_placements=self._agent.reference_placements,
        )
        self._canvas_view = FsmCanvasView(self._graph_scene)
        self._graph_scene.node_double_clicked.connect(self._open_local_skill)
        splitter.addWidget(self._canvas_view)

        splitter.setStretchFactor(0, 0)  # sidebar: 고정폭
        splitter.setStretchFactor(1, 1)  # canvas: 확장

        lay.addWidget(splitter)
        self._open_skill_tabs: dict[str, int] = {}
        self._migrate_fsm()
        self._load_agent_fsm()
        self._refresh_skill_list()
        QTimer.singleShot(0, self._canvas_view.fit_to_content)
        return container

    def _migrate_fsm(self) -> None:
        """기존 에이전트 FSM 마이그레이션.

        - EntryPoint/ExitPoint가 없으면 추가
        - skill_ref 없는 일반 SimpleState 제거 (구버전 잔재)
        """
        from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
        from daedalus.model.fsm.state import SimpleState

        fsm = self._agent.fsm
        # 1) skill_ref 없는 SimpleState 제거
        orphans = [
            s for s in fsm.states
            if isinstance(s, SimpleState) and (not hasattr(s, "skill_ref") or s.skill_ref is None)
        ]
        for s in orphans:
            fsm.states.remove(s)
            # 연결된 전이도 제거
            fsm.transitions = [
                t for t in fsm.transitions if t.source is not s and t.target is not s
            ]
        # 2) EntryPoint 없으면 추가
        if not any(isinstance(s, EntryPoint) for s in fsm.states):
            entry = EntryPoint(name="entry")
            fsm.states.insert(0, entry)
            fsm.initial_state = entry
        # 3) ExitPoint 없으면 추가
        if not any(isinstance(s, ExitPoint) for s in fsm.states):
            exit_done = ExitPoint(name="done")
            fsm.states.append(exit_done)
            fsm.final_states.append(exit_done)

    def _load_agent_fsm(self) -> None:
        """에이전트 FSM 상태를 Graph VM에 로드. 저장된 레이아웃이 있으면 복원."""
        from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
        from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

        entries = []
        exits = []
        others = []
        for state in self._agent.fsm.states:
            if isinstance(state, EntryPoint):
                entries.append(state)
            elif isinstance(state, ExitPoint):
                exits.append(state)
            else:
                others.append(state)

        # EntryPoint(좌) → 일반 노드(중간) → ExitPoint(우)
        ordered = entries + others + exits
        saved = self._agent.graph_layout
        x = 0.0
        vm_map: dict[str, StateViewModel] = {}
        for state in ordered:
            if state.name in saved:
                sx, sy = saved[state.name]
                vm = StateViewModel(model=state, x=sx, y=sy)
            else:
                vm = StateViewModel(model=state, x=x, y=100.0)
            self._graph_vm.state_vms.append(vm)
            vm_map[state.name] = vm
            x += 220.0

        for trans in self._agent.fsm.transitions:
            src_vm = vm_map.get(trans.source.name)
            tgt_vm = vm_map.get(trans.target.name)
            if src_vm and tgt_vm:
                tvm = TransitionViewModel(model=trans, source_vm=src_vm, target_vm=tgt_vm)
                self._graph_vm.transition_vms.append(tvm)
        self._graph_vm.notify()

    def _save_graph_layout(self) -> None:
        """그래프 노드 위치를 모델에 저장."""
        layout: dict[str, list[float]] = {}
        for svm in self._graph_vm.state_vms:
            layout[svm.model.name] = [svm.x, svm.y]
        self._agent.graph_layout = layout

    def _local_skill_lookup(self, name: str) -> object | None:
        for skill in self._agent.skills:
            if skill.name == name:
                return skill
        # 전역 참조 스킬 탐색
        if self._project is not None:
            for skill in self._project.skills:
                if skill.name == name:
                    from daedalus.model.plugin.skill import ReferenceSkill
                    if isinstance(skill, ReferenceSkill):
                        return skill
        return None

    def _refresh_skill_list(self) -> None:
        from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill, TransferSkill
        self._proc_section.clear()
        self._transfer_section.clear()
        self._ref_section.clear()
        placed_ids: set[int] = set()
        for svm in self._graph_vm.state_vms:
            if hasattr(svm.model, "skill_ref") and svm.model.skill_ref is not None:
                placed_ids.add(id(svm.model.skill_ref))  # type: ignore[union-attr]
        for skill in self._agent.skills:
            placed = id(skill) in placed_ids
            if isinstance(skill, TransferSkill):
                self._transfer_section.add_item(skill, placed)
            elif not isinstance(skill, ReferenceSkill):
                self._proc_section.add_item(skill, placed)
        # 참조 스킬은 전역 프로젝트에서 가져옴
        if self._project is not None:
            for skill in self._project.skills:
                if isinstance(skill, ReferenceSkill):
                    self._ref_section.add_item(skill, placed=False)

    def _on_add_local_skill(self, kind: str) -> None:
        name, ok = QInputDialog.getText(self, "새 로컬 스킬", "이름:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(s.name == name for s in self._agent.skills):
            QMessageBox.warning(self, "이름 중복", f"'{name}' 스킬이 이미 존재합니다.")
            return
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill
        s = SimpleState(name="start")
        fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
        if kind == "procedural":
            skill = ProceduralSkill(fsm=fsm, name=name, description="")
        else:
            skill = TransferSkill(fsm=fsm, name=name, description="")
        self._agent.skills.append(skill)
        self._refresh_skill_list()
        self._on_model_changed()

    def _open_local_skill(self, component: object) -> None:
        from daedalus.view.editors.skill_editor import SkillEditor
        name = getattr(component, "name", None)
        if name is None:
            return
        if name in self._open_skill_tabs:
            self._tabs.setCurrentIndex(self._open_skill_tabs[name])
            return
        editor = SkillEditor(component, on_notify_fn=self._on_model_changed, show_call_agents=False)  # type: ignore[arg-type]
        idx = self._tabs.addTab(editor, f"⚙ {name}")
        self._open_skill_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _build_content_tab(self) -> QWidget:
        """Content 탭: ComponentEditor + caller_contracts 우측 패널."""
        from daedalus.view.editors.component_editor import ComponentEditor
        from daedalus.view.editors.skill_editor import _ContractButtons

        right_widgets: list[QWidget] = []
        self._caller_contract_buttons = _ContractButtons(
            "🔒 입력 프로시저", self._agent.caller_contracts,
        )
        right_widgets.append(self._caller_contract_buttons)

        self._component_editor = ComponentEditor(
            self._agent,
            right_widgets=right_widgets,
            on_notify_fn=self._on_model_changed,
        )

        self._caller_contract_buttons.section_clicked.connect(
            self._component_editor.show_contract_section
        )

        return self._component_editor

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """탭 닫힘 시 씬 리스너를 해제해 메모리 누수 방지."""
        self._graph_scene.close()
        super().closeEvent(event)  # type: ignore[arg-type]

    def _on_model_changed(self) -> None:
        if hasattr(self, "_graph_vm"):
            self._save_graph_layout()
        if hasattr(self, "_proc_section"):
            self._refresh_skill_list()
        if hasattr(self, "_caller_contract_buttons"):
            self._caller_contract_buttons.refresh()
        self.agent_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
