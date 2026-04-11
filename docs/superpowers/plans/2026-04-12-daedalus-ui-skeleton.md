# Daedalus UI Skeleton (A-Stage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PyQt6 기반 노드 에디터 UI의 최초 스켈레톤을 구축한다. SimpleState + Transition을 캔버스에서 배치/연결할 수 있으며, Command 패턴으로 Undo/Redo를 지원한다.

**Architecture:** MVC 패턴 — model/(불변 코어) + view/(UI 레이어). view/ 내부는 Command 패턴 + ViewModel 어댑터 + QGraphicsScene 캔버스. 모든 편집은 CommandStack을 경유하며, ProjectViewModel이 단일 진실 공급원.

**Tech Stack:** Python 3.12, PyQt6 >= 6.6, pytest >= 8.0, uv (패키지 관리/실행)

**Spec:** `docs/superpowers/specs/2026-04-12-daedalus-ui-skeleton-design.md`

---

## File Structure

### New Files (view layer)

| File | Responsibility |
|------|---------------|
| `daedalus/__main__.py` | QApplication 생성, MainWindow 실행 |
| `daedalus/view/__init__.py` | 패키지 |
| `daedalus/view/app.py` | MainWindow — DockWidget, QTabWidget, 메뉴바, 상태바 |
| `daedalus/view/commands/__init__.py` | 패키지 |
| `daedalus/view/commands/base.py` | Command(ABC), MacroCommand, CommandStack |
| `daedalus/view/commands/state_commands.py` | CreateStateCmd, DeleteStateCmd, MoveStateCmd, RenameStateCmd |
| `daedalus/view/commands/transition_commands.py` | CreateTransitionCmd, DeleteTransitionCmd |
| `daedalus/view/viewmodel/__init__.py` | 패키지 |
| `daedalus/view/viewmodel/state_vm.py` | StateViewModel, TransitionViewModel |
| `daedalus/view/viewmodel/project_vm.py` | ProjectViewModel |
| `daedalus/view/canvas/__init__.py` | 패키지 |
| `daedalus/view/canvas/scene.py` | FsmScene (QGraphicsScene) |
| `daedalus/view/canvas/canvas_view.py` | FsmCanvasView (QGraphicsView) |
| `daedalus/view/canvas/node_item.py` | StateNodeItem (QGraphicsItem) |
| `daedalus/view/canvas/edge_item.py` | TransitionEdgeItem (QGraphicsPathItem) |
| `daedalus/view/editors/__init__.py` | 패키지 |
| `daedalus/view/editors/decl_skill_editor.py` | DeclarativeSkill placeholder 에디터 |
| `daedalus/view/panels/__init__.py` | 패키지 |
| `daedalus/view/panels/tree_panel.py` | ProjectTreePanel (QTreeView + 필터 토글) |
| `daedalus/view/panels/property_panel.py` | PropertyPanel (선택 요소 속성 편집) |
| `daedalus/view/panels/history_panel.py` | HistoryPanel (커맨드 이력 + goto) |

### New Test Files

| File | Tests |
|------|-------|
| `tests/view/__init__.py` | 패키지 |
| `tests/view/conftest.py` | qapp fixture (QApplication 세션 스코프) |
| `tests/view/commands/__init__.py` | 패키지 |
| `tests/view/commands/test_base.py` | Command, MacroCommand, CommandStack |
| `tests/view/commands/test_state_commands.py` | 상태 커맨드 4종 |
| `tests/view/commands/test_transition_commands.py` | 전이 커맨드 2종 |
| `tests/view/viewmodel/__init__.py` | 패키지 |
| `tests/view/viewmodel/test_state_vm.py` | StateViewModel, TransitionViewModel |
| `tests/view/viewmodel/test_project_vm.py` | ProjectViewModel |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | dependencies에 PyQt6 추가 |

---

## Task 1: Project Scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `daedalus/__main__.py`
- Create: all `__init__.py` files
- Create: `tests/view/conftest.py`

- [ ] **Step 1: Add PyQt6 dependency**

`pyproject.toml` — dependencies 변경:
```toml
dependencies = ["PyQt6>=6.6"]
```

- [ ] **Step 2: Create all `__init__.py` files**

빈 파일 생성:
```
daedalus/view/__init__.py
daedalus/view/commands/__init__.py
daedalus/view/viewmodel/__init__.py
daedalus/view/canvas/__init__.py
daedalus/view/editors/__init__.py
daedalus/view/panels/__init__.py
tests/view/__init__.py
tests/view/commands/__init__.py
tests/view/viewmodel/__init__.py
```

- [ ] **Step 3: Create test conftest with qapp fixture**

```python
# tests/view/conftest.py
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """PyQt6 테스트용 QApplication 싱글턴."""
    app = QApplication.instance() or QApplication([])
    yield app
```

- [ ] **Step 4: Create stub `__main__.py`**

```python
# daedalus/__main__.py
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Daedalus — FSM Plugin Designer")
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Install and verify**

Run: `uv sync --extra dev && uv run python -m daedalus`

Expected: 빈 PyQt6 윈도우가 열림. 타이틀: "Daedalus — FSM Plugin Designer". 닫으면 종료.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml daedalus/__main__.py daedalus/view/ tests/view/
git commit -m "feat: scaffold view package and PyQt6 entry point"
```

---

## Task 2: Command Infrastructure (TDD)

**Files:**
- Create: `daedalus/view/commands/base.py`
- Test: `tests/view/commands/test_base.py`

- [ ] **Step 1: Write failing tests for CommandStack and MacroCommand**

```python
# tests/view/commands/test_base.py
from __future__ import annotations

from daedalus.view.commands.base import Command, CommandStack, MacroCommand


class AppendCmd(Command):
    """테스트용: 리스트에 값 추가/제거."""

    def __init__(self, target: list[int], value: int) -> None:
        self._target = target
        self._value = value

    @property
    def description(self) -> str:
        return f"Append {self._value}"

    def execute(self) -> None:
        self._target.append(self._value)

    def undo(self) -> None:
        self._target.remove(self._value)


class TestCommandStack:
    def test_execute_runs_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        assert data == [1]

    def test_undo_reverses_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        assert data == []

    def test_redo_reapplies_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        stack.redo()
        assert data == [1]

    def test_execute_clears_redo_stack(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        stack.execute(AppendCmd(data, 2))
        assert not stack.can_redo

    def test_can_undo_empty(self):
        assert not CommandStack().can_undo

    def test_can_redo_empty(self):
        assert not CommandStack().can_redo

    def test_history_returns_undo_stack(self):
        stack = CommandStack()
        cmd1 = AppendCmd([], 1)
        cmd2 = AppendCmd([], 2)
        stack.execute(cmd1)
        stack.execute(cmd2)
        assert stack.history == [cmd1, cmd2]

    def test_current_index(self):
        stack = CommandStack()
        stack.execute(AppendCmd([], 1))
        stack.execute(AppendCmd([], 2))
        assert stack.current_index == 1
        stack.undo()
        assert stack.current_index == 0

    def test_current_index_empty(self):
        assert CommandStack().current_index == -1

    def test_goto_backward(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.execute(AppendCmd(data, 2))
        stack.execute(AppendCmd(data, 3))
        stack.goto(0)
        assert data == [1]
        assert stack.current_index == 0

    def test_goto_forward(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.execute(AppendCmd(data, 2))
        stack.execute(AppendCmd(data, 3))
        stack.goto(0)
        stack.goto(2)
        assert data == [1, 2, 3]

    def test_listener_notified_on_execute(self):
        calls: list[str] = []
        stack = CommandStack()
        stack.add_listener(lambda: calls.append("changed"))
        stack.execute(AppendCmd([], 1))
        assert calls == ["changed"]

    def test_listener_notified_on_undo(self):
        calls: list[str] = []
        stack = CommandStack()
        stack.execute(AppendCmd([], 1))
        stack.add_listener(lambda: calls.append("changed"))
        stack.undo()
        assert calls == ["changed"]


class TestMacroCommand:
    def test_execute_runs_all_children(self):
        data: list[int] = []
        macro = MacroCommand(
            children=[AppendCmd(data, 1), AppendCmd(data, 2)],
            description="Append 1 and 2",
        )
        macro.execute()
        assert data == [1, 2]

    def test_undo_reverses_in_reverse_order(self):
        data: list[int] = []
        macro = MacroCommand(
            children=[AppendCmd(data, 1), AppendCmd(data, 2)],
            description="Append 1 and 2",
        )
        macro.execute()
        macro.undo()
        assert data == []

    def test_description(self):
        macro = MacroCommand(children=[], description="Test macro")
        assert macro.description == "Test macro"

    def test_children_returns_copy(self):
        cmd = AppendCmd([], 1)
        macro = MacroCommand(children=[cmd], description="x")
        macro.children.append(AppendCmd([], 2))
        assert len(macro.children) == 1  # 원본 불변
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/view/commands/test_base.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'daedalus.view.commands.base'`

- [ ] **Step 3: Implement Command, MacroCommand, CommandStack**

```python
# daedalus/view/commands/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Command(ABC):
    """모든 편집 동작의 기반."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Undo/Redo 메뉴 및 히스토리 패널에 표시될 설명."""

    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...


class MacroCommand(Command):
    """여러 커맨드를 하나의 Undo 단위로 묶음."""

    def __init__(self, children: list[Command], description: str) -> None:
        self._children = list(children)
        self._description = description

    @property
    def description(self) -> str:
        return self._description

    @property
    def children(self) -> list[Command]:
        return list(self._children)

    def execute(self) -> None:
        for cmd in self._children:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self._children):
            cmd.undo()


class CommandStack:
    """Undo/Redo 스택. 모든 편집의 관문."""

    def __init__(self) -> None:
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def execute(self, cmd: Command) -> None:
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        self._notify()

    def undo(self) -> None:
        if not self.can_undo:
            return
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._notify()

    def redo(self) -> None:
        if not self.can_redo:
            return
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        self._notify()

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def history(self) -> list[Command]:
        return list(self._undo_stack)

    @property
    def current_index(self) -> int:
        return len(self._undo_stack) - 1

    def goto(self, index: int) -> None:
        """히스토리 특정 지점으로 점프."""
        while self.current_index > index:
            self.undo()
        while self.current_index < index:
            self.redo()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/view/commands/test_base.py -v`

Expected: 17 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/commands/base.py tests/view/commands/test_base.py
git commit -m "feat: add Command, MacroCommand, CommandStack with TDD"
```

---

## Task 3: ViewModel Layer (TDD)

**Files:**
- Create: `daedalus/view/viewmodel/state_vm.py`
- Create: `daedalus/view/viewmodel/project_vm.py`
- Test: `tests/view/viewmodel/test_state_vm.py`
- Test: `tests/view/viewmodel/test_project_vm.py`

- [ ] **Step 1: Write failing tests for StateViewModel and TransitionViewModel**

```python
# tests/view/viewmodel/test_state_vm.py
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


class TestStateViewModel:
    def test_wraps_model(self):
        model = SimpleState(name="Idle")
        vm = StateViewModel(model=model)
        assert vm.model is model
        assert vm.model.name == "Idle"

    def test_default_position(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.x == 0.0
        assert vm.y == 0.0

    def test_default_size(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.width == 140.0
        assert vm.height == 60.0

    def test_default_not_selected(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.selected is False

    def test_position_mutable(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        vm.x = 100.0
        vm.y = 200.0
        assert vm.x == 100.0
        assert vm.y == 200.0


class TestTransitionViewModel:
    def test_wraps_model_and_endpoints(self):
        s1 = SimpleState(name="A")
        s2 = SimpleState(name="B")
        model = Transition(source=s1, target=s2)
        vm_a = StateViewModel(model=s1)
        vm_b = StateViewModel(model=s2)
        tvm = TransitionViewModel(model=model, source_vm=vm_a, target_vm=vm_b)
        assert tvm.model is model
        assert tvm.source_vm is vm_a
        assert tvm.target_vm is vm_b

    def test_default_not_selected(self):
        s1 = SimpleState(name="A")
        s2 = SimpleState(name="B")
        tvm = TransitionViewModel(
            model=Transition(source=s1, target=s2),
            source_vm=StateViewModel(model=s1),
            target_vm=StateViewModel(model=s2),
        )
        assert tvm.selected is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/view/viewmodel/test_state_vm.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement StateViewModel and TransitionViewModel**

```python
# daedalus/view/viewmodel/state_vm.py
from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition


@dataclass
class StateViewModel:
    """SimpleState + UI 전용 상태."""

    model: SimpleState
    x: float = 0.0
    y: float = 0.0
    width: float = 140.0
    height: float = 60.0
    selected: bool = False


@dataclass
class TransitionViewModel:
    """Transition + UI 전용 상태."""

    model: Transition
    source_vm: StateViewModel
    target_vm: StateViewModel
    selected: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/view/viewmodel/test_state_vm.py -v`

Expected: 7 tests PASS

- [ ] **Step 5: Write failing tests for ProjectViewModel**

```python
# tests/view/viewmodel/test_project_vm.py
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.commands.base import CommandStack
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _make_state_vm(name: str = "S") -> StateViewModel:
    return StateViewModel(model=SimpleState(name=name))


def _make_transition_vm(
    src: StateViewModel, tgt: StateViewModel
) -> TransitionViewModel:
    return TransitionViewModel(
        model=Transition(source=src.model, target=tgt.model),
        source_vm=src,
        target_vm=tgt,
    )


class TestProjectViewModel:
    def test_initially_empty(self):
        pvm = ProjectViewModel()
        assert pvm.state_vms == []
        assert pvm.transition_vms == []

    def test_has_command_stack(self):
        pvm = ProjectViewModel()
        assert isinstance(pvm.command_stack, CommandStack)

    def test_add_and_remove_state_vm(self):
        pvm = ProjectViewModel()
        vm = _make_state_vm("A")
        pvm.add_state_vm(vm)
        assert vm in pvm.state_vms
        pvm.remove_state_vm(vm)
        assert vm not in pvm.state_vms

    def test_add_and_remove_transition_vm(self):
        pvm = ProjectViewModel()
        a = _make_state_vm("A")
        b = _make_state_vm("B")
        tvm = _make_transition_vm(a, b)
        pvm.add_transition_vm(tvm)
        assert tvm in pvm.transition_vms
        pvm.remove_transition_vm(tvm)
        assert tvm not in pvm.transition_vms

    def test_get_state_vm_found(self):
        pvm = ProjectViewModel()
        vm = _make_state_vm("X")
        pvm.add_state_vm(vm)
        assert pvm.get_state_vm("X") is vm

    def test_get_state_vm_not_found(self):
        pvm = ProjectViewModel()
        assert pvm.get_state_vm("missing") is None

    def test_get_transitions_for(self):
        pvm = ProjectViewModel()
        a = _make_state_vm("A")
        b = _make_state_vm("B")
        c = _make_state_vm("C")
        t_ab = _make_transition_vm(a, b)
        t_bc = _make_transition_vm(b, c)
        pvm.add_transition_vm(t_ab)
        pvm.add_transition_vm(t_bc)
        assert pvm.get_transitions_for(b) == [t_ab, t_bc]
        assert pvm.get_transitions_for(a) == [t_ab]
        assert pvm.get_transitions_for(c) == [t_bc]

    def test_listener_notified(self):
        calls: list[str] = []
        pvm = ProjectViewModel()
        pvm.add_listener(lambda: calls.append("changed"))
        pvm.notify()
        assert calls == ["changed"]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `uv run python -m pytest tests/view/viewmodel/test_project_vm.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement ProjectViewModel**

```python
# daedalus/view/viewmodel/project_vm.py
from __future__ import annotations

from typing import Callable

from daedalus.view.commands.base import Command, CommandStack
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


class ProjectViewModel:
    """전체 편집 세션의 상태를 관리. 단일 진실 공급원."""

    def __init__(self) -> None:
        self.state_vms: list[StateViewModel] = []
        self.transition_vms: list[TransitionViewModel] = []
        self.command_stack = CommandStack()
        self._listeners: list[Callable[[], None]] = []

    # --- 변경 (Command를 통해서만 호출) ---

    def execute(self, cmd: Command) -> None:
        """커맨드 실행 후 리스너에 알림."""
        self.command_stack.execute(cmd)
        self.notify()

    # --- 조회 ---

    def get_state_vm(self, name: str) -> StateViewModel | None:
        for vm in self.state_vms:
            if vm.model.name == name:
                return vm
        return None

    def get_transitions_for(
        self, state_vm: StateViewModel
    ) -> list[TransitionViewModel]:
        return [
            t
            for t in self.transition_vms
            if t.source_vm is state_vm or t.target_vm is state_vm
        ]

    # --- 직접 변이 (커맨드 내부에서만 호출) ---

    def add_state_vm(self, vm: StateViewModel) -> None:
        self.state_vms.append(vm)

    def remove_state_vm(self, vm: StateViewModel) -> None:
        self.state_vms.remove(vm)

    def add_transition_vm(self, vm: TransitionViewModel) -> None:
        self.transition_vms.append(vm)

    def remove_transition_vm(self, vm: TransitionViewModel) -> None:
        self.transition_vms.remove(vm)

    # --- 옵저버 ---

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def notify(self) -> None:
        for listener in self._listeners:
            listener()
```

- [ ] **Step 8: Run all viewmodel tests**

Run: `uv run python -m pytest tests/view/viewmodel/ -v`

Expected: 16 tests PASS (7 state_vm + 9 project_vm)

- [ ] **Step 9: Commit**

```bash
git add daedalus/view/viewmodel/ tests/view/viewmodel/
git commit -m "feat: add StateViewModel, TransitionViewModel, ProjectViewModel with TDD"
```

---

## Task 4: State Commands (TDD)

**Files:**
- Create: `daedalus/view/commands/state_commands.py`
- Test: `tests/view/commands/test_state_commands.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/view/commands/test_state_commands.py
from daedalus.model.fsm.state import SimpleState
from daedalus.view.viewmodel.state_vm import StateViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.commands.state_commands import (
    CreateStateCmd,
    DeleteStateCmd,
    MoveStateCmd,
    RenameStateCmd,
)


def _make_pvm_with_state(name: str = "S") -> tuple[ProjectViewModel, StateViewModel]:
    pvm = ProjectViewModel()
    vm = StateViewModel(model=SimpleState(name=name))
    pvm.add_state_vm(vm)
    return pvm, vm


class TestCreateStateCmd:
    def test_execute_adds_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        assert vm in pvm.state_vms

    def test_undo_removes_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm not in pvm.state_vms

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = CreateStateCmd(ProjectViewModel(), vm)
        assert "Idle" in cmd.description


class TestDeleteStateCmd:
    def test_execute_removes_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        assert vm not in pvm.state_vms

    def test_undo_restores_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm in pvm.state_vms

    def test_description(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        assert "X" in cmd.description


class TestMoveStateCmd:
    def test_execute_updates_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        assert vm.x == 100.0
        assert vm.y == 200.0

    def test_undo_restores_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        cmd.undo()
        assert vm.x == 0.0
        assert vm.y == 0.0

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = MoveStateCmd(vm, 0, 0, 1, 1)
        assert "Idle" in cmd.description


class TestRenameStateCmd:
    def test_execute_changes_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        assert vm.model.name == "New"

    def test_undo_restores_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        cmd.undo()
        assert vm.model.name == "Old"

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, "Old", "New")
        assert "Old" in cmd.description and "New" in cmd.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/view/commands/test_state_commands.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement state commands**

```python
# daedalus/view/commands/state_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import StateViewModel

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class CreateStateCmd(Command):
    def __init__(self, project_vm: ProjectViewModel, state_vm: StateViewModel) -> None:
        self._project_vm = project_vm
        self._state_vm = state_vm

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 생성"

    def execute(self) -> None:
        self._project_vm.add_state_vm(self._state_vm)

    def undo(self) -> None:
        self._project_vm.remove_state_vm(self._state_vm)


class DeleteStateCmd(Command):
    def __init__(self, project_vm: ProjectViewModel, state_vm: StateViewModel) -> None:
        self._project_vm = project_vm
        self._state_vm = state_vm

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 삭제"

    def execute(self) -> None:
        self._project_vm.remove_state_vm(self._state_vm)

    def undo(self) -> None:
        self._project_vm.add_state_vm(self._state_vm)


class MoveStateCmd(Command):
    def __init__(
        self,
        state_vm: StateViewModel,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
    ) -> None:
        self._state_vm = state_vm
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 이동"

    def execute(self) -> None:
        self._state_vm.x = self._new_x
        self._state_vm.y = self._new_y

    def undo(self) -> None:
        self._state_vm.x = self._old_x
        self._state_vm.y = self._old_y


class RenameStateCmd(Command):
    def __init__(
        self, state_vm: StateViewModel, old_name: str, new_name: str
    ) -> None:
        self._state_vm = state_vm
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"상태 이름 변경: '{self._old_name}' → '{self._new_name}'"

    def execute(self) -> None:
        self._state_vm.model.name = self._new_name

    def undo(self) -> None:
        self._state_vm.model.name = self._old_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/view/commands/test_state_commands.py -v`

Expected: 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/commands/state_commands.py tests/view/commands/test_state_commands.py
git commit -m "feat: add state commands (Create, Delete, Move, Rename) with TDD"
```

---

## Task 5: Transition Commands (TDD)

**Files:**
- Create: `daedalus/view/commands/transition_commands.py`
- Test: `tests/view/commands/test_transition_commands.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/view/commands/test_transition_commands.py
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.commands.transition_commands import (
    CreateTransitionCmd,
    DeleteTransitionCmd,
)


def _make_transition_vm() -> tuple[ProjectViewModel, TransitionViewModel]:
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    pvm = ProjectViewModel()
    vm_a = StateViewModel(model=s1)
    vm_b = StateViewModel(model=s2)
    tvm = TransitionViewModel(
        model=Transition(source=s1, target=s2),
        source_vm=vm_a,
        target_vm=vm_b,
    )
    return pvm, tvm


class TestCreateTransitionCmd:
    def test_execute_adds_transition(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        cmd.execute()
        assert tvm in pvm.transition_vms

    def test_undo_removes_transition(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        cmd.execute()
        cmd.undo()
        assert tvm not in pvm.transition_vms

    def test_description(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        assert "A" in cmd.description and "B" in cmd.description


class TestDeleteTransitionCmd:
    def test_execute_removes_transition(self):
        pvm, tvm = _make_transition_vm()
        pvm.add_transition_vm(tvm)
        cmd = DeleteTransitionCmd(pvm, tvm)
        cmd.execute()
        assert tvm not in pvm.transition_vms

    def test_undo_restores_transition(self):
        pvm, tvm = _make_transition_vm()
        pvm.add_transition_vm(tvm)
        cmd = DeleteTransitionCmd(pvm, tvm)
        cmd.execute()
        cmd.undo()
        assert tvm in pvm.transition_vms

    def test_description(self):
        pvm, tvm = _make_transition_vm()
        cmd = DeleteTransitionCmd(pvm, tvm)
        assert "A" in cmd.description and "B" in cmd.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/view/commands/test_transition_commands.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement transition commands**

```python
# daedalus/view/commands/transition_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import TransitionViewModel

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class CreateTransitionCmd(Command):
    def __init__(
        self, project_vm: ProjectViewModel, transition_vm: TransitionViewModel
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm

    @property
    def description(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f"전이 '{src}→{tgt}' 생성"

    def execute(self) -> None:
        self._project_vm.add_transition_vm(self._transition_vm)

    def undo(self) -> None:
        self._project_vm.remove_transition_vm(self._transition_vm)


class DeleteTransitionCmd(Command):
    def __init__(
        self, project_vm: ProjectViewModel, transition_vm: TransitionViewModel
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm

    @property
    def description(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f"전이 '{src}→{tgt}' 삭제"

    def execute(self) -> None:
        self._project_vm.remove_transition_vm(self._transition_vm)

    def undo(self) -> None:
        self._project_vm.add_transition_vm(self._transition_vm)
```

- [ ] **Step 4: Run full command test suite**

Run: `uv run python -m pytest tests/view/commands/ -v`

Expected: 35 tests PASS (17 base + 12 state + 6 transition)

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/commands/transition_commands.py tests/view/commands/test_transition_commands.py
git commit -m "feat: add transition commands (Create, Delete) with TDD"
```

---

## Task 6: Canvas Items

**Files:**
- Create: `daedalus/view/canvas/node_item.py`
- Create: `daedalus/view/canvas/edge_item.py`

- [ ] **Step 1: Implement StateNodeItem**

```python
# daedalus/view/canvas/node_item.py
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.viewmodel.state_vm import StateViewModel

_BORDER_NORMAL = QColor("#4455aa")
_BORDER_SELECTED = QColor("#88aaff")
_FILL = QColor("#2a2a4a")
_HEADER_FILL = QColor("#334")
_TEXT_COLOR = QColor("#ddd")
_TEXT_SELECTED = QColor("#fff")
_SUBTEXT_COLOR = QColor("#888")


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 SimpleState 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self.setPos(state_vm.x, state_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._drag_start_pos = None

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._state_vm.width, self._state_vm.height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        rect = self.boundingRect()
        selected = self.isSelected()
        border = _BORDER_SELECTED if selected else _BORDER_NORMAL

        # 본체
        painter.setPen(QPen(border, 2))
        painter.setBrush(QBrush(_FILL))
        painter.drawRoundedRect(rect, 8, 8)

        # 헤더
        header_h = 20.0
        header_rect = QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, header_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_HEADER_FILL))
        painter.drawRoundedRect(header_rect, 7, 7)
        painter.drawRect(
            QRectF(header_rect.x(), header_rect.y() + 10, header_rect.width(), header_h - 10)
        )

        painter.setPen(QPen(_SUBTEXT_COLOR))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            header_rect.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "SimpleState"
        )

        # 이름
        name_rect = QRectF(rect.x(), rect.y() + header_h, rect.width(), rect.height() - header_h)
        painter.setPen(QPen(_TEXT_SELECTED if selected else _TEXT_COLOR))
        font = QFont("Segoe UI", 11)
        if selected:
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, self._state_vm.model.name)

    def mousePressEvent(self, event) -> None:
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            scene = self.scene()
            if hasattr(scene, "handle_node_moved"):
                scene.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
```

- [ ] **Step 2: Implement TransitionEdgeItem**

```python
# daedalus/view/canvas/edge_item.py
from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPathItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.viewmodel.state_vm import TransitionViewModel

_EDGE_COLOR = QColor("#6674cc")
_EDGE_SELECTED = QColor("#88aaff")
_ARROW_SIZE = 8.0


class TransitionEdgeItem(QGraphicsPathItem):
    """두 StateNodeItem을 연결하는 전이 화살표."""

    def __init__(
        self,
        transition_vm: TransitionViewModel,
        source_node: StateNodeItem,
        target_node: StateNodeItem,
    ) -> None:
        super().__init__()
        self._transition_vm = transition_vm
        self._source_node = source_node
        self._target_node = target_node
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)
        self.update_path()

    @property
    def transition_vm(self) -> TransitionViewModel:
        return self._transition_vm

    @property
    def source_node(self) -> StateNodeItem:
        return self._source_node

    @property
    def target_node(self) -> StateNodeItem:
        return self._target_node

    def update_path(self) -> None:
        """소스/타겟 노드 위치 기반으로 베지어 경로 재계산."""
        src_rect = self._source_node.sceneBoundingRect()
        tgt_rect = self._target_node.sceneBoundingRect()

        src_pt = QPointF(src_rect.right(), src_rect.center().y())
        tgt_pt = QPointF(tgt_rect.left(), tgt_rect.center().y())

        if tgt_rect.center().x() < src_rect.center().x():
            src_pt = QPointF(src_rect.left(), src_rect.center().y())
            tgt_pt = QPointF(tgt_rect.right(), tgt_rect.center().y())

        dx = abs(tgt_pt.x() - src_pt.x()) * 0.5
        ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
        ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())

        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)
        self.setPath(path)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        color = _EDGE_SELECTED if self.isSelected() else _EDGE_COLOR
        painter.setPen(QPen(color, 2))
        painter.drawPath(self.path())

        # 화살표 머리
        path = self.path()
        if path.isEmpty():
            return
        end_pt = path.pointAtPercent(1.0)
        tangent_pt = path.pointAtPercent(0.95)
        dx = end_pt.x() - tangent_pt.x()
        dy = end_pt.y() - tangent_pt.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            dx /= length
            dy /= length
            left = QPointF(
                end_pt.x() - _ARROW_SIZE * dx + _ARROW_SIZE * 0.5 * dy,
                end_pt.y() - _ARROW_SIZE * dy - _ARROW_SIZE * 0.5 * dx,
            )
            right = QPointF(
                end_pt.x() - _ARROW_SIZE * dx - _ARROW_SIZE * 0.5 * dy,
                end_pt.y() - _ARROW_SIZE * dy + _ARROW_SIZE * 0.5 * dx,
            )
            arrow = QPolygonF([end_pt, left, right])
            painter.setBrush(color)
            painter.setPen(QPen(color))
            painter.drawPolygon(arrow)
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from daedalus.view.canvas.node_item import StateNodeItem; from daedalus.view.canvas.edge_item import TransitionEdgeItem; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add daedalus/view/canvas/node_item.py daedalus/view/canvas/edge_item.py
git commit -m "feat: add StateNodeItem and TransitionEdgeItem canvas items"
```

---

## Task 7: Canvas Scene & View

**Files:**
- Create: `daedalus/view/canvas/scene.py`
- Create: `daedalus/view/canvas/canvas_view.py`

- [ ] **Step 1: Implement FsmScene**

```python
# daedalus/view/canvas/scene.py
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene, QMenu

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
        self.setBackgroundBrush(QColor(_BG_COLOR))
        self.setSceneRect(-2000, -2000, 4000, 4000)

        self._connecting = False
        self._connect_source: StateNodeItem | None = None

        self._project_vm.add_listener(self._rebuild)

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

    def contextMenuEvent(self, event) -> None:
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

    def mousePressEvent(self, event) -> None:
        if self._connecting and event.button() == Qt.MouseButton.RightButton:
            self._connecting = False
            self._connect_source = None
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._connecting and self._connect_source:
            target = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
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

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            for item in list(self.selectedItems()):
                if isinstance(item, StateNodeItem):
                    self._delete_state(item.state_vm)
                elif isinstance(item, TransitionEdgeItem):
                    self._delete_transition(item.transition_vm)
            return
        super().keyPressEvent(event)
```

- [ ] **Step 2: Implement FsmCanvasView**

```python
# daedalus/view/canvas/canvas_view.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QGraphicsView

from daedalus.view.canvas.scene import FsmScene


class FsmCanvasView(QGraphicsView):
    """pan/zoom 지원 캔버스 뷰."""

    def __init__(self, scene: FsmScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._panning = False
        self._pan_start = None

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_start:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 3: Commit**

```bash
git add daedalus/view/canvas/scene.py daedalus/view/canvas/canvas_view.py
git commit -m "feat: add FsmScene and FsmCanvasView with interactions"
```

---

## Task 8: Panels

**Files:**
- Create: `daedalus/view/panels/tree_panel.py`
- Create: `daedalus/view/panels/property_panel.py`
- Create: `daedalus/view/panels/history_panel.py`

- [ ] **Step 1: Implement ProjectTreePanel**

```python
# daedalus/view/panels/tree_panel.py
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTreeView, QVBoxLayout, QWidget

from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject

_COLOR_PROCEDURAL = QColor("#88cc88")
_COLOR_DECLARATIVE = QColor("#cccc88")
_COLOR_AGENT = QColor("#cc8888")
_COLOR_FOLDER = QColor("#aab8ff")
_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1


class ProjectTreePanel(QWidget):
    """프로젝트 트리뷰 + 스킬 타입 필터 토글."""

    component_double_clicked = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._show_procedural = True
        self._show_declarative = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(4, 4, 4, 4)
        self._btn_proc = QPushButton("Procedural")
        self._btn_proc.setCheckable(True)
        self._btn_proc.setChecked(True)
        self._btn_proc.clicked.connect(self._on_filter_changed)
        self._btn_decl = QPushButton("Declarative")
        self._btn_decl.setCheckable(True)
        self._btn_decl.setChecked(True)
        self._btn_decl.clicked.connect(self._on_filter_changed)
        filter_bar.addWidget(self._btn_proc)
        filter_bar.addWidget(self._btn_decl)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._model = QStandardItemModel()
        self._tree.setModel(self._model)
        layout.addWidget(self._tree)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def _rebuild(self) -> None:
        self._model.clear()
        if not self._project:
            return
        root = self._model.invisibleRootItem()

        proj_item = QStandardItem(self._project.name)
        proj_item.setForeground(_COLOR_FOLDER)
        proj_item.setEditable(False)
        root.appendRow(proj_item)

        skills_folder = QStandardItem("Skills")
        skills_folder.setForeground(_COLOR_FOLDER)
        skills_folder.setEditable(False)
        proj_item.appendRow(skills_folder)

        for skill in self._project.skills:
            if isinstance(skill, ProceduralSkill) and not self._show_procedural:
                continue
            if isinstance(skill, DeclarativeSkill) and not self._show_declarative:
                continue
            item = QStandardItem(skill.name)
            item.setData(skill, _ROLE_COMPONENT)
            item.setEditable(False)
            if isinstance(skill, ProceduralSkill):
                item.setForeground(_COLOR_PROCEDURAL)
            else:
                item.setForeground(_COLOR_DECLARATIVE)
            skills_folder.appendRow(item)

        agents_folder = QStandardItem("Agents")
        agents_folder.setForeground(_COLOR_FOLDER)
        agents_folder.setEditable(False)
        proj_item.appendRow(agents_folder)

        for agent in self._project.agents:
            item = QStandardItem(agent.name)
            item.setData(agent, _ROLE_COMPONENT)
            item.setEditable(False)
            item.setForeground(_COLOR_AGENT)
            agents_folder.appendRow(item)

        self._tree.expandAll()

    def _on_filter_changed(self) -> None:
        self._show_procedural = self._btn_proc.isChecked()
        self._show_declarative = self._btn_decl.isChecked()
        self._rebuild()

    def _on_double_click(self, index) -> None:
        item = self._model.itemFromIndex(index)
        if item:
            component = item.data(_ROLE_COMPONENT)
            if component is not None:
                self.component_double_clicked.emit(component)
```

- [ ] **Step 2: Implement PropertyPanel**

```python
# daedalus/view/panels/property_panel.py
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.commands.state_commands import RenameStateCmd
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class PropertyPanel(QWidget):
    """선택한 노드/전이의 속성을 표시/편집."""

    def __init__(self, project_vm: ProjectViewModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_vm = project_vm

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._title = QLabel("선택 없음")
        self._title.setStyleSheet("color: #888; font-size: 10px;")
        self._layout.addWidget(self._title)

        self._form_widget = QWidget()
        self._form = QFormLayout(self._form_widget)
        self._layout.addWidget(self._form_widget)
        self._layout.addStretch()

    def show_state(self, state_vm: StateViewModel) -> None:
        self._clear_form()
        self._title.setText("PROPERTIES — SimpleState")

        name_edit = QLineEdit(state_vm.model.name)
        name_edit.editingFinished.connect(
            lambda: self._rename_state(state_vm, name_edit.text())
        )
        self._form.addRow("Name", name_edit)
        self._form.addRow("on_entry", QLabel(f"{len(state_vm.model.on_entry)} action(s)"))
        self._form.addRow("on_exit", QLabel(f"{len(state_vm.model.on_exit)} action(s)"))
        self._form.addRow("x", QLabel(f"{state_vm.x:.0f}"))
        self._form.addRow("y", QLabel(f"{state_vm.y:.0f}"))

    def show_transition(self, transition_vm: TransitionViewModel) -> None:
        self._clear_form()
        self._title.setText("PROPERTIES — Transition")
        self._form.addRow("Source", QLabel(transition_vm.source_vm.model.name))
        self._form.addRow("Target", QLabel(transition_vm.target_vm.model.name))
        self._form.addRow("Type", QLabel(transition_vm.model.type.value))

    def clear(self) -> None:
        self._clear_form()
        self._title.setText("선택 없음")

    def _clear_form(self) -> None:
        while self._form.rowCount() > 0:
            self._form.removeRow(0)

    def _rename_state(self, state_vm: StateViewModel, new_name: str) -> None:
        old_name = state_vm.model.name
        if new_name and new_name != old_name:
            self._project_vm.execute(RenameStateCmd(state_vm, old_name, new_name))
```

- [ ] **Step 3: Implement HistoryPanel**

```python
# daedalus/view/panels/history_panel.py
from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from daedalus.view.commands.base import CommandStack

_HIGHLIGHT_BG = QColor("#2a2a4a")
_TEXT_COLOR = QColor("#ccc")
_DIM_COLOR = QColor("#555")


class HistoryPanel(QWidget):
    """커맨드 이력 표시 + 클릭으로 goto."""

    def __init__(self, command_stack: CommandStack, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack = command_stack
        self._stack.add_listener(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def _rebuild(self) -> None:
        self._list.clear()
        current = self._stack.current_index
        for i, cmd in enumerate(self._stack.history):
            item = QListWidgetItem(f"  {cmd.description}")
            if i == current:
                item.setBackground(_HIGHLIGHT_BG)
                item.setForeground(_TEXT_COLOR)
            else:
                item.setForeground(_DIM_COLOR)
            self._list.addItem(item)
        if self._stack.history:
            self._list.scrollToBottom()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        if row != self._stack.current_index:
            self._stack.goto(row)
```

- [ ] **Step 4: Commit**

```bash
git add daedalus/view/panels/
git commit -m "feat: add tree, property, and history panels"
```

---

## Task 9: Main Window Assembly & Entry Point

**Files:**
- Create: `daedalus/view/app.py`
- Create: `daedalus/view/editors/decl_skill_editor.py`
- Modify: `daedalus/__main__.py`

- [ ] **Step 1: Create DeclarativeSkill placeholder editor**

```python
# daedalus/view/editors/decl_skill_editor.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from daedalus.model.plugin.skill import DeclarativeSkill


class DeclSkillEditor(QWidget):
    """DeclarativeSkill 폼 에디터 — A단계 placeholder."""

    def __init__(self, skill: DeclarativeSkill, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch()
        label = QLabel(f"{skill.name}\n\n편집 기능 준비 중")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(label)
        layout.addStretch()
```

- [ ] **Step 2: Implement MainWindow**

```python
# daedalus/view/app.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
)

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.canvas.canvas_view import FsmCanvasView
from daedalus.view.canvas.edge_item import TransitionEdgeItem
from daedalus.view.canvas.node_item import StateNodeItem
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.editors.decl_skill_editor import DeclSkillEditor
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.tree_panel import ProjectTreePanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1200, 800)

        self._project_vm = ProjectViewModel()
        self._open_tabs: dict[str, int] = {}

        self._setup_central()
        self._setup_docks()
        self._setup_menus()
        self._setup_statusbar()
        self._connect_signals()

    def _setup_central(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

    def _setup_docks(self) -> None:
        self._tree_panel = ProjectTreePanel()
        tree_dock = QDockWidget("Project")
        tree_dock.setWidget(self._tree_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tree_dock)

        self._history_panel = HistoryPanel(self._project_vm.command_stack)
        history_dock = QDockWidget("History")
        history_dock.setWidget(self._history_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, history_dock)

        self._property_panel = PropertyPanel(self._project_vm)
        prop_dock = QDockWidget("Properties")
        prop_dock.setWidget(self._property_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, prop_dock)

    def _setup_menus(self) -> None:
        menubar = self.menuBar()

        edit_menu = menubar.addMenu("Edit")
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menubar.addMenu("View")
        for dock in self.findChildren(QDockWidget):
            view_menu.addAction(dock.toggleViewAction())

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel("Ready")
        self._statusbar.addWidget(self._status_label)
        self._project_vm.add_listener(self._update_statusbar)

    def _update_statusbar(self) -> None:
        s = len(self._project_vm.state_vms)
        t = len(self._project_vm.transition_vms)
        self._status_label.setText(f"States: {s} | Transitions: {t}")

    def _connect_signals(self) -> None:
        self._tree_panel.component_double_clicked.connect(self._open_component)
        self._project_vm.command_stack.add_listener(self._update_undo_redo)

    def _update_undo_redo(self) -> None:
        stack = self._project_vm.command_stack
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        if stack.can_undo:
            self._undo_action.setText(f"Undo: {stack.history[-1].description}")
        else:
            self._undo_action.setText("Undo")

    def _open_component(self, component) -> None:
        name = component.name
        if name in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[name])
            return
        if isinstance(component, (ProceduralSkill, AgentDefinition)):
            scene = FsmScene(self._project_vm)
            view = FsmCanvasView(scene)
            scene.selectionChanged.connect(lambda s=scene: self._on_scene_selection(s))
            idx = self._tabs.addTab(view, name)
        elif isinstance(component, DeclarativeSkill):
            idx = self._tabs.addTab(DeclSkillEditor(component), name)
        else:
            return
        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }

    def _on_tab_changed(self, index: int) -> None:
        if index < 0:
            self._property_panel.clear()

    def _on_scene_selection(self, scene: FsmScene) -> None:
        selected = scene.selectedItems()
        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, StateNodeItem):
                self._property_panel.show_state(item.state_vm)
            elif isinstance(item, TransitionEdgeItem):
                self._property_panel.show_transition(item.transition_vm)
        else:
            self._property_panel.clear()

    def _undo(self) -> None:
        self._project_vm.command_stack.undo()
        self._project_vm.notify()

    def _redo(self) -> None:
        self._project_vm.command_stack.redo()
        self._project_vm.notify()

    def set_project(self, project: PluginProject) -> None:
        self._tree_panel.set_project(project)
```

- [ ] **Step 3: Update `__main__.py` with demo project and dark theme**

```python
# daedalus/__main__.py
import sys

from PyQt6.QtWidgets import QApplication

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow

_DARK_STYLE = """
QMainWindow, QWidget { background-color: #1a1a2e; color: #ccc; }
QMenuBar { background-color: #252540; color: #999; }
QMenuBar::item:selected { background-color: #334; }
QMenu { background-color: #252540; color: #ccc; }
QMenu::item:selected { background-color: #334; }
QDockWidget::title { background-color: #252540; color: #888; padding: 4px; }
QTabWidget::pane { border: 1px solid #333; }
QTabBar::tab { background: #252540; color: #666; padding: 6px 14px; }
QTabBar::tab:selected { background: #1a1a2e; color: #ccc; border-top: 2px solid #6674cc; }
QTreeView { background-color: #1e1e32; border: none; }
QListWidget { background-color: #1e1e32; border: none; }
QLineEdit { background-color: #252540; border: 1px solid #444; border-radius: 3px;
            padding: 4px 8px; color: #88aaff; }
QPushButton { background-color: #252540; border: 1px solid #444; border-radius: 3px;
              padding: 4px 8px; color: #ccc; }
QPushButton:checked { background-color: #334; border-color: #6674cc; color: #88aaff; }
QStatusBar { background-color: #252540; color: #555; }
QLabel { color: #ccc; }
"""


def _demo_project() -> PluginProject:
    """개발용 데모 프로젝트."""
    s1 = SimpleState(name="Start")
    s2 = SimpleState(name="Process")
    s3 = SimpleState(name="End")
    init_fsm = StateMachine(
        name="init_fsm",
        initial_state=s1,
        states=[s1, s2, s3],
        transitions=[Transition(source=s1, target=s2), Transition(source=s2, target=s3)],
        final_states=[s3],
    )
    init_skill = ProceduralSkill(fsm=init_fsm, name="init", description="초기화 스킬")

    c1 = SimpleState(name="Cleanup")
    cleanup_fsm = StateMachine(
        name="cleanup_fsm", initial_state=c1, states=[c1], final_states=[c1]
    )
    cleanup_skill = ProceduralSkill(fsm=cleanup_fsm, name="cleanup", description="정리 스킬")

    rules_skill = DeclarativeSkill(name="rules", description="기반 규칙", content="코딩 컨벤션")

    w1 = SimpleState(name="Receive")
    w2 = SimpleState(name="Execute")
    worker_fsm = StateMachine(
        name="worker_fsm",
        initial_state=w1,
        states=[w1, w2],
        transitions=[Transition(source=w1, target=w2)],
        final_states=[w2],
    )
    worker = AgentDefinition(fsm=worker_fsm, name="worker", description="작업 에이전트")

    return PluginProject(
        name="MyPlugin",
        skills=[init_skill, cleanup_skill, rules_skill],
        agents=[worker],
    )


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(_DARK_STYLE)

    window = MainWindow()
    window.set_project(_demo_project())
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke test**

Run: `uv run python -m daedalus`

체크리스트:
1. 다크 테마 윈도우 열림
2. 좌측 트리: MyPlugin > Skills (init=초록, cleanup=초록, rules=노랑) + Agents (worker=빨강)
3. 필터 토글로 Procedural/Declarative 숨기기/보이기
4. init 더블클릭 → 캔버스 탭 열림
5. rules 더블클릭 → placeholder 폼 탭 열림
6. 캔버스 우클릭 → "상태 추가" → 노드 생성
7. 노드 드래그 → 이동
8. 노드 선택 → 프로퍼티 패널 갱신
9. Ctrl+Z / Ctrl+Y → Undo/Redo
10. 히스토리 패널에 이력 표시, 클릭으로 goto
11. Delete → 삭제 (연결 전이도 함께)
12. 상태바에 States/Transitions 수 표시

- [ ] **Step 5: Commit**

```bash
git add daedalus/view/app.py daedalus/view/editors/decl_skill_editor.py daedalus/__main__.py
git commit -m "feat: assemble MainWindow with docks, tabs, menus, and demo project"
```

- [ ] **Step 6: Run full test suite**

Run: `uv run python -m pytest tests/ -v`

Expected: 기존 model 102개 + 새 view 35개 = 137개 PASS

- [ ] **Step 7: Final fixup commit (if needed)**

```bash
git add -A
git commit -m "fix: address smoke test issues"
```
