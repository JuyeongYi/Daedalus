# Daedalus Model Layer Reinforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 평가에서 발견된 이슈를 해결하고, 모델 레이어의 미흡/보통 영역을 양호 수준으로 보강한다.

**Architecture:** CompositeState/Region을 sub_machine 포함 구조로 변경, 이벤트 계층에 CompletionEvent 추가 및 빈 추상 클래스 제거, FieldType 통합 및 ComponentConfig 공통 베이스 추출, Validator를 재귀 구조로 리팩토링하고 4개 검증 규칙 추가.

**Tech Stack:** Python 3.12+, dataclasses, abc, pytest

**Spec:** `docs/superpowers/specs/2026-04-11-daedalus-model-reinforcement.md`

---

## File Structure (변경 대상만)

```
daedalus/model/fsm/
├── event.py       # CompletionEvent 추가, TransitionEvent·CompositeStateEvent 제거
├── variable.py    # VariableType → FieldType 교체
├── state.py       # CompositeState·Region 구조 변경
└── blackboard.py  # DynamicFieldType 제거, FieldType 사용
daedalus/model/plugin/
└── config.py      # ComponentConfig 추출
daedalus/model/
└── validation.py  # 재귀 구조 + 신규 4개 규칙
tests/ (위 변경에 맞춰 수정)
```

---

### Task 1: FieldType 통합 (variable.py + blackboard.py)

**Files:**
- Modify: `daedalus/model/fsm/variable.py`
- Modify: `daedalus/model/fsm/blackboard.py`
- Modify: `tests/model/fsm/test_variable.py`
- Modify: `tests/model/fsm/test_blackboard.py`

- [ ] **Step 1: Write the failing test for FieldType**

```python
# tests/model/fsm/test_variable.py — 전체 교체
from __future__ import annotations

from daedalus.model.fsm.variable import (
    Variable,
    VariableScope,
    FieldType,
    ConflictResolution,
)


def test_variable_scope_enum():
    assert VariableScope.LOCAL.value == "local"
    assert VariableScope.BLACKBOARD.value == "blackboard"


def test_field_type_enum():
    assert FieldType.STRING.value == "string"
    assert FieldType.INT.value == "int"
    assert FieldType.FLOAT.value == "float"
    assert FieldType.NUMBER.value == "number"
    assert FieldType.BOOL.value == "bool"
    assert FieldType.LIST.value == "list"
    assert FieldType.JSON.value == "json"
    assert FieldType.ANY.value == "any"


def test_conflict_resolution_enum():
    assert ConflictResolution.LAST_WRITE.value == "last_write"
    assert ConflictResolution.MERGE_LIST.value == "merge_list"
    assert ConflictResolution.ERROR.value == "error"
    assert ConflictResolution.CUSTOM.value == "custom"


def test_variable_instantiation():
    var = Variable(name="result", description="작업 결과")
    assert var.name == "result"
    assert var.description == "작업 결과"
    assert var.scope == VariableScope.LOCAL
    assert var.field_type == FieldType.ANY
    assert var.required is False
    assert var.default is None
    assert var.conflict_resolution == ConflictResolution.LAST_WRITE


def test_variable_blackboard_scope():
    var = Variable(
        name="user",
        description="사용자 정보",
        scope=VariableScope.BLACKBOARD,
        field_type=FieldType.JSON,
        required=True,
    )
    assert var.scope == VariableScope.BLACKBOARD
    assert var.field_type == FieldType.JSON
    assert var.required is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/fsm/test_variable.py -v`
Expected: FAIL — `FieldType` not found, `var_type` attribute errors

- [ ] **Step 3: Update variable.py**

```python
# daedalus/model/fsm/variable.py — 전체 교체
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class VariableScope(Enum):
    LOCAL = "local"
    BLACKBOARD = "blackboard"


class FieldType(Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    NUMBER = "number"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"


class ConflictResolution(Enum):
    LAST_WRITE = "last_write"
    MERGE_LIST = "merge_list"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class Variable:
    name: str
    description: str
    scope: VariableScope = VariableScope.LOCAL
    field_type: FieldType = FieldType.ANY
    required: bool = False
    default: Any | None = None
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE
```

- [ ] **Step 4: Run variable test to verify it passes**

Run: `python -m pytest tests/model/fsm/test_variable.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Update blackboard test for FieldType**

```python
# tests/model/fsm/test_blackboard.py — 전체 교체
from __future__ import annotations

from daedalus.model.fsm.blackboard import (
    Blackboard,
    DynamicClass,
    DynamicField,
    CollectionType,
)
from daedalus.model.fsm.variable import Variable, VariableScope, FieldType


def test_collection_type_enum():
    assert CollectionType.NONE.value == "none"
    assert CollectionType.LIST.value == "list"
    assert CollectionType.SET.value == "set"


def test_dynamic_field():
    f = DynamicField(name="status", field_type=FieldType.STRING)
    assert f.name == "status"
    assert f.collection == CollectionType.NONE
    assert f.required is False
    assert f.default is None


def test_dynamic_class():
    fields = [
        DynamicField(name="status", field_type=FieldType.STRING, required=True),
        DynamicField(name="errors", field_type=FieldType.STRING, collection=CollectionType.LIST),
        DynamicField(name="count", field_type=FieldType.INT, default=0),
    ]
    dc = DynamicClass(name="BuildResult", description="빌드 결과", fields=fields)
    assert dc.name == "BuildResult"
    assert len(dc.fields) == 3
    assert dc.fields[0].required is True
    assert dc.fields[1].collection == CollectionType.LIST
    assert dc.fields[2].default == 0


def test_blackboard_empty():
    bb = Blackboard()
    assert bb.class_definitions == []
    assert bb.variables == {}
    assert bb.parent is None


def test_blackboard_with_variables():
    var = Variable(name="status", description="상태", scope=VariableScope.BLACKBOARD)
    bb = Blackboard(variables={"status": var})
    assert "status" in bb.variables
    assert bb.variables["status"] is var


def test_blackboard_scoping():
    parent_bb = Blackboard()
    child_bb = Blackboard(parent=parent_bb)
    assert child_bb.parent is parent_bb


def test_blackboard_with_dynamic_class():
    dc = DynamicClass(
        name="DeployLog",
        description="배포 로그",
        fields=[DynamicField(name="timestamp", field_type=FieldType.STRING)],
    )
    bb = Blackboard(class_definitions=[dc])
    assert len(bb.class_definitions) == 1
    assert bb.class_definitions[0].name == "DeployLog"
```

- [ ] **Step 6: Update blackboard.py — remove DynamicFieldType, use FieldType**

```python
# daedalus/model/fsm/blackboard.py — 전체 교체
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from daedalus.model.fsm.variable import FieldType, Variable


class CollectionType(Enum):
    NONE = "none"
    LIST = "list"
    SET = "set"


@dataclass
class DynamicField:
    name: str
    field_type: FieldType
    collection: CollectionType = CollectionType.NONE
    default: Any | None = None
    required: bool = False


@dataclass
class DynamicClass:
    name: str
    description: str
    fields: list[DynamicField] = field(default_factory=list)


@dataclass
class Blackboard:
    class_definitions: list[DynamicClass] = field(default_factory=list)
    variables: dict[str, Variable] = field(default_factory=dict)
    parent: Blackboard | None = None
```

- [ ] **Step 7: Run both tests**

Run: `python -m pytest tests/model/fsm/test_variable.py tests/model/fsm/test_blackboard.py -v`
Expected: PASS (12 tests)

- [ ] **Step 8: Commit**

```bash
git add daedalus/model/fsm/variable.py daedalus/model/fsm/blackboard.py tests/model/fsm/test_variable.py tests/model/fsm/test_blackboard.py
git commit -m "refactor: unify VariableType and DynamicFieldType into FieldType"
```

---

### Task 2: Event 계층 보강 (CompletionEvent + 정리)

**Files:**
- Modify: `daedalus/model/fsm/event.py`
- Modify: `tests/model/fsm/test_event.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_event.py — 전체 교체
from __future__ import annotations

import pytest
from daedalus.model.fsm.event import (
    Event,
    StateEvent,
    BlackboardEvent,
    BlackboardTrigger,
    CompletionEvent,
)


def test_event_is_abstract():
    with pytest.raises(TypeError):
        Event(name="e")


def test_state_event_is_abstract():
    with pytest.raises(TypeError):
        StateEvent(name="e")


def test_blackboard_event_is_abstract():
    with pytest.raises(TypeError):
        BlackboardEvent(name="e")


def test_completion_event():
    ev = CompletionEvent(name="done")
    assert ev.name == "done"
    assert ev.kind == "completion"


def test_blackboard_trigger_instantiation():
    trigger = BlackboardTrigger(
        name="status_changed",
        variable="status",
    )
    assert trigger.name == "status_changed"
    assert trigger.variable == "status"
    assert trigger.condition is None


def test_blackboard_trigger_with_condition():
    from daedalus.model.fsm.strategy import ExpressionEvaluation

    cond = ExpressionEvaluation(expression="${bb.status} == 'done'")
    trigger = BlackboardTrigger(
        name="done_check",
        variable="status",
        condition=cond,
    )
    assert trigger.condition is cond
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/fsm/test_event.py -v`
Expected: FAIL — `CompletionEvent` not found, `TransitionEvent`/`CompositeStateEvent` import errors

- [ ] **Step 3: Update event.py**

```python
# daedalus/model/fsm/event.py — 전체 교체
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daedalus.model.fsm.strategy import EvaluationStrategy


@dataclass
class Event(ABC):
    name: str

    @property
    @abstractmethod
    def kind(self) -> str:
        """이벤트 종류 식별자."""


@dataclass
class StateEvent(Event, ABC):
    """상태 관련 이벤트 베이스."""


@dataclass
class CompletionEvent(StateEvent):
    """상태 완료 시 발생하는 이벤트.

    SimpleState 작업 완료, CompositeState sub_machine 종료,
    ParallelState 전 Region 완료 시 발생.
    """

    @property
    def kind(self) -> str:
        return "completion"


@dataclass
class BlackboardEvent(Event, ABC):
    """블랙보드 변경 이벤트 베이스."""


@dataclass
class BlackboardTrigger(BlackboardEvent):
    """블랙보드 변수 변경 감지 트리거."""
    variable: str = ""
    condition: EvaluationStrategy | None = None

    @property
    def kind(self) -> str:
        return "blackboard_trigger"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/fsm/test_event.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/event.py tests/model/fsm/test_event.py
git commit -m "refactor: add CompletionEvent, remove empty TransitionEvent and CompositeStateEvent"
```

---

### Task 3: CompositeState + Region 구조 변경

**Files:**
- Modify: `daedalus/model/fsm/state.py`
- Modify: `tests/model/fsm/test_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_state.py — 전체 교체
from __future__ import annotations

import pytest
from daedalus.model.fsm.state import (
    State,
    SimpleState,
    CompositeState,
    ParallelState,
    Region,
)
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution
from daedalus.model.fsm.variable import Variable, VariableScope
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.blackboard import Blackboard


def test_state_is_abstract():
    with pytest.raises(TypeError):
        State(name="s")


def test_simple_state():
    s = SimpleState(name="idle")
    assert s.name == "idle"
    assert s.on_entry == []
    assert s.on_exit == []
    assert s.inputs == []
    assert s.outputs == []
    assert s.custom_events == {}


def test_simple_state_with_actions():
    action = Action(name="greet", execution=LLMExecution(prompt="인사"))
    s = SimpleState(
        name="greeting",
        on_entry=[action],
    )
    assert len(s.on_entry) == 1
    assert s.on_entry[0].name == "greet"


def test_simple_state_with_io():
    inp = Variable(name="data", description="입력")
    out = Variable(name="result", description="출력", scope=VariableScope.BLACKBOARD)
    s = SimpleState(name="process", inputs=[inp], outputs=[out])
    assert len(s.inputs) == 1
    assert len(s.outputs) == 1
    assert s.outputs[0].scope == VariableScope.BLACKBOARD


def test_composite_state():
    s1 = SimpleState(name="s1")
    s2 = SimpleState(name="s2")
    t = Transition(source=s1, target=s2)
    sub = StateMachine(
        name="inner",
        states=[s1, s2],
        transitions=[t],
        initial_state=s1,
        final_states=[s2],
    )
    cs = CompositeState(name="agent_x", sub_machine=sub)
    assert cs.name == "agent_x"
    assert cs.sub_machine is sub
    assert len(cs.sub_machine.states) == 2
    assert len(cs.sub_machine.transitions) == 1
    assert cs.sub_machine.initial_state is s1
    assert cs.sub_machine.final_states == [s2]


def test_composite_state_blackboard_scoping():
    parent_bb = Blackboard()
    child_bb = Blackboard(parent=parent_bb)
    s1 = SimpleState(name="s1")
    sub = StateMachine(name="inner", initial_state=s1, states=[s1], blackboard=child_bb)
    cs = CompositeState(name="scoped", sub_machine=sub)
    assert cs.sub_machine.blackboard.parent is parent_bb


def test_region():
    s1 = SimpleState(name="r1_s1")
    sub = StateMachine(name="r1_flow", initial_state=s1, states=[s1])
    r = Region(name="region_1", sub_machine=sub)
    assert r.name == "region_1"
    assert r.sub_machine is sub
    assert r.sub_machine.initial_state is s1


def test_parallel_state():
    s1 = SimpleState(name="a")
    s2 = SimpleState(name="b")
    sub1 = StateMachine(name="r1_flow", initial_state=s1, states=[s1])
    sub2 = StateMachine(name="r2_flow", initial_state=s2, states=[s2])
    r1 = Region(name="r1", sub_machine=sub1)
    r2 = Region(name="r2", sub_machine=sub2)
    ps = ParallelState(name="parallel", regions=[r1, r2])
    assert len(ps.regions) == 2
    assert ps.regions[0].sub_machine.initial_state is s1
    assert ps.regions[1].sub_machine.initial_state is s2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/fsm/test_state.py -v`
Expected: FAIL — `sub_machine` attribute not found on CompositeState

- [ ] **Step 3: Update state.py**

```python
# daedalus/model/fsm/state.py — 전체 교체
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.variable import Variable

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine


@dataclass
class State(ABC):
    name: str
    # 진입 이벤트
    on_entry_start: list[Action] = field(default_factory=list)
    on_entry: list[Action] = field(default_factory=list)
    on_entry_end: list[Action] = field(default_factory=list)
    # 탈출 이벤트
    on_exit_start: list[Action] = field(default_factory=list)
    on_exit: list[Action] = field(default_factory=list)
    on_exit_end: list[Action] = field(default_factory=list)
    # 활동
    on_active: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    # 데이터
    inputs: list[Variable] = field(default_factory=list)
    outputs: list[Variable] = field(default_factory=list)

    @property
    @abstractmethod
    def kind(self) -> str:
        """상태 종류 식별자."""


@dataclass
class SimpleState(State):
    """리프 상태. 하위 상태 없음."""

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
    """별도 컨텍스트의 상태 기계. 내부에 완전한 sub FSM 보유."""
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/fsm/test_state.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/state.py tests/model/fsm/test_state.py
git commit -m "refactor: CompositeState and Region now contain sub_machine"
```

---

### Task 4: 연쇄 테스트 수정 (validation, project, skill, agent)

CompositeState API 변경으로 깨지는 기존 테스트를 수정한다.

**Files:**
- Modify: `tests/model/test_validation.py`
- Modify: `tests/model/test_project.py`
- Modify: `tests/model/plugin/test_skill.py`
- Modify: `tests/model/plugin/test_agent.py`

- [ ] **Step 1: Update test_validation.py**

```python
# tests/model/test_validation.py — 전체 교체
from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable, VariableScope


def _make_sm(states, transitions):
    return StateMachine(
        name="test",
        states=states,
        transitions=transitions,
        initial_state=states[0],
    )


def _make_agent(name, child_names):
    """헬퍼: SimpleState 자식을 가진 CompositeState 생성."""
    children = [SimpleState(name=n) for n in child_names]
    sub = StateMachine(
        name=f"{name}_flow",
        states=children,
        initial_state=children[0],
    )
    return CompositeState(name=name, sub_machine=sub)


def test_no_agent_inside_agent():
    """CompositeState 내부에 CompositeState 불가."""
    inner_agent = _make_agent("inner_agent", ["x"])
    outer_sub = StateMachine(
        name="outer_flow",
        states=[inner_agent],
        initial_state=inner_agent,
    )
    outer_agent = CompositeState(name="outer_agent", sub_machine=outer_sub)
    sm = _make_sm([outer_agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_nested_agent" for e in errors)


def test_no_agent_to_agent_direct():
    """Agent→Agent 직접 엣지 불가."""
    a1 = _make_agent("agent1", ["x"])
    a2 = _make_agent("agent2", ["y"])
    t = Transition(source=a1, target=a2)
    sm = _make_sm([a1, a2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_agent_to_agent" for e in errors)


def test_valid_skill_to_agent():
    """Skill→Agent 엣지는 허용."""
    skill = SimpleState(name="skill_a")
    agent = _make_agent("agent_x", ["s1"])
    t = Transition(source=skill, target=agent)
    sm = _make_sm([skill, agent], [t])
    errors = Validator.validate(sm)
    agent_errors = [e for e in errors if e.rule in ("no_agent_to_agent", "no_nested_agent")]
    assert agent_errors == []


def test_missing_required_input():
    """타겟의 필수 input이 data_map에 없으면 경고."""
    s1 = SimpleState(name="A", outputs=[Variable(name="result", description="r")])
    s2 = SimpleState(
        name="B",
        inputs=[Variable(name="data", description="d", required=True)],
    )
    t = Transition(source=s1, target=s2, data_map={})
    sm = _make_sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "missing_required_input" for e in errors)


def test_required_input_satisfied():
    """필수 input이 data_map에 있으면 에러 없음."""
    s1 = SimpleState(name="A", outputs=[Variable(name="result", description="r")])
    s2 = SimpleState(
        name="B",
        inputs=[Variable(name="data", description="d", required=True)],
    )
    t = Transition(source=s1, target=s2, data_map={"result": "data"})
    sm = _make_sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "missing_required_input" for e in errors)
```

- [ ] **Step 2: Run to verify validation tests pass**

Run: `python -m pytest tests/model/test_validation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 3: Run full test suite to find remaining breakage**

Run: `python -m pytest tests/ -v`
Expected: 일부 테스트가 `VariableType`, `DynamicFieldType` import 에러로 실패할 수 있음. 아래에서 수정.

- [ ] **Step 4: Fix test_project.py if broken**

test_project.py에서 CompositeState를 직접 사용하지 않으므로 변경 불필요할 가능성 높음. 깨지면 `VariableType` → `FieldType` import만 수정.

- [ ] **Step 5: Fix test_skill.py / test_agent.py if broken**

이 파일들도 CompositeState를 직접 사용하지 않으므로 변경 불필요할 가능성 높음. 깨지면 import만 수정.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "fix: update tests for CompositeState sub_machine and FieldType changes"
```

---

### Task 5: ComponentConfig 추출

**Files:**
- Modify: `daedalus/model/plugin/config.py`
- Modify: `tests/model/plugin/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/plugin/test_config.py — 전체 교체
from __future__ import annotations

import pytest
from daedalus.model.plugin.config import (
    ComponentConfig,
    SkillConfig,
    ProceduralSkillConfig,
    DeclarativeSkillConfig,
    AgentConfig,
)
from daedalus.model.plugin.enums import (
    ModelType,
    EffortLevel,
    SkillContext,
    SkillShell,
    PermissionMode,
    MemoryScope,
    AgentIsolation,
    AgentColor,
)


def test_component_config_is_abstract():
    with pytest.raises(TypeError):
        ComponentConfig()


def test_skill_config_is_abstract():
    with pytest.raises(TypeError):
        SkillConfig()


def test_procedural_skill_config_defaults():
    c = ProceduralSkillConfig()
    assert c.model == ModelType.INHERIT
    assert c.effort is None
    assert c.hooks is None
    assert c.argument_hint is None
    assert c.allowed_tools == []
    assert c.paths is None
    assert c.disable_model_invocation is False
    assert c.user_invocable is True
    assert c.context == SkillContext.INLINE
    assert c.agent is None
    assert c.shell == SkillShell.BASH


def test_procedural_skill_config_custom():
    c = ProceduralSkillConfig(
        allowed_tools=["Bash", "Read"],
        model=ModelType.SONNET,
        effort=EffortLevel.HIGH,
        disable_model_invocation=True,
        context=SkillContext.FORK,
        agent="Explore",
    )
    assert c.allowed_tools == ["Bash", "Read"]
    assert c.model == ModelType.SONNET
    assert c.context == SkillContext.FORK
    assert c.agent == "Explore"


def test_declarative_skill_config():
    c = DeclarativeSkillConfig(user_invocable=False)
    assert c.user_invocable is False
    assert c.disable_model_invocation is False


def test_agent_config_defaults():
    c = AgentConfig()
    assert c.model == ModelType.INHERIT
    assert c.effort is None
    assert c.hooks is None
    assert c.tools is None
    assert c.disallowed_tools is None
    assert c.permission_mode == PermissionMode.DEFAULT
    assert c.max_turns is None
    assert c.skills == []
    assert c.mcp_servers is None
    assert c.memory is None
    assert c.background is False
    assert c.isolation == AgentIsolation.NONE
    assert c.color is None
    assert c.initial_prompt is None


def test_agent_config_custom():
    c = AgentConfig(
        tools=["Read", "Grep", "Glob"],
        model=ModelType.HAIKU,
        permission_mode=PermissionMode.DONT_ASK,
        memory=MemoryScope.PROJECT,
        color=AgentColor.BLUE,
    )
    assert c.tools == ["Read", "Grep", "Glob"]
    assert c.model == ModelType.HAIKU
    assert c.memory == MemoryScope.PROJECT
    assert c.color == AgentColor.BLUE


def test_component_config_shared_fields():
    """ComponentConfig 공통 필드가 모든 서브클래스에서 동작하는지 확인."""
    proc = ProceduralSkillConfig(model=ModelType.OPUS, effort=EffortLevel.MAX)
    agent = AgentConfig(model=ModelType.OPUS, effort=EffortLevel.MAX)
    assert proc.model == agent.model
    assert proc.effort == agent.effort
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/model/plugin/test_config.py -v`
Expected: FAIL — `ComponentConfig` not found

- [ ] **Step 3: Update config.py**

```python
# daedalus/model/plugin/config.py — 전체 교체
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillShell,
)


@dataclass
class ComponentConfig(ABC):
    """플러그인 컴포넌트 공통 설정."""
    model: ModelType | str = ModelType.INHERIT
    effort: EffortLevel | None = None
    hooks: dict[str, Any] | None = None

    @property
    @abstractmethod
    def kind(self) -> str:
        """설정 종류 식별자."""


@dataclass
class SkillConfig(ComponentConfig, ABC):
    """스킬 공통 프론트매터."""
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    paths: list[str] | None = None


@dataclass
class ProceduralSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: SkillContext = SkillContext.INLINE
    agent: str | None = None
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return "procedural"


@dataclass
class DeclarativeSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True

    @property
    def kind(self) -> str:
        return "declarative"


@dataclass
class AgentConfig(ComponentConfig):
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] | None = None
    memory: MemoryScope | None = None
    background: bool = False
    isolation: AgentIsolation = AgentIsolation.NONE
    color: AgentColor | None = None
    initial_prompt: str | None = None

    @property
    def kind(self) -> str:
        return "agent"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/model/plugin/test_config.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/plugin/config.py tests/model/plugin/test_config.py
git commit -m "refactor: extract ComponentConfig base class for SkillConfig and AgentConfig"
```

---

### Task 6: Validator 재귀 구조 + 신규 규칙

**Files:**
- Modify: `daedalus/model/validation.py`
- Modify: `tests/model/test_validation.py`

- [ ] **Step 1: Write failing tests for new validation rules**

기존 test_validation.py(Task 4에서 수정된 버전)에 신규 테스트 추가:

```python
# tests/model/test_validation.py 끝에 추가

from daedalus.model.fsm.state import ParallelState, Region
from daedalus.model.fsm.pseudo import ChoiceState, HistoryState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.blackboard import Blackboard


# -- initial_state_in_states --

def test_initial_state_not_in_states():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    sm = StateMachine(name="test", states=[s1], initial_state=s2)
    errors = Validator.validate(sm)
    assert any(e.rule == "initial_state_in_states" for e in errors)


def test_initial_state_in_states_ok():
    s1 = SimpleState(name="A")
    sm = StateMachine(name="test", states=[s1], initial_state=s1)
    errors = Validator.validate(sm)
    assert not any(e.rule == "initial_state_in_states" for e in errors)


# -- final_states_in_states --

def test_final_state_not_in_states():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    sm = StateMachine(name="test", states=[s1], initial_state=s1, final_states=[s2])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)


# -- pseudo_state_hooks --

def test_choice_state_with_hooks_warns():
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    choice = ChoiceState(name="c", on_entry=[action])
    sm = StateMachine(name="test", states=[choice], initial_state=choice)
    errors = Validator.validate(sm)
    assert any(e.rule == "pseudo_state_hooks" for e in errors)


def test_history_state_with_hooks_no_warning():
    """HistoryState는 on_entry 훅 허용."""
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    h = HistoryState(name="H", on_entry=[action])
    sm = StateMachine(name="test", states=[h], initial_state=h)
    errors = Validator.validate(sm)
    assert not any(e.rule == "pseudo_state_hooks" for e in errors)


def test_terminate_state_with_hooks_warns():
    action = Action(name="a", execution=LLMExecution(prompt="x"))
    t = TerminateState(name="t", on_exit=[action])
    sm = StateMachine(name="test", states=[t], initial_state=t)
    errors = Validator.validate(sm)
    assert any(e.rule == "pseudo_state_hooks" for e in errors)


# -- completion_event_on_composite --

def test_composite_without_completion_trigger_warns():
    agent = _make_agent("agent1", ["s1"])
    s2 = SimpleState(name="next")
    t = Transition(source=agent, target=s2)  # trigger=None
    sm = _make_sm([agent, s2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "completion_event_on_composite" for e in errors)


def test_composite_with_completion_trigger_ok():
    agent = _make_agent("agent1", ["s1"])
    s2 = SimpleState(name="next")
    t = Transition(source=agent, target=s2, trigger=CompletionEvent(name="done"))
    sm = _make_sm([agent, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "completion_event_on_composite" for e in errors)


# -- 재귀 검증 --

def test_recursive_validation_in_composite():
    """CompositeState 내부의 sub_machine도 검증."""
    inner_s1 = SimpleState(name="inner1")
    inner_s2 = SimpleState(name="inner2")
    inner_sm = StateMachine(
        name="inner",
        states=[inner_s1],
        initial_state=inner_s1,
        final_states=[inner_s2],  # inner_s2가 states에 없음
    )
    agent = CompositeState(name="agent", sub_machine=inner_sm)
    sm = _make_sm([agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)


def test_recursive_validation_in_region():
    """Region 내부의 sub_machine도 검증."""
    s1 = SimpleState(name="r_s1")
    s2 = SimpleState(name="r_s2")
    region_sm = StateMachine(
        name="region_flow",
        states=[s1],
        initial_state=s1,
        final_states=[s2],  # s2가 states에 없음
    )
    r = Region(name="r1", sub_machine=region_sm)
    ps = ParallelState(name="par", regions=[r])
    sm = _make_sm([ps], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "final_states_in_states" for e in errors)
```

- [ ] **Step 2: Run test to verify new tests fail**

Run: `python -m pytest tests/model/test_validation.py -v`
Expected: FAIL — 새 규칙 함수들이 아직 없음

- [ ] **Step 3: Update validation.py**

```python
# daedalus/model/validation.py — 전체 교체
from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, State
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import VariableScope


@dataclass
class ValidationError:
    rule: str
    message: str
    source: str = ""


class Validator:
    @staticmethod
    def validate(sm: StateMachine) -> list[ValidationError]:
        return Validator._validate_machine(sm)

    @staticmethod
    def _validate_machine(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        errors.extend(Validator._check_initial_in_states(sm))
        errors.extend(Validator._check_final_in_states(sm))
        errors.extend(Validator._check_nested_agents(sm.states))
        errors.extend(Validator._check_agent_to_agent(sm.transitions))
        errors.extend(Validator._check_required_inputs(sm.transitions))
        errors.extend(Validator._check_pseudo_state_hooks(sm.states))
        errors.extend(Validator._check_completion_events(sm))
        # 재귀
        for state in sm.states:
            if isinstance(state, CompositeState):
                errors.extend(Validator._validate_machine(state.sub_machine))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    errors.extend(Validator._validate_machine(region.sub_machine))
        return errors

    @staticmethod
    def _check_initial_in_states(sm: StateMachine) -> list[ValidationError]:
        if sm.states and sm.initial_state not in sm.states:
            return [ValidationError(
                rule="initial_state_in_states",
                message=f"'{sm.name}': initial_state '{sm.initial_state.name}'이 states에 포함되지 않습니다.",
                source=sm.name,
            )]
        return []

    @staticmethod
    def _check_final_in_states(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for fs in sm.final_states:
            if fs not in sm.states:
                errors.append(ValidationError(
                    rule="final_states_in_states",
                    message=f"'{sm.name}': final_state '{fs.name}'이 states에 포함되지 않습니다.",
                    source=sm.name,
                ))
        return errors

    @staticmethod
    def _check_nested_agents(states: list[State]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for state in states:
            if isinstance(state, CompositeState):
                for child in state.sub_machine.states:
                    if isinstance(child, CompositeState):
                        errors.append(ValidationError(
                            rule="no_nested_agent",
                            message=(
                                f"CompositeState '{state.name}' 내부에 "
                                f"CompositeState '{child.name}'이 존재합니다."
                            ),
                            source=state.name,
                        ))
        return errors

    @staticmethod
    def _check_agent_to_agent(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            if isinstance(t.source, CompositeState) and isinstance(t.target, CompositeState):
                errors.append(ValidationError(
                    rule="no_agent_to_agent",
                    message=(
                        f"Agent '{t.source.name}' → Agent '{t.target.name}' "
                        f"직접 전이 불가. Skill을 경유해야 합니다."
                    ),
                    source=f"{t.source.name}->{t.target.name}",
                ))
        return errors

    @staticmethod
    def _check_required_inputs(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            target_required = [v for v in t.target.inputs if v.required]
            mapped_targets = set(t.data_map.values())
            for var in target_required:
                if var.name not in mapped_targets and var.scope != VariableScope.BLACKBOARD:
                    errors.append(ValidationError(
                        rule="missing_required_input",
                        message=(
                            f"전이 '{t.source.name}' → '{t.target.name}': "
                            f"필수 input '{var.name}'이 data_map에 없습니다."
                        ),
                        source=f"{t.source.name}->{t.target.name}",
                    ))
        return errors

    @staticmethod
    def _check_pseudo_state_hooks(states: list[State]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        pseudo_types = (ChoiceState, TerminateState, EntryPoint, ExitPoint)
        hook_fields = [
            "on_entry_start", "on_entry", "on_entry_end",
            "on_exit_start", "on_exit", "on_exit_end",
            "on_active",
        ]
        for state in states:
            if isinstance(state, pseudo_types):
                for field_name in hook_fields:
                    if getattr(state, field_name, []):
                        errors.append(ValidationError(
                            rule="pseudo_state_hooks",
                            message=(
                                f"의사 상태 '{state.name}'({state.kind})에 "
                                f"'{field_name}' 훅이 설정되어 있습니다."
                            ),
                            source=state.name,
                        ))
                        break  # 상태당 1개 경고
        return errors

    @staticmethod
    def _check_completion_events(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        composite_states = {
            s for s in sm.states
            if isinstance(s, (CompositeState, ParallelState))
        }
        for cs in composite_states:
            outgoing = [t for t in sm.transitions if t.source is cs]
            if outgoing and not any(isinstance(t.trigger, CompletionEvent) for t in outgoing):
                errors.append(ValidationError(
                    rule="completion_event_on_composite",
                    message=(
                        f"'{cs.name}'에서 나가는 전이에 CompletionEvent trigger가 없습니다."
                    ),
                    source=cs.name,
                ))
        return errors
```

- [ ] **Step 4: Run test to verify all pass**

Run: `python -m pytest tests/model/test_validation.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/validation.py tests/model/test_validation.py
git commit -m "feat: recursive Validator with 4 new rules (initial/final check, pseudo hooks, completion events)"
```

---

### Task 7: __init__.py 정리 + 전체 테스트

**Files:**
- Modify: `daedalus/model/fsm/__init__.py`

- [ ] **Step 1: Update fsm/__init__.py**

변경 없음 — 기존 `from daedalus.model.fsm.event import *` 등이 새 클래스를 자동 export.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Verify test count**

기존 91개에서 신규 테스트 추가로 약 100개 이상 예상.

- [ ] **Step 4: Commit (if any remaining changes)**

```bash
git add -A
git commit -m "chore: final cleanup after model reinforcement"
```

---

### Task 8: CLAUDE.md 업데이트

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

다음 내용을 반영:
- FieldType 통합 (VariableType, DynamicFieldType 삭제)
- CompositeState.sub_machine 구조
- Region.sub_machine 구조
- CompletionEvent
- ComponentConfig 계층
- Validator 7개 규칙
- 블랙보드 역할 정의: "서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치"
- 스킬/에이전트 개념: ProceduralSkill(작업 지침), DeclarativeSkill(배경 지식), Agent(별도 컨텍스트의 상태 기계)

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with model reinforcement changes"
```
