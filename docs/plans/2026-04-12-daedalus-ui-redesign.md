# Daedalus UI 재설계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SimpleState 기반 일반 에디터를 스킬/에이전트 중심 노드 그래프 에디터로 재설계 — Registry Palette에서 정의한 스킬을 FSM 캔버스에 드래그하여 배치하고, 포트(입력 1개 + 이벤트별 출력 복수)로 전이를 연결한다.

**Architecture:** 모델 레이어(`model/`)에 `SimpleState.skill_ref`, `output_events`, `SkillSection` Enum, Validator 규칙을 추가하고, 뷰 레이어(`view/`)를 `RegistryPanel` + 타입별 노드 + `SkillEditor`로 전면 교체한다. 드래그-드롭은 `RegistryPanel` → `FsmCanvasView` → `FsmScene` 경로로 흐른다.

**Tech Stack:** Python 3.11+, PyQt6, pytest

---

## 파일 구조

| 상태 | 파일 | 역할 |
|------|------|------|
| 신규 | `daedalus/model/fsm/section.py` | SkillSection Enum |
| 수정 | `daedalus/model/fsm/state.py` | SimpleState.skill_ref 추가 |
| 수정 | `daedalus/model/plugin/skill.py` | ProceduralSkill.output_events 추가 |
| 수정 | `daedalus/model/plugin/agent.py` | AgentDefinition.output_events 추가 |
| 수정 | `daedalus/model/validation.py` | no_duplicate_skill_ref 규칙 추가 |
| 수정 | `daedalus/view/canvas/node_item.py` | 타입별 색상, 입력/출력 포트 |
| 수정 | `daedalus/view/canvas/edge_item.py` | 포트 위치 기반 경로 계산 |
| 수정 | `daedalus/view/canvas/scene.py` | event_name 파라미터, drop_skill() |
| 수정 | `daedalus/view/canvas/canvas_view.py` | 드래그 드롭 수신 |
| 신규 | `daedalus/view/panels/registry_panel.py` | Registry Palette |
| 신규 | `daedalus/view/editors/skill_editor.py` | 프론트매터 폼 + 섹션 카드 |
| 수정 | `daedalus/view/app.py` | 전체 배선 |
| 신규 | `tests/model/fsm/test_section.py` | SkillSection 테스트 |
| 수정 | `tests/model/fsm/test_state.py` | skill_ref 테스트 추가 |
| 수정 | `tests/model/plugin/test_skill.py` | output_events 테스트 추가 |
| 수정 | `tests/model/plugin/test_agent.py` | output_events 테스트 추가 |
| 수정 | `tests/model/test_validation.py` | no_duplicate_skill_ref 테스트 추가 |

---

## Task 1: SkillSection Enum

**Files:**
- Create: `daedalus/model/fsm/section.py`
- Create: `tests/model/fsm/test_section.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/model/fsm/test_section.py
from daedalus.model.fsm.section import SkillSection


def test_skill_section_members():
    assert SkillSection.INSTRUCTIONS.value == "instructions"
    assert SkillSection.WHEN_ENTER.value == "when_enter"
    assert SkillSection.WHEN_FINISHED.value == "when_finished"
    assert SkillSection.WHEN_ACTIVE.value == "when_active"
    assert SkillSection.WHEN_ERROR.value == "when_error"
    assert SkillSection.CONTEXT.value == "context"


def test_skill_section_count():
    assert len(SkillSection) == 6


def test_skill_section_order():
    members = list(SkillSection)
    assert members[0] == SkillSection.INSTRUCTIONS
    assert members[-1] == SkillSection.CONTEXT
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```
python -m pytest tests/model/fsm/test_section.py -v
```
Expected: ImportError (파일 없음)

- [ ] **Step 3: SkillSection 구현**

```python
# daedalus/model/fsm/section.py
from __future__ import annotations

from enum import Enum


class SkillSection(Enum):
    """스킬 본문 섹션 열거형.

    항목 추가 시 SkillEditor UI가 자동으로 섹션 카드를 추가한다.
    """
    INSTRUCTIONS  = "instructions"   # 항상 활성, 항상 표시
    WHEN_ENTER    = "when_enter"     # on_entry hook
    WHEN_FINISHED = "when_finished"  # on_exit hook
    WHEN_ACTIVE   = "when_active"    # on_active hook
    WHEN_ERROR    = "when_error"     # custom_event hook
    CONTEXT       = "context"        # declarative 배경지식
```

- [ ] **Step 4: 테스트 통과 확인**

```
python -m pytest tests/model/fsm/test_section.py -v
```
Expected: 3 passed

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/fsm/section.py tests/model/fsm/test_section.py
git commit -m "feat: add SkillSection enum for skill body sections"
```

---

## Task 2: Model — skill_ref + output_events

**Files:**
- Modify: `daedalus/model/fsm/state.py`
- Modify: `daedalus/model/plugin/skill.py`
- Modify: `daedalus/model/plugin/agent.py`
- Modify: `tests/model/fsm/test_state.py`
- Modify: `tests/model/plugin/test_skill.py`
- Modify: `tests/model/plugin/test_agent.py`

### 2-1. SimpleState.skill_ref

- [ ] **Step 1: test_state.py에 실패 테스트 추가**

```python
# tests/model/fsm/test_state.py 에 추가 (기존 import 아래)
from daedalus.model.plugin.skill import ProceduralSkill, DeclarativeSkill
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.fsm.machine import StateMachine as _SM


def _make_fsm_for_skill():
    s = SimpleState(name="s")
    return _SM(name="f", states=[s], initial_state=s)


def test_simple_state_skill_ref_default():
    s = SimpleState(name="s")
    assert s.skill_ref is None


def test_simple_state_with_procedural_skill_ref():
    fsm = _make_fsm_for_skill()
    skill = ProceduralSkill(fsm=fsm, name="WriteSkill", description="쓰기")
    s = SimpleState(name="write", skill_ref=skill)
    assert s.skill_ref is skill
    assert s.skill_ref.name == "WriteSkill"


def test_simple_state_with_agent_ref():
    fsm = _make_fsm_for_skill()
    agent = AgentDefinition(fsm=fsm, name="WriterAgent", description="에이전트")
    s = SimpleState(name="node", skill_ref=agent)
    assert s.skill_ref is agent


def test_simple_state_skill_ref_can_be_cleared():
    skill = DeclarativeSkill(name="Guide", description="가이드")
    s = SimpleState(name="ctx", skill_ref=skill)
    s.skill_ref = None
    assert s.skill_ref is None
```

- [ ] **Step 2: 테스트 실패 확인**

```
python -m pytest tests/model/fsm/test_state.py::test_simple_state_skill_ref_default -v
```
Expected: FAIL (TypeError: unexpected keyword argument 'skill_ref')

- [ ] **Step 3: state.py 수정 — SimpleState에 skill_ref 추가**

```python
# daedalus/model/fsm/state.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.variable import Variable

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill


@dataclass
class State(ABC):
    name: str
    on_entry_start: list[Action] = field(default_factory=list)
    on_entry: list[Action] = field(default_factory=list)
    on_entry_end: list[Action] = field(default_factory=list)
    on_exit_start: list[Action] = field(default_factory=list)
    on_exit: list[Action] = field(default_factory=list)
    on_exit_end: list[Action] = field(default_factory=list)
    on_active: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    inputs: list[Variable] = field(default_factory=list)
    outputs: list[Variable] = field(default_factory=list)

    @property
    @abstractmethod
    def kind(self) -> str:
        """상태 종류 식별자."""


@dataclass
class SimpleState(State):
    """리프 상태. 하위 상태 없음."""
    skill_ref: ProceduralSkill | DeclarativeSkill | AgentDefinition | None = None

    @property
    def kind(self) -> str:
        return "simple"


@dataclass
class Region:
    """ParallelState 내 독립 실행 단위."""
    name: str
    sub_machine: StateMachine


@dataclass
class CompositeState(State):
    """별도 컨텍스트의 상태 기계."""
    sub_machine: StateMachine = None

    @property
    def kind(self) -> str:
        return "composite"


@dataclass
class ParallelState(State):
    """병렬 리전. 동시 실행."""
    regions: list[Region] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "parallel"
```

- [ ] **Step 4: 테스트 통과 확인**

```
python -m pytest tests/model/fsm/test_state.py -v
```
Expected: 전체 통과 (기존 + 신규)

### 2-2. output_events

- [ ] **Step 5: test_skill.py에 실패 테스트 추가**

기존 `_make_fsm()` 헬퍼가 없으면 `test_skill.py` 상단에 추가:

```python
def _make_fsm():
    from daedalus.model.fsm.state import SimpleState as _SS
    from daedalus.model.fsm.machine import StateMachine as _SM
    s = _SS(name="s")
    return _SM(name="f", states=[s], initial_state=s)
```

그 다음 테스트 추가:

```python
def test_procedural_skill_output_events_default():
    fsm = _make_fsm()
    skill = ProceduralSkill(fsm=fsm, name="S", description="d")
    assert skill.output_events == ["done"]


def test_procedural_skill_output_events_custom():
    fsm = _make_fsm()
    skill = ProceduralSkill(
        fsm=fsm, name="S", description="d",
        output_events=["done", "error", "retry"],
    )
    assert skill.output_events == ["done", "error", "retry"]
```

- [ ] **Step 6: test_agent.py에 실패 테스트 추가**

기존 `_make_fsm()` 헬퍼가 없으면 같은 방식으로 추가:

```python
def test_agent_output_events_default():
    fsm = _make_fsm()
    agent = AgentDefinition(fsm=fsm, name="A", description="d")
    assert agent.output_events == ["done"]


def test_agent_output_events_custom():
    fsm = _make_fsm()
    agent = AgentDefinition(
        fsm=fsm, name="A", description="d",
        output_events=["done", "failed"],
    )
    assert agent.output_events == ["done", "failed"]
```

- [ ] **Step 7: 테스트 실패 확인**

```
python -m pytest tests/model/plugin/test_skill.py tests/model/plugin/test_agent.py -v -k "output_events"
```
Expected: FAIL

- [ ] **Step 8: skill.py에 output_events 추가**

`ProceduralSkill` 클래스의 기존 `config` 필드 아래에 추가:

```python
    output_events: list[str] = field(default_factory=lambda: ["done"])
```

전체 파일:

```python
# daedalus/model/plugin/skill.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import DeclarativeSkillConfig, ProceduralSkillConfig


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, output_events (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    output_events: list[str] = field(default_factory=lambda: ["done"])

    @property
    def kind(self) -> str:
        return "procedural_skill"


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only. FSM 없음."""
    content: str = ""
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"
```

- [ ] **Step 9: agent.py에 output_events 추가**

`AgentDefinition` 클래스의 `execution_policy` 필드 아래에 추가:

```python
    output_events: list[str] = field(default_factory=lambda: ["done"])
```

전체 파일:

```python
# daedalus/model/plugin/agent.py
from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, execution_policy, output_events (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    output_events: list[str] = field(default_factory=lambda: ["done"])

    @property
    def kind(self) -> str:
        return "agent"
```

- [ ] **Step 10: 전체 모델 테스트 통과 확인**

```
python -m pytest tests/model/ -v
```
Expected: 전체 통과

- [ ] **Step 11: 커밋**

```bash
git add daedalus/model/fsm/state.py daedalus/model/plugin/skill.py daedalus/model/plugin/agent.py tests/model/fsm/test_state.py tests/model/plugin/test_skill.py tests/model/plugin/test_agent.py
git commit -m "feat: add skill_ref to SimpleState and output_events to skills/agents"
```

---

## Task 3: Validator — no_duplicate_skill_ref

**Files:**
- Modify: `daedalus/model/validation.py`
- Modify: `tests/model/test_validation.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
# tests/model/test_validation.py 에 추가
from daedalus.model.plugin.skill import ProceduralSkill


def _make_procedural(name: str) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def test_no_duplicate_skill_ref_passes_when_unique():
    skill_a = _make_procedural("SkillA")
    skill_b = _make_procedural("SkillB")
    s1 = SimpleState(name="n1", skill_ref=skill_a)
    s2 = SimpleState(name="n2", skill_ref=skill_b)
    sm = _make_sm([s1, s2], [])
    errors = Validator.validate(sm)
    dup = [e for e in errors if e.rule == "no_duplicate_skill_ref"]
    assert dup == []


def test_no_duplicate_skill_ref_fails_when_same_skill_placed_twice():
    skill = _make_procedural("SkillA")
    s1 = SimpleState(name="n1", skill_ref=skill)
    s2 = SimpleState(name="n2", skill_ref=skill)
    sm = _make_sm([s1, s2], [])
    errors = Validator.validate(sm)
    dup = [e for e in errors if e.rule == "no_duplicate_skill_ref"]
    assert len(dup) == 1
    assert "SkillA" in dup[0].message


def test_no_duplicate_skill_ref_allows_multiple_none():
    s1 = SimpleState(name="n1")
    s2 = SimpleState(name="n2")
    sm = _make_sm([s1, s2], [])
    errors = Validator.validate(sm)
    dup = [e for e in errors if e.rule == "no_duplicate_skill_ref"]
    assert dup == []
```

- [ ] **Step 2: 테스트 실패 확인**

```
python -m pytest tests/model/test_validation.py -v -k "duplicate_skill_ref"
```
Expected: FAIL

- [ ] **Step 3: validation.py에 규칙 추가**

`Validator._validate_machine()` 내 errors.extend 목록에 추가:

```python
        errors.extend(Validator._check_duplicate_skill_ref(sm.states))
```

정적 메서드 추가 (클래스 내부):

```python
    @staticmethod
    def _check_duplicate_skill_ref(states: list[State]) -> list[ValidationError]:
        from daedalus.model.fsm.state import SimpleState
        seen: set[int] = set()
        errors: list[ValidationError] = []
        for state in states:
            if not isinstance(state, SimpleState):
                continue
            ref = state.skill_ref
            if ref is None:
                continue
            ref_id = id(ref)
            if ref_id in seen:
                errors.append(ValidationError(
                    rule="no_duplicate_skill_ref",
                    message=(
                        f"'{ref.name}' 스킬/에이전트가 동일 StateMachine에 "
                        f"두 번 이상 배치되었습니다."
                    ),
                    source=state.name,
                ))
            else:
                seen.add(ref_id)
        return errors
```

- [ ] **Step 4: 테스트 통과 확인**

```
python -m pytest tests/model/test_validation.py -v
```
Expected: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add daedalus/model/validation.py tests/model/test_validation.py
git commit -m "feat: add no_duplicate_skill_ref validator rule"
```

---

## Task 4: View — StateNodeItem 재설계 + TransitionEdgeItem 포트 연결

**Files:**
- Modify: `daedalus/view/canvas/node_item.py`
- Modify: `daedalus/view/canvas/edge_item.py`
- Modify: `daedalus/view/canvas/scene.py` (일부)

UI 전용이므로 단위 테스트 없음. 기존 `node_item.py`를 전면 교체한다.

- [ ] **Step 1: node_item.py 교체**

```python
# daedalus/view/canvas/node_item.py
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from daedalus.view.viewmodel.state_vm import StateViewModel

_W = 160.0          # 노드 본체 너비
_HEADER_H = 20.0    # 헤더 높이
_PORT_R = 6.0       # 포트 원 반지름
_PORT_SPACING = 22.0  # 출력 포트 간 수직 간격
_PORT_PAD = 12.0    # 포트 영역 상하 패딩
_LABEL_W = 44.0     # 출력 포트 레이블 너비

# skill kind → (배경, 테두리, 헤더 텍스트, 아이콘)
_TYPE_STYLE: dict[str | None, tuple[str, str, str, str]] = {
    "procedural_skill": ("#1a2a1a", "#4a8a4a", "PROCEDURAL", "⚙"),
    "declarative_skill": ("#2a2a1a", "#8a8a4a", "DECLARATIVE", "📄"),
    "agent":             ("#2a1a1a", "#8a4a4a", "AGENT",       "🤖"),
    None:                ("#1a1a2a", "#334466", "STATE",        ""),
}

_PORT_COLORS: dict[str, QColor] = {
    "done":  QColor("#4488ff"),
    "error": QColor("#cc3333"),
}
_PORT_DEFAULT_COLOR = QColor("#cc8800")


class StateNodeItem(QGraphicsItem):
    """캔버스 위의 스킬/에이전트 노드."""

    def __init__(
        self, state_vm: StateViewModel, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._state_vm = state_vm
        self.setPos(state_vm.x, state_vm.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self._drag_start_pos: QPointF | None = None
        self._dragging_connection = False
        self._drag_event_name: str | None = None
        self._sync_height()

    @property
    def state_vm(self) -> StateViewModel:
        return self._state_vm

    # --- 치수 ---

    def _output_events(self) -> list[str]:
        ref = self._state_vm.model.skill_ref
        if ref is not None and hasattr(ref, "output_events"):
            return list(ref.output_events)
        return []

    def _height(self) -> float:
        n = max(1, len(self._output_events()))
        port_area = _PORT_SPACING * n + _PORT_PAD * 2
        return _HEADER_H + max(44.0, port_area)

    def _output_port_y(self, i: int, n: int) -> float:
        body_h = self._height() - _HEADER_H
        spacing = body_h / (n + 1)
        return _HEADER_H + spacing * (i + 1)

    def _sync_height(self) -> None:
        new_h = self._height()
        if self._state_vm.height != new_h:
            self.prepareGeometryChange()
            self._state_vm.height = new_h

    def update_from_model(self) -> None:
        """output_events 변경 후 호출 — 높이/포트 재계산."""
        self._sync_height()
        self.update()

    # --- QGraphicsItem ---

    def boundingRect(self) -> QRectF:
        h = self._height()
        return QRectF(-_PORT_R * 2 - 2, 0, _W + _PORT_R * 2 + 2 + _LABEL_W, h)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return

        ref = self._state_vm.model.skill_ref
        kind = ref.kind if ref is not None else None
        bg_str, border_str, header_label, icon = _TYPE_STYLE.get(kind, _TYPE_STYLE[None])
        border_color = QColor(border_str)
        active_border = border_color.lighter(160) if self.isSelected() else border_color

        h = self._height()
        events = self._output_events() or ["done"]
        n = len(events)

        # 본체
        body_rect = QRectF(0, 0, _W, h)
        painter.setPen(QPen(active_border, 2))
        painter.setBrush(QBrush(QColor(bg_str)))
        painter.drawRoundedRect(body_rect, 7, 7)

        # 헤더
        header_rect = QRectF(1, 1, _W - 2, _HEADER_H - 1)
        hdr_bg = QColor(bg_str).darker(140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(hdr_bg))
        painter.drawRoundedRect(header_rect, 6, 6)
        painter.drawRect(QRectF(1, 10, _W - 2, _HEADER_H - 11))

        painter.setPen(QPen(border_color.lighter(130)))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            header_rect.adjusted(6, 0, -20, 0),
            Qt.AlignmentFlag.AlignVCenter, header_label,
        )
        if icon:
            painter.drawText(
                header_rect.adjusted(0, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                icon,
            )

        # 이름
        name_rect = QRectF(4, _HEADER_H, _W - 8, h - _HEADER_H - 12)
        text_color = QColor("#eee") if self.isSelected() else QColor("#ccc")
        painter.setPen(QPen(text_color))
        font = QFont("Segoe UI", 11)
        if self.isSelected():
            font.setBold(True)
        painter.setFont(font)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignCenter, self._state_vm.model.name)

        # 서브텍스트
        subtext_rect = QRectF(4, h - 12, _W - 8, 12)
        painter.setPen(QPen(border_color.lighter(80)))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(subtext_rect, Qt.AlignmentFlag.AlignCenter, kind or "state")

        # 입력 포트 (좌측 중앙)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#888")))
        painter.drawEllipse(QPointF(0.0, h / 2), _PORT_R, _PORT_R)

        # 출력 포트 (우측, 이벤트별)
        for i, event_name in enumerate(events):
            y = self._output_port_y(i, n)
            port_color = _PORT_COLORS.get(event_name, _PORT_DEFAULT_COLOR)
            painter.setPen(QPen(QColor("#111"), 1))
            painter.setBrush(QBrush(port_color))
            painter.drawEllipse(QPointF(_W, y), _PORT_R, _PORT_R)
            lbl_rect = QRectF(_W + _PORT_R + 2, y - 7, _LABEL_W - 4, 14)
            painter.setPen(QPen(port_color.lighter(140)))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignVCenter, event_name)

    # --- 포트 씬 좌표 ---

    def output_port_scene_pos(self, event_name: str) -> QPointF:
        events = self._output_events() or ["done"]
        n = len(events)
        try:
            i = events.index(event_name)
        except ValueError:
            i = 0
        return self.mapToScene(QPointF(_W, self._output_port_y(i, n)))

    def input_port_scene_pos(self) -> QPointF:
        return self.mapToScene(QPointF(0.0, self._height() / 2))

    # --- 히트 테스트 ---

    def _get_output_port_event(self, local_pos: QPointF) -> str | None:
        events = self._output_events() or ["done"]
        n = len(events)
        hit_r = _PORT_R * 1.8
        for i, name in enumerate(events):
            y = self._output_port_y(i, n)
            dx = local_pos.x() - _W
            dy = local_pos.y() - y
            if dx * dx + dy * dy <= hit_r * hit_r:
                return name
        return None

    def is_input_port(self, local_pos: QPointF) -> bool:
        h = self._height()
        dy = local_pos.y() - h / 2
        return local_pos.x() <= _PORT_R * 2 and abs(dy) <= _PORT_R * 2

    # --- 마우스 이벤트 ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event_name = self._get_output_port_event(event.pos())
            if event_name is not None:
                self._dragging_connection = True
                self._drag_event_name = event_name
                sc: Any = self.scene()
                if sc is not None and hasattr(sc, "begin_transition_drag"):
                    sc.begin_transition_drag(self, event_name)
                event.accept()
                return
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_connection:
            sc: Any = self.scene()
            if sc is not None and hasattr(sc, "update_transition_drag"):
                sc.update_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        sc: Any = self.scene()
        if self._dragging_connection:
            self._dragging_connection = False
            self._drag_event_name = None
            if sc is not None and hasattr(sc, "end_transition_drag"):
                sc.end_transition_drag(self.mapToScene(event.pos()))
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None and self._drag_start_pos != self.pos():
            if sc is not None and hasattr(sc, "handle_node_moved"):
                sc.handle_node_moved(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None
```

- [ ] **Step 2: edge_item.py — update_path 포트 기반으로 교체**

`update_path` 메서드만 교체:

```python
    def update_path(self) -> None:
        """출력/입력 포트 위치 기반 베지어 경로."""
        trigger = self._transition_vm.model.trigger
        event_name = trigger.name if trigger is not None else "done"

        src_pt = self._source_node.output_port_scene_pos(event_name)
        tgt_pt = self._target_node.input_port_scene_pos()

        if tgt_pt.x() < src_pt.x():
            # 역방향 — 더 크게 휘어짐
            dx = abs(tgt_pt.x() - src_pt.x()) * 0.8 + 80
            ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
            ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())
        else:
            dx = abs(tgt_pt.x() - src_pt.x()) * 0.5
            ctrl1 = QPointF(src_pt.x() + dx, src_pt.y())
            ctrl2 = QPointF(tgt_pt.x() - dx, tgt_pt.y())

        path = QPainterPath(src_pt)
        path.cubicTo(ctrl1, ctrl2, tgt_pt)
        self.setPath(path)
```

- [ ] **Step 3: scene.py의 _rebuild()에 update_from_model 추가**

`_rebuild()` 내 기존 노드 갱신 블록에서:

```python
# 수정 전:
else:
    self._node_items[vm].setPos(vm.x, vm.y)

# 수정 후:
else:
    self._node_items[vm].setPos(vm.x, vm.y)
    self._node_items[vm].update_from_model()
```

- [ ] **Step 4: 앱 실행하여 노드 시각 확인**

```
python -m daedalus.main
```

- [ ] **Step 5: 커밋**

```bash
git add daedalus/view/canvas/node_item.py daedalus/view/canvas/edge_item.py daedalus/view/canvas/scene.py
git commit -m "feat: redesign node with typed ports — input left, output right per event"
```

---

## Task 5: FsmScene + FsmCanvasView — Registry 드롭 지원

**Files:**
- Modify: `daedalus/view/canvas/scene.py`
- Modify: `daedalus/view/canvas/canvas_view.py`

- [ ] **Step 1: scene.py 수정 — 전체 교체**

아래 내용으로 `scene.py`를 교체한다. 주요 변경:
- `__init__`에 `skill_lookup: Callable[[str], object] | None = None` 파라미터 추가
- `begin_transition_drag(source, event_name)` — event_name 파라미터 추가
- `end_transition_drag` — `_item_at_input_port()` 히트테스트로 교체
- `drop_skill(skill_name, scene_pos)` 메서드 추가
- `_connect_event: str | None` 필드 추가

```python
# daedalus/view/canvas/scene.py
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPen
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

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel

_BG_COLOR = QColor("#12122a")
_DRAG_LINE_COLOR = QColor("#4488ff")


class FsmScene(QGraphicsScene):
    """FSM 노드 편집 씬."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        skill_lookup: Callable[[str], object] | None = None,
    ) -> None:
        super().__init__()
        self._project_vm = project_vm
        self._skill_lookup = skill_lookup
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
            src_center = self._connect_source.sceneBoundingRect().center()
            self._drag_line.setLine(
                src_center.x(), src_center.y(),
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

    # --- Registry 드롭 ---

    def drop_skill(self, skill_name: str, scene_pos: QPointF) -> None:
        if self._skill_lookup is None:
            return
        skill = self._skill_lookup(skill_name)
        if skill is None:
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
            delete_act = menu.addAction("전이 삭제")
            if menu.exec(event.screenPos()) == delete_act:
                self._delete_transition(item.transition_vm)
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
```

- [ ] **Step 2: canvas_view.py 수정 — 드롭 수신 추가**

```python
# daedalus/view/canvas/canvas_view.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QGraphicsView

from daedalus.view.canvas.scene import FsmScene


class FsmCanvasView(QGraphicsView):
    """pan/zoom + 레지스트리 드롭 수신 캔버스 뷰."""

    def __init__(self, scene: FsmScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAcceptDrops(True)
        self._panning = False
        self._pan_start = None

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event is not None and event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent | None) -> None:
        if event is None or not event.mimeData().hasText():
            return
        skill_name = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        sc = self.scene()
        if isinstance(sc, FsmScene):
            sc.drop_skill(skill_name, scene_pos)
        event.acceptProposedAction()

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._panning and self._pan_start is not None:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar is not None:
                h_bar.setValue(h_bar.value() - int(delta.x()))
            if v_bar is not None:
                v_bar.setValue(v_bar.value() - int(delta.y()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if self._panning:
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)
```

- [ ] **Step 3: 커밋**

```bash
git add daedalus/view/canvas/scene.py daedalus/view/canvas/canvas_view.py
git commit -m "feat: add skill_lookup + registry drop to FsmScene/FsmCanvasView"
```

---

## Task 6: RegistryPanel

**Files:**
- Create: `daedalus/view/panels/registry_panel.py`

- [ ] **Step 1: registry_panel.py 작성**

```python
# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QMimeData

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2

_COLOR_PROCEDURAL = QColor("#88cc88")
_COLOR_DECLARATIVE = QColor("#cccc88")
_COLOR_AGENT = QColor("#cc8888")
_COLOR_PLACED = QColor("#445544")

_ICON = {
    "procedural_skill": "⚙",
    "declarative_skill": "📄",
    "agent": "🤖",
}


class _DraggableList(QListWidget):
    """배치된 항목은 드래그 불가인 목록 위젯."""

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.data(_ROLE_PLACED):
            return
        component = item.data(_ROLE_COMPONENT)
        if component is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(component.name)
        drag.setMimeData(mime)
        # QDrag.exec() 로 드래그 실행 — PyQt6 메서드명
        _run_drag = getattr(drag, "exec")
        _run_drag(Qt.DropAction.CopyAction)


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트."""

    component_double_clicked = pyqtSignal(object)
    new_skill_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        layout.addWidget(self._section_label("⚙ PROCEDURAL"))
        self._proc_list = self._make_list()
        layout.addWidget(self._proc_list)

        layout.addWidget(self._section_label("📄 DECLARATIVE"))
        self._decl_list = self._make_list()
        layout.addWidget(self._decl_list)

        layout.addWidget(self._section_label("🤖 AGENTS"))
        self._agent_list = self._make_list()
        layout.addWidget(self._agent_list)

        btn = QPushButton("+ 새 스킬 정의")
        btn.clicked.connect(self.new_skill_requested)
        layout.addWidget(btn)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #668; font-size: 9px; padding: 4px 2px 0px 2px;")
        return lbl

    def _make_list(self) -> _DraggableList:
        lst = _DraggableList()
        lst.setDragEnabled(True)
        lst.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        lst.setMaximumHeight(130)
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.doubleClicked.connect(self._on_double_click)
        lst.setStyleSheet(
            "QListWidget { background: #13132a; border: 1px solid #2a2a44; }"
            "QListWidget::item { padding: 4px 6px; }"
            "QListWidget::item:selected { background: #2a2a4a; }"
        )
        return lst

    def _rebuild(self) -> None:
        for lst in (self._proc_list, self._decl_list, self._agent_list):
            lst.clear()
        if self._project is None:
            return
        for skill in self._project.skills:
            placed = id(skill) in self._placed_ids
            if isinstance(skill, ProceduralSkill):
                self._add_item(self._proc_list, skill, _COLOR_PROCEDURAL, placed)
            elif isinstance(skill, DeclarativeSkill):
                self._add_item(self._decl_list, skill, _COLOR_DECLARATIVE, placed)
        for agent in self._project.agents:
            placed = id(agent) in self._placed_ids
            self._add_item(self._agent_list, agent, _COLOR_AGENT, placed)

    def _add_item(
        self,
        lst: QListWidget,
        component: object,
        color: QColor,
        placed: bool,
    ) -> None:
        kind = getattr(component, "kind", "")
        icon = _ICON.get(kind, "")
        name = getattr(component, "name", str(component))
        item = QListWidgetItem(f"{icon} {name}")
        item.setData(_ROLE_COMPONENT, component)
        item.setData(_ROLE_PLACED, placed)
        if placed:
            item.setForeground(_COLOR_PLACED)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        else:
            item.setForeground(color)
        lst.addItem(item)

    def _on_double_click(self, index) -> None:
        lst = self.sender()
        if not isinstance(lst, QListWidget):
            return
        item = lst.itemFromIndex(index)
        if item:
            comp = item.data(_ROLE_COMPONENT)
            if comp is not None:
                self.component_double_clicked.emit(comp)
```

- [ ] **Step 2: 커밋**

```bash
git add daedalus/view/panels/registry_panel.py
git commit -m "feat: add RegistryPanel with drag-and-drop and placed-dim"
```

---

## Task 7: SkillEditor

**Files:**
- Create: `daedalus/view/editors/skill_editor.py`

- [ ] **Step 1: skill_editor.py 작성**

```python
# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import SkillSection
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.plugin.agent import AgentDefinition

_INPUT_STYLE = (
    "background: #1a1a2e; border: 1px solid #446; color: #aac; "
    "padding: 3px 5px; border-radius: 3px;"
)
_DARK_BG = "background: #13132a; color: #aac;"


class _SectionCard(QFrame):
    """SkillSection 하나를 표현하는 카드."""

    def __init__(
        self,
        section: SkillSection,
        always_active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._section = section
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #13132a; border: 1px solid #336; border-radius: 5px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: #1a1a3a; border-radius: 4px 4px 0 0;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 8, 4)

        if always_active:
            lbl = QLabel(section.name)
            lbl.setStyleSheet("color: #88aaff; font-weight: bold; font-size: 11px;")
            h_layout.addWidget(lbl)
            self._checkbox: QCheckBox | None = None
        else:
            self._checkbox = QCheckBox(section.name)
            self._checkbox.setStyleSheet("color: #88cc88; font-weight: bold; font-size: 11px;")
            self._checkbox.toggled.connect(self._on_toggled)
            h_layout.addWidget(self._checkbox)

        h_layout.addStretch()
        key_lbl = QLabel(section.value)
        key_lbl.setStyleSheet("color: #446; font-size: 9px; font-family: Consolas;")
        h_layout.addWidget(key_lbl)
        layout.addWidget(header)

        self._body = QTextEdit()
        self._body.setStyleSheet(
            "background: #0d0d1f; color: #ccc; border: 1px solid #335; "
            "font-family: Consolas; font-size: 10px; padding: 4px;"
        )
        self._body.setMinimumHeight(50)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._body)

        if not always_active:
            self._body.hide()

    @property
    def section(self) -> SkillSection:
        return self._section

    def is_active(self) -> bool:
        if self._checkbox is None:
            return True
        return self._checkbox.isChecked()

    def get_text(self) -> str:
        return self._body.toPlainText()

    def set_text(self, text: str) -> None:
        self._body.setPlainText(text)

    def set_active(self, active: bool) -> None:
        if self._checkbox is not None:
            self._checkbox.setChecked(active)

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)


class SkillEditor(QWidget):
    """ProceduralSkill / DeclarativeSkill / AgentDefinition 편집기."""

    skill_changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn
        self._section_cards: list[_SectionCard] = []

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 좌측: Frontmatter
        fm_scroll = QScrollArea()
        fm_scroll.setWidgetResizable(True)
        fm_scroll.setFixedWidth(285)
        fm_scroll.setStyleSheet(_DARK_BG)
        fm_inner = QWidget()
        fm_inner.setStyleSheet(_DARK_BG)
        self._fm_layout = QFormLayout(fm_inner)
        self._fm_layout.setContentsMargins(8, 8, 8, 8)
        self._fm_layout.setSpacing(6)
        fm_scroll.setWidget(fm_inner)
        main_layout.addWidget(fm_scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #333;")
        main_layout.addWidget(sep)

        # 우측: Body sections
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setStyleSheet(_DARK_BG)
        body_inner = QWidget()
        body_inner.setStyleSheet(_DARK_BG)
        self._body_layout = QVBoxLayout(body_inner)
        self._body_layout.setContentsMargins(8, 8, 8, 8)
        self._body_layout.setSpacing(8)
        body_scroll.setWidget(body_inner)
        main_layout.addWidget(body_scroll, 1)

        self._build_frontmatter()
        self._build_sections()
        self._build_buttons()

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666; font-size: 10px;")
        return lbl

    def _input(self) -> QLineEdit:
        w = QLineEdit()
        w.setStyleSheet(_INPUT_STYLE)
        return w

    def _combo(self, values: list[str]) -> QComboBox:
        w = QComboBox()
        w.setStyleSheet(_INPUT_STYLE)
        for v in values:
            w.addItem(v)
        return w

    def _build_frontmatter(self) -> None:
        lay = self._fm_layout
        comp = self._component
        config = getattr(comp, "config", None)

        self._w_name = self._input()
        self._w_name.setText(comp.name)
        lay.addRow(self._lbl("name"), self._w_name)

        self._w_desc = QTextEdit()
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.setFixedHeight(48)
        self._w_desc.setPlainText(comp.description)
        lay.addRow(self._lbl("description *"), self._w_desc)

        if config is not None and hasattr(config, "argument_hint"):
            self._w_arg_hint = self._input()
            self._w_arg_hint.setPlaceholderText("[topic]")
            if config.argument_hint:
                self._w_arg_hint.setText(config.argument_hint)
            lay.addRow(self._lbl("argument-hint"), self._w_arg_hint)

        self._w_model = self._combo([e.value for e in ModelType])
        if config is not None:
            mv = config.model.value if isinstance(config.model, ModelType) else str(config.model)
            idx = self._w_model.findText(mv)
            if idx >= 0:
                self._w_model.setCurrentIndex(idx)
        lay.addRow(self._lbl("model"), self._w_model)

        self._w_effort = self._combo(["(inherit)"] + [e.value for e in EffortLevel])
        if config is not None and config.effort is not None:
            idx = self._w_effort.findText(config.effort.value)
            if idx >= 0:
                self._w_effort.setCurrentIndex(idx)
        lay.addRow(self._lbl("effort"), self._w_effort)

        if config is not None and hasattr(config, "allowed_tools"):
            self._w_tools = self._input()
            self._w_tools.setPlaceholderText("Read Grep WebSearch")
            self._w_tools.setText(" ".join(config.allowed_tools))
            lay.addRow(self._lbl("allowed-tools"), self._w_tools)

        if isinstance(config, ProceduralSkillConfig):
            self._w_context = self._combo([e.value for e in SkillContext])
            idx = self._w_context.findText(config.context.value)
            if idx >= 0:
                self._w_context.setCurrentIndex(idx)
            lay.addRow(self._lbl("context"), self._w_context)

            self._w_disable_model = QCheckBox()
            self._w_disable_model.setChecked(config.disable_model_invocation)
            lay.addRow(self._lbl("disable-model-invocation"), self._w_disable_model)

            self._w_user_invocable = QCheckBox()
            self._w_user_invocable.setChecked(config.user_invocable)
            lay.addRow(self._lbl("user-invocable"), self._w_user_invocable)

            self._w_paths = self._input()
            self._w_paths.setPlaceholderText("src/**/*.py")
            if config.paths:
                self._w_paths.setText(" ".join(config.paths))
            lay.addRow(self._lbl("paths (glob)"), self._w_paths)

            self._w_shell = self._combo([e.value for e in SkillShell])
            idx = self._w_shell.findText(config.shell.value)
            if idx >= 0:
                self._w_shell.setCurrentIndex(idx)
            lay.addRow(self._lbl("shell"), self._w_shell)

        # output_events (ProceduralSkill / AgentDefinition)
        if hasattr(comp, "output_events"):
            self._w_output_events = self._input()
            self._w_output_events.setPlaceholderText("done error")
            self._w_output_events.setText(" ".join(comp.output_events))
            self._w_output_events.editingFinished.connect(self._on_output_events_changed)
            lay.addRow(self._lbl("output_events"), self._w_output_events)

    def _on_output_events_changed(self) -> None:
        if not hasattr(self, "_w_output_events"):
            return
        raw = self._w_output_events.text().strip()
        events = [e for e in raw.split() if e] or ["done"]
        if hasattr(self._component, "output_events"):
            self._component.output_events = events
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    def _build_sections(self) -> None:
        for section in SkillSection:
            always = section == SkillSection.INSTRUCTIONS
            card = _SectionCard(section, always_active=always)
            self._section_cards.append(card)
            self._body_layout.addWidget(card)
        self._body_layout.addStretch()

    def _build_buttons(self) -> None:
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(
            "background: #1a3a1a; border: 1px solid #4a8a4a; color: #88cc88; padding: 5px 14px;"
        )
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        preview_btn = QPushButton("SKILL.md 미리보기")
        preview_btn.setStyleSheet(
            "background: #2a1a2a; border: 1px solid #6a4a8a; color: #aa88cc; padding: 5px 14px;"
        )
        preview_btn.clicked.connect(self._on_preview)
        btn_layout.addWidget(preview_btn)

        self._body_layout.insertWidget(self._body_layout.count() - 1, btn_row)

    def _on_save(self) -> None:
        self._component.name = self._w_name.text().strip()
        self._component.description = self._w_desc.toPlainText().strip()
        self.skill_changed.emit()

    def _on_preview(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "SKILL.md 미리보기", "컴파일러 미구현 (B-stage 스코프 외)"
        )
```

- [ ] **Step 2: 커밋**

```bash
git add daedalus/view/editors/skill_editor.py
git commit -m "feat: add SkillEditor with frontmatter form and SkillSection cards"
```

---

## Task 8: MainWindow 배선

**Files:**
- Modify: `daedalus/view/app.py`

- [ ] **Step 1: app.py 전체 교체**

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
from daedalus.view.editors.skill_editor import SkillEditor
from daedalus.view.panels.history_panel import HistoryPanel
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.panels.registry_panel import RegistryPanel
from daedalus.view.panels.script_listener import ScriptListenerPanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


class MainWindow(QMainWindow):
    """Daedalus 메인 윈도우."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Daedalus — FSM Plugin Designer")
        self.resize(1400, 860)

        self._project: PluginProject | None = None
        self._project_vm = ProjectViewModel()
        self._tab_vms: dict[int, ProjectViewModel] = {}
        self._open_tabs: dict[str, int] = {}
        self._active_stack = self._project_vm.command_stack

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
        self._registry_panel = RegistryPanel()
        registry_dock = QDockWidget("Registry")
        registry_dock.setWidget(self._registry_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, registry_dock)

        self._history_panel = HistoryPanel(
            self._project_vm.command_stack, on_goto=self._project_vm.notify,
        )
        history_dock = QDockWidget("History")
        history_dock.setWidget(self._history_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, history_dock)

        self._property_panel = PropertyPanel(self._project_vm)
        prop_dock = QDockWidget("Properties")
        prop_dock.setWidget(self._property_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, prop_dock)

        self._script_panel = ScriptListenerPanel()
        script_dock = QDockWidget("Script Listener")
        script_dock.setWidget(self._script_panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, script_dock)

    def _setup_menus(self) -> None:
        menubar = self.menuBar()
        if menubar is None:
            return
        edit_menu = menubar.addMenu("Edit")
        if edit_menu is None:
            return
        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.triggered.connect(self._undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.triggered.connect(self._redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menubar.addMenu("View")
        if view_menu is None:
            return
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
        self._registry_panel.component_double_clicked.connect(self._open_component)
        self._registry_panel.new_skill_requested.connect(self._on_new_skill_requested)
        self._active_stack.add_listener(self._update_undo_redo)

    # --- 프로젝트 ---

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._registry_panel.set_project(project)

    def _skill_lookup(self, name: str) -> ProceduralSkill | DeclarativeSkill | AgentDefinition | None:
        if self._project is None:
            return None
        for skill in self._project.skills:
            if skill.name == name:
                return skill
        for agent in self._project.agents:
            if agent.name == name:
                return agent
        return None

    def _get_placed_ids(self, tab_vm: ProjectViewModel) -> set[int]:
        return {
            id(svm.model.skill_ref)
            for svm in tab_vm.state_vms
            if svm.model.skill_ref is not None
        }

    def _notify_all_tabs(self) -> None:
        self._project_vm.notify()
        for vm in self._tab_vms.values():
            vm.notify()

    # --- 탭 관리 ---

    def _open_component(self, component: object) -> None:
        name = getattr(component, "name", None)
        if name is None:
            return
        if name in self._open_tabs:
            self._tabs.setCurrentIndex(self._open_tabs[name])
            return

        if isinstance(component, (ProceduralSkill, AgentDefinition)):
            tab_vm = ProjectViewModel()
            tab_vm.add_listener(lambda: self._on_tab_vm_changed(tab_vm))
            scene = FsmScene(tab_vm, skill_lookup=self._skill_lookup)
            view = FsmCanvasView(scene)
            scene.selectionChanged.connect(lambda s=scene: self._on_scene_selection(s))
            idx = self._tabs.addTab(view, name)
            self._tab_vms[idx] = tab_vm

        elif isinstance(component, DeclarativeSkill):
            editor = SkillEditor(component, on_notify_fn=self._notify_all_tabs)
            idx = self._tabs.addTab(editor, name)

        else:
            return

        self._open_tabs[name] = idx
        self._tabs.setCurrentIndex(idx)

    def _on_tab_vm_changed(self, tab_vm: ProjectViewModel) -> None:
        placed = self._get_placed_ids(tab_vm)
        self._registry_panel.set_placed_ids(placed)

    def _on_new_skill_requested(self) -> None:
        from daedalus.model.fsm.machine import StateMachine
        from daedalus.model.fsm.state import SimpleState as _SS
        s = _SS(name="start")
        fsm = StateMachine(name="new_fsm", states=[s], initial_state=s)
        skill = ProceduralSkill(fsm=fsm, name="NewSkill", description="")
        if self._project is not None:
            self._project.skills.append(skill)
            self._registry_panel.set_project(self._project)
        editor = SkillEditor(skill, on_notify_fn=self._notify_all_tabs)
        idx = self._tabs.addTab(editor, "NewSkill")
        self._open_tabs["NewSkill"] = idx
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        name = next((n for n, i in self._open_tabs.items() if i == index), None)
        if name:
            del self._open_tabs[name]
        widget = self._tabs.widget(index)
        if isinstance(widget, FsmCanvasView):
            scene = widget.scene()
            if isinstance(scene, FsmScene):
                scene.close()
        self._tab_vms.pop(index, None)
        self._tabs.removeTab(index)
        self._open_tabs = {
            n: (i if i < index else i - 1) for n, i in self._open_tabs.items()
        }
        self._tab_vms = {
            (i if i < index else i - 1): vm
            for i, vm in self._tab_vms.items()
            if i != index
        }

    def _on_tab_changed(self, index: int) -> None:
        self._property_panel.clear()
        self._active_stack.remove_listener(self._update_undo_redo)

        if index >= 0 and index in self._tab_vms:
            active_vm = self._tab_vms[index]
            self._active_stack = active_vm.command_stack
            self._history_panel.set_stack(active_vm.command_stack, on_goto=active_vm.notify)
            self._property_panel.set_project_vm(active_vm)
            self._script_panel.set_stack(active_vm.command_stack)
            self._registry_panel.set_placed_ids(self._get_placed_ids(active_vm))
        else:
            self._active_stack = self._project_vm.command_stack
            self._registry_panel.set_placed_ids(set())

        self._active_stack.add_listener(self._update_undo_redo)
        self._update_undo_redo()

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

    def _update_undo_redo(self) -> None:
        index = self._tabs.currentIndex()
        stack = (
            self._tab_vms[index].command_stack
            if index >= 0 and index in self._tab_vms
            else self._project_vm.command_stack
        )
        self._undo_action.setEnabled(stack.can_undo)
        self._redo_action.setEnabled(stack.can_redo)
        self._undo_action.setText(
            f"Undo: {stack.history[-1].description}" if stack.can_undo else "Undo"
        )
        self._redo_action.setText(
            f"Redo: {stack.redo_history[0].description}" if stack.can_redo else "Redo"
        )

    def _undo(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0 and index in self._tab_vms:
            vm = self._tab_vms[index]
            vm.command_stack.undo()
            vm.notify()
        else:
            self._project_vm.command_stack.undo()
            self._project_vm.notify()

    def _redo(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0 and index in self._tab_vms:
            vm = self._tab_vms[index]
            vm.command_stack.redo()
            vm.notify()
        else:
            self._project_vm.command_stack.redo()
            self._project_vm.notify()

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._registry_panel.set_project(project)
```

- [ ] **Step 2: 전체 테스트 통과 확인**

```
python -m pytest tests/ -v
```
Expected: 전체 통과

- [ ] **Step 3: 앱 실행 통합 확인**

```
python -m daedalus.main
```

확인 사항:
1. 좌측 Registry Palette에 스킬/에이전트 목록 표시됨
2. 스킬 더블클릭 → SkillEditor 탭 열림 (frontmatter 폼 + 섹션 카드)
3. 스킬 드래그 → 캔버스 드롭 → 타입별 색상 노드 생성
4. 드롭된 스킬은 레지스트리에서 dim 처리됨
5. 출력 포트 드래그 → 다른 노드 입력 포트에 드롭 → 전이 엣지 생성
6. output_events 수정 후 Enter → 포트 수 갱신

- [ ] **Step 4: 커밋**

```bash
git add daedalus/view/app.py
git commit -m "feat: wire RegistryPanel + SkillEditor — B-stage complete"
```

---

## 셀프 리뷰

**스펙 커버리지:**
- ✅ `SimpleState.skill_ref` → Task 2
- ✅ `output_events` 동적 포트 → Task 2, 4
- ✅ `SkillSection` Enum 확장성 → Task 1, 7
- ✅ `no_duplicate_skill_ref` validator → Task 3
- ✅ 노드 타입별 색상/아이콘 → Task 4
- ✅ 입력 포트 1개 (다중 incoming 허용) → Task 4 (`is_input_port`)
- ✅ 출력 포트 동적 생성 → Task 4 (`_output_events()`)
- ✅ Registry dim 처리 → Task 6 (`_ROLE_PLACED`)
- ✅ Registry 드래그 → 캔버스 드롭 배치 → Task 5, 6
- ✅ SkillEditor 프론트매터 폼 → Task 7
- ✅ SkillEditor 섹션 카드 (Enum 자동) → Task 7
- ✅ output_events 수정 → 캔버스 포트 갱신 → Task 7 + Task 4 (`update_from_model`)
- ✅ `_skill_lookup` + `skill_ref` 동일성 기반 유일성 체크 → Task 5 (`drop_skill`)
- ⛔ SKILL.md 컴파일러 (스코프 외)
- ⛔ 내부 FSM 탐색 (C-stage)

**타입 일관성:**
- `begin_transition_drag(source, event_name)` — Task 4 호출 ↔ Task 5 정의 일치
- `output_port_scene_pos(event_name)` — Task 4 정의 ↔ edge_item 사용 일치
- `drop_skill(skill_name, scene_pos)` — Task 5 정의 ↔ canvas_view 호출 일치
- `set_placed_ids(set[int])` — Task 6 정의 ↔ Task 8 호출 일치
- `_run_drag = getattr(drag, "exec"); _run_drag(...)` — PyQt6 QDrag 실행 패턴
