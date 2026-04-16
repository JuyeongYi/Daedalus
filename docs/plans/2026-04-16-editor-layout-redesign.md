# Editor Layout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SkillEditor/AgentEditor의 QStackedWidget 레이아웃을 재사용 가능한 `ComponentEditor` 위젯 기반 스플리터 레이아웃으로 교체한다.

**Architecture:** 좌측(SectionTree + FrontmatterPanel), 중앙(BreadcrumbNav + ContentPanel), 우측(옵션, 타입별 위젯)의 3컬럼 QSplitter. 좌측/우측은 내부 수직 QSplitter. 우측 위젯이 없으면 2컬럼. 기존 위젯(`_FrontmatterPanel`, `SectionTree`, `BreadcrumbNav`, `SectionContentPanel`, `_TransferOnPanel`, `_ContractButtons`)은 변경 없이 재사용.

**Tech Stack:** Python 3.12, PyQt6, dataclass 모델

---

### File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `daedalus/view/editors/component_editor.py` | 재사용 복합 에디터 위젯 |
| Create | `tests/view/editors/test_component_editor.py` | ComponentEditor 테스트 |
| Modify | `daedalus/view/editors/skill_editor.py` | SkillEditor를 ComponentEditor 래퍼로 변경 |
| Modify | `daedalus/view/editors/agent_editor.py` | Content 탭을 ComponentEditor로 교체 |
| Modify | `tests/view/editors/test_skill_editor.py` | 기존 테스트를 새 레이아웃에 맞게 수정 |

---

### Task 1: ComponentEditor 테스트 작성

**Files:**
- Create: `tests/view/editors/test_component_editor.py`

- [ ] **Step 1: 2컬럼 모드 테스트 작성**

```python
# tests/view/editors/test_component_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QSplitter, QWidget


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="d")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="K", description="d")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="d")


def test_two_column_no_right_widgets(qapp):
    """right_widgets가 없으면 2컬럼(좌측+중앙)만 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 2  # left + center


def test_three_column_with_right_widgets(qapp):
    """right_widgets가 있으면 3컬럼(좌측+중앙+우측)."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_procedural()
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    rw = [_TransferOnPanel(comp.transfer_on)]
    editor = ComponentEditor(comp, right_widgets=rw)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 3  # left + center + right


def test_left_splitter_has_tree_and_frontmatter(qapp):
    """좌측 수직 스플리터에 SectionTree + FrontmatterPanel."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.body_editor import SectionTree
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    tree = editor.findChild(SectionTree)
    fm = editor.findChild(_FrontmatterPanel)
    assert tree is not None
    assert fm is not None


def test_center_has_breadcrumb_and_content(qapp):
    """중앙에 BreadcrumbNav + SectionContentPanel."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.body_editor import BreadcrumbNav, SectionContentPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    nav = editor.findChild(BreadcrumbNav)
    cp = editor.findChild(SectionContentPanel)
    assert nav is not None
    assert cp is not None


def test_changed_signal(qapp):
    """changed 시그널이 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    assert hasattr(editor, "changed")


def test_right_widgets_in_vertical_splitter(qapp):
    """우측 위젯이 수직 스플리터에 배치."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    comp = _make_procedural()
    t1 = _TransferOnPanel(comp.transfer_on)
    t2 = _TransferOnPanel(comp.call_agents, default_color="#8a4a4a", multiline_desc=True)
    editor = ComponentEditor(comp, right_widgets=[t1, t2])
    # 우측 스플리터는 수직이어야 함
    splitters = editor.findChildren(QSplitter)
    # root(H) + left(V) + right(V) = 3개
    assert len(splitters) >= 3


def test_on_notify_callback(qapp):
    """on_notify_fn이 모델 변경 시 호출."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    called = []
    editor = ComponentEditor(comp, on_notify_fn=lambda: called.append(1))
    editor._on_model_changed()
    assert len(called) == 1
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `python -m pytest tests/view/editors/test_component_editor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'daedalus.view.editors.component_editor'`

---

### Task 2: ComponentEditor 구현

**Files:**
- Create: `daedalus/view/editors/component_editor.py`

- [ ] **Step 3: ComponentEditor 위젯 작성**

```python
# daedalus/view/editors/component_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.view.editors.body_editor import (
    BreadcrumbNav,
    SectionContentPanel,
    SectionTree,
    VariablePopup,
    find_path,
)
from daedalus.view.editors.skill_editor import _FrontmatterPanel
from daedalus.view.editors.variable_loader import load_variables

_ComponentType = ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition

_LEFT_MIN_W = 120
_LEFT_CHILD_MIN_H = 80
_CENTER_MIN_W = 200
_RIGHT_MIN_W = 120
_RIGHT_CHILD_MIN_H = 60


class ComponentEditor(QWidget):
    """재사용 복합 에디터 — 좌(SectionTree+Frontmatter) | 중(Breadcrumb+Content) | 우(옵션)."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: _ComponentType,
        right_widgets: list[QWidget] | None = None,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn

        variables = load_variables()

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 좌측: SectionTree + FrontmatterPanel (수직 스플리터) ---
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setMinimumWidth(_LEFT_MIN_W)

        self._section_tree = SectionTree(component.sections)
        self._section_tree.setMinimumHeight(_LEFT_CHILD_MIN_H)
        self._section_tree.section_selected.connect(self._on_tree_selected)
        self._section_tree.structure_changed.connect(self._on_structure_changed)
        self._section_tree.add_root_requested.connect(
            lambda: self._on_breadcrumb_add(None, 0)
        )
        left_splitter.addWidget(self._section_tree)

        self._fm = _FrontmatterPanel(component)
        self._fm.setMinimumHeight(_LEFT_CHILD_MIN_H)
        self._fm.changed.connect(self._on_model_changed)
        left_splitter.addWidget(self._fm)

        root_splitter.addWidget(left_splitter)

        # --- 중앙: BreadcrumbNav + SectionContentPanel ---
        center = QWidget()
        center.setMinimumWidth(_CENTER_MIN_W)
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)

        self._breadcrumb = BreadcrumbNav(component.sections)
        self._breadcrumb.section_selected.connect(self._on_breadcrumb_selected)
        self._breadcrumb.section_add_requested.connect(self._on_breadcrumb_add)
        center_lay.addWidget(self._breadcrumb)

        self._content_panel = SectionContentPanel()
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._content_panel.add_child_requested.connect(self._on_add_child)
        center_lay.addWidget(self._content_panel, 1)

        root_splitter.addWidget(center)

        # --- 우측: right_widgets (수직 스플리터, 있을 때만) ---
        rw = right_widgets or []
        if rw:
            right_splitter = QSplitter(Qt.Orientation.Vertical)
            right_splitter.setMinimumWidth(_RIGHT_MIN_W)
            for w in rw:
                w.setMinimumHeight(_RIGHT_CHILD_MIN_H)
                right_splitter.addWidget(w)
            root_splitter.addWidget(right_splitter)

        # stretch: 좌0, 중1, 우0
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)
        if rw:
            root_splitter.setStretchFactor(2, 0)

        root_lay.addWidget(root_splitter)

        # Variable popup
        self._var_popup = VariablePopup(variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        # Initial selection
        if component.sections:
            self._select_section(component.sections[0])

    # --- 섹션 네비게이션 ---

    def _select_section(self, section: Section) -> None:
        path = find_path(section, self._component.sections)
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

    def _on_breadcrumb_add(self, parent: Section | None, depth: int) -> None:
        siblings = self._component.sections if parent is None else parent.children
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

    def _on_add_child(self) -> None:
        if self._content_panel._section is None:
            return
        self._on_breadcrumb_add(self._content_panel._section, 0)

    def _on_structure_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
        self._on_model_changed()

    def _on_content_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
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
        self.changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    def show_contract_section(self, section: Section) -> None:
        """잠금 계약 섹션 표시 — 타이틀 잠금, 내용만 편집 가능."""
        self._content_panel.show_section(section, [section.title], title_locked=True)
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `python -m pytest tests/view/editors/test_component_editor.py -v`
Expected: 8 tests PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/editors/component_editor.py tests/view/editors/test_component_editor.py
git commit -m "feat: add ComponentEditor reusable composite widget"
```

---

### Task 3: SkillEditor를 ComponentEditor 래퍼로 변경

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py:450-643` (SkillEditor 클래스 전체)

- [ ] **Step 6: SkillEditor 클래스를 ComponentEditor 기반으로 재작성**

`SkillEditor` 클래스를 아래로 교체. `_OptionalRow`, `_FrontmatterPanel`, `_ColorPickerPopup`, `_EventCard`, `_ContractButtons`, `_TransferOnPanel`은 그대로 유지.

```python
class SkillEditor(QWidget):
    """스킬/에이전트 편집기 — ComponentEditor + 타입별 우측 패널."""

    skill_changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        show_call_agents: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from daedalus.view.editors.component_editor import ComponentEditor

        right_widgets: list[QWidget] = []
        if isinstance(component, ProceduralSkill):
            right_widgets.append(_TransferOnPanel(component.transfer_on))
            if show_call_agents:
                right_widgets.append(
                    _TransferOnPanel(component.call_agents, default_color="#8a4a4a", multiline_desc=True)
                )

        self._editor = ComponentEditor(
            component,
            right_widgets=right_widgets,
            on_notify_fn=self._on_notify,
        )

        self._on_notify_fn = on_notify_fn

        # right_widgets의 changed 시그널 연결
        for w in right_widgets:
            if hasattr(w, "transfer_on_changed"):
                w.transfer_on_changed.connect(self._editor._on_model_changed)

        self._editor.changed.connect(self.skill_changed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._editor)

    def _on_notify(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
```

- [ ] **Step 7: SkillEditor에서 삭제할 코드**

기존 SkillEditor 클래스의 다음 메서드/코드를 모두 삭제:
- `__init__`의 QSplitter/QStackedWidget 구성 코드
- `_select_section`, `_on_tree_selected`, `_on_breadcrumb_selected`
- `_on_breadcrumb_add`, `_on_add_child`
- `_on_transfer_on_selected`, `_on_call_agents_selected`
- `_on_structure_changed`, `_on_content_changed`
- `_on_variable_insert`, `_on_model_changed`

이 메서드들은 모두 `ComponentEditor`로 이동했음.

- [ ] **Step 8: 기존 테스트 실행 — 통과 확인**

Run: `python -m pytest tests/view/editors/test_skill_editor.py -v`
Expected: 기존 테스트에서 `findChild(QSplitter)`, `findChild(BreadcrumbNav)`, `findChild(SectionTree)` 등은 ComponentEditor 내부에서 찾아지므로 통과해야 함.

- [ ] **Step 9: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 268+ tests PASS

- [ ] **Step 10: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py
git commit -m "refactor: SkillEditor wraps ComponentEditor, remove QStackedWidget"
```

---

### Task 4: AgentEditor Content 탭을 ComponentEditor로 교체

**Files:**
- Modify: `daedalus/view/editors/agent_editor.py:282-352` (`_build_content_tab` 메서드)

- [ ] **Step 11: `_build_content_tab`를 ComponentEditor 기반으로 재작성**

```python
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

    # 계약 섹션 클릭 → content panel에 잠금 표시
    self._caller_contract_buttons.section_clicked.connect(
        self._component_editor.show_contract_section
    )

    return self._component_editor
```

- [ ] **Step 12: AgentEditor에서 삭제할 코드**

Content 탭 관련 중복 메서드 삭제:
- `_select_section`, `_on_tree_selected`, `_on_breadcrumb_selected`
- `_on_breadcrumb_add`, `_on_add_child`
- `_on_structure_changed`, `_on_contract_clicked`
- `_on_content_changed`, `_on_variable_insert`

`_build_content_tab`에서 사용하던 인스턴스 변수 삭제:
- `self._fm_panel`, `self._section_tree`, `self._breadcrumb`
- `self._content_panel`, `self._var_popup`

`_on_model_changed`에서 `_caller_contract_buttons.refresh()` 호출은 유지.

AgentEditor `__init__`의 initial section selection도 수정:
```python
# 기존:
if agent.sections:
    self._select_section(agent.sections[0])
# 이 코드 삭제 — ComponentEditor가 자체적으로 initial selection 처리
```

미사용 import 정리: `BreadcrumbNav`, `SectionContentPanel`, `SectionTree`, `VariablePopup`, `find_path` 등.

- [ ] **Step 13: 기존 AgentEditor 테스트 실행**

Run: `python -m pytest tests/view/editors/test_agent_editor.py -v`
Expected: PASS

- [ ] **Step 14: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 268+ tests PASS

- [ ] **Step 15: 커밋**

```bash
git add daedalus/view/editors/agent_editor.py
git commit -m "refactor: AgentEditor Content tab uses ComponentEditor"
```

---

### Task 5: 정리 및 최종 검증

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py` (미사용 import 정리)
- Modify: `daedalus/view/editors/agent_editor.py` (미사용 import 정리)

- [ ] **Step 16: 미사용 import 정리**

`skill_editor.py`에서 더 이상 사용하지 않는 import 제거:
- `QSplitter`, `QStackedWidget` (ComponentEditor로 이동)
- `SectionTree`, `BreadcrumbNav`, `SectionContentPanel`, `VariablePopup`, `find_path` (ComponentEditor에서 import)

`agent_editor.py`에서 더 이상 사용하지 않는 import 제거:
- `BreadcrumbNav`, `SectionContentPanel`, `SectionTree`, `VariablePopup`, `find_path`
- `_FrontmatterPanel` (ComponentEditor 내부에서 import)

- [ ] **Step 17: 전체 테스트 + Pyright 진단 확인**

Run: `python -m pytest tests/ -v`
Expected: 276+ tests PASS (기존 268 + 신규 8)

- [ ] **Step 18: 최종 커밋**

```bash
git add -A
git commit -m "chore: clean up unused imports after editor layout redesign"
```
