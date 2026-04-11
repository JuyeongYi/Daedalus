# Daedalus Model Layer Reinforcement Design

## 목표

평가에서 발견된 이슈를 해결하고, 미흡/보통 판정 영역을 양호 수준으로 보강한다.

## 변경 범위

1. CompositeState + Region 구조 변경 (sub_machine 포함)
2. 이벤트 계층 구체화 (CompletionEvent 추가, 빈 추상 클래스 제거)
3. 타입 통합 (FieldType) 및 Config 공통화 (ComponentConfig)
4. Validator 보강 (재귀 순회 + 신규 규칙 4개)

---

## 1. CompositeState + Region 구조 변경

### 1-1. CompositeState

**변경 전:**
```python
@dataclass
class CompositeState(State):
    children: list[State] = field(default_factory=list)
    initial_state: State | None = None
    final_states: list[State] = field(default_factory=list)
    on_child_enter: list[Action] = field(default_factory=list)
    on_child_exit: list[Action] = field(default_factory=list)
```

**변경 후:**
```python
@dataclass
class CompositeState(State):
    sub_machine: StateMachine
```

- `children` → `sub_machine.states`
- `initial_state` → `sub_machine.initial_state`
- `final_states` → `sub_machine.final_states`
- `on_child_enter`/`on_child_exit` → sub_machine 내부 상태의 `on_entry`/`on_exit`
- 5개 필드 제거, 1개 필드 추가

**설계 근거:**
- CompositeState = "별도 컨텍스트에서의 상태 기계" (에이전트 개념)
- 내부에 완전한 FSM(상태 + 전이 + 블랙보드)이 필요하므로 StateMachine 포함이 자연스러움
- UML 스테이트차트의 composite state 원래 정의와 일치

### 1-2. Region

**변경 전:**
```python
@dataclass
class Region:
    name: str
    states: list[State] = field(default_factory=list)
    initial_state: State | None = None
```

**변경 후:**
```python
@dataclass
class Region:
    name: str
    sub_machine: StateMachine
```

- Region 클래스 유지 (StateMachine으로 대체하지 않음)
- Region은 "병렬 실행 블록 내의 독립적인 하나의 작업 트랙"이라는 고유 개념
- 향후 리전별 우선순위, 취소 정책, 동기화 포인트 등 확장 가능

### 1-3. StateMachine 계층

StateMachine 베이스 클래스 계층은 불필요. 구조적 차이가 아닌 설정값(`blackboard.parent`) 차이이므로 단일 클래스 유지.

StateMachine = 상태 + 상태전이 + 블랙보드를 포함하는 자기완결적 작업 공간.

### 1-4. Blackboard 스코핑

- 최상위 StateMachine: `Blackboard(parent=None)` — 루트
- CompositeState.sub_machine: `Blackboard(parent=부모_machine.blackboard)` — 스코프 체인
- Region.sub_machine: `Blackboard(parent=부모_machine.blackboard)` — 스코프 체인

블랙보드 = 서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치.
동일 컨텍스트 내에서는 블랙보드가 불필요 — 이미 같은 맥락을 공유.

---

## 2. 이벤트 계층 보강

### 2-1. 변경 전/후

**변경 전:**
```
Event(ABC)
├── StateEvent(ABC)              ← 구체 클래스 0개
├── TransitionEvent(ABC)         ← 구체 클래스 0개
├── CompositeStateEvent(ABC)     ← 구체 클래스 0개
├── BlackboardEvent(ABC)
│   └── BlackboardTrigger
```

**변경 후:**
```
Event(ABC)
├── StateEvent(ABC)
│   └── CompletionEvent          ← 신규
├── BlackboardEvent(ABC)
│   └── BlackboardTrigger        ← 유지
```

### 2-2. CompletionEvent

```python
@dataclass
class CompletionEvent(StateEvent):
    """상태 완료 시 발생하는 이벤트."""

    @property
    def kind(self) -> str:
        return "completion"
```

세 가지 완료를 통합적으로 표현:
- SimpleState 작업 완료 → 부모 FSM에 완료 신호
- CompositeState sub_machine이 final_state 도달 → 부모 FSM에 완료 신호
- ParallelState 전 Region 완료 → 부모 FSM에 완료 신호

Transition에서 `trigger: CompletionEvent`를 설정하면 해당 상태 완료 시 자동 전이.

### 2-3. 제거 대상

- `TransitionEvent(ABC)` — 구체 하위 클래스 없음, 전이 관련 로직은 Transition의 액션 훅이 담당
- `CompositeStateEvent(ABC)` — CompositeState 완료는 CompletionEvent로 통합

---

## 3. 타입 통합 및 Config 공통화

### 3-1. FieldType 통합

**변경 전:**
```python
class DynamicFieldType(Enum):    # blackboard.py
    STRING, INT, FLOAT, BOOL

class VariableType(Enum):        # variable.py
    STRING, NUMBER, BOOL, LIST, JSON, ANY
```

**변경 후:**
```python
class FieldType(Enum):           # variable.py로 통합
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    NUMBER = "number"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"
```

- `Variable.var_type: VariableType` → `Variable.field_type: FieldType`
- `DynamicField.field_type: DynamicFieldType` → `DynamicField.field_type: FieldType`
- `DynamicFieldType`, `VariableType` 삭제
- UI에서 DynamicField 편집 시 선택 가능한 타입 제한은 UI 레벨 책임

### 3-2. ComponentConfig 베이스 추출

**변경 전:**
```
SkillConfig(ABC)
├── ProceduralSkillConfig
└── DeclarativeSkillConfig
AgentConfig                      ← 별도, 공통 베이스 없음
```

**변경 후:**
```
ComponentConfig(ABC)
├── SkillConfig(ABC)
│   ├── ProceduralSkillConfig
│   └── DeclarativeSkillConfig
└── AgentConfig
```

```python
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
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    paths: list[str] | None = None

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

---

## 4. Validator 보강

### 4-1. 재귀 순회 구조

```python
class Validator:
    @staticmethod
    def validate(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        errors.extend(Validator._validate_machine(sm))
        return errors

    @staticmethod
    def _validate_machine(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        # 현재 machine 레벨 검증
        errors.extend(Validator._check_initial_in_states(sm))
        errors.extend(Validator._check_final_in_states(sm))
        errors.extend(Validator._check_nested_agents(sm.states))
        errors.extend(Validator._check_agent_to_agent(sm.transitions))
        errors.extend(Validator._check_required_inputs(sm.transitions))
        errors.extend(Validator._check_pseudo_state_hooks(sm.states))
        errors.extend(Validator._check_completion_events(sm))
        # 재귀: sub_machine, Region 내부
        for state in sm.states:
            if isinstance(state, CompositeState):
                errors.extend(Validator._validate_machine(state.sub_machine))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    errors.extend(Validator._validate_machine(region.sub_machine))
        return errors
```

### 4-2. 검증 규칙 목록

**기존 (재귀 적용):**

| 규칙 | 설명 | 재귀 |
|------|------|------|
| `no_nested_agent` | CompositeState 내부에 CompositeState 불가 | O |
| `no_agent_to_agent` | Agent→Agent 직접 전이 불가 | O |
| `missing_required_input` | LOCAL scope 필수 input이 data_map에 없으면 경고 | O |

**신규:**

| 규칙 | 설명 | 재귀 |
|------|------|------|
| `initial_state_in_states` | `sm.initial_state ∈ sm.states` 검증 | O |
| `final_states_in_states` | `sm.final_states ⊆ sm.states` 검증 | O |
| `pseudo_state_hooks` | ChoiceState, TerminateState, EntryPoint, ExitPoint에 lifecycle 훅 설정 시 경고. HistoryState 제외 | O |
| `completion_event_on_composite` | CompositeState/ParallelState에서 나가는 전이에 CompletionEvent trigger 없으면 경고 | O |

---

## 5. 변경 영향 요약

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `model/fsm/event.py` | CompletionEvent 추가, TransitionEvent·CompositeStateEvent 제거 |
| `model/fsm/variable.py` | VariableType → FieldType 교체, Variable.var_type → field_type |
| `model/fsm/state.py` | CompositeState: children 등 5필드 → sub_machine, Region: sub_machine 추가 |
| `model/fsm/blackboard.py` | DynamicFieldType 제거, DynamicField.field_type → FieldType 사용 |
| `model/plugin/config.py` | ComponentConfig 추출, SkillConfig·AgentConfig 상속 구조 변경 |
| `model/validation.py` | 재귀 구조 + 신규 4개 규칙 |
| 테스트 전체 | 위 변경에 맞춰 수정 |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `model/fsm/strategy.py` | 영향 없음 |
| `model/fsm/guard.py` | 영향 없음 |
| `model/fsm/action.py` | 영향 없음 |
| `model/fsm/pseudo.py` | 구조 변경 없음 (Validator가 경고) |
| `model/fsm/transition.py` | 영향 없음 |
| `model/fsm/machine.py` | 영향 없음 |
| `model/plugin/enums.py` | 영향 없음 |
| `model/plugin/policy.py` | 영향 없음 |
| `model/plugin/base.py` | 영향 없음 |
| `model/plugin/skill.py` | 영향 없음 |
| `model/plugin/agent.py` | 영향 없음 |
| `model/project.py` | 영향 없음 |

### 스킬/에이전트 개념 정리

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| AgentDefinition | 별도 컨텍스트의 상태 기계 | 자체 FSM + 별도 블랙보드 |

"동일 컨텍스트 내 상태"는 별도 스킬 유스케이스가 아니라, FSM 안의 일반 상태(SimpleState)가 액션을 통해 작업 지침 역할을 하는 것.
