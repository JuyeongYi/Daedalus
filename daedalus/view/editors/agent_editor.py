# daedalus/view/editors/agent_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
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

from daedalus.model.fsm.section import Section
from daedalus.model.plugin.agent import AgentDefinition

from daedalus.view.editors.body_editor import (
    BreadcrumbNav,
    SectionContentPanel,
    SectionTree,
    VariablePopup,
    find_path,
)
from daedalus.view.editors.skill_editor import _FrontmatterPanel
from daedalus.view.editors.variable_loader import load_variables
from daedalus.view.panels.registry_panel import _RegistrySection


class AgentEditor(QWidget):
    """AgentDefinition 편집기 — Graph / Content(+Config) 탭."""

    agent_changed = pyqtSignal()

    def __init__(
        self,
        agent: AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent
        self._on_notify_fn = on_notify_fn
        self._variables = load_variables()

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

        # Initial section selection
        if agent.sections:
            self._select_section(agent.sections[0])

    # ------------------------------------------------------------------ #
    # Tab builders                                                          #
    # ------------------------------------------------------------------ #

    def _build_graph_tab(self) -> QWidget:
        """Graph 탭: 미니 레지스트리(좌) + FsmCanvasView(우)."""
        from daedalus.view.canvas.canvas_view import FsmCanvasView
        from daedalus.view.canvas.scene import AgentFsmScene
        from daedalus.view.viewmodel.project_vm import ProjectViewModel

        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 로컬 스킬 레지스트리 (좌측 사이드바)
        self._skill_section = _RegistrySection("Local Skills", QColor("#4a8a4a"))
        self._skill_section.add_requested.connect(self._on_add_local_skill)
        self._skill_section.item_double_clicked.connect(self._open_local_skill)
        self._skill_section.setMinimumWidth(120)
        self._skill_section.setMaximumWidth(200)
        splitter.addWidget(self._skill_section)

        # 캔버스 (우측)
        self._graph_vm = ProjectViewModel()
        self._graph_vm.add_listener(self._on_model_changed)
        self._graph_scene = AgentFsmScene(self._graph_vm, agent_fsm=self._agent.fsm)
        self._canvas_view = FsmCanvasView(self._graph_scene)
        splitter.addWidget(self._canvas_view)

        splitter.setStretchFactor(0, 0)  # registry: 고정폭
        splitter.setStretchFactor(1, 1)  # canvas: 확장

        lay.addWidget(splitter)
        self._open_skill_tabs: dict[str, int] = {}
        self._migrate_fsm()
        self._load_agent_fsm()
        self._refresh_skill_list()
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
        """에이전트 FSM 상태를 Graph VM에 로드."""
        from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
        x_offset = 0.0
        vm_map: dict[str, StateViewModel] = {}
        for state in self._agent.fsm.states:
            vm = StateViewModel(model=state, x=x_offset, y=100.0)
            self._graph_vm.state_vms.append(vm)
            vm_map[state.name] = vm
            x_offset += 220.0
        for trans in self._agent.fsm.transitions:
            src_vm = vm_map.get(trans.source.name)
            tgt_vm = vm_map.get(trans.target.name)
            if src_vm and tgt_vm:
                tvm = TransitionViewModel(model=trans, source_vm=src_vm, target_vm=tgt_vm)
                self._graph_vm.transition_vms.append(tvm)
        self._graph_vm.notify()

    def _refresh_skill_list(self) -> None:
        self._skill_section.clear()
        placed_ids: set[int] = set()
        for svm in self._graph_vm.state_vms:
            if hasattr(svm.model, "skill_ref") and svm.model.skill_ref is not None:
                placed_ids.add(id(svm.model.skill_ref))  # type: ignore[union-attr]
        for skill in self._agent.skills:
            self._skill_section.add_item(skill, id(skill) in placed_ids)

    def _on_add_local_skill(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        act_proc = menu.addAction("Procedural Skill")
        act_trans = menu.addAction("Transfer Skill")
        cursor_pos = self._skill_section.mapToGlobal(
            self._skill_section.rect().bottomLeft()
        )
        chosen = menu.exec(cursor_pos)
        if chosen is None:
            return
        kind = "procedural" if chosen == act_proc else "transfer" if chosen == act_trans else None
        if kind is None:
            return
        name, ok = QInputDialog.getText(self, "New local skill", "Name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(s.name == name for s in self._agent.skills):
            QMessageBox.warning(self, "Name conflict", f"'{name}' already exists.")
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
        editor = SkillEditor(component, on_notify_fn=self._on_model_changed)  # type: ignore[arg-type]
        idx = self._tabs.addTab(editor, f"⚙ {name}")
        self._open_skill_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _build_content_tab(self) -> QWidget:
        """Content 탭: FrontmatterPanel(좌) + SectionTree(중) + ContentPanel(우).

        SkillEditor와 동일한 3-column QSplitter 레이아웃.
        """
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: FrontmatterPanel (name / description / config 필드)
        self._fm_panel = _FrontmatterPanel(self._agent)
        self._fm_panel.changed.connect(self._on_model_changed)
        splitter.addWidget(self._fm_panel)

        # Center: SectionTree
        self._section_tree = SectionTree(self._agent.sections)
        self._section_tree.section_selected.connect(self._on_tree_selected)
        self._section_tree.structure_changed.connect(self._on_structure_changed)
        self._section_tree.add_root_requested.connect(
            lambda: self._on_breadcrumb_add(None, 0)
        )
        splitter.addWidget(self._section_tree)

        # Right: BreadcrumbNav + SectionContentPanel
        right_area = QWidget()
        right_lay = QVBoxLayout(right_area)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self._breadcrumb = BreadcrumbNav(self._agent.sections)
        self._breadcrumb.section_selected.connect(self._on_breadcrumb_selected)
        self._breadcrumb.section_add_requested.connect(self._on_breadcrumb_add)
        right_lay.addWidget(self._breadcrumb)

        self._content_panel = SectionContentPanel()
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        right_lay.addWidget(self._content_panel, 1)

        splitter.addWidget(right_area)

        splitter.setStretchFactor(0, 0)  # frontmatter: 고정폭
        splitter.setStretchFactor(1, 0)  # tree: 고정폭
        splitter.setStretchFactor(2, 1)  # content: 확장

        lay.addWidget(splitter)

        # Variable popup (parented to content_panel)
        self._var_popup = VariablePopup(self._variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        return container

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """탭 닫힘 시 씬 리스너를 해제해 메모리 누수 방지."""
        self._graph_scene.close()
        super().closeEvent(event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #
    # Bidirectional sync (Content tab)                                     #
    # ------------------------------------------------------------------ #

    def _select_section(self, section: Section) -> None:
        path = find_path(section, self._agent.sections)
        if path is None:
            return
        path_titles = [s.title for s in path]
        self._section_tree.select_section(section)
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path_titles)

    def _on_tree_selected(self, section: Section, path: list[str]) -> None:
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path)

    def _on_breadcrumb_selected(self, section: Section, path: list[str]) -> None:
        self._section_tree.select_section(section)
        self._content_panel.show_section(section, path)

    def _on_breadcrumb_add(self, parent: Section | None, _depth: int = 0) -> None:
        siblings = self._agent.sections if parent is None else parent.children
        existing_names = {s.title for s in siblings}

        while True:
            name, ok = QInputDialog.getText(self, "섹션 추가", "섹션 이름:")
            if not ok or not name.strip():
                return
            name = name.strip()
            if name in existing_names:
                QMessageBox.warning(self, "이름 중복", f"'{name}' 섹션이 이미 존재합니다.")
                continue
            break

        new = Section(title=name)
        siblings.append(new)
        self._on_structure_changed()
        self._select_section(new)

    def _on_structure_changed(self) -> None:
        self._section_tree.set_sections(self._agent.sections)
        self._breadcrumb.set_sections(self._agent.sections)
        self._on_model_changed()

    def _on_content_changed(self) -> None:
        self._section_tree.set_sections(self._agent.sections)
        self._breadcrumb.set_sections(self._agent.sections)
        self._on_model_changed()

    def _on_variable_insert(self) -> None:
        if self._var_popup.isVisible():
            self._var_popup.hide()
            return
        from PyQt6.QtCore import QPoint
        btn = self._content_panel._btn_variable
        pos = btn.mapTo(self._content_panel, QPoint(0, btn.height()))
        self._var_popup.move(pos)
        self._var_popup.show()
        self._var_popup.raise_()

    def _on_model_changed(self) -> None:
        if hasattr(self, "_skill_section"):
            self._refresh_skill_list()
        self.agent_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
