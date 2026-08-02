# Daedalus

FSM 기반 Claude Code 플러그인 하네스 엔지니어링 도구.
스킬(Skill)과 에이전트(Agent) 컴포넌트를 FSM + Blackboard 모델로 설계하고, 컴파일러 패턴으로 플러그인 파일을 생성한다.

## 개발 환경

```bash
pip install -e ".[dev]"      # 개발 의존성 설치
python -m pytest tests/ -v   # 전체 테스트
python -m pytest tests/model/fsm/ -v      # FSM 코어만
python -m pytest tests/model/plugin/ -v  # 플러그인 레이어만
```

pytest는 `python -m pytest`로 실행한다 (`pytest` 직접 실행 시 command not found).

## 아키텍처

**컴파일러 패턴:** 순수 모델(model/) → 컴파일러(compiler/) → 플러그인 파일

현재 구현 범위: **model/ + view/ + compiler/** (FSM 코어 + 플러그인 메타데이터 + PySide6 에디터 + SKILL.md/agent .md 생성).

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
│   │   ├── join.py         # JoinStrategy (병렬 조인 전략 — 순수 FSM 개념, policy.py가 re-export)
│   │   ├── blackboard.py   # Blackboard, DynamicClass, DynamicField(FieldType 사용), FIELD_TYPE_TO_JSON_SCHEMA
│   │   ├── section.py      # Section(자유 콘텐츠 계층), EventDef(TransferOn 출력 이벤트)
│   │   └── machine.py      # StateMachine
│   ├── plugin/       # Claude 플러그인 메타데이터
│   │   ├── enums.py        # ModelType, EffortLevel, SkillContext, PermissionMode, AgentField, FieldEmit 등
│   │   ├── policy.py       # ExecutionPolicy (병렬 서브에이전트). JoinStrategy는 fsm/join.py에서 re-export(하위 호환)
│   │   ├── config.py       # ComponentConfig(ABC), SkillConfig(ABC), ProceduralSkillConfig,
│   │   │                   # DeclarativeSkillConfig, TransferSkillConfig, ReferenceSkillConfig, AgentConfig
│   │   ├── base.py         # PluginComponent(ABC), WorkflowComponent(ABC)
│   │   ├── skill.py        # Skill(ABC), ProceduralSkill, DeclarativeSkill, TransferSkill, ReferenceSkill
│   │   ├── agent.py        # AgentDefinition
│   │   ├── delegation.py   # DelegationDef(CompositionMode/guidance 포함) + TeamSpawnDef/DynamicWorkflowDef/AgoraDispatchDef (CC 위임 노드)
│   │   ├── tool.py         # Tool(ABC) + BuiltinTool/MCPTool/UserDefinedTool (tool_shelf 도구 단일 진실)
│   │   ├── hook.py         # HookDef + HookEvent(CC 9종) (hook_library 훅 단일 진실)
│   │   ├── hook_presets.py # BUILTIN_HOOK_PRESETS (복사용 훅 템플릿) + preset_copy
│   │   └── field_matrix.py # FieldRule(emit 포함), SKILL_FIELD_MATRIX, AGENT_FIELD_MATRIX (스킬/에이전트 유형별 프론트매터 필드 규칙)
│   ├── project.py           # PluginProject (최상위 컨테이너, name+description+version — plugin.json 매니페스트 소스), ReferencePlacement, tool_shelf, hook_library, blackboard(최상위), graph(워크플로 백킹 머신)+graph_layout
│   │                       # + rename_component(project, component, new_name) — 이름 변경 + 문자열 참조 3종 일괄 갱신 (Qt 무관)
│   │                       # + remove_component(project, component) → list[str] — 모델 정리 (graph placement, skill_ref None화, 위임 agent_ref None화 등)
│   ├── serialize.py         # serialize_project/deserialize_project (모델↔JSON dict, 안정 ID 기반)
│   └── validation.py        # Validator + ValidationError + WARNING_RULES + is_warning (머신 규칙 19종 + 프로젝트 규칙 12종, 재귀)
├── compiler/         # 순수 모델 → 플러그인 파일 (Qt 무관)
│   ├── emit.py             # compile_skill/compile_agent/compile_hooks_json — model → SKILL.md/agent .md/hooks.json 텍스트 (결정적, LF)
│   └── project_compiler.py # compile_project(project, out_dir) → CompileResult (검증 게이트 + 파일 쓰기)
└── view/             # PySide6 기반 노드 에디터
    ├── app.py              # 메인 윈도우 (Ctrl+N "새 프로젝트"(기본 이름 "new-plugin"), F7 "프로젝트 검증", Ctrl+B "컴파일", 파일→"프로젝트 속성...", 도구→"훅 라이브러리...")
    │                       # 컴포넌트 이름 변경: _FrontmatterPanel.renamed → _on_component_renamed (중복 거부 + rename_component 호출 + 탭 타이틀 동기화)
    │                       # 컴포넌트 삭제: 레지스트리 우클릭 → _on_delete_component (확인 다이얼로그 + remove_component + 탭 닫기 + notify)
    │                       # 프로젝트 속성: _edit_project_properties → ProjectPropertiesDialog(name/description/version, 이름 규약 미강제)
    ├── canvas/             # GraphicsView/Scene, NodeItem, EdgeItem, RefNodeItem, RefEdgeItem, node_badges(뱃지 로직), sync(VM→모델 동기화 — Qt 무관)
    ├── commands/           # Undo/Redo 커맨드 (state, transition, section, exit_point)
    ├── editors/            # 속성 편집기 (skill, agent, delegation, hook, body, component, variable_loader, field_widgets, project_properties)
    │                       # body: SectionContentPanel = MarkdownToolbar + QStackedWidget(0=MarkdownEditor 편집, 1=QTextBrowser 프리뷰 — setMarkdown 1회 렌더, show_section이 편집 모드로 리셋, 프리뷰 중 편집 버튼·변수 삽입 잠금)
    ├── panels/             # TreePanel, PropertyPanel, RegistryPanel, HistoryPanel, ValidationPanel (F7 검증 결과)
    │                       # RegistryPanel: component_delete_requested 시그널 + _RegistrySection 우클릭 "삭제" 컨텍스트 메뉴
    ├── viewmodel/          # ProjectViewModel(notify structure/content 채널), StateViewModel (모델↔뷰 중간 계층)
    └── widgets/            # ComboWidgets, TagInput, PresetPicker, markdown_editor(MarkdownHighlighter+MarkdownEditor — 하이브리드 마크다운 하이라이팅·편집, SectionContentPanel 본문에 통합
                            #   + `/` 슬래시 메뉴(_SlashMenu — 에디터 viewport 자식 오버레이, Qt.Popup 아님) + MarkdownToolbar(서식 버튼 행 + 프리뷰 토글 시그널))
```

## 핵심 개념

### 스킬과 에이전트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| TransferSkill | 전이 시 실행되는 보조 지침 | 자체 FSM 보유 |
| ReferenceSkill | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| AgentDefinition | 별도 컨텍스트의 상태 기계 | 자체 FSM + 별도 블랙보드 |

### CompositeState = 에이전트

- CompositeState는 "별도 컨텍스트에서의 상태 기계"로, 에이전트 개념에 해당
- `sub_machine: StateMachine`을 포함 — 내부에 완전한 FSM(상태 + 전이 + 블랙보드)을 보유
- UML 스테이트차트의 composite state 원래 정의와 일치

### Region = 병렬 실행 트랙

- `ParallelState` 내 독립 실행 단위
- `sub_machine: StateMachine`을 포함 — 각 Region은 자신만의 FSM을 가짐
- 향후 리전별 우선순위, 취소 정책, 동기화 포인트 등 확장 가능
- **조인 전략:** `ParallelState.join: JoinStrategy = ALL` + `join_count: int | None`. ALL=전 Region, ANY=하나, N_OF=`join_count`개 완료 시 join. `JoinStrategy`는 순수 FSM 개념이라 `model/fsm/join.py`에 있고 `model/plugin/policy.py`가 re-export로 하위 호환 유지(`ExecutionPolicy`도 동일 enum 사용).

### Blackboard = 컨텍스트 간 공유 장치

- **역할:** 서로 다른 컨텍스트 간에 외부 데이터를 통해 맥락을 공유하는 장치
- 동일 컨텍스트 내에서는 불필요 — 이미 같은 맥락을 공유
- 스코핑: 최상위 `Blackboard(parent=None)`, 하위 `Blackboard(parent=부모.blackboard)`
- **최상위 블랙보드:** `PluginProject.blackboard`(default_factory) — schemas.json의 소스(DynamicClass 단일 진실). 에이전트/스킬 FSM의 `blackboard.parent`는 **생성 경로의 책임**으로 이 객체에 배선한다 (app.py `_register_component`, agent_editor 로컬 스킬 생성, **그리고 `deserialize_project` — 역직렬화도 생성 경로**: 최상위 스킬/에이전트 FSM→프로젝트 블랙보드, 로컬 스킬 FSM→소유 에이전트 FSM 블랙보드로 재연결되어 parent 스코핑이 저장/로드를 견딘다). 마이그레이션 없음 — 메모리 내 기존 객체는 강제하지 않는다. 직렬화는 parent를 ID로 평탄화하지 않고 **소유 구조로 재연결**(`_deser_machine`의 `parent_bb` 전달).
- **DynamicClass → JSON Schema 매핑:** `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA` 정본(STRING→string, INT→integer, FLOAT/NUMBER→number, BOOL→boolean, LIST→array, JSON→object, ANY→{}). CollectionType은 array로 래핑(LIST→items, SET→items+uniqueItems). 컴파일러 `compile_schemas_json(project)`가 프로젝트 블랙보드 class_definitions를 `<out>/schemas/schemas.json`으로(정의 없으면 None).

### FSM + Blackboard 하이브리드

- **로컬 데이터:** Transition.data_map으로 상태 간 명시적 전달 (`{src_output: tgt_input}`)
- **공유 데이터:** Blackboard.variables (Variable.scope = BLACKBOARD)
- **동적 상태 파일:** Blackboard.class_definitions (DynamicClass) — 설계 시 정의, 런타임에 work 폴더 state/에 생성

### Section / EventDef

- `Section`: 스킬 본문의 자유 콘텐츠 계층 (H1–H6). `children: list[Section]`으로 재귀 트리 구성
- `EventDef`: TransferOn 스킬의 출력 이벤트 정의. 노드 출력 포트에 대응 (`name`, `color`, `description`)

### PluginProject.graph = 워크플로 백킹 머신

- **역할:** 프로젝트 캔버스(탭 0)의 노드/전이를 담는 정식 `StateMachine`. 각 캔버스 노드는 "정식 FSM 상태"이며 백킹 머신에 들어가 **직렬화·컴파일·검증의 단일 진실**이 된다 (캔버스 VM은 그 투영). 이전에는 fsm=None 경로로 도메인 모델에 들어가지 않아 저장/컴파일에서 누락됐다.
- **기본값:** `default_factory=_make_project_graph` — `EntryPoint(name="start")`를 `initial_state`로 갖는 빈 머신(states 포함). `StateMachine.initial_state`는 required 유지(Optional 완화 없음), 직렬화 포맷도 불변.
- **EntryPoint 격하 (WP-EP):** CC 플러그인에는 단일 진입점이 없다 — user_invocable 스킬은 전부 `/skill`로 독립 시작 가능하고 모델 자동 인보크도 있어, FSM 관념의 "시작점"이 성립하지 않는다. 따라서 **프로젝트 캔버스(탭 0)는 EntryPoint와 그에 닿는 전이를 그리지 않는다** — `app._load_project_graph`가 `graph.states`에서 EntryPoint 인스턴스를 스킵하고(VM 미생성), EntryPoint에 닿는 전이도 VM이 없어 자연히 렌더되지 않는다(구버전 파일의 시작 전이도 경고 없이 조용히 숨는다). 모델은 불변 — `project.graph.initial_state`는 여전히 EntryPoint이고 구버전 파일의 시작 전이도 저장 왕복 시 보존된다. `FsmScene`의 EntryPoint 삭제-방어 코드(`_delete_state`/컨텍스트 메뉴/keyPress)는 `AgentFsmScene`과 공용이라 그대로 두지만, 프로젝트 캔버스에서는 VM이 없어 자연히 죽은 경로가 된다. **에이전트 FSM의 EntryPoint/ExitPoint(agent_editor, AgentFsmScene)는 이 격하와 무관** — 에이전트는 별도 컨텍스트의 실재하는 단일 진입점이다.
- **placement:** 배치된 스킬/에이전트는 `SimpleState(skill_ref=...)`로 그래프에 들어간다 (에이전트도 SimpleState로, CompositeState 승격 없음). `FsmScene.set_project`가 `_target_fsm = project.graph`로 배선해 Create/Delete/Transition 커맨드가 그래프에 동기화된다 (undo/redo 일관). `AgentFsmScene`은 `_target_fsm`을 에이전트 FSM으로 별도 설정.
- **graph_layout:** `dict[str, list[float]]` — 키는 **state.id** (AgentDefinition.graph_layout과 동일 규약, 이름 변경 안전). 저장 직전 `app._save_graph_layout`이 VM 좌표를 기록, 로드 시 `app._load_project_graph`가 graph+graph_layout으로 캔버스 VM을 재구성(`agent_editor._load_agent_fsm` 미러링). EntryPoint는 캔버스 VM이 없으므로 `graph_layout`에도 그 키가 기록되지 않는다(WP-EP).
- **블랙보드 배선:** `project.graph.blackboard.parent = project.blackboard` — `PluginProject.__post_init__`(생성 경로)과 `deserialize_project`(역직렬화 생성 경로) 양쪽에서 보장.

### 안정 ID + 직렬화 (serialize.py)

- **안정 ID:** `State`(베이스)/`Transition`/`StateMachine`/`Region`/`Variable`/`Skill`(베이스)/`AgentDefinition`/`DelegationDef`(베이스)에 `id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)`. kw_only로 다중 상속 필드 순서 제약을 회피한다. eq=False 클래스는 identity 동등성/해시를 유지(id는 `__eq__`/`__hash__` 무관)하고, 값 동등성 클래스(Variable/Skill/Agent/Delegation)는 `compare=False`로 값 비교에서 제외한다.
- **직렬화 원칙:** `serialize_project`/`deserialize_project`는 JSON 호환 dict(`"format": 1` 버전 키)를 만든다. **소유 객체는 인라인, 참조는 ID 문자열로 평탄화**한다 — Transition.source/target(state id), SimpleState.skill_ref·Transition.skill_ref(component id), StateMachine.initial_state/final_states(state id), Delegation.agent_ref(agent id). 다형성은 `kind` property를 태그로 재사용. enum은 `.value`↔타입 복원. 역직렬화는 2-pass(객체 생성+id 레지스트리 → 참조 해소)이고 dangling id는 None+경고. `Blackboard.parent`는 ID가 아니라 sub_machine 소유 구조로 재연결한다. serialize.py는 순수 모델(Qt 무관).
- **프로젝트 그래프 직렬화:** `serialize_project`는 `graph`(`_ser_machine` 재사용)와 `graph_layout`을 왕복한다. 그래프 placement의 skill_ref는 component id로 평탄화되고, 역직렬화 시 pass1에서 등록된 skills/agents를 pass2가 해소한다(그래프 `_deser_machine`은 pass1에서 호출). 하위 호환: `"graph"` 키 부재(구버전 파일) → `_make_project_graph()`로 빈 그래프 생성(경고 없음). graph.blackboard.parent는 역직렬화 시 프로젝트 블랙보드로 재연결.
- `AgentDefinition.graph_layout`/`PluginProject.graph_layout`의 키는 state.name이 아니라 **state.id**다 (이름 변경 시 레이아웃 유실 방지).

### SKILL_FIELD_MATRIX

스킬 유형(procedural, declarative, transfer, reference, local_*)별로 프론트매터 필드의 `FieldRule`을 정의하는 매트릭스.

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility   # REQUIRED / OPTIONAL / DEFAULT / FIXED
    fixed_value: Any = None       # FIXED일 때 컴파일러가 강제할 출력값 (enum)
    default_value: Any = None     # 위젯 초기 표시용 (단일 진실은 config 선언 기본값)
    emit: FieldEmit = FieldEmit.FRONTMATTER  # 컴파일러 배출 위치 (FRONTMATTER/BODY/INVOCATION/SETTINGS)
```

`field_matrix.py`는 순수 모델(Qt 무관)이다. 편집 위젯 매핑은 view 측 `daedalus/view/editors/field_widgets.py`의 `FIELD_WIDGETS: dict[SkillField, type[QWidget]]`(1차원, kind 무관)과 `AGENT_FIELD_WIDGETS: dict[AgentField, type[QWidget]]`로 분리되어 있다. 프론트매터 키는 `SkillField.frontmatter_key` property가 제공한다 (kebab-case, `WHEN_TO_USE`는 None — description/본문 합류는 컴파일러 정책). `AgentField.frontmatter_key`는 전 멤버 kebab-case 변환. FIXED 필드는 편집기 비노출이며 `fixed_value`는 컴파일러 출력 시 강제(config에 미기록). `AGENT_FIELD_MATRIX`는 에이전트 전용 1차원 매트릭스.

### FieldType (통합 타입)

```python
class FieldType(Enum):
    STRING = "string"   # Variable / DynamicField 공용
    INT = "int"
    FLOAT = "float"
    NUMBER = "number"   # deprecated: INT/FLOAT 사용, 컴파일 시 JSON Schema "number"로 합류(FLOAT와 동일)
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"
```

- `VariableType`과 `DynamicFieldType`을 통합한 단일 열거형
- `Variable.field_type: FieldType`, `DynamicField.field_type: FieldType`
- `NUMBER`는 **deprecated** — 의미가 명확한 INT/FLOAT을 쓰라. 컴파일 시 INT→integer, FLOAT/NUMBER→number로 합류된다(하위 호환용 잔존). 매핑 정본은 `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA`.

### ComponentConfig 계층

```
ComponentConfig(ABC)          # model, effort, hooks 공통 필드
├── SkillConfig(ABC)          # argument_hint, allowed_tools, paths
│   ├── ProceduralSkillConfig # disable_model_invocation, context, agent, shell 등
│   ├── DeclarativeSkillConfig
│   ├── TransferSkillConfig
│   └── ReferenceSkillConfig
└── AgentConfig               # tools, permission_mode, skills, isolation 등
```

### CompletionEvent

세 가지 완료를 통합적으로 표현:
- SimpleState 작업 완료 → 부모 FSM에 완료 신호
- CompositeState sub_machine이 final_state 도달 → 부모 FSM에 완료 신호
- ParallelState는 `ParallelState.join` 전략에 따라 완료 (ALL=전 Region, ANY=하나, N_OF=join_count개) → 부모 FSM에 완료 신호

`Transition.trigger = CompletionEvent(name="done")` 으로 설정.

### Validator 규칙 (재귀 적용)

`ValidationError` 필드: `rule`, `message`, `source`(기존) + `subject: object | None`(문제 객체, 향후 노드 점프용 — `compare=False`이므로 identity 비교로 조회) + `path: tuple[str, ...]`(중첩 경로, 예: `("agent:Writer", "region:r1")`). 기본값이 있어 기존 생성자 호환. `validate_project`는 최상위 FSM 오류에 root path(`"skill:<이름>"`/`"agent:<이름>"`)를 주입한다.

`ValidationError.is_warning` property — 규칙이 경고 등급이면 True, 에러 등급이면 False. `WARNING_RULES: frozenset[str]` 모듈 상수가 경고 등급 규칙 집합을 단일 진실로 보유 (view에서 rule 이름 하드코딩 금지). `invalid_component_name`은 빈 이름=에러/불일치=경고를 `is_warning`에서 메시지 내용으로 세분화한다.

#### 머신 수준 (19규칙명)

| 규칙 | 설명 |
|------|------|
| `initial_state_in_states` | `sm.initial_state ∈ sm.states` (identity 기준) |
| `final_states_in_states` | `sm.final_states ⊆ sm.states` |
| `no_nested_agent` | CompositeState 안에 CompositeState 불가 |
| `no_agent_to_agent` | Agent → Agent 직접 전이 불가 (Skill 경유 필수) |
| `missing_required_input` | LOCAL scope 필수 input이 data_map에 없으면 경고 |
| `pseudo_state_hooks` | 의사 상태에 lifecycle 훅 설정 시 경고 |
| `completion_event_on_composite` | Composite/ParallelState 출발 전이에 CompletionEvent 없으면 경고 |
| `no_duplicate_skill_ref` | 동일 스킬/에이전트의 중복 배치 금지 (DelegationDef는 면제) |
| `transfer_on_not_empty` | ProceduralSkill transfer_on / Agent ExitPoint 최소 1개 |
| `empty_delegation` | 위임 노드 내용 누락 (팀원 0명·count<1, objective/msgtype 빈 값) 경고 |
| `forget_completion_mismatch` | forget 모드 위임 노드의 결과 분기 시도 경고 |
| `transition_endpoint_not_in_states` | Transition.source/target이 sm.states에 없으면 에러 (initial/final 비대칭 해소) |
| `duplicate_state_name` | 동일 머신 내 동명 상태 경고 (컴파일/직렬화 혼동 방지) |
| `unreachable_state` | initial_state + 모든 EntryPoint에서 전이 그래프로 도달 불가 상태 경고 (스킬/에이전트 FSM 대상. 프로젝트 그래프 자체는 WP-EP로 스킵 — 아래 "프로젝트 그래프 검증" 참조) |
| `invalid_data_map_source` | Transition.data_map의 key가 source.outputs에 없으면 경고 (pseudo 상태 스킵) |
| `trigger_unknown_event` | CompletionEvent trigger.name이 source 출력 이벤트 집합에 없으면 경고 (EventDef rename 고아 전이 검출) |
| `transition_type_consistency` | INTERNAL/SELF 타입인데 `source is not target`이면 에러 |
| `choice_completeness` | ChoiceState outgoing 0개=에러, 무가드 2개 이상=에러(else 중복/비결정) |
| `choice_completeness_missing_else` | ChoiceState 무가드(else) 전이 0개=경고 (LLM 해석 결정성 저하) |
| `parallel_join_count` | ParallelState join=N_OF인데 join_count가 None이거나 region 수 초과 시 경고 |

**INTERNAL vs custom_events 역할 분리:** INTERNAL = 상태 비이탈 + guard/action 있는 반응(entry/exit 미발화, `source is target` 필수). 단순 반응(guard·data_map 없이 액션만)은 `State.custom_events`로 표현한다. 의사 상태(Choice/Terminate/Entry/Exit)에는 lifecycle 훅뿐 아니라 custom_events도 `pseudo_state_hooks` 경고 대상이다.

**ChoiceState else 관례:** ChoiceState outgoing 중 **무가드 전이 = else 분기**. 가드 전이를 선언 순서로 평가하고 모두 실패하면 유일한 무가드 전이로 진행. 컴파일러 절차 서술은 무가드 전이를 `[else]`로, ParallelState는 join 전략 문구로 출력한다.

재귀: CompositeState.sub_machine과 Region.sub_machine 내부도 동일하게 검증. 재귀 시 `path`에 `"agent:<이름>"` 또는 `"region:<이름>"`이 누적된다.

**skip_rules (WP-EP):** `Validator.validate`/`_validate_machine`은 `skip_rules: frozenset[str] = frozenset()` 파라미터를 받아 이름이 속한 규칙 검사를 생략한다(기본값 빈 집합이라 기존 호출 전부 하위 호환). 재귀 호출(sub_machine/Region)에는 **전파하지 않는다** — 호출부가 지정한 그 머신 자체에만 적용된다.

**프로젝트 그래프 검증:** `validate_project`는 `project.graph`도 머신 규칙으로 검증하며 root path는 `("project",)`다. 단 그래프에 placement(EntryPoint 외 노드)가 0개면 검증을 스킵(`_graph_has_placements`) — 빈 캔버스 경고 폭주 방지. `transfer_on_not_empty` 같은 컴포넌트 수준 규칙은 머신 검증에 없으므로 무관. **`unreachable_state`는 `skip_rules={"unreachable_state"}`로 스킵된다(WP-EP)** — CC 플러그인 의미론상 프로젝트 그래프의 모든 배치는 user_invocable 스킬 등으로 독립 시작 가능해 "EntryPoint에서 도달 불가"가 성립하지 않는다. skip_rules는 재귀에 전파되지 않으므로 에이전트 sub_machine 내부의 `unreachable_state`는 기존대로 검사된다.

#### 프로젝트 수준 (12종)

`Validator.validate_project(project)` — 전체 FSM 검증 후 추가:

| 규칙 | 설명 |
|------|------|
| `dangling_teammate_ref` | 위임 정의의 agent_ref가 project.agents에 실존하지 않으면 경고 |
| `unregistered_delegation` | 배치된 SimpleState.skill_ref가 DelegationDef인데 project.delegations에 미등록이면 경고 |
| `duplicate_component_name` | skills/agents/delegations 전체에서 동명 컴포넌트 에러 (컴파일 디렉토리 충돌) |
| `invalid_component_name` | 이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 시 경고, 빈 이름은 에러 |
| `dangling_string_reference` | `ProceduralSkillConfig.agent`, `AgentConfig.skills`, `reference_placements.skill_name`의 문자열 참조 실존 검사. AgentConfig.skills는 전역 + 에이전트 로컬 스킬 합산 |
| `duplicate_tool_name` | `tool_shelf` 내 동명 Tool 에러 (이름 참조 모호) |
| `empty_tool_definition` | UserDefinedTool 본문(body) 빈 값 / MCPTool server·tool_name 빈 값 경고 |
| `dangling_tool_ref` | FSM의 ToolEvaluation/ToolExecution.tool이 `tool_shelf ∪ CC_BUILTIN_TOOLS`에 없으면 경고 (빈 문자열은 스킵). 참조 수집은 상태 훅·custom_events·전이 가드/액션 체인 + Composite 중첩 + sub_machine/Region 재귀 |
| `duplicate_hook_name` | `hook_library` 내 동명 HookDef 에러 (이름 참조 모호) |
| `empty_hook_command` | HookDef.command 빈 값 경고 |
| `hook_matcher_without_tool_event` | matcher가 있는데 event가 Pre/PostToolUse가 아니면 경고 (matcher는 도구 이벤트 전용) |
| `dangling_hook_ref` | config.hooks 키가 hook_library에 없으면 경고 (스킬·에이전트·에이전트 로컬 스킬 전부 검사) |

도구 모델(`tool.py`): `Tool(PluginComponent, ABC)` 단일 진실 + `BuiltinTool`/`MCPTool`/`UserDefinedTool`. shelf = 프로젝트(`PluginProject.tool_shelf`) 소유, FSM은 `Tool.name` 문자열로 참조(fsm/는 plugin 무관 — 객체 참조 금지, Validator가 실존 검증). `CC_BUILTIN_TOOLS`는 validation.py 모듈 frozenset(Read/Write/Edit/Bash/Glob/Grep/WebFetch/WebSearch/Agent/Task/TodoWrite/NotebookEdit/SlashCommand/PowerShell).

### 훅 (HookDef / hook_library)

훅은 CC lifecycle hooks의 설계 모델이다. `hook.py`의 `HookDef`(name·event·matcher·command·timeout, 안정 ID)가 단일 진실이고 `PluginProject.hook_library`에 모인다(tool_shelf와 동일 shelf 패턴). `HookEvent`는 CC 9종 이벤트(PreToolUse/PostToolUse/UserPromptSubmit/SessionStart/SessionEnd/Stop/SubagentStop/Notification/PreCompact). `ComponentConfig.hooks: dict`는 **이름 참조**다 — 키=hook_library의 HookDef.name, 값=오버라이드(빈 dict면 정의 그대로). `hook_presets.py`의 `BUILTIN_HOOK_PRESETS`(6종)는 복사해 출발점으로 쓰는 템플릿이며 `preset_copy`로 새 id 사본을 만든다. 컴파일러는 참조된 훅을 모아 `<out>/hooks/hooks.json`(CC settings hooks 스키마: matcher는 Pre/PostToolUse만, timeout은 있을 때만, 이벤트 키=HookEvent 선언 순서, 같은 이벤트 복수 훅=라이브러리 순서)을 생성하고, 스킬 프론트매터에는 `hooks: [이름, …]` 목록만 표기한다. UI는 `editors/hook_editor.HookLibraryDialog`(도구 메뉴) + `widgets/preset_picker`의 `set_hook_name_provider`로 HookPresetPicker가 hook_library 이름을 동적 표시한다.

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

### dataclass 동등성 정책

FSM 모델 클래스(State 계열·pseudo 4종·Transition·StateMachine·Region·Section)는
`@dataclass(eq=False)` — identity 동등성 + hashable. 서브클래스에 `@dataclass`를
다시 적용할 때 `eq=False`를 빠뜨리면 `__eq__` 재생성 + unhashable로 되돌아가므로 주의.

plugin 레이어(Skill, AgentDefinition 등)와 값 객체(EventDef, Variable 등)는 기본
dataclass(값 동등성, unhashable) 유지 — 컬렉션 멤버십에는 list/`id()` 사용.

### notify 채널 (structure / content)

`ProjectViewModel.notify(scope=...)`와 `add_listener(listener, scope=...)`는 두 채널을
구분한다. **structure**(기본값)는 상태/전이/참조의 추가·삭제·이동 등 구조 변경으로,
캔버스 `_rebuild`·레지스트리·트리·상태바 같은 무거운 리스너가 구독한다. **content**는
섹션 content/title·description·when_to_use 같은 텍스트 키스트로크로, structure 리스너를
깨우지 않아 타이핑마다 재구성이 도는 것을 막는다(채널은 서로 격리 — 교차 호출 없음).
에디터는 임의의 `Callable[[], None]`을 `on_notify_fn`으로 받으므로, `call_notify(fn, scope)`
헬퍼가 시그니처를 검사해 scope를 받는 콜백에만 채널을 전달한다(상위 호환). 텍스트 편집
패널은 위젯 재생성으로 편집 중 위젯이 파괴되지 않도록 in-place 동기화 원칙을 따른다
(`_ContractPanel.refresh` 참조).

## 컴파일러 (compiler/)

`compile_project(project, out_dir) → CompileResult`. 순수 stdlib(Qt 무관, import 순수성 테스트로 고정).

**출력 구조 (CC 플러그인 규약):**
- `<out>/.claude-plugin/plugin.json` — 플러그인 매니페스트 (항상 생성 — 이게 없으면 산출 디렉토리를 CC 플러그인으로 설치할 수 없다)
- `<out>/skills/<skill-name>/SKILL.md` — 전역 스킬 4종 전부 (Declarative/Reference도 SKILL.md)
- `<out>/skills/<agent-name>--<skill-name>/SKILL.md` — 에이전트 로컬 스킬 (`--` 결합은 충돌 무결하지 **않음** — 이름 규약이 연속 하이픈을 허용하므로 게이트가 사전 경로 집합 검사로 충돌 시 거부)
- `<out>/agents/<agent-name>.md` — 에이전트

**컴파일 정책 (확정):**
1. **프론트매터**: 해당 kind 매트릭스에서 `emit==FRONTMATTER`인 필드만. 키는 `frontmatter_key`(kebab-case).
   FIXED는 `fixed_value` 강제 출력. `model==INHERIT`는 키 생략. OPTIONAL 값이 config 선언 기본값과 같으면 생략(잡음 제거).
   enum은 `.value`, bool은 `true`/`false`, 리스트는 flow-style `[a, b]`.
2. **when_to_use**: description과 합류 — `<description> Use when <when_to_use>` (description이 `.!?`로 끝나면 공백, 아니면 `. `로 연결).
3. **본문**: `sections` 트리 → 마크다운 헤딩(루트 H1, 깊이별 `#`/`##`/…, 최대 H6).
4. **ProceduralSkill FSM → 절차 단락**: initial_state부터 전이 BFS 순서로 번호 매긴 상태 목록(시작/종료 표지),
   각 SimpleState skill_ref는 "skill 이름 사용", CompositeState는 "에이전트 X에 위임", 전이별 트리거/가드 조건 + transfer_on 출력 이벤트.
5. **위임 노드**: 스펙 4절 문구(TeamSpawn/DynamicWorkflow/AgoraDispatch 도구 호출 지침) + 1-b절 GUIDED(유도문 + teammates/phases "힌트" 격하 + guidance).
   wait/forget 의미론 + 공통 전제(팀/워크플로 도구·Agora `.mcp.json`) 단락.
6. **tool_shelf**: 참조 문서 단락으로만(실행 코드 생성은 Tier 2).
6-b. **다음 단계 (project.graph 기반)**: `compile_skill(skill, project=...)`이 `project.graph`에서 그 스킬 placement(skill_ref identity 일치)의 outgoing 전이를 모아 SKILL.md 본문 끝에 **"## 다음 단계"** 단락을 배출한다(버그 2 — 인보크/전이 문구 누락 해소). 형식: 스킬 타깃은 `- [<조건>] → \`<skill>\` 스킬을 인보크하라`, 에이전트 타깃은 `에이전트 \`X\`에게 위임하라` + **그 에이전트 placement의 outgoing을 한 단계 인라인**("위임 완료 후: [조건] → \`C\` 스킬을 인보크하라" — 에이전트는 별도 컨텍스트라 자기 .md에 호출자 지침을 담을 수 없으므로 호출자 스킬 쪽에 후속 지시를 둔다). 조건은 `_transition_condition`(트리거+가드) 재사용, 무가드·무트리거 전이는 "무조건". outgoing 0개면 단락 생략. **에이전트 .md / 로컬 스킬에는 다음 단계 단락 없음**(전역 스킬 + project 인수 있을 때만). EntryPoint outgoing(시작 스킬)은 v1에서 스킬별 단락에 영향 없음.
7. **에이전트**: `emit==FRONTMATTER`만 프론트매터, INVOCATION(max_turns/background/isolation)은 "호출 파라미터" 본문 단락,
   SETTINGS(hooks/mcp_servers)는 "요구 환경" 언급만(파일 생성은 WP-HOOK 예정).
8. **컴파일 게이트**: `Validator.validate_project`의 에러(`is_warning=False`) 1건이라도 있으면 거부(파일 미생성, errors 반환). 경고는 통과(warnings 동봉).
   게이트 강화 2종(파일 쓰기 전 산출 계획 단계): ① 산출 이름이 되는 컴포넌트(전역 스킬·에이전트·로컬 스킬) **및 프로젝트 이름**의 이름이
   `^[a-z0-9][a-z0-9-]*$` 불일치면 `compile_invalid_component_name` **에러로 승격** 거부 (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다). 프로젝트 이름은 plugin.json의 `name`(플러그인 식별자)이 되므로 동일 규약을 적용한다.
   ② 전체 산출 경로 집합에 중복이 있으면 `compile_output_path_conflict` 에러로 거부 + 충돌 경로/원인 컴포넌트 보고 (조용한 덮어쓰기 방지).
9. **plugin.json 매니페스트**: `compile_plugin_manifest(project)`가 `project.name`/`description`/`version`으로 `.claude-plugin/plugin.json`을 무조건 생성한다. 키 순서 `name`→`description`(빈 문자열이면 키 생략)→`version`.
10. **블랙보드 사용 지침 단락**: 프로젝트 최상위 블랙보드에 `class_definitions`가 1개 이상이면, 전역 `ProceduralSkill`(로컬 스킬 제외)의 tool_shelf 단락 뒤·"다음 단계" 단락 앞, 그리고 에이전트 `.md` 본문 마지막에 `_blackboard_section(project)`이 "## 공유 상태 (블랙보드)" 단락(`state/<ClassName>.json` 파일 목록 + 읽기-수정-쓰기 규칙)을 배출한다. 정의가 0개면 단락 생략.

출력은 결정적(같은 모델 → 같은 텍스트), LF 줄바꿈, UTF-8(BOM 없음). 텍스트 생성(`compile_skill`/`compile_agent`)은 파일시스템과 분리되어 문자열 단위 테스트 가능.

## 미구현 예정

- `compiler/` Tier 2: ToolExecution/ToolEvaluation 실행 래퍼(인자 이스케이프·shell 분기·success_condition), MCP 서버 실행 코드
- `hooks.json` / `.mcp.json` 설정 파일 생성 (WP-HOOK)
- CLI: 기존 Claude Code CLI 툴 연동 (플러그인 내 명시)
