# Daedalus Model Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daedalus의 FSM + Blackboard 모델 계층 클래스를 구현한다 (model/ 패키지).

**Architecture:** 컴파일러 패턴 — 순수 FSM 코어(model/fsm/)와 Claude 플러그인 메타데이터(model/plugin/)를 분리. dataclasses + ABC로 데이터 모델 정의. 테스트는 pytest.

**Tech Stack:** Python 3.12+, dataclasses, abc, pytest

**Spec:** `docs/superpowers/specs/2026-04-11-daedalus-fsm-design.md`

---

## File Structure

```
daedalus/
├── __init__.py
├── model/
│   ├── __init__.py
│   ├── fsm/
│   │   ├── __init__.py
│   │   ├── event.py          # Event, StateEvent, TransitionEvent, CompositeStateEvent, BlackboardEvent, BlackboardTrigger
│   │   ├── variable.py       # Variable, VariableScope, VariableType, ConflictResolution
│   │   ├── strategy.py       # EvaluationStrategy 계열 + ExecutionStrategy 계열
│   │   ├── guard.py          # Guard
│   │   ├── action.py         # Action
│   │   ├── state.py          # State, SimpleState, CompositeState, ParallelState, Region
│   │   ├── pseudo.py         # HistoryState, ChoiceState, TerminateState, EntryPoint, ExitPoint
│   │   ├── transition.py     # Transition, TransitionType
│   │   ├── blackboard.py     # Blackboard, DynamicClass, DynamicField, DynamicFieldType, CollectionType
│   │   └── machine.py        # StateMachine
│   ├── plugin/
│   │   ├── __init__.py
│   │   ├── enums.py          # ModelType, EffortLevel, SkillContext, SkillShell, PermissionMode, MemoryScope, AgentIsolation, AgentColor
│   │   ├── policy.py         # ExecutionPolicy, JoinStrategy
│   │   ├── config.py         # SkillConfig, ProceduralSkillConfig, DeclarativeSkillConfig, AgentConfig
│   │   ├── base.py           # PluginComponent, WorkflowComponent
│   │   ├── skill.py          # Skill, ProceduralSkill, DeclarativeSkill
│   │   └── agent.py          # AgentDefinition
│   ├── project.py            # PluginProject
│   └── validation.py         # ValidationError, Validator
tests/
├── __init__.py
├── model/
│   ├── __init__.py
│   ├── fsm/
│   │   ├── __init__.py
│   │   ├── test_event.py
│   │   ├── test_variable.py
│   │   ├── test_strategy.py
│   │   ├── test_guard.py
│   │   ├── test_action.py
│   │   ├── test_state.py
│   │   ├── test_pseudo.py
│   │   ├── test_transition.py
│   │   ├── test_blackboard.py
│   │   └── test_machine.py
│   ├── plugin/
│   │   ├── __init__.py
│   │   ├── test_enums.py
│   │   ├── test_policy.py
│   │   ├── test_config.py
│   │   ├── test_skill.py
│   │   └── test_agent.py
│   ├── test_project.py
│   └── test_validation.py
pyproject.toml
```

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `daedalus/__init__.py`
- Create: `daedalus/model/__init__.py`
- Create: `daedalus/model/fsm/__init__.py`
- Create: `daedalus/model/plugin/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/model/__init__.py`
- Create: `tests/model/fsm/__init__.py`
- Create: `tests/model/plugin/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "daedalus"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package __init__.py files**

```bash
mkdir -p daedalus/model/fsm daedalus/model/plugin tests/model/fsm tests/model/plugin
touch daedalus/__init__.py daedalus/model/__init__.py daedalus/model/fsm/__init__.py daedalus/model/plugin/__init__.py
touch tests/__init__.py tests/model/__init__.py tests/model/fsm/__init__.py tests/model/plugin/__init__.py
```

- [ ] **Step 3: Install and verify**

Run: `pip install -e ".[dev]"`
Expected: 성공

- [ ] **Step 4: Verify pytest runs**

Run: `pytest --co -q`
Expected: "no tests ran" (테스트 파일 없으므로 정상)

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml daedalus/ tests/
git commit -m "chore: initialize Daedalus project structure"
```

---

### Task 2: FSM Event Hierarchy

**Files:**
- Create: `daedalus/model/fsm/event.py`
- Test: `tests/model/fsm/test_event.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_event.py
from __future__ import annotations

import pytest
from daedalus.model.fsm.event import (
    Event,
    StateEvent,
    TransitionEvent,
    CompositeStateEvent,
    BlackboardEvent,
    BlackboardTrigger,
)


def test_event_is_abstract():
    with pytest.raises(TypeError):
        Event(name="e")


def test_state_event_is_abstract():
    with pytest.raises(TypeError):
        StateEvent(name="e")


def test_transition_event_is_abstract():
    with pytest.raises(TypeError):
        TransitionEvent(name="e")


def test_composite_state_event_is_abstract():
    with pytest.raises(TypeError):
        CompositeStateEvent(name="e")


def test_blackboard_event_is_abstract():
    with pytest.raises(TypeError):
        BlackboardEvent(name="e")


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

Run: `pytest tests/model/fsm/test_event.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/event.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daedalus.model.fsm.strategy import EvaluationStrategy


@dataclass
class Event(ABC):
    name: str


@dataclass
class StateEvent(Event, ABC):
    """상태 관련 이벤트 베이스."""


@dataclass
class TransitionEvent(Event, ABC):
    """전이 관련 이벤트 베이스."""


@dataclass
class CompositeStateEvent(StateEvent, ABC):
    """CompositeState 전용 이벤트."""


@dataclass
class BlackboardEvent(Event, ABC):
    """블랙보드 변경 이벤트 베이스."""


@dataclass
class BlackboardTrigger(BlackboardEvent):
    """블랙보드 변수 변경 감지 트리거."""
    variable: str = ""
    condition: EvaluationStrategy | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_event.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/event.py tests/model/fsm/test_event.py
git commit -m "feat: add FSM Event hierarchy"
```

---

### Task 3: FSM Variable

**Files:**
- Create: `daedalus/model/fsm/variable.py`
- Test: `tests/model/fsm/test_variable.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_variable.py
from __future__ import annotations

from daedalus.model.fsm.variable import (
    Variable,
    VariableScope,
    VariableType,
    ConflictResolution,
)


def test_variable_scope_enum():
    assert VariableScope.LOCAL.value == "local"
    assert VariableScope.BLACKBOARD.value == "blackboard"


def test_variable_type_enum():
    assert VariableType.STRING.value == "string"
    assert VariableType.NUMBER.value == "number"
    assert VariableType.BOOL.value == "bool"
    assert VariableType.LIST.value == "list"
    assert VariableType.JSON.value == "json"
    assert VariableType.ANY.value == "any"


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
    assert var.var_type == VariableType.ANY
    assert var.required is False
    assert var.default is None
    assert var.conflict_resolution == ConflictResolution.LAST_WRITE


def test_variable_blackboard_scope():
    var = Variable(
        name="user",
        description="사용자 정보",
        scope=VariableScope.BLACKBOARD,
        var_type=VariableType.JSON,
        required=True,
    )
    assert var.scope == VariableScope.BLACKBOARD
    assert var.var_type == VariableType.JSON
    assert var.required is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_variable.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/variable.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VariableScope(Enum):
    LOCAL = "local"
    BLACKBOARD = "blackboard"


class VariableType(Enum):
    STRING = "string"
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
    var_type: VariableType = VariableType.ANY
    required: bool = False
    default: Any | None = None
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_variable.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/variable.py tests/model/fsm/test_variable.py
git commit -m "feat: add FSM Variable with scope and type enums"
```

---

### Task 4: FSM Strategies (Evaluation + Execution)

**Files:**
- Create: `daedalus/model/fsm/strategy.py`
- Test: `tests/model/fsm/test_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_strategy.py
from __future__ import annotations

import pytest
from daedalus.model.fsm.strategy import (
    EvaluationStrategy,
    LLMEvaluation,
    ToolEvaluation,
    MCPEvaluation,
    ExpressionEvaluation,
    CompositeEvaluation,
    ExecutionStrategy,
    LLMExecution,
    ToolExecution,
    MCPExecution,
    CompositeExecution,
)


# -- EvaluationStrategy --

def test_evaluation_strategy_is_abstract():
    with pytest.raises(TypeError):
        EvaluationStrategy()


def test_llm_evaluation():
    e = LLMEvaluation(prompt="빌드가 성공했는가?")
    assert e.prompt == "빌드가 성공했는가?"


def test_tool_evaluation():
    e = ToolEvaluation(tool="Bash", command="npm test", success_condition="exit_code == 0")
    assert e.tool == "Bash"
    assert e.command == "npm test"
    assert e.success_condition == "exit_code == 0"


def test_mcp_evaluation():
    e = MCPEvaluation(
        server="github",
        tool="get_pr_status",
        arguments={"pr": 123},
        success_condition="result == 'merged'",
    )
    assert e.server == "github"
    assert e.arguments == {"pr": 123}


def test_expression_evaluation():
    e = ExpressionEvaluation(expression="${bb.retry_count} < 3")
    assert e.expression == "${bb.retry_count} < 3"


def test_composite_evaluation():
    child1 = LLMEvaluation(prompt="코드 품질 충분?")
    child2 = ToolEvaluation(tool="Bash", command="npm test", success_condition="exit_code == 0")
    comp = CompositeEvaluation(operator="and", children=[child1, child2])
    assert comp.operator == "and"
    assert len(comp.children) == 2


# -- ExecutionStrategy --

def test_execution_strategy_is_abstract():
    with pytest.raises(TypeError):
        ExecutionStrategy()


def test_llm_execution():
    e = LLMExecution(prompt="코드를 리뷰해라")
    assert e.prompt == "코드를 리뷰해라"


def test_tool_execution():
    e = ToolExecution(tool="Bash", command="npm run build")
    assert e.tool == "Bash"
    assert e.command == "npm run build"


def test_mcp_execution():
    e = MCPExecution(server="slack", tool="send_message", arguments={"channel": "#dev"})
    assert e.server == "slack"


def test_composite_execution_sequential():
    c1 = ToolExecution(tool="Bash", command="npm test")
    c2 = ToolExecution(tool="Bash", command="npm run build")
    comp = CompositeExecution(mode="sequential", children=[c1, c2])
    assert comp.mode == "sequential"
    assert len(comp.children) == 2


def test_composite_execution_parallel():
    c1 = LLMExecution(prompt="분석1")
    c2 = LLMExecution(prompt="분석2")
    comp = CompositeExecution(mode="parallel", children=[c1, c2])
    assert comp.mode == "parallel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_strategy.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/strategy.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Literal


# ── 평가 전략 (Guard용) ──


@dataclass
class EvaluationStrategy(ABC):
    """전이 조건 평가 방식."""


@dataclass
class LLMEvaluation(EvaluationStrategy):
    """LLM 자연어 판단."""
    prompt: str = ""


@dataclass
class ToolEvaluation(EvaluationStrategy):
    """CLI 도구 실행 결과 판단."""
    tool: str = ""
    command: str = ""
    success_condition: str = ""


@dataclass
class MCPEvaluation(EvaluationStrategy):
    """MCP 도구 호출 결과 판단."""
    server: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    success_condition: str = ""


@dataclass
class ExpressionEvaluation(EvaluationStrategy):
    """BB 변수 기반 표현식 평가."""
    expression: str = ""


@dataclass
class CompositeEvaluation(EvaluationStrategy):
    """복합 조건 (AND/OR)."""
    operator: Literal["and", "or"] = "and"
    children: list[EvaluationStrategy] = field(default_factory=list)


# ── 실행 전략 (Action용) ──


@dataclass
class ExecutionStrategy(ABC):
    """액션 실행 방식."""


@dataclass
class LLMExecution(ExecutionStrategy):
    """LLM 프롬프트 실행."""
    prompt: str = ""


@dataclass
class ToolExecution(ExecutionStrategy):
    """CLI 도구 실행."""
    tool: str = ""
    command: str = ""


@dataclass
class MCPExecution(ExecutionStrategy):
    """MCP 도구 호출."""
    server: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompositeExecution(ExecutionStrategy):
    """순차/병렬 실행 조합."""
    mode: Literal["sequential", "parallel"] = "sequential"
    children: list[ExecutionStrategy] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_strategy.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/strategy.py tests/model/fsm/test_strategy.py
git commit -m "feat: add EvaluationStrategy and ExecutionStrategy hierarchies"
```

---

### Task 5: FSM Guard + Action

**Files:**
- Create: `daedalus/model/fsm/guard.py`
- Create: `daedalus/model/fsm/action.py`
- Test: `tests/model/fsm/test_guard.py`
- Test: `tests/model/fsm/test_action.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/fsm/test_guard.py
from __future__ import annotations

from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.strategy import ExpressionEvaluation, LLMEvaluation


def test_guard_with_expression():
    g = Guard(evaluation=ExpressionEvaluation(expression="${bb.count} > 0"))
    assert isinstance(g.evaluation, ExpressionEvaluation)


def test_guard_with_llm():
    g = Guard(evaluation=LLMEvaluation(prompt="준비 완료?"))
    assert g.evaluation.prompt == "준비 완료?"
```

```python
# tests/model/fsm/test_action.py
from __future__ import annotations

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution, ToolExecution
from daedalus.model.fsm.variable import Variable


def test_action_basic():
    a = Action(
        name="run_tests",
        execution=ToolExecution(tool="Bash", command="pytest"),
    )
    assert a.name == "run_tests"
    assert a.output_variable is None


def test_action_with_output():
    var = Variable(name="result", description="테스트 결과")
    a = Action(
        name="analyze",
        execution=LLMExecution(prompt="코드 분석"),
        output_variable=var,
    )
    assert a.output_variable is var
    assert a.output_variable.name == "result"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/fsm/test_guard.py tests/model/fsm/test_action.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementations**

```python
# daedalus/model/fsm/guard.py
from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.strategy import EvaluationStrategy


@dataclass
class Guard:
    evaluation: EvaluationStrategy
```

```python
# daedalus/model/fsm/action.py
from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.strategy import ExecutionStrategy
from daedalus.model.fsm.variable import Variable


@dataclass
class Action:
    name: str
    execution: ExecutionStrategy
    output_variable: Variable | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/fsm/test_guard.py tests/model/fsm/test_action.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/guard.py daedalus/model/fsm/action.py tests/model/fsm/test_guard.py tests/model/fsm/test_action.py
git commit -m "feat: add Guard and Action classes"
```

---

### Task 6: FSM State Hierarchy

**Files:**
- Create: `daedalus/model/fsm/state.py`
- Test: `tests/model/fsm/test_state.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_state.py
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
    child1 = SimpleState(name="s1")
    child2 = SimpleState(name="s2")
    cs = CompositeState(
        name="agent_x",
        children=[child1, child2],
        initial_state=child1,
        final_states=[child2],
    )
    assert cs.name == "agent_x"
    assert len(cs.children) == 2
    assert cs.initial_state is child1
    assert cs.final_states == [child2]
    assert cs.on_child_enter == []
    assert cs.on_child_exit == []


def test_region():
    s1 = SimpleState(name="r1_s1")
    r = Region(name="region_1", states=[s1], initial_state=s1)
    assert r.name == "region_1"
    assert r.initial_state is s1


def test_parallel_state():
    s1 = SimpleState(name="a")
    s2 = SimpleState(name="b")
    r1 = Region(name="r1", states=[s1], initial_state=s1)
    r2 = Region(name="r2", states=[s2], initial_state=s2)
    ps = ParallelState(name="parallel", regions=[r1, r2])
    assert len(ps.regions) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/state.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.variable import Variable


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


@dataclass
class SimpleState(State):
    """리프 상태. 하위 상태 없음."""


@dataclass
class Region:
    """ParallelState 내 독립 실행 단위."""
    name: str
    states: list[State] = field(default_factory=list)
    initial_state: State | None = None


@dataclass
class CompositeState(State):
    """계층형. 내부에 하위 FSM 보유."""
    children: list[State] = field(default_factory=list)
    initial_state: State | None = None
    final_states: list[State] = field(default_factory=list)
    on_child_enter: list[Action] = field(default_factory=list)
    on_child_exit: list[Action] = field(default_factory=list)


@dataclass
class ParallelState(State):
    """병렬 리전. 동시 실행."""
    regions: list[Region] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_state.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/state.py tests/model/fsm/test_state.py
git commit -m "feat: add State hierarchy (Simple, Composite, Parallel)"
```

---

### Task 7: FSM Pseudo-states

**Files:**
- Create: `daedalus/model/fsm/pseudo.py`
- Test: `tests/model/fsm/test_pseudo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_pseudo.py
from __future__ import annotations

from daedalus.model.fsm.pseudo import (
    HistoryState,
    ChoiceState,
    TerminateState,
    EntryPoint,
    ExitPoint,
)


def test_history_state_shallow():
    h = HistoryState(name="H", mode="shallow")
    assert h.mode == "shallow"


def test_history_state_deep():
    h = HistoryState(name="H*", mode="deep")
    assert h.mode == "deep"


def test_choice_state():
    c = ChoiceState(name="check_status")
    assert c.name == "check_status"


def test_terminate_state():
    t = TerminateState(name="abort")
    assert t.name == "abort"


def test_entry_point():
    ep = EntryPoint(name="alt_entry")
    assert ep.name == "alt_entry"


def test_exit_point():
    xp = ExitPoint(name="error_exit")
    assert xp.name == "error_exit"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_pseudo.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/pseudo.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from daedalus.model.fsm.state import State


@dataclass
class HistoryState(State):
    """재진입 시 마지막 위치에서 재개."""
    mode: Literal["shallow", "deep"] = "shallow"


@dataclass
class ChoiceState(State):
    """즉시 평가 후 분기. 머무르지 않음."""


@dataclass
class TerminateState(State):
    """FSM 강제 종료."""


@dataclass
class EntryPoint(State):
    """CompositeState의 특정 하위 상태로 직접 진입."""


@dataclass
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_pseudo.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/pseudo.py tests/model/fsm/test_pseudo.py
git commit -m "feat: add pseudo-states (History, Choice, Terminate, Entry/ExitPoint)"
```

---

### Task 8: FSM Transition

**Files:**
- Create: `daedalus/model/fsm/transition.py`
- Test: `tests/model/fsm/test_transition.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_transition.py
from __future__ import annotations

from daedalus.model.fsm.transition import Transition, TransitionType
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import ExpressionEvaluation, ToolExecution
from daedalus.model.fsm.event import BlackboardTrigger


def test_transition_type_enum():
    assert TransitionType.EXTERNAL.value == "external"
    assert TransitionType.INTERNAL.value == "internal"
    assert TransitionType.SELF.value == "self"
    assert TransitionType.LOCAL.value == "local"


def test_transition_basic():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    t = Transition(source=s1, target=s2)
    assert t.source is s1
    assert t.target is s2
    assert t.type == TransitionType.EXTERNAL
    assert t.trigger is None
    assert t.guard is None
    assert t.data_map == {}


def test_transition_with_guard():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    guard = Guard(evaluation=ExpressionEvaluation(expression="${bb.ready}"))
    t = Transition(source=s1, target=s2, guard=guard)
    assert t.guard is guard


def test_transition_with_trigger():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    trigger = BlackboardTrigger(name="status_change", variable="status")
    t = Transition(source=s1, target=s2, trigger=trigger)
    assert t.trigger is trigger


def test_transition_with_data_map():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    t = Transition(
        source=s1,
        target=s2,
        data_map={"result": "input_data", "status": "priority"},
    )
    assert t.data_map["result"] == "input_data"
    assert len(t.data_map) == 2


def test_transition_with_traverse_actions():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    action = Action(name="log", execution=ToolExecution(tool="Bash", command="echo transition"))
    t = Transition(
        source=s1,
        target=s2,
        on_traverse=[action],
    )
    assert len(t.on_traverse) == 1


def test_transition_self_type():
    s1 = SimpleState(name="A")
    t = Transition(source=s1, target=s1, type=TransitionType.SELF)
    assert t.type == TransitionType.SELF
    assert t.source is t.target
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_transition.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/transition.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.event import Event
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.state import State


class TransitionType(Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    SELF = "self"
    LOCAL = "local"


@dataclass
class Transition:
    source: State
    target: State
    type: TransitionType = TransitionType.EXTERNAL
    trigger: Event | None = None
    guard: Guard | None = None
    # 이벤트
    on_guard_check: list[Action] = field(default_factory=list)
    on_traverse_start: list[Action] = field(default_factory=list)
    on_traverse: list[Action] = field(default_factory=list)
    on_traverse_end: list[Action] = field(default_factory=list)
    custom_events: dict[str, list[Action]] = field(default_factory=dict)
    # 데이터
    data_map: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_transition.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/transition.py tests/model/fsm/test_transition.py
git commit -m "feat: add Transition with type, guard, trigger, data_map"
```

---

### Task 9: FSM Blackboard + DynamicClass

**Files:**
- Create: `daedalus/model/fsm/blackboard.py`
- Test: `tests/model/fsm/test_blackboard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_blackboard.py
from __future__ import annotations

from daedalus.model.fsm.blackboard import (
    Blackboard,
    DynamicClass,
    DynamicField,
    DynamicFieldType,
    CollectionType,
)
from daedalus.model.fsm.variable import Variable, VariableScope


def test_dynamic_field_type_enum():
    assert DynamicFieldType.STRING.value == "string"
    assert DynamicFieldType.INT.value == "int"
    assert DynamicFieldType.FLOAT.value == "float"
    assert DynamicFieldType.BOOL.value == "bool"


def test_collection_type_enum():
    assert CollectionType.NONE.value == "none"
    assert CollectionType.LIST.value == "list"
    assert CollectionType.SET.value == "set"


def test_dynamic_field():
    f = DynamicField(name="status", field_type=DynamicFieldType.STRING)
    assert f.name == "status"
    assert f.collection == CollectionType.NONE
    assert f.required is False
    assert f.default is None


def test_dynamic_class():
    fields = [
        DynamicField(name="status", field_type=DynamicFieldType.STRING, required=True),
        DynamicField(name="errors", field_type=DynamicFieldType.STRING, collection=CollectionType.LIST),
        DynamicField(name="count", field_type=DynamicFieldType.INT, default=0),
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
        fields=[DynamicField(name="timestamp", field_type=DynamicFieldType.STRING)],
    )
    bb = Blackboard(class_definitions=[dc])
    assert len(bb.class_definitions) == 1
    assert bb.class_definitions[0].name == "DeployLog"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_blackboard.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/blackboard.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from daedalus.model.fsm.variable import Variable


class DynamicFieldType(Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"


class CollectionType(Enum):
    NONE = "none"
    LIST = "list"
    SET = "set"


@dataclass
class DynamicField:
    name: str
    field_type: DynamicFieldType
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_blackboard.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/fsm/blackboard.py tests/model/fsm/test_blackboard.py
git commit -m "feat: add Blackboard with DynamicClass and scoping"
```

---

### Task 10: FSM StateMachine

**Files:**
- Create: `daedalus/model/fsm/machine.py`
- Test: `tests/model/fsm/test_machine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/fsm/test_machine.py
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.blackboard import Blackboard


def test_state_machine_basic():
    s1 = SimpleState(name="start")
    s2 = SimpleState(name="end")
    t = Transition(source=s1, target=s2)
    bb = Blackboard()
    sm = StateMachine(
        name="workflow",
        states=[s1, s2],
        transitions=[t],
        initial_state=s1,
        final_states=[s2],
        blackboard=bb,
    )
    assert sm.name == "workflow"
    assert len(sm.states) == 2
    assert len(sm.transitions) == 1
    assert sm.initial_state is s1
    assert sm.final_states == [s2]
    assert sm.blackboard is bb


def test_state_machine_defaults():
    s1 = SimpleState(name="only")
    sm = StateMachine(name="minimal", initial_state=s1)
    assert sm.states == []
    assert sm.transitions == []
    assert sm.final_states == []
    assert sm.blackboard is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/fsm/test_machine.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/fsm/machine.py
from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.blackboard import Blackboard
from daedalus.model.fsm.state import State
from daedalus.model.fsm.transition import Transition


@dataclass
class StateMachine:
    name: str
    initial_state: State
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    final_states: list[State] = field(default_factory=list)
    blackboard: Blackboard = field(default_factory=Blackboard)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/fsm/test_machine.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update fsm/__init__.py with public API**

```python
# daedalus/model/fsm/__init__.py
from daedalus.model.fsm.event import *
from daedalus.model.fsm.variable import *
from daedalus.model.fsm.strategy import *
from daedalus.model.fsm.guard import *
from daedalus.model.fsm.action import *
from daedalus.model.fsm.state import *
from daedalus.model.fsm.pseudo import *
from daedalus.model.fsm.transition import *
from daedalus.model.fsm.blackboard import *
from daedalus.model.fsm.machine import *
```

- [ ] **Step 6: Run all FSM tests**

Run: `pytest tests/model/fsm/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add daedalus/model/fsm/machine.py daedalus/model/fsm/__init__.py tests/model/fsm/test_machine.py
git commit -m "feat: add StateMachine, complete FSM core layer"
```

---

### Task 11: Plugin Enums + ExecutionPolicy

**Files:**
- Create: `daedalus/model/plugin/enums.py`
- Create: `daedalus/model/plugin/policy.py`
- Test: `tests/model/plugin/test_enums.py`
- Test: `tests/model/plugin/test_policy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/plugin/test_enums.py
from __future__ import annotations

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


def test_model_type():
    assert ModelType.SONNET.value == "sonnet"
    assert ModelType.OPUS.value == "opus"
    assert ModelType.HAIKU.value == "haiku"
    assert ModelType.INHERIT.value == "inherit"


def test_effort_level():
    assert EffortLevel.LOW.value == "low"
    assert EffortLevel.MAX.value == "max"


def test_skill_context():
    assert SkillContext.INLINE.value == "inline"
    assert SkillContext.FORK.value == "fork"


def test_skill_shell():
    assert SkillShell.BASH.value == "bash"
    assert SkillShell.POWERSHELL.value == "powershell"


def test_permission_mode():
    assert PermissionMode.DEFAULT.value == "default"
    assert PermissionMode.BYPASS.value == "bypassPermissions"
    assert PermissionMode.ACCEPT_EDITS.value == "acceptEdits"
    assert PermissionMode.DONT_ASK.value == "dontAsk"


def test_memory_scope():
    assert MemoryScope.USER.value == "user"
    assert MemoryScope.PROJECT.value == "project"
    assert MemoryScope.LOCAL.value == "local"


def test_agent_isolation():
    assert AgentIsolation.NONE.value == "none"
    assert AgentIsolation.WORKTREE.value == "worktree"


def test_agent_color_all_values():
    expected = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
    actual = {c.value for c in AgentColor}
    assert actual == expected
```

```python
# tests/model/plugin/test_policy.py
from __future__ import annotations

from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy


def test_join_strategy():
    assert JoinStrategy.ALL.value == "all"
    assert JoinStrategy.ANY.value == "any"
    assert JoinStrategy.N_OF.value == "n_of"


def test_execution_policy_defaults():
    p = ExecutionPolicy()
    assert p.mode == "fixed"
    assert p.count == 1
    assert p.join == JoinStrategy.ALL
    assert p.join_count is None


def test_execution_policy_parallel():
    p = ExecutionPolicy(mode="fixed", count=3, join=JoinStrategy.N_OF, join_count=2)
    assert p.count == 3
    assert p.join == JoinStrategy.N_OF
    assert p.join_count == 2


def test_execution_policy_dynamic():
    p = ExecutionPolicy(mode="dynamic")
    assert p.mode == "dynamic"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/plugin/ -v`
Expected: FAIL

- [ ] **Step 3: Write implementations**

```python
# daedalus/model/plugin/enums.py
from __future__ import annotations

from enum import Enum


class ModelType(Enum):
    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"
    INHERIT = "inherit"


class EffortLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class SkillContext(Enum):
    INLINE = "inline"
    FORK = "fork"


class SkillShell(Enum):
    BASH = "bash"
    POWERSHELL = "powershell"


class PermissionMode(Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"
    PLAN = "plan"


class MemoryScope(Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class AgentIsolation(Enum):
    NONE = "none"
    WORKTREE = "worktree"


class AgentColor(Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"
    PURPLE = "purple"
    ORANGE = "orange"
    PINK = "pink"
    CYAN = "cyan"
```

```python
# daedalus/model/plugin/policy.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class JoinStrategy(Enum):
    ALL = "all"
    ANY = "any"
    N_OF = "n_of"


@dataclass
class ExecutionPolicy:
    mode: Literal["fixed", "dynamic"] = "fixed"
    count: int = 1
    join: JoinStrategy = JoinStrategy.ALL
    join_count: int | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/plugin/ -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/plugin/enums.py daedalus/model/plugin/policy.py tests/model/plugin/test_enums.py tests/model/plugin/test_policy.py
git commit -m "feat: add plugin enums and ExecutionPolicy"
```

---

### Task 12: Plugin Config Classes

**Files:**
- Create: `daedalus/model/plugin/config.py`
- Test: `tests/model/plugin/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/plugin/test_config.py
from __future__ import annotations

import pytest
from daedalus.model.plugin.config import (
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


def test_skill_config_is_abstract():
    with pytest.raises(TypeError):
        SkillConfig()


def test_procedural_skill_config_defaults():
    c = ProceduralSkillConfig()
    assert c.argument_hint is None
    assert c.allowed_tools == []
    assert c.model == ModelType.INHERIT
    assert c.effort is None
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
    assert c.tools is None
    assert c.disallowed_tools is None
    assert c.model == ModelType.INHERIT
    assert c.permission_mode == PermissionMode.DEFAULT
    assert c.max_turns is None
    assert c.skills == []
    assert c.mcp_servers is None
    assert c.hooks is None
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/plugin/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/plugin/config.py
from __future__ import annotations

from abc import ABC
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
class SkillConfig(ABC):
    """스킬 공통 프론트매터."""
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    model: ModelType | str = ModelType.INHERIT
    effort: EffortLevel | None = None
    hooks: dict[str, Any] | None = None
    paths: list[str] | None = None


@dataclass
class ProceduralSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: SkillContext = SkillContext.INLINE
    agent: str | None = None
    shell: SkillShell = SkillShell.BASH


@dataclass
class DeclarativeSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True


@dataclass
class AgentConfig:
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    model: ModelType | str = ModelType.INHERIT
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] | None = None
    hooks: dict[str, Any] | None = None
    memory: MemoryScope | None = None
    background: bool = False
    effort: EffortLevel | None = None
    isolation: AgentIsolation = AgentIsolation.NONE
    color: AgentColor | None = None
    initial_prompt: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/plugin/test_config.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/plugin/config.py tests/model/plugin/test_config.py
git commit -m "feat: add plugin Config classes (Skill, Agent)"
```

---

### Task 13: Plugin Base + Skill + Agent

**Files:**
- Create: `daedalus/model/plugin/base.py`
- Create: `daedalus/model/plugin/skill.py`
- Create: `daedalus/model/plugin/agent.py`
- Test: `tests/model/plugin/test_skill.py`
- Test: `tests/model/plugin/test_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/model/plugin/test_skill.py
from __future__ import annotations

import pytest
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.skill import Skill, ProceduralSkill, DeclarativeSkill
from daedalus.model.plugin.config import ProceduralSkillConfig, DeclarativeSkillConfig
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def test_plugin_component_is_abstract():
    with pytest.raises(TypeError):
        PluginComponent(name="x", description="y")


def test_skill_is_abstract():
    with pytest.raises(TypeError):
        Skill(name="x", description="y")


def test_procedural_skill():
    s1 = SimpleState(name="start")
    sm = StateMachine(name="flow", initial_state=s1, states=[s1])
    skill = ProceduralSkill(
        name="deploy",
        description="배포 스킬",
        fsm=sm,
        config=ProceduralSkillConfig(),
    )
    assert skill.name == "deploy"
    assert skill.fsm is sm
    assert skill.fsm.blackboard is not None
    assert isinstance(skill, Skill)
    assert isinstance(skill, WorkflowComponent)
    assert isinstance(skill, PluginComponent)


def test_procedural_skill_mro():
    mro_names = [c.__name__ for c in ProceduralSkill.__mro__]
    assert mro_names.index("Skill") < mro_names.index("PluginComponent")
    assert "WorkflowComponent" in mro_names


def test_declarative_skill():
    skill = DeclarativeSkill(
        name="api-conventions",
        description="API 컨벤션",
        content="RESTful 패턴을 사용하라.",
        config=DeclarativeSkillConfig(),
    )
    assert skill.name == "api-conventions"
    assert skill.content == "RESTful 패턴을 사용하라."
    assert isinstance(skill, Skill)
    assert not isinstance(skill, WorkflowComponent)
```

```python
# tests/model/plugin/test_agent.py
from __future__ import annotations

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import ModelType, AgentColor
from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def test_agent_definition():
    s1 = SimpleState(name="analyze")
    s2 = SimpleState(name="report")
    sm = StateMachine(name="review_flow", initial_state=s1, states=[s1, s2])
    agent = AgentDefinition(
        name="code-reviewer",
        description="코드 리뷰 에이전트",
        fsm=sm,
        config=AgentConfig(
            tools=["Read", "Grep"],
            model=ModelType.SONNET,
            color=AgentColor.BLUE,
        ),
    )
    assert agent.name == "code-reviewer"
    assert agent.fsm is sm
    assert agent.config.tools == ["Read", "Grep"]
    assert isinstance(agent, PluginComponent)
    assert isinstance(agent, WorkflowComponent)


def test_agent_execution_policy_default():
    s1 = SimpleState(name="s")
    sm = StateMachine(name="f", initial_state=s1)
    agent = AgentDefinition(
        name="worker",
        description="작업자",
        fsm=sm,
        config=AgentConfig(),
    )
    assert agent.execution_policy.mode == "fixed"
    assert agent.execution_policy.count == 1


def test_agent_execution_policy_parallel():
    s1 = SimpleState(name="s")
    sm = StateMachine(name="f", initial_state=s1)
    agent = AgentDefinition(
        name="researcher",
        description="연구 에이전트",
        fsm=sm,
        config=AgentConfig(),
        execution_policy=ExecutionPolicy(
            mode="fixed",
            count=3,
            join=JoinStrategy.ANY,
        ),
    )
    assert agent.execution_policy.count == 3
    assert agent.execution_policy.join == JoinStrategy.ANY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/model/plugin/test_skill.py tests/model/plugin/test_agent.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementations**

```python
# daedalus/model/plugin/base.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass

from daedalus.model.fsm.machine import StateMachine


@dataclass
class PluginComponent(ABC):
    """플러그인 구성 요소 공통."""
    name: str
    description: str


@dataclass
class WorkflowComponent(ABC):
    """FSM 보유 믹스인."""
    fsm: StateMachine
```

```python
# daedalus/model/plugin/skill.py
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import DeclarativeSkillConfig, ProceduralSkillConfig


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM."""
    fsm: StateMachine = field(default=None)
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only."""
    content: str = ""
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)
```

```python
# daedalus/model/plugin/agent.py
from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM."""
    fsm: StateMachine = field(default=None)
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/model/plugin/test_skill.py tests/model/plugin/test_agent.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/plugin/base.py daedalus/model/plugin/skill.py daedalus/model/plugin/agent.py tests/model/plugin/test_skill.py tests/model/plugin/test_agent.py
git commit -m "feat: add Skill hierarchy and AgentDefinition with multiple inheritance"
```

---

### Task 14: PluginProject

**Files:**
- Create: `daedalus/model/project.py`
- Test: `tests/model/test_project.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/test_project.py
from __future__ import annotations

from daedalus.model.project import PluginProject
from daedalus.model.plugin.skill import ProceduralSkill, DeclarativeSkill
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig, DeclarativeSkillConfig, AgentConfig
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState


def test_plugin_project_empty():
    proj = PluginProject(name="my-plugin")
    assert proj.name == "my-plugin"
    assert proj.skills == []
    assert proj.agents == []


def test_plugin_project_with_components():
    s1 = SimpleState(name="s1")
    sm = StateMachine(name="flow", initial_state=s1, states=[s1])

    proc_skill = ProceduralSkill(
        name="deploy",
        description="배포",
        fsm=sm,
        config=ProceduralSkillConfig(),
    )
    decl_skill = DeclarativeSkill(
        name="conventions",
        description="컨벤션",
        content="...",
        config=DeclarativeSkillConfig(),
    )
    agent = AgentDefinition(
        name="reviewer",
        description="리뷰어",
        fsm=sm,
        config=AgentConfig(),
    )

    proj = PluginProject(
        name="my-plugin",
        skills=[proc_skill, decl_skill],
        agents=[agent],
    )
    assert len(proj.skills) == 2
    assert len(proj.agents) == 1
    assert isinstance(proj.skills[0], ProceduralSkill)
    assert isinstance(proj.skills[1], DeclarativeSkill)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/test_project.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/project.py
from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import Skill


@dataclass
class PluginProject:
    name: str
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/test_project.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add daedalus/model/project.py tests/model/test_project.py
git commit -m "feat: add PluginProject root container"
```

---

### Task 15: Validation Rules

**Files:**
- Create: `daedalus/model/validation.py`
- Test: `tests/model/test_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/model/test_validation.py
from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable, VariableScope, VariableType


def _make_sm(states, transitions):
    return StateMachine(
        name="test",
        states=states,
        transitions=transitions,
        initial_state=states[0],
    )


def test_no_agent_inside_agent():
    """CompositeState 내부에 CompositeState 불가."""
    inner_agent = CompositeState(name="inner_agent", children=[SimpleState(name="x")])
    outer_agent = CompositeState(
        name="outer_agent",
        children=[inner_agent],
        initial_state=inner_agent,
    )
    sm = _make_sm([outer_agent], [])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_nested_agent" for e in errors)


def test_no_agent_to_agent_direct():
    """Agent→Agent 직접 엣지 불가."""
    a1 = CompositeState(name="agent1", children=[SimpleState(name="x")])
    a2 = CompositeState(name="agent2", children=[SimpleState(name="y")])
    t = Transition(source=a1, target=a2)
    sm = _make_sm([a1, a2], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "no_agent_to_agent" for e in errors)


def test_valid_skill_to_agent():
    """Skill→Agent 엣지는 허용."""
    skill = SimpleState(name="skill_a")
    agent = CompositeState(name="agent_x", children=[SimpleState(name="s1")])
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

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/model/test_validation.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# daedalus/model/validation.py
from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import CompositeState, State
from daedalus.model.fsm.transition import Transition


@dataclass
class ValidationError:
    rule: str
    message: str
    source: str = ""


class Validator:
    @staticmethod
    def validate(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        errors.extend(Validator._check_nested_agents(sm.states))
        errors.extend(Validator._check_agent_to_agent(sm.transitions))
        errors.extend(Validator._check_required_inputs(sm.transitions))
        return errors

    @staticmethod
    def _check_nested_agents(states: list[State]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for state in states:
            if isinstance(state, CompositeState):
                for child in state.children:
                    if isinstance(child, CompositeState):
                        errors.append(
                            ValidationError(
                                rule="no_nested_agent",
                                message=f"CompositeState '{state.name}' 내부에 "
                                        f"CompositeState '{child.name}'이 존재합니다.",
                                source=state.name,
                            )
                        )
        return errors

    @staticmethod
    def _check_agent_to_agent(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            if isinstance(t.source, CompositeState) and isinstance(t.target, CompositeState):
                errors.append(
                    ValidationError(
                        rule="no_agent_to_agent",
                        message=f"Agent '{t.source.name}' → Agent '{t.target.name}' "
                                f"직접 전이 불가. Skill을 경유해야 합니다.",
                        source=f"{t.source.name}->{t.target.name}",
                    )
                )
        return errors

    @staticmethod
    def _check_required_inputs(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            target_required = [v for v in t.target.inputs if v.required]
            mapped_targets = set(t.data_map.values())
            for var in target_required:
                if var.name not in mapped_targets:
                    bb_var = var.scope.value == "blackboard"
                    if not bb_var:
                        errors.append(
                            ValidationError(
                                rule="missing_required_input",
                                message=f"전이 '{t.source.name}' → '{t.target.name}': "
                                        f"필수 input '{var.name}'이 data_map에 없습니다.",
                                source=f"{t.source.name}->{t.target.name}",
                            )
                        )
        return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/model/test_validation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Update model/__init__.py and plugin/__init__.py**

```python
# daedalus/model/plugin/__init__.py
from daedalus.model.plugin.enums import *
from daedalus.model.plugin.policy import *
from daedalus.model.plugin.config import *
from daedalus.model.plugin.base import *
from daedalus.model.plugin.skill import *
from daedalus.model.plugin.agent import *
```

```python
# daedalus/model/__init__.py
from daedalus.model.fsm import *
from daedalus.model.plugin import *
from daedalus.model.project import *
from daedalus.model.validation import *
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add daedalus/model/validation.py daedalus/model/__init__.py daedalus/model/plugin/__init__.py tests/model/test_validation.py
git commit -m "feat: add validation rules, complete model layer"
```
