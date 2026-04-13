# daedalus/view/editors/agent_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
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


class _MiniRegistry(QWidget):
    """에이전트 로컬 스킬 목록 + '＋ 새 스킬' 버튼."""

    skill_added = pyqtSignal(str)

    def __init__(
        self,
        agent: AgentDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._agent = agent

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        hdr = QLabel("로컬 스킬")
        lay.addWidget(hdr)

        self._list = QListWidget()
        self._rebuild()
        lay.addWidget(self._list, 1)

        add_btn = QPushButton("＋ 새 스킬")
        add_btn.clicked.connect(self._on_add_skill)
        lay.addWidget(add_btn)

    def _rebuild(self) -> None:
        self._list.clear()
        for skill in self._agent.skills:
            self._list.addItem(skill.name)

    def _on_add_skill(self) -> None:
        self.skill_added.emit("")


class AgentEditor(QWidget):
    """AgentDefinition 편집기 — Graph / Content / Config 탭."""

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

        # Tab 1: Content
        content_tab = self._build_content_tab()
        self._tabs.addTab(content_tab, "📝 Content")

        # Tab 2: Config
        config_tab = _FrontmatterPanel(agent)
        config_tab.changed.connect(self._on_model_changed)
        self._tabs.addTab(config_tab, "⚙ Config")

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

        # 미니 레지스트리 (좌측 사이드바)
        self._mini_registry = _MiniRegistry(self._agent)
        splitter.addWidget(self._mini_registry)

        # 캔버스 (우측)
        self._graph_vm = ProjectViewModel()
        self._graph_vm.add_listener(self._on_model_changed)
        self._graph_scene = AgentFsmScene(self._graph_vm, agent_fsm=self._agent.fsm)
        self._canvas_view = FsmCanvasView(self._graph_scene)
        splitter.addWidget(self._canvas_view)

        splitter.setStretchFactor(0, 0)  # registry: 고정폭
        splitter.setStretchFactor(1, 1)  # canvas: 확장

        lay.addWidget(splitter)
        self._load_agent_fsm()
        return container

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

    def _build_content_tab(self) -> QWidget:
        """Content 탭: SectionTree + BreadcrumbNav + SectionContentPanel."""
        container = QWidget()
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: SectionTree
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

        self._stack = QStackedWidget()

        self._content_panel = SectionContentPanel()
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._stack.addWidget(self._content_panel)

        right_lay.addWidget(self._stack, 1)
        splitter.addWidget(right_area)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        lay.addWidget(splitter)

        # Variable popup (parented to content_panel)
        self._var_popup = VariablePopup(self._variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        return container

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
        self._stack.setCurrentIndex(0)

    def _on_tree_selected(self, section: Section, path: list[str]) -> None:
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path)
        self._stack.setCurrentIndex(0)

    def _on_breadcrumb_selected(self, section: Section, path: list[str]) -> None:
        self._section_tree.select_section(section)
        self._content_panel.show_section(section, path)
        self._stack.setCurrentIndex(0)

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
        self.agent_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
