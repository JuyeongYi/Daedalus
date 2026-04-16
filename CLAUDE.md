# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.
스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개발 환경

```bash
pip install -e ".[dev]"      # 개발 의존성 설치
python -m pytest tests/ -v   # 전체 테스트 (102개)
python -m pytest tests/model/fsm/ -v      # FSM 코어만
python -m pytest tests/model/plugin/ -v  # 플러그인 레이어만
```

pytest는 `python -m pytest`로 실행한다 (`pytest` 직접 실행 시 command not found).

## 아키텍처

**컴파일러 패턴:** 순수 모델(model/) → 컴파일러(compiler/, 미구현) → 플러그인 파일

현재 구현 범위: **model/ + view/** (FSM 코어 + 플러그인 메타데이터 + PyQt6 에디터).

```
daedalus/
├── model/
│   ├── fsm/          # 순수 FSM 개념 (Claude 무관)
│   │   ├── event.py        # 이벤트 계층 (StateEvent, CompletionEvent, BlackboardTrigger)
│   │   ├── variable.py     # Variable + VariableScope/FieldType/ConflictResolution
│   │   ├── strategy.py     # EvaluationStrategy 계열 (Guard용) + ExecutionStrategy 계열 (Action용)
│   │   ├── guard.py        # Guard(evaluation: EvaluationStrategy)
│   │   ├── action.py       # Action(name, execution, output_variable)
│   │   ├── state.py        # State(ABC), SimpleState, CompositeState, ParallelState, Region
│   │   ├── pseudo.py       # ChoiceState, TerminateState, EntryPoint, ExitPoint
│   │   ├── transition.py   # Transition + TransitionType
│   │   ├── blackboard.py   # Blackboard, DynamicClass, DynamicField(FieldType 사용)
│   │   ├── section.py      # Section(자유 콘텐츠 계층), EventDef(TransferOn 출력 이벤트)
│   │   └── machine.py      # StateMachine
│   ├── plugin/       # Claude 플러그인 메타데이터
│   │   ├── enums.py        # ModelType, EffortLevel, SkillContext, PermissionMode 등
│   │   ├── policy.py       # ExecutionPolicy, JoinStrategy (병렬 서브에이전트)
│   │   ├── config.py       # ComponentConfig(ABC), SkillConfig(ABC), ProceduralSkillConfig,
│   │   │                   # DeclarativeSkillConfig, AgentConfig
│   │   ├── base.py         # PluginComponent(ABC), WorkflowComponent(ABC)
│   │   ├── skill.py        # Skill(ABC), ProceduralSkill, DeclarativeSkill
│   │   ├── agent.py        # AgentDefinition
│   │   └── field_matrix.py # FieldRule, SKILL_FIELD_MATRIX (스킬 유형별 프론트매터 필드 규칙)
│   ├── project.py           # PluginProject (최상위 컨테이너)
│   └── validation.py        # Validator + ValidationError (7개 규칙, 재귀)
└── view/             # PyQt6 기반 노드 에디터
    ├── app.py              # 메인 윈도우
    ├── canvas/             # GraphicsView/Scene, NodeItem, EdgeItem, RefNodeItem, RefEdgeItem
    ├── commands/           # Undo/Redo 커맨드 (state, transition, section, exit_point)
    ├── editors/            # 속성 편집기 (skill, agent, body, component, variable_loader)
    ├── panels/             # TreePanel, PropertyPanel, RegistryPanel, HistoryPanel
    ├── viewmodel/          # ProjectViewModel, StateViewModel (모델↔뷰 중간 계층)
    └── widgets/            # ComboWidgets, TagInput, PresetPicker
```

## 핵심 개념

### 스킬과 에이전트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| AgentDefinition | 별도 컨텍스트의 상태 기계 | 자체 FSM + 별도 블랙보드 |

### CompositeState = 에이전트

- CompositeState는 "별도 컨텍스트에서의 상태 기계"로, 에이전트 개념에 해당
- `sub_machine: StateMachine`을 포함 — 내부에 완전한 FSM(상태 + 전이 + 블랙보드)을 보유
- UML 스테이트차트의 composite state 원래 정의와 일치

### Region = 병렬 실행 트랙

- `ParallelState` 내 독립 실행 단위
- `sub_machine: StateMachine`을 포함 — 각 Region은 자신만의 FSM을 가짐
- 향후 리전별 우선순위, 취소 정책, 동기화 포인트 등 확장 가능

### Blackboard = 컨텍스트 간 공유 장치

- **역할:** 서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치
- 동일 컨텍스트 내에서는 불필요 — 이미 같은 맥락을 공유
- 스코핑: 최상위 `Blackboard(parent=None)`, 하위 `Blackboard(parent=부모.blackboard)`

### FSM + Blackboard 하이브리드

- **로컬 데이터:** Transition.data_map으로 상태 간 명시적 전달 (`{src_output: tgt_input}`)
- **공유 데이터:** Blackboard.variables (Variable.scope = BLACKBOARD)
- **동적 상태 파일:** Blackboard.class_definitions (DynamicClass) — 설계 시 정의, 런타임에 work 폴더 state/에 생성

### Section / EventDef

- `Section`: 스킬 본문의 자유 콘텐츠 계층 (H1–H6). `children: list[Section]`으로 재귀 트리 구성
- `EventDef`: TransferOn 스킬의 출력 이벤트 정의. 노드 출력 포트에 대응 (`name`, `color`, `description`)

### SKILL_FIELD_MATRIX

스킬 유형(procedural, declarative, transfer, reference, local_*)별로 프론트매터 필드의 `FieldRule`을 정의하는 매트릭스.

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility   # REQUIRED / OPTIONAL / DEFAULT / FIXED
    widget: type[QWidget]         # 편집기에서 사용할 위젯 클래스
    fixed_value: Any = None       # FIXED일 때 고정값
    default_value: Any = None
```

`field_matrix.py`는 model/ 안에 있지만 view 위젯을 import한다 (편집기 위젯 매핑 목적).

### FieldType (통합 타입)

```python
class FieldType(Enum):
    STRING = "string"   # Variable / DynamicField 공용
    INT = "int"
    FLOAT = "float"
    NUMBER = "number"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"
```

- `VariableType`과 `DynamicFieldType`을 통합한 단일 열거형
- `Variable.field_type: FieldType`, `DynamicField.field_type: FieldType`

### ComponentConfig 계층

```
ComponentConfig(ABC)          # model, effort, hooks 공통 필드
├── SkillConfig(ABC)          # argument_hint, allowed_tools, paths
│   ├── ProceduralSkillConfig # disable_model_invocation, context, agent, shell 등
│   └── DeclarativeSkillConfig
└── AgentConfig               # tools, permission_mode, skills, isolation 등
```

### CompletionEvent

세 가지 완료를 통합적으로 표현:
- SimpleState 작업 완료 → 부모 FSM에 완료 신호
- CompositeState sub_machine이 final_state 도달 → 부모 FSM에 완료 신호
- ParallelState 전 Region 완료 → 부모 FSM에 완료 신호

`Transition.trigger = CompletionEvent(name="done")` 으로 설정.

### Validator 규칙 (7개, 재귀 적용)

| 규칙 | 설명 |
|------|------|
| `initial_state_in_states` | `sm.initial_state ∈ sm.states` |
| `final_states_in_states` | `sm.final_states ⊆ sm.states` |
| `no_nested_agent` | CompositeState 안에 CompositeState 불가 |
| `no_agent_to_agent` | Agent → Agent 직접 전이 불가 (Skill 경유 필수) |
| `missing_required_input` | LOCAL scope 필수 input이 data_map에 없으면 경고 |
| `pseudo_state_hooks` | ChoiceState, TerminateState, EntryPoint, ExitPoint에 lifecycle 훅 설정 시 경고 |
| `completion_event_on_composite` | CompositeState/ParallelState에서 나가는 전이에 CompletionEvent trigger 없으면 경고 |

재귀: CompositeState.sub_machine과 Region.sub_machine 내부도 동일하게 검증.

### 전략 패턴 (Guard / Action 공통)

```
EvaluationStrategy(ABC)        ExecutionStrategy(ABC)
├── LLMEvaluation              ├── LLMExecution
├── ToolEvaluation             ├── ToolExecution
├── MCPEvaluation              ├── MCPExecution
├── ExpressionEvaluation       └── CompositeExecution
└── CompositeEvaluation
```

## 구현 시 주의사항

### ABC + dataclass

`@dataclass class Foo(ABC):`만으로는 인스턴스화가 막히지 않는다.
반드시 `@abstractmethod`가 하나 이상 있어야 TypeError 발생.
이 프로젝트에서는 모든 ABC 클래스에 `@property @abstractmethod kind(self) -> str`를 추가한다.

### dataclass 다중 상속 필드 순서

`ProceduralSkill(Skill, WorkflowComponent)` 같은 다중 상속 dataclass에서
부모의 required 필드(default 없음)보다 앞에 default 필드가 오면 Python 에러가 난다.

**해결:** 자식 클래스에서 부모 필드를 `field(default=None)`으로 오버라이드하지 않는다.
`fsm`은 required로 유지하고, 테스트에서는 항상 keyword 인수로 전달한다.

MRO 기반 필드 순서 (ProceduralSkill 예시):
```
fsm (WorkflowComponent, required)
name, description (PluginComponent, required)
config (ProceduralSkill, default_factory)
```

### dataclass는 unhashable

dataclass 인스턴스는 기본적으로 `__hash__`가 None (mutable). set 컴프리헨션 대신 list 사용.

## 미구현 예정

- `compiler/`: model → SKILL.md / Agent .md 파일 생성
- CLI: 기존 Claude Code CLI 툴 연동 (플러그인 내 명시)
