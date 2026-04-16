# Agent Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에이전트 서브그래프를 별도 탭에서 편집할 수 있는 UI 구현 (EntryPoint/ExitPoint 기반, 에이전트 로컬 스킬)

**Architecture:** 모델 변경(ExitPoint.color, AgentDefinition에서 transfer_on 제거) → 노드 렌더링 확장(pseudo state) → ExitPoint 커맨드 → AgentEditor 위젯(Graph/Content/Config 탭) → app.py 라우팅 통합

**Tech Stack:** Python 3.12, PyQt6, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-04-13-agent-graph-design.md`

---

## File Structure

**Create:**
| File | Responsibility |
|------|----------------|
| `daedalus/view/editors/agent_editor.py` | AgentEditor 위젯 (Graph/Content/Config 탭) |
| `daedalus/view/commands/exit_point_commands.py` | ExitPoint 추가/삭제/이름변경/색상변경 커맨드 |
| `tests/view/editors/test_agent_editor.py` | AgentEditor 테스트 |
| `tests/view/commands/test_exit_point_commands.py` | ExitPoint 커맨드 테스트 |

**Modify:**
| File | Change |
|------|--------|
| `daedalus/model/fsm/pseudo.py:47-52` | ExitPoint에 color 필드 추가 |
| `daedalus/model/plugin/agent.py:12-35` | transfer_on 제거, skills 추가, output_events를 ExitPoint에서 파생 |
| `daedalus/view/canvas/node_item.py:20-25,50-62,149-168` | _TYPE_STYLE 확장, _event_defs 분기, 포트 제한 |
| `daedalus/view/canvas/scene.py` | AgentFsmScene 서브클래스 추가 |
| `daedalus/view/app.py:176-189` | AgentDefinition → AgentEditor 라우팅 |
| `tests/model/fsm/test_pseudo.py` | ExitPoint.color 테스트 추가 |
| `tests/model/plugin/test_agent.py` | transfer_on 테스트 → ExitPoint 기반으로 교체 |

---

### Task 1: ExitPoint.color 모델 변경

**Files:**
- Modify: `daedalus/model/fsm/pseudo.py:47-52`
- Test: `tests/model/fsm/test_pseudo.py`

- [ ] **Step 1: Write the failing test**

`tests/model/fsm/test_pseudo.py`에 추가:

```python
def test_exit_point_default_color():
    xp = ExitPoint(name="done")
    assert xp.color == "#4488ff"


def test_exit_point_custom_color():
    xp = ExitPoint(name="error", color="#cc3333")
    assert xp.color == "#cc3333"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/fsm/test_pseudo.py::test_exit_point_default_color -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'color'`

- [ ] **Step 3: Add color field to ExitPoint**

`daedalus/model/fsm/pseudo.py` ExitPoint 수정:

```python
@dataclass
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
    color: str = "#4488ff"

    @property
    def kind(self) -> str:
        return "exit_point"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/fsm/test_pseudo.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/pseudo.py tests/model/fsm/test_pseudo.py
git commit -m "feat(model): add color field to ExitPoint for port color rendering"
```

---

### Task 2: AgentDefinition 모델 리팩터

**Files:**
- Modify: `daedalus/model/plugin/agent.py`
- Test: `tests/model/plugin/test_agent.py`

- [ ] **Step 1: Write the failing tests**

`tests/model/plugin/test_agent.py` 수정. 기존 `_make_fsm`, `test_agent_sections_default`, `test_agent_transfer_on_default`, `test_agent_output_events_default`, `test_agent_output_events_via_property` 삭제 후 교체:

```python
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint

def _make_agent_fsm():
    """에이전트 기본 FSM — EntryPoint + ExitPoint."""
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm",
        states=[entry, exit_done],
        initial_state=entry,
        final_states=[exit_done],
    )


def test_agent_sections_default():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert len(agent.sections) == 1
    assert agent.sections[0].title == "instruction"


def test_agent_no_transfer_on():
    """AgentDefinition에 transfer_on 필드가 없어야 함."""
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert not hasattr(agent, "transfer_on")


def test_agent_output_events_from_exit_points():
    """output_events는 FSM의 ExitPoint 이름에서 파생."""
    entry = EntryPoint(name="entry")
    exit_ok = ExitPoint(name="success")
    exit_err = ExitPoint(name="error")
    fsm = StateMachine(
        name="f",
        states=[entry, exit_ok, exit_err],
        initial_state=entry,
        final_states=[exit_ok, exit_err],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert set(agent.output_events) == {"success", "error"}


def test_agent_exit_points_property():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done", color="#44aa44")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert len(agent.exit_points) == 1
    assert agent.exit_points[0].name == "done"
    assert agent.exit_points[0].color == "#44aa44"


def test_agent_output_event_defs():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done", color="#44aa44")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    defs = agent.output_event_defs
    assert len(defs) == 1
    assert defs[0].name == "done"
    assert defs[0].color == "#44aa44"


def test_agent_skills_default():
    fsm = _make_agent_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.skills == []
```

기존 `test_agent_definition`, `test_agent_execution_policy_default`, `test_agent_execution_policy_parallel`은 `transfer_on`을 사용하지 않으므로 유지. 단, `_make_fsm`을 사용하는 테스트는 `_make_agent_fsm`으로 교체.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/plugin/test_agent.py -v`
Expected: FAIL — `transfer_on` 여전히 존재, `exit_points`/`output_event_defs` 미정의

- [ ] **Step 3: Refactor AgentDefinition**

`daedalus/model/plugin/agent.py` 전체 교체:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy

if TYPE_CHECKING:
    from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, execution_policy, sections, skills (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    sections: list[Section] = field(
        default_factory=lambda: [Section(title="instruction")]
    )
    skills: list[ProceduralSkill | TransferSkill] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "agent"

    @property
    def exit_points(self) -> list[ExitPoint]:
        """sub_machine의 ExitPoint 목록."""
        return [s for s in self.fsm.states if isinstance(s, ExitPoint)]

    @property
    def output_events(self) -> list[str]:
        """ExitPoint 이름 목록 (StateNodeItem 호환)."""
        return [ep.name for ep in self.exit_points]

    @property
    def output_event_defs(self) -> list[EventDef]:
        """노드 포트 렌더링용 — ExitPoint에서 EventDef 변환."""
        return [EventDef(name=ep.name, color=ep.color) for ep in self.exit_points]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/plugin/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: `transfer_on` 참조하는 다른 곳에서 실패 가능 — 다음 태스크에서 수정

- [ ] **Step 6: Commit**

```bash
git add daedalus/model/plugin/agent.py tests/model/plugin/test_agent.py
git commit -m "refactor(model): remove transfer_on from AgentDefinition, derive outputs from ExitPoints"
```

---

### Task 3: StateNodeItem의 EntryPoint/ExitPoint 렌더링

**Files:**
- Modify: `daedalus/view/canvas/node_item.py:20-25,50-62,149-168`
- Test: `tests/view/editors/test_skill_editor.py`

- [ ] **Step 1: Write the failing test**

`tests/view/editors/test_skill_editor.py`에 추가:

```python
def test_node_item_entry_point_style(qapp):
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    assert "entry_point" in _TYPE_STYLE


def test_node_item_exit_point_style(qapp):
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    assert "exit_point" in _TYPE_STYLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/view/editors/test_skill_editor.py::test_node_item_entry_point_style -v`
Expected: FAIL — KeyError

- [ ] **Step 3: Extend _TYPE_STYLE and add port restrictions**

`daedalus/view/canvas/node_item.py` 수정:

**3a.** Import 추가:
```python
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
```

**3b.** `_TYPE_STYLE` 확장:
```python
_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "PROCEDURAL", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    "entry_point":       ("#1a1a3a", "#4488ff", "▶ ENTRY",     ""),
    "exit_point":        ("#2a1a1a", "#cc6666", "⏹ EXIT",      ""),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}
```

**3c.** 헬퍼 메서드 추가:
```python
def _is_entry_point(self) -> bool:
    return isinstance(self._state_vm.model, EntryPoint)

def _is_exit_point(self) -> bool:
    return isinstance(self._state_vm.model, ExitPoint)
```

**3d.** `_event_defs()` 수정 — AgentDefinition의 `output_event_defs` 우선:
```python
def _event_defs(self) -> list[EventDef]:
    ref = self._state_vm.model.skill_ref
    if ref is not None and hasattr(ref, "output_event_defs"):
        return list(ref.output_event_defs)
    if ref is not None and hasattr(ref, "transfer_on"):
        return list(ref.transfer_on)
    return []
```

**3e.** `paint()` 수정 — kind 결정 로직:
```python
model = self._state_vm.model
if isinstance(model, ExitPoint):
    kind = "exit_point"
    bg_str, _, header_label, icon = _TYPE_STYLE["exit_point"]
    border_str = model.color
elif isinstance(model, EntryPoint):
    kind = "entry_point"
    bg_str, border_str, header_label, icon = _TYPE_STYLE["entry_point"]
else:
    ref = model.skill_ref if hasattr(model, "skill_ref") else None
    kind = ref.kind if ref is not None else None
    bg_str, border_str, header_label, icon = _TYPE_STYLE.get(kind, _TYPE_STYLE[None])
```

**3f.** `paint()` 수정 — 포트 조건부 렌더링:
```python
# 입력 포트 — EntryPoint이면 생략
if not self._is_entry_point():
    n_in = max(1, self._input_count)
    # ... 기존 입력 포트 렌더링 ...

# 출력 포트 — ExitPoint이면 생략
if not self._is_exit_point():
    event_defs = self._event_defs()
    # ... 기존 출력 포트 렌더링 ...
```

**3g.** `is_input_port()` 수정:
```python
def is_input_port(self, local_pos: QPointF) -> bool:
    if self._is_entry_point():
        return False
    if local_pos.x() > _PORT_R * 2:
        return False
    h = self._height()
    return _HEADER_H <= local_pos.y() <= h
```

**3h.** `_get_output_port_event()` 수정:
```python
def _get_output_port_event(self, local_pos: QPointF) -> str | None:
    if self._is_exit_point():
        return None
    events = self._output_events() or ["done"]
    # ... 기존 히트 판정 코드 ...
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/view/editors/test_skill_editor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/canvas/node_item.py tests/view/editors/test_skill_editor.py
git commit -m "feat(canvas): render EntryPoint/ExitPoint as special nodes with port restrictions"
```

---

### Task 4: ExitPoint 커맨드 (Undo/Redo)

**Files:**
- Create: `daedalus/view/commands/exit_point_commands.py`
- Create: `tests/view/commands/test_exit_point_commands.py`

- [ ] **Step 1: Write the failing tests**

`tests/view/commands/test_exit_point_commands.py` 생성:

```python
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.view.commands.exit_point_commands import (
    AddExitPointCmd,
    DeleteExitPointCmd,
    RenameExitPointCmd,
    ChangeExitPointColorCmd,
)


def _make_agent_fsm():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    return StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )


def test_add_exit_point():
    fsm = _make_agent_fsm()
    new_ep = ExitPoint(name="error", color="#cc3333")
    cmd = AddExitPointCmd(fsm, new_ep)
    cmd.execute()
    assert new_ep in fsm.states
    assert new_ep in fsm.final_states
    cmd.undo()
    assert new_ep not in fsm.states
    assert new_ep not in fsm.final_states


def test_delete_exit_point():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]  # ExitPoint("done")
    cmd = DeleteExitPointCmd(fsm, ep)
    cmd.execute()
    assert ep not in fsm.states
    assert ep not in fsm.final_states
    cmd.undo()
    assert ep in fsm.states
    assert ep in fsm.final_states


def test_rename_exit_point():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]
    cmd = RenameExitPointCmd(ep, "done", "success")
    cmd.execute()
    assert ep.name == "success"
    cmd.undo()
    assert ep.name == "done"


def test_change_exit_point_color():
    fsm = _make_agent_fsm()
    ep = fsm.states[1]
    cmd = ChangeExitPointColorCmd(ep, "#4488ff", "#cc3333")
    cmd.execute()
    assert ep.color == "#cc3333"
    cmd.undo()
    assert ep.color == "#4488ff"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/view/commands/test_exit_point_commands.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement exit point commands**

`daedalus/view/commands/exit_point_commands.py` 생성:

```python
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.view.commands.base import Command


class AddExitPointCmd(Command):
    def __init__(self, fsm: StateMachine, exit_point: ExitPoint) -> None:
        self._fsm = fsm
        self._ep = exit_point

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 추가"

    @property
    def script_repr(self) -> str:
        return f'add_exit_point("{self._ep.name}")'

    def execute(self) -> None:
        self._fsm.states.append(self._ep)
        self._fsm.final_states.append(self._ep)

    def undo(self) -> None:
        if self._ep in self._fsm.states:
            self._fsm.states.remove(self._ep)
        if self._ep in self._fsm.final_states:
            self._fsm.final_states.remove(self._ep)


class DeleteExitPointCmd(Command):
    def __init__(self, fsm: StateMachine, exit_point: ExitPoint) -> None:
        self._fsm = fsm
        self._ep = exit_point
        self._state_idx: int = -1
        self._final_idx: int = -1

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 삭제"

    @property
    def script_repr(self) -> str:
        return f'delete_exit_point("{self._ep.name}")'

    def execute(self) -> None:
        if self._ep in self._fsm.states:
            self._state_idx = self._fsm.states.index(self._ep)
            self._fsm.states.remove(self._ep)
        if self._ep in self._fsm.final_states:
            self._final_idx = self._fsm.final_states.index(self._ep)
            self._fsm.final_states.remove(self._ep)

    def undo(self) -> None:
        if self._state_idx >= 0:
            self._fsm.states.insert(self._state_idx, self._ep)
        if self._final_idx >= 0:
            self._fsm.final_states.insert(self._final_idx, self._ep)


class RenameExitPointCmd(Command):
    def __init__(self, exit_point: ExitPoint, old_name: str, new_name: str) -> None:
        self._ep = exit_point
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"ExitPoint 이름 변경: '{self._old_name}' → '{self._new_name}'"

    @property
    def script_repr(self) -> str:
        return f'rename_exit_point("{self._old_name}", "{self._new_name}")'

    def execute(self) -> None:
        self._ep.name = self._new_name

    def undo(self) -> None:
        self._ep.name = self._old_name


class ChangeExitPointColorCmd(Command):
    def __init__(self, exit_point: ExitPoint, old_color: str, new_color: str) -> None:
        self._ep = exit_point
        self._old_color = old_color
        self._new_color = new_color

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 색상 변경"

    @property
    def script_repr(self) -> str:
        return f'change_exit_point_color("{self._ep.name}", "{self._new_color}")'

    def execute(self) -> None:
        self._ep.color = self._new_color

    def undo(self) -> None:
        self._ep.color = self._old_color
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/view/commands/test_exit_point_commands.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/commands/exit_point_commands.py tests/view/commands/test_exit_point_commands.py
git commit -m "feat(commands): add ExitPoint add/delete/rename/color commands with undo"
```

---

### Task 5: AgentEditor 위젯 (Content + Config 탭)

**Files:**
- Create: `daedalus/view/editors/agent_editor.py`
- Create: `tests/view/editors/test_agent_editor.py`

- [ ] **Step 1: Write the failing tests**

`tests/view/editors/test_agent_editor.py` 생성:

```python
from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition


def _make_agent():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    fsm = StateMachine(
        name="test_fsm", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    return AgentDefinition(fsm=fsm, name="test-agent", description="테스트")


def test_agent_editor_smoke(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())


def test_agent_editor_has_three_tabs(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 3


def test_agent_editor_tab_names(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert "Graph" in tabs.tabText(0)
    assert "Content" in tabs.tabText(1)
    assert "Config" in tabs.tabText(2)


def test_agent_editor_changed_signal(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    assert hasattr(editor, "agent_changed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/view/editors/test_agent_editor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement AgentEditor (Content + Config, Graph placeholder)**

`daedalus/view/editors/agent_editor.py` 생성:

```python
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
        self._graph_tab = self._build_graph_tab()
        self._tabs.addTab(self._graph_tab, "📐 Graph")

        # Tab 1: Content
        self._content_tab = self._build_content_tab()
        self._tabs.addTab(self._content_tab, "📝 Content")

        # Tab 2: Config
        self._config_tab = _FrontmatterPanel(agent)
        self._config_tab.changed.connect(self._on_model_changed)
        self._tabs.addTab(self._config_tab, "⚙ Config")

        if agent.sections:
            self._select_section(agent.sections[0])

    # --- Graph tab ---

    def _build_graph_tab(self) -> QWidget:
        from daedalus.view.canvas.canvas_view import FsmCanvasView
        from daedalus.view.canvas.scene import AgentFsmScene
        from daedalus.view.viewmodel.project_vm import ProjectViewModel

        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Mini registry
        self._mini_registry = _MiniRegistry(self._agent)
        splitter.addWidget(self._mini_registry)

        # Canvas
        self._agent_vm = ProjectViewModel()
        self._agent_scene = AgentFsmScene(
            self._agent_vm,
            agent_fsm=self._agent.fsm,
            skill_lookup=self._agent_skill_lookup,
        )
        self._agent_vm.add_listener(self._on_model_changed)
        canvas = FsmCanvasView(self._agent_scene)
        splitter.addWidget(canvas)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter)

        self._load_agent_fsm()
        return widget

    def _load_agent_fsm(self) -> None:
        from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
        x_offset = 0.0
        for state in self._agent.fsm.states:
            vm = StateViewModel(model=state, x=x_offset, y=0.0)
            self._agent_vm.state_vms.append(vm)
            x_offset += 200.0
        for trans in self._agent.fsm.transitions:
            src_vm = self._agent_vm.get_state_vm(trans.source.name)
            tgt_vm = self._agent_vm.get_state_vm(trans.target.name)
            if src_vm and tgt_vm:
                tvm = TransitionViewModel(
                    model=trans, source_vm=src_vm, target_vm=tgt_vm
                )
                self._agent_vm.transition_vms.append(tvm)
        self._agent_vm.notify()

    def _agent_skill_lookup(self, name: str):
        for skill in self._agent.skills:
            if skill.name == name:
                return skill
        return None

    # --- Content tab ---

    def _build_content_tab(self) -> QWidget:
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._section_tree = SectionTree(self._agent.sections)
        self._section_tree.section_selected.connect(self._on_tree_selected)
        self._section_tree.structure_changed.connect(self._on_structure_changed)
        self._section_tree.add_root_requested.connect(
            lambda: self._on_add_section(None)
        )
        lay.addWidget(self._section_tree)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self._breadcrumb = BreadcrumbNav(self._agent.sections)
        self._breadcrumb.section_selected.connect(self._on_breadcrumb_selected)
        self._breadcrumb.section_add_requested.connect(self._on_add_section)
        right_lay.addWidget(self._breadcrumb)

        self._content_panel = SectionContentPanel()
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._content_panel.variable_insert_requested.connect(
            self._on_variable_insert
        )
        right_lay.addWidget(self._content_panel, 1)

        lay.addWidget(right, 1)

        self._var_popup = VariablePopup(self._variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        return widget

    # --- Section helpers ---

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

    def _on_add_section(self, parent: Section | None) -> None:
        siblings = self._agent.sections if parent is None else parent.children
        existing = {s.title for s in siblings}
        while True:
            name, ok = QInputDialog.getText(self, "섹션 추가", "섹션 이름:")
            if not ok or not name.strip():
                return
            name = name.strip()
            if name in existing:
                QMessageBox.warning(
                    self, "이름 중복", f"'{name}' 섹션이 이미 존재합니다."
                )
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


class _MiniRegistry(QWidget):
    """에이전트 로컬 스킬 목록 + 추가 버튼."""

    def __init__(
        self, agent: AgentDefinition, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._agent = agent
        self.setMinimumWidth(120)
        self.setMaximumWidth(200)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(QLabel("Local Skills"))

        self._list = QListWidget()
        lay.addWidget(self._list, 1)

        btn = QPushButton("＋ 새 스킬")
        btn.clicked.connect(self._on_add_skill)
        lay.addWidget(btn)

        self._rebuild()

    def _rebuild(self) -> None:
        self._list.clear()
        for skill in self._agent.skills:
            self._list.addItem(f"⚙ {skill.name}")

    def _on_add_skill(self) -> None:
        name, ok = QInputDialog.getText(self, "새 로컬 스킬", "이름:")
        if not ok or not name.strip():
            return
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill
        s = SimpleState(name="start")
        fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
        skill = ProceduralSkill(fsm=fsm, name=name.strip(), description="")
        self._agent.skills.append(skill)
        self._rebuild()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/view/editors/test_agent_editor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/editors/agent_editor.py tests/view/editors/test_agent_editor.py
git commit -m "feat(editor): add AgentEditor with Graph, Content, Config tabs"
```

---

### Task 6: AgentFsmScene 서브클래스

**Files:**
- Modify: `daedalus/view/canvas/scene.py`
- Test: `tests/view/editors/test_agent_editor.py` (추가)

- [ ] **Step 1: Write the failing test**

`tests/view/editors/test_agent_editor.py`에 추가:

```python
from daedalus.view.canvas.canvas_view import FsmCanvasView


def test_agent_editor_graph_tab_has_canvas(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    graph_tab = editor._tabs.widget(0)
    canvas = graph_tab.findChild(FsmCanvasView)
    assert canvas is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/view/editors/test_agent_editor.py::test_agent_editor_graph_tab_has_canvas -v`
Expected: FAIL — `AgentFsmScene` 미정의

- [ ] **Step 3: Add AgentFsmScene to scene.py**

`daedalus/view/canvas/scene.py` 하단에 추가:

```python
from daedalus.model.fsm.machine import StateMachine as _SM


class AgentFsmScene(FsmScene):
    """에이전트 서브그래프 전용 씬."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        agent_fsm: _SM,
        skill_lookup: Callable[[str], object] | None = None,
    ) -> None:
        super().__init__(project_vm, skill_lookup=skill_lookup)
        self._agent_fsm = agent_fsm

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
                no_del = menu.addAction("삭제 불가 (EntryPoint)")
                if no_del is not None:
                    no_del.setEnabled(False)
                menu.exec(event.screenPos())
            elif isinstance(model, _XP):
                rename_act = menu.addAction(f"'{model.name}' 이름 변경")
                color_act = menu.addAction("색상 변경")
                exit_count = len([
                    s for s in self._agent_fsm.states if isinstance(s, _XP)
                ])
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
                delete_act = menu.addAction(f"'{item.state_vm.model.name}' 삭제")
                if menu.exec(event.screenPos()) == delete_act:
                    self._delete_state(item.state_vm)
        elif isinstance(item, TransitionEdgeItem):
            delete_act = menu.addAction("전이 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self._delete_transition(item.transition_vm)
        else:
            add_state = menu.addAction("빈 상태 추가")
            add_exit = menu.addAction("ExitPoint 추가")
            chosen = menu.exec(event.screenPos())
            if chosen == add_state:
                self._create_state(pos)
            elif chosen == add_exit:
                self._create_exit_point(pos)

    def _create_exit_point(self, pos: QPointF) -> None:
        from daedalus.model.fsm.pseudo import ExitPoint as _XP
        from daedalus.view.commands.exit_point_commands import AddExitPointCmd
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
        name, ok = QInputDialog.getText(
            view, "ExitPoint 이름 변경", "이름:", text=model.name
        )
        if ok and name.strip() and name.strip() != model.name:
            self._project_vm.execute(
                RenameExitPointCmd(model, model.name, name.strip())
            )

    def _change_exit_point_color(self, model) -> None:
        from daedalus.view.commands.exit_point_commands import ChangeExitPointColorCmd
        from PyQt6.QtWidgets import QColorDialog
        view = self.views()[0] if self.views() else None
        color = QColorDialog.getColor(QColor(model.color), view, "ExitPoint 색상")
        if color.isValid() and color.name() != model.color:
            self._project_vm.execute(
                ChangeExitPointColorCmd(model, model.color, color.name())
            )

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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/view/editors/test_agent_editor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/canvas/scene.py tests/view/editors/test_agent_editor.py
git commit -m "feat(canvas): add AgentFsmScene with ExitPoint context menus and constraints"
```

---

### Task 7: App 라우팅 + 에이전트 초기 FSM + 통합

**Files:**
- Modify: `daedalus/view/app.py:176-189,229-239`

- [ ] **Step 1: Update _open_component for AgentDefinition routing**

`daedalus/view/app.py`의 `_open_component()` 수정:

```python
def _open_component(self, component: object) -> None:
    """레지스트리에서 더블클릭 → SkillEditor/AgentEditor 탭 열기."""
    name = getattr(component, "name", None)
    if name is None:
        return
    if name in self._open_tabs:
        self._tabs.setCurrentIndex(self._open_tabs[name])
        return

    if isinstance(component, AgentDefinition):
        from daedalus.view.editors.agent_editor import AgentEditor
        editor = AgentEditor(component, on_notify_fn=self._project_vm.notify)
        idx = self._tabs.addTab(editor, f"🤖 {name}")
        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)
    elif isinstance(component, (ProceduralSkill, DeclarativeSkill, TransferSkill)):
        editor = SkillEditor(component, on_notify_fn=self._project_vm.notify)
        idx = self._tabs.addTab(editor, name)
        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)
```

- [ ] **Step 2: Add _make_agent_fsm factory**

`daedalus/view/app.py`에 추가:

```python
def _make_agent_fsm(self, name: str) -> object:
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    return StateMachine(
        name=f"{name}_fsm",
        states=[entry, exit_done],
        initial_state=entry,
        final_states=[exit_done],
    )
```

- [ ] **Step 3: Update agent factory in _on_new_component**

`_on_new_component`의 factories 딕셔너리에서 agent 항목 수정:

```python
"agent": lambda: AgentDefinition(
    fsm=self._make_agent_fsm(name), name=name, description=""
),
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Manual integration test**

Run: `python -m daedalus` (또는 앱 실행 명령)

확인 항목:
1. Registry "+" → "새 Agent" → 이름 입력 → 에이전트 생성
2. 에이전트 노드 캔버스 배치 → entry/done 출력 포트 표시
3. 에이전트 노드 더블클릭 → AgentEditor 탭 (3개 서브탭)
4. Graph 탭: EntryPoint + ExitPoint 노드 표시
5. Graph 탭 빈 공간 우클릭 → "ExitPoint 추가" 동작
6. ExitPoint 추가 후 프로젝트 FSM 에이전트 노드 포트 갱신
7. Content 탭: "instruction" 섹션 표시
8. Config 탭: name/description 표시

- [ ] **Step 6: Commit**

```bash
git add daedalus/view/app.py
git commit -m "feat(app): route AgentDefinition to AgentEditor, agent-specific FSM factory"
```
