# Frontmatter Field Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스킬 프론트매터 필드를 전역 enum 매트릭스로 정의하고, 전용 위젯 클래스 기반 _FrontmatterPanel로 교체한다.

**Architecture:** `FieldVisibility`/`SkillField` enum + `FieldRule` dataclass로 매트릭스를 `field_matrix.py`에 한 번 정의. 콤보박스/태그/프리셋 위젯은 `daedalus/view/widgets/`에 각각 자기 선택지를 캡슐화. `_FrontmatterPanel`은 매트릭스를 읽어 REQUIRED/OPTIONAL만 위젯을 생성.

**Tech Stack:** Python 3.12, PyQt6, dataclass, Enum

---

### File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `daedalus/model/plugin/field_matrix.py` | FieldVisibility, SkillField enum + FieldRule + SKILL_FIELD_MATRIX |
| Create | `daedalus/view/widgets/__init__.py` | 위젯 패키지 |
| Create | `daedalus/view/widgets/combo_widgets.py` | ModelComboBox, EffortComboBox, ContextComboBox, ShellComboBox |
| Create | `daedalus/view/widgets/tag_input.py` | TagInput (list[str] 편집) |
| Create | `daedalus/view/widgets/preset_picker.py` | PresetPicker (폴더 스캔 체크리스트), HookPresetPicker, McpPresetPicker |
| Create | `tests/model/plugin/test_field_matrix.py` | 매트릭스 테스트 |
| Create | `tests/view/widgets/test_combo_widgets.py` | 콤보 위젯 테스트 |
| Create | `tests/view/widgets/test_tag_input.py` | TagInput 테스트 |
| Create | `tests/view/widgets/conftest.py` | qapp fixture 재사용 |
| Modify | `daedalus/model/plugin/enums.py` | FieldVisibility, SkillField 추가 |
| Modify | `daedalus/model/plugin/config.py` | FieldSpec, FIELD_REGISTRY 삭제 |
| Modify | `daedalus/view/editors/skill_editor.py` | _FrontmatterPanel을 매트릭스 기반으로 재작성 |
| Modify | `tests/model/plugin/test_config.py` | FieldSpec/FIELD_REGISTRY 테스트를 field_matrix로 이동 |

---

### Task 1: FieldVisibility, SkillField enum 추가

**Files:**
- Modify: `daedalus/model/plugin/enums.py`
- Create: `tests/model/plugin/test_field_matrix.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/model/plugin/test_field_matrix.py
from __future__ import annotations

from daedalus.model.plugin.enums import FieldVisibility, SkillField


def test_field_visibility_values():
    assert FieldVisibility.REQUIRED.value == "required"
    assert FieldVisibility.OPTIONAL.value == "optional"
    assert FieldVisibility.DEFAULT.value == "default"
    assert FieldVisibility.FIXED.value == "fixed"


def test_skill_field_values():
    assert SkillField.NAME.value == "name"
    assert SkillField.MODEL.value == "model"
    assert SkillField.HOOKS.value == "hooks"
    assert SkillField.DISABLE_MODEL.value == "disable_model_invocation"
    assert SkillField.USER_INVOCABLE.value == "user_invocable"
    # 14개 확인
    assert len(SkillField) == 14
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `python -m pytest tests/model/plugin/test_field_matrix.py -v`
Expected: FAIL — `ImportError: cannot import name 'FieldVisibility'`

- [ ] **Step 3: enums.py에 추가**

`daedalus/model/plugin/enums.py` 파일 끝에 추가:

```python
class FieldVisibility(Enum):
    """프론트매터 필드 표시 모드."""
    REQUIRED = "required"    # UI 표시, 입력 필요
    OPTIONAL = "optional"    # UI 표시, 체크박스 활성/비활성
    DEFAULT = "default"      # UI 미표시, 컴파일 시 필드 생략
    FIXED = "fixed"          # UI 미표시, 컴파일 시 고정값 출력


class SkillField(Enum):
    """스킬 프론트매터 필드 식별자."""
    NAME = "name"
    DESCRIPTION = "description"
    WHEN_TO_USE = "when_to_use"
    ARGUMENT_HINT = "argument_hint"
    MODEL = "model"
    EFFORT = "effort"
    ALLOWED_TOOLS = "allowed_tools"
    CONTEXT = "context"
    AGENT = "agent"
    SHELL = "shell"
    PATHS = "paths"
    HOOKS = "hooks"
    DISABLE_MODEL = "disable_model_invocation"
    USER_INVOCABLE = "user_invocable"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/model/plugin/test_field_matrix.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/plugin/enums.py tests/model/plugin/test_field_matrix.py
git commit -m "feat: add FieldVisibility and SkillField enums"
```

---

### Task 2: 콤보 위젯 4개 생성

**Files:**
- Create: `daedalus/view/widgets/__init__.py`
- Create: `daedalus/view/widgets/combo_widgets.py`
- Create: `tests/view/widgets/__init__.py`
- Create: `tests/view/widgets/conftest.py`
- Create: `tests/view/widgets/test_combo_widgets.py`

- [ ] **Step 6: 테스트 작성**

```python
# tests/view/widgets/test_combo_widgets.py
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox


def test_model_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ModelComboBox
    w = ModelComboBox()
    assert isinstance(w, QComboBox)
    items = [w.itemText(i) for i in range(w.count())]
    assert "sonnet" in items
    assert "opus" in items
    assert "haiku" in items


def test_effort_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import EffortComboBox
    w = EffortComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "low" in items
    assert "max" in items


def test_context_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ContextComboBox
    w = ContextComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "inline" in items
    assert "fork" in items


def test_shell_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ShellComboBox
    w = ShellComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "bash" in items
    assert "powershell" in items
```

conftest.py (tests/view/widgets/conftest.py):
```python
# tests/view/widgets/conftest.py — qapp fixture는 상위 conftest.py에서 상속
```

- [ ] **Step 7: 실행 — 실패 확인**

Run: `python -m pytest tests/view/widgets/test_combo_widgets.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 8: 위젯 구현**

```python
# daedalus/view/widgets/__init__.py
```

```python
# daedalus/view/widgets/combo_widgets.py
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell


class ModelComboBox(QComboBox):
    """모델 선택 콤보박스 — sonnet/opus/haiku."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for m in ModelType:
            if m != ModelType.INHERIT:
                self.addItem(m.value)


class EffortComboBox(QComboBox):
    """Effort 레벨 콤보박스 — low/medium/high/max."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for e in EffortLevel:
            self.addItem(e.value)


class ContextComboBox(QComboBox):
    """실행 컨텍스트 콤보박스 — inline/fork."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for c in SkillContext:
            self.addItem(c.value)


class ShellComboBox(QComboBox):
    """셸 선택 콤보박스 — bash/powershell."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for s in SkillShell:
            self.addItem(s.value)
```

- [ ] **Step 9: 테스트 통과 확인**

Run: `python -m pytest tests/view/widgets/test_combo_widgets.py -v`
Expected: 4 tests PASS

- [ ] **Step 10: 커밋**

```bash
git add daedalus/view/widgets/ tests/view/widgets/
git commit -m "feat: add combo widget classes (Model, Effort, Context, Shell)"
```

---

### Task 3: TagInput 위젯 생성

**Files:**
- Create: `daedalus/view/widgets/tag_input.py`
- Create: `tests/view/widgets/test_tag_input.py`

- [ ] **Step 11: 테스트 작성**

```python
# tests/view/widgets/test_tag_input.py
from __future__ import annotations


def test_tag_input_empty(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    assert w.get_tags() == []


def test_tag_input_set_tags(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep", "Bash"])
    assert w.get_tags() == ["Read", "Grep", "Bash"]


def test_tag_input_add_tag(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.add_tag("Read")
    w.add_tag("Grep")
    assert w.get_tags() == ["Read", "Grep"]


def test_tag_input_no_duplicates(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.add_tag("Read")
    w.add_tag("Read")
    assert w.get_tags() == ["Read"]


def test_tag_input_remove_tag(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep", "Bash"])
    w.remove_tag("Grep")
    assert w.get_tags() == ["Read", "Bash"]


def test_tag_input_changed_signal(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    called = []
    w.tags_changed.connect(lambda: called.append(1))
    w.add_tag("Read")
    assert len(called) == 1
```

- [ ] **Step 12: 실행 — 실패 확인**

Run: `python -m pytest tests/view/widgets/test_tag_input.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 13: TagInput 구현**

```python
# daedalus/view/widgets/tag_input.py
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _TagChip(QWidget):
    """개별 태그 칩 — 이름 + x 버튼."""

    remove_requested = pyqtSignal(str)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        from PyQt6.QtWidgets import QLabel
        lay.addWidget(QLabel(name))
        btn = QPushButton("x")
        btn.setFixedSize(16, 16)
        btn.clicked.connect(lambda: self.remove_requested.emit(self._name))
        lay.addWidget(btn)

    @property
    def name(self) -> str:
        return self._name


class TagInput(QWidget):
    """태그 입력 위젯 — list[str] 편집. Enter로 추가, x로 제거."""

    tags_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        self._chips_layout.addStretch()
        lay.addWidget(self._chips_widget)

        self._input = QLineEdit()
        self._input.setPlaceholderText("입력 후 Enter")
        self._input.returnPressed.connect(self._on_enter)
        lay.addWidget(self._input)

    def get_tags(self) -> list[str]:
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild()

    def add_tag(self, tag: str) -> None:
        tag = tag.strip()
        if not tag or tag in self._tags:
            return
        self._tags.append(tag)
        self._rebuild()
        self.tags_changed.emit()

    def remove_tag(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.tags_changed.emit()

    def _on_enter(self) -> None:
        text = self._input.text().strip()
        if text:
            self.add_tag(text)
            self._input.clear()

    def _rebuild(self) -> None:
        while self._chips_layout.count() > 1:
            child = self._chips_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        for tag in self._tags:
            chip = _TagChip(tag)
            chip.remove_requested.connect(self.remove_tag)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)
```

- [ ] **Step 14: 테스트 통과 확인**

Run: `python -m pytest tests/view/widgets/test_tag_input.py -v`
Expected: 6 tests PASS

- [ ] **Step 15: 커밋**

```bash
git add daedalus/view/widgets/tag_input.py tests/view/widgets/test_tag_input.py
git commit -m "feat: add TagInput widget for list[str] editing"
```

---

### Task 4: PresetPicker 위젯 생성

**Files:**
- Create: `daedalus/view/widgets/preset_picker.py`
- Create: `tests/view/widgets/test_preset_picker.py`

- [ ] **Step 16: 테스트 작성**

```python
# tests/view/widgets/test_preset_picker.py
from __future__ import annotations

import os
import tempfile


def test_preset_picker_empty_dir(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        w = PresetPicker(scan_path=d)
        assert w.get_selected() == []


def test_preset_picker_scans_json_files(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        # .json 파일 2개 생성
        for name in ["hook-a.json", "hook-b.json", "readme.txt"]:
            with open(os.path.join(d, name), "w") as f:
                f.write("{}")
        w = PresetPicker(scan_path=d)
        items = w.get_available()
        assert "hook-a" in items
        assert "hook-b" in items
        assert "readme" not in items  # .json만


def test_preset_picker_select_and_get(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        for name in ["a.json", "b.json"]:
            with open(os.path.join(d, name), "w") as f:
                f.write("{}")
        w = PresetPicker(scan_path=d)
        w.set_selected(["a"])
        assert w.get_selected() == ["a"]


def test_preset_picker_changed_signal(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "x.json"), "w") as f:
            f.write("{}")
        w = PresetPicker(scan_path=d)
        called = []
        w.selection_changed.connect(lambda: called.append(1))
        w.set_selected(["x"])
        assert len(called) == 1


def test_preset_picker_nonexistent_dir(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    w = PresetPicker(scan_path="/nonexistent/path/12345")
    assert w.get_available() == []
    assert w.get_selected() == []
```

- [ ] **Step 17: 실행 — 실패 확인**

Run: `python -m pytest tests/view/widgets/test_preset_picker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 18: PresetPicker 구현**

```python
# daedalus/view/widgets/preset_picker.py
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget


class PresetPicker(QWidget):
    """폴더 스캔 → .json 파일 체크리스트. 선택한 파일 이름(확장자 제외)을 반환."""

    selection_changed = pyqtSignal()

    def __init__(
        self,
        scan_path: str = "",
        label: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scan_path = scan_path
        self._checkboxes: dict[str, QCheckBox] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        if label:
            lay.addWidget(QLabel(label))

        self._items_layout = QVBoxLayout()
        lay.addLayout(self._items_layout)

        self._scan()

    def _scan(self) -> None:
        """scan_path에서 .json 파일 목록을 읽어 체크박스 생성."""
        self._checkboxes.clear()
        while self._items_layout.count():
            child = self._items_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        if not self._scan_path or not os.path.isdir(self._scan_path):
            return

        for name in sorted(os.listdir(self._scan_path)):
            if not name.endswith(".json"):
                continue
            stem = Path(name).stem
            cb = QCheckBox(stem)
            cb.toggled.connect(lambda _checked: self.selection_changed.emit())
            self._checkboxes[stem] = cb
            self._items_layout.addWidget(cb)

    def get_available(self) -> list[str]:
        return list(self._checkboxes.keys())

    def get_selected(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected(self, names: list[str]) -> None:
        for name, cb in self._checkboxes.items():
            cb.setChecked(name in names)
        self.selection_changed.emit()


class HookPresetPicker(PresetPicker):
    """Hooks 프리셋 피커 — .claude/hooks/ 스캔."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(scan_path=".claude/hooks", label="Hooks", parent=parent)


class McpPresetPicker(PresetPicker):
    """MCP 서버 프리셋 피커 — .claude/mcp/ 스캔."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(scan_path=".claude/mcp", label="MCP Servers", parent=parent)
```

- [ ] **Step 19: 테스트 통과 확인**

Run: `python -m pytest tests/view/widgets/test_preset_picker.py -v`
Expected: 5 tests PASS

- [ ] **Step 20: 커밋**

```bash
git add daedalus/view/widgets/preset_picker.py tests/view/widgets/test_preset_picker.py
git commit -m "feat: add PresetPicker widget for hook/mcp selection"
```

---

### Task 5: FieldRule + SKILL_FIELD_MATRIX 정의

**Files:**
- Create: `daedalus/model/plugin/field_matrix.py`
- Modify: `tests/model/plugin/test_field_matrix.py`

- [ ] **Step 21: 매트릭스 테스트 추가**

`tests/model/plugin/test_field_matrix.py`에 추가:

```python
from daedalus.model.plugin.field_matrix import FieldRule, SKILL_FIELD_MATRIX
from daedalus.model.plugin.enums import FieldVisibility, SkillField


def test_field_rule_dataclass():
    from PyQt6.QtWidgets import QLineEdit
    r = FieldRule(FieldVisibility.REQUIRED, QLineEdit, default_value="test")
    assert r.visibility == FieldVisibility.REQUIRED
    assert r.widget is QLineEdit
    assert r.default_value == "test"
    assert r.fixed_value is None


def test_matrix_has_all_skill_kinds():
    expected = {"procedural", "declarative", "transfer", "reference", "local_procedural", "local_transfer"}
    assert set(SKILL_FIELD_MATRIX.keys()) == expected


def test_matrix_procedural_model_required():
    rules = SKILL_FIELD_MATRIX["procedural"]
    assert rules[SkillField.MODEL].visibility == FieldVisibility.REQUIRED
    assert rules[SkillField.MODEL].default_value == "sonnet"


def test_matrix_transfer_fixed_values():
    rules = SKILL_FIELD_MATRIX["transfer"]
    assert rules[SkillField.DISABLE_MODEL].visibility == FieldVisibility.FIXED
    assert rules[SkillField.DISABLE_MODEL].fixed_value is True
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_reference_user_invocable_fixed():
    rules = SKILL_FIELD_MATRIX["reference"]
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_local_procedural_context_fixed_fork():
    rules = SKILL_FIELD_MATRIX["local_procedural"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.FIXED
    assert rules[SkillField.CONTEXT].fixed_value == "fork"


def test_matrix_declarative_context_default():
    rules = SKILL_FIELD_MATRIX["declarative"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.DEFAULT


def test_matrix_all_kinds_have_all_fields():
    """모든 kind에 14개 SkillField가 전부 정의되어 있어야 함."""
    for kind, rules in SKILL_FIELD_MATRIX.items():
        for field in SkillField:
            assert field in rules, f"{kind} missing {field.value}"
```

- [ ] **Step 22: 실행 — 실패 확인**

Run: `python -m pytest tests/model/plugin/test_field_matrix.py -v`
Expected: FAIL — `ImportError: cannot import name 'FieldRule'`

- [ ] **Step 23: field_matrix.py 구현**

```python
# daedalus/model/plugin/field_matrix.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtWidgets import QCheckBox, QLineEdit, QWidget

from daedalus.model.plugin.enums import FieldVisibility, SkillField
from daedalus.view.widgets.combo_widgets import (
    ContextComboBox,
    EffortComboBox,
    ModelComboBox,
    ShellComboBox,
)
from daedalus.view.widgets.preset_picker import HookPresetPicker
from daedalus.view.widgets.tag_input import TagInput

R = FieldVisibility.REQUIRED
O = FieldVisibility.OPTIONAL
D = FieldVisibility.DEFAULT
F = FieldVisibility.FIXED


@dataclass
class FieldRule:
    """프론트매터 필드 규칙 — visibility + widget 클래스 + 값."""
    visibility: FieldVisibility
    widget: type[QWidget]
    fixed_value: Any = None
    default_value: Any = None


# fmt: off
_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(O, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(O, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(O, ContextComboBox),
    SkillField.AGENT:          FieldRule(O, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(O, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(O, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(O, QCheckBox),
}

_DECLARATIVE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(O, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(O, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(D, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(D, ShellComboBox),
    SkillField.PATHS:          FieldRule(O, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(O, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(O, QCheckBox),
}

_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(O, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_REFERENCE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(D, TagInput),
    SkillField.CONTEXT:        FieldRule(D, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(D, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(D, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(D, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_LOCAL_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(D, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(F, ContextComboBox, fixed_value="fork"),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_LOCAL_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(D, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(F, ContextComboBox, fixed_value="fork"),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}
# fmt: on

SKILL_FIELD_MATRIX: dict[str, dict[SkillField, FieldRule]] = {
    "procedural": _PROCEDURAL,
    "declarative": _DECLARATIVE,
    "transfer": _TRANSFER,
    "reference": _REFERENCE,
    "local_procedural": _LOCAL_PROCEDURAL,
    "local_transfer": _LOCAL_TRANSFER,
}
```

- [ ] **Step 24: 테스트 통과 확인**

Run: `python -m pytest tests/model/plugin/test_field_matrix.py -v`
Expected: 10 tests PASS

- [ ] **Step 25: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 275+ tests PASS

- [ ] **Step 26: 커밋**

```bash
git add daedalus/model/plugin/field_matrix.py tests/model/plugin/test_field_matrix.py
git commit -m "feat: add SKILL_FIELD_MATRIX with FieldRule definitions"
```

---

### Task 6: _FrontmatterPanel을 매트릭스 기반으로 재작성

**Files:**
- Modify: `daedalus/view/editors/skill_editor.py` (`_FrontmatterPanel` 클래스)
- Modify: `daedalus/model/plugin/config.py` (`FieldSpec`, `FIELD_REGISTRY` 삭제)
- Modify: `tests/model/plugin/test_config.py` (FieldSpec/FIELD_REGISTRY 테스트 삭제)

- [ ] **Step 27: _FrontmatterPanel 재작성**

`skill_editor.py`의 `_FrontmatterPanel` 클래스를 아래로 교체:

```python
class _FrontmatterPanel(QScrollArea):
    """좌측 패널 — SKILL_FIELD_MATRIX 기반 프론트매터 편집."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        skill_kind: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        lay.addWidget(QLabel("Frontmatter"))

        # name (필수, 항상 표시)
        lay.addWidget(QLabel("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        # description (필수, 항상 표시)
        lay.addWidget(QLabel("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # SKILL_FIELD_MATRIX 기반 필드 생성
        from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX, FieldRule
        from daedalus.model.plugin.enums import FieldVisibility, SkillField

        kind = skill_kind or self._detect_kind(component)
        rules = SKILL_FIELD_MATRIX.get(kind, {})
        config = getattr(component, "config", None)

        skip = {SkillField.NAME, SkillField.DESCRIPTION}
        for field, rule in rules.items():
            if field in skip:
                continue
            if rule.visibility == FieldVisibility.REQUIRED:
                widget = rule.widget()
                self._apply_value(widget, config, field, rule)
                lay.addWidget(QLabel(field.value))
                lay.addWidget(widget)
            elif rule.visibility == FieldVisibility.OPTIONAL:
                widget = rule.widget()
                current = self._get_current(config, field)
                enabled = current is not None and current != "" and current != [] and current != False
                self._apply_value(widget, config, field, rule)
                lay.addWidget(_OptionalRow(field.value, widget, initially_enabled=enabled))

        lay.addStretch()
        self.setWidget(inner)

    @staticmethod
    def _detect_kind(component: object) -> str:
        config = getattr(component, "config", None)
        if config is not None and hasattr(config, "kind"):
            return config.kind
        return "procedural"

    @staticmethod
    def _get_current(config: object, field) -> object:
        from daedalus.model.plugin.enums import SkillField
        attr_map = {
            SkillField.WHEN_TO_USE: "when_to_use",
            SkillField.ARGUMENT_HINT: "argument_hint",
            SkillField.MODEL: "model",
            SkillField.EFFORT: "effort",
            SkillField.ALLOWED_TOOLS: "allowed_tools",
            SkillField.CONTEXT: "context",
            SkillField.AGENT: "agent",
            SkillField.SHELL: "shell",
            SkillField.PATHS: "paths",
            SkillField.HOOKS: "hooks",
            SkillField.DISABLE_MODEL: "disable_model_invocation",
            SkillField.USER_INVOCABLE: "user_invocable",
        }
        attr = attr_map.get(field)
        if attr and config is not None:
            return getattr(config, attr, None)
        return None

    @staticmethod
    def _apply_value(widget, config, field, rule) -> None:
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QLineEdit
        from daedalus.view.widgets.tag_input import TagInput
        current = _FrontmatterPanel._get_current(config, field)

        if isinstance(widget, QComboBox):
            val = None
            if current is not None:
                val = current.value if hasattr(current, "value") else str(current)
            elif rule.default_value is not None:
                val = str(rule.default_value)
            if val is not None:
                idx = widget.findText(val)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(current) if current is not None else False)
        elif isinstance(widget, TagInput):
            if isinstance(current, list):
                widget.set_tags(current)
        elif isinstance(widget, QLineEdit):
            if isinstance(current, list):
                widget.setText(" ".join(current) if current else "")
            elif current is not None:
                widget.setText(str(current))

    def _save_name(self) -> None:
        self._component.name = self._w_name.text().strip()
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        self.changed.emit()
```

- [ ] **Step 28: config.py에서 FieldSpec, FIELD_REGISTRY 삭제**

`daedalus/model/plugin/config.py`에서 `FieldSpec` 클래스와 `FIELD_REGISTRY` dict를 삭제. `ReferenceSkillConfig` 클래스 뒤의 모든 코드를 삭제.

- [ ] **Step 29: skill_editor.py에서 미사용 import 정리**

`skill_editor.py`에서 삭제:
- `from daedalus.model.plugin.config import FIELD_REGISTRY, FieldSpec`
- `from daedalus.model.plugin.enums import ModelType`
- `_make_field_widget` 메서드 전체

- [ ] **Step 30: test_config.py에서 FieldSpec/FIELD_REGISTRY 테스트 삭제**

`tests/model/plugin/test_config.py`에서 삭제:
- `FieldSpec` import
- `FIELD_REGISTRY` import
- `test_field_spec_dataclass`
- `test_field_registry_has_all_kinds`
- `test_field_registry_procedural_fields`
- `test_field_registry_transfer_fields`
- `test_field_registry_declarative_fields`
- `test_field_registry_agent_fields`

- [ ] **Step 31: SkillEditor에 skill_kind 전달**

`SkillEditor.__init__`에서 `_FrontmatterPanel` 생성 시 적절한 `skill_kind`를 전달하도록 수정. ComponentEditor를 거치므로 ComponentEditor에 `skill_kind` 매개변수를 추가하고 `_FrontmatterPanel`에 전달.

`component_editor.py`의 `ComponentEditor.__init__` 시그니처에 `skill_kind: str | None = None` 추가:

```python
def __init__(
    self,
    component: _ComponentType,
    right_widgets: list[QWidget] | None = None,
    on_notify_fn: Callable[[], None] | None = None,
    skill_kind: str | None = None,
    parent: QWidget | None = None,
) -> None:
```

`_FrontmatterPanel` 생성 라인을:
```python
self._fm = _FrontmatterPanel(component)
```
에서:
```python
self._fm = _FrontmatterPanel(component, skill_kind=skill_kind)
```
로 변경.

`SkillEditor.__init__`에서 `skill_kind`를 결정하여 `ComponentEditor`에 전달:

```python
# SkillEditor.__init__ 내부
if isinstance(component, ProceduralSkill):
    kind = "local_procedural" if not show_call_agents else "procedural"
elif isinstance(component, TransferSkill):
    kind = "local_transfer" if not show_call_agents else "transfer"
elif isinstance(component, DeclarativeSkill):
    kind = "declarative"
elif isinstance(component, ReferenceSkill):
    kind = "reference"
else:
    kind = None

self._editor = ComponentEditor(
    component,
    right_widgets=right_widgets,
    on_notify_fn=self._on_notify,
    skill_kind=kind,
)
```

- [ ] **Step 32: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과 (FieldSpec/FIELD_REGISTRY 테스트 삭제, 새 매트릭스 테스트 추가)

- [ ] **Step 33: 커밋**

```bash
git add daedalus/model/plugin/config.py daedalus/view/editors/skill_editor.py daedalus/view/editors/component_editor.py tests/model/plugin/test_config.py
git commit -m "refactor: replace FieldSpec/FIELD_REGISTRY with SKILL_FIELD_MATRIX"
```

---

### Task 7: when_to_use 모델 필드 추가

**Files:**
- Modify: `daedalus/model/plugin/skill.py`
- Modify: `tests/model/plugin/test_skill.py`

- [ ] **Step 34: 테스트 작성**

`tests/model/plugin/test_skill.py`에 추가:

```python
def test_procedural_skill_when_to_use_default():
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(fsm=fsm, name="t", description="d")
    assert skill.when_to_use == ""


def test_declarative_skill_when_to_use_default():
    skill = DeclarativeSkill(name="t", description="d")
    assert skill.when_to_use == ""
```

- [ ] **Step 35: 모델에 필드 추가**

`daedalus/model/plugin/skill.py`의 `Skill` ABC 클래스에 추가:

```python
@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""
    when_to_use: str = ""
```

- [ ] **Step 36: 테스트 통과 확인**

Run: `python -m pytest tests/model/plugin/test_skill.py -v`
Expected: PASS

- [ ] **Step 37: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 전체 통과

- [ ] **Step 38: 커밋**

```bash
git add daedalus/model/plugin/skill.py tests/model/plugin/test_skill.py
git commit -m "feat: add when_to_use field to Skill base class"
```
