# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.
스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개발 환경

```bash
pip install -e ".[dev]"      # 개발 의존성 설치
python -m pytest tests/ -v   # 전체 테스트 (91개)
python -m pytest tests/model/fsm/ -v      # FSM 코어만
python -m pytest tests/model/plugin/ -v  # 플러그인 레이어만
```

pytest는 `python -m pytest`로 실행한다 (`pytest` 직접 실행 시 command not found).

## 아키텍처

**컴파일러 패턴:** 순수 모델(model/) → 컴파일러(compiler/, 미구현) → 플러그인 파일

현재 구현 범위: **model/ 패키지만** (FSM 코어 + 플러그인 메타데이터).

```
daedalus/model/
├── fsm/          # 순수 FSM 개념 (Claude 무관)
│   ├── event.py        # 이벤트 계층 (StateEvent, TransitionEvent, BlackboardTrigger 등)
│   ├── variable.py     # Variable + VariableScope/Type/ConflictResolution
│   ├── strategy.py     # EvaluationStrategy 계열 (Guard용) + ExecutionStrategy 계열 (Action용)
│   ├── guard.py        # Guard(evaluation: EvaluationStrategy)
│   ├── action.py       # Action(name, execution, output_variable)
│   ├── state.py        # State(ABC), SimpleState, CompositeState, ParallelState, Region
│   ├── pseudo.py       # HistoryState, ChoiceState, TerminateState, EntryPoint, ExitPoint
│   ├── transition.py   # Transition + TransitionType
│   ├── blackboard.py   # Blackboard, DynamicClass, DynamicField
│   └── machine.py      # StateMachine
└── plugin/       # Claude 플러그인 메타데이터
    ├── enums.py        # ModelType, EffortLevel, SkillContext, PermissionMode 등
    ├── policy.py       # ExecutionPolicy, JoinStrategy (병렬 서브에이전트)
    ├── config.py       # SkillConfig(ABC), ProceduralSkillConfig, DeclarativeSkillConfig, AgentConfig
    ├── base.py         # PluginComponent(ABC), WorkflowComponent(ABC)
    ├── skill.py        # Skill(ABC), ProceduralSkill, DeclarativeSkill
    └── agent.py        # AgentDefinition
model/project.py         # PluginProject (최상위 컨테이너)
model/validation.py      # Validator + ValidationError (3개 규칙)
```

## 핵심 설계

### FSM + Blackboard 하이브리드

- **로컬 데이터:** Transition.data_map으로 상태 간 명시적 전달 (`{src_output: tgt_input}`)
- **공유 데이터:** Blackboard.variables (Variable.scope = BLACKBOARD)
- **동적 상태 파일:** Blackboard.class_definitions (DynamicClass) — 설계 시 정의, 런타임에 work 폴더 state/에 생성

### 플러그인 컴포넌트 구분

| 종류 | 클래스 | FSM 보유 |
|------|--------|----------|
| 절차형 스킬 | ProceduralSkill(Skill, WorkflowComponent) | O |
| 선언형 스킬 | DeclarativeSkill(Skill) | X |
| 에이전트 | AgentDefinition(PluginComponent, WorkflowComponent) | O |

### 전이 규칙 (Validator)

- `no_nested_agent`: CompositeState 안에 CompositeState 불가
- `no_agent_to_agent`: Agent → Agent 직접 전이 불가 (Skill 경유 필수)
- `missing_required_input`: LOCAL scope 필수 input이 data_map에 없으면 경고

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

## 미구현 예정

- `compiler/`: model → SKILL.md / Agent .md 파일 생성
- `ui/`: PyQt6 기반 노드 에디터
- CLI: 기존 Claude Code CLI 툴 연동 (플러그인 내 명시)
