# 플러그인 컴포넌트 모델 — 스킬·에이전트 종류, 필드 매트릭스, 진입 의미론

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 스킬 7종과 에이전트 2종

| 종류 | `kind` | 본질 | FSM·배치 |
|------|--------|------|---------|
| ProceduralSkill | `procedural_skill` | 메인 대화에서 그대로 도는 작업 지침 | 자체 FSM, 캔버스 상태 노드 |
| SyncForkSkill | `sync_fork_skill` | 서브에이전트에서 도는 단계 — `background: false`, 부른 쪽이 보고를 기다린다 (2026-09-17) | 절차형과 같다(배치·포트·전이·본문). 본문이 `config.agent` 서브에이전트의 작업 지시가 된다 |
| AsyncForkSkill | `async_fork_skill` | 서브에이전트에서 도는 단계 — `background: true`, 보고가 작업 알림으로 온다 (2026-09-17) | 〃 |
| DeclarativeSkill | `declarative_skill` | 배경 지식 | FSM 없음 |
| TransferSkill | `transfer_skill` | 전이 시 실행되는 보조 지침 | 자체 FSM 보유, 엣지 위 |
| ReferenceSkill | `reference_skill` | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| WrappedSkill | `wrapped_skill` | 다른 플러그인 스킬의 랩핑(WP-WR) | 본문 없음 — 정본은 config.source의 외부 스킬(런타임 참조). 배치·transfer_on은 procedural과 동일(단일 배치) |
| AgentDefinition | `agent` | 별도 컨텍스트의 작업자 — **워크플로 에이전트**(캔버스 노드) | **내부 FSM 퇴역(WP-AF)** — 절차는 본문, 결과 분기는 transfer_on |
| ForkAgent | `fork_agent` | fork 스킬의 **실행 기반** (2026-09-17) | fsm·포트 없음, **캔버스 배치 불가**. 산출은 워크플로 에이전트와 같은 `agents/<이름>.md` |

### 클래스 계층 — "구체 클래스가 구체 클래스를 상속하지 않는다"

```
PluginComponent(ABC)                      base.py  (name, description, abstract kind)
├── Skill(Skill, ABC)                     skill.py (when_to_use, id)
│   ├── StepSkill(Skill, WorkflowComponent, ABC)   # 절차형 계열 공통: fsm·config·body·transfer_on·call_agents
│   │   ├── ProceduralSkill(StepSkill)             kind "procedural_skill"
│   │   └── ForkSkill(StepSkill, ABC)              # 추상 — fork 공통. 인스턴스화 금지
│   │       ├── SyncForkSkill(ForkSkill)           kind "sync_fork_skill"
│   │       └── AsyncForkSkill(ForkSkill)          kind "async_fork_skill"
│   ├── WrappedSkill(Skill, WorkflowComponent)     kind "wrapped_skill"
│   ├── DeclarativeSkill / TransferSkill / ReferenceSkill
└── Agent(PluginComponent, ABC)           agent.py  # 추상 — config·안정 id 공통
    ├── AgentDefinition(Agent, WorkflowComponent)  kind "agent"
    └── ForkAgent(Agent)                            kind "fork_agent"
```

- `StepSkill`은 예전의 `ForkSkill ⊂ ProceduralSkill` 상속이 지탱하던 **"워크플로 단계 스킬"** 판정의 새 이름이다.
  `isinstance(x, StepSkill)` = "단계(fork 포함)", `isinstance(x, ProceduralSkill)` = "절차형만", `isinstance(x, ForkSkill)` = "fork 2종".
  `(StepSkill, WrappedSkill)` 튜플이 "배치되는 스킬"을 묻는 자리에 쓰인다.
- 에이전트 쪽도 **같은 축으로 두 판정**이다: "에이전트 컴포넌트 전반"(어느 리스트에 담는가 / 어느 컴파일러로
  보내는가 / 어느 매트릭스·에디터를 쓰는가)은 `Agent`, "그래프에 **배치된 노드**가 에이전트인가"(위임 문구·호출
  계약·캔버스·MCP 연결 규칙)는 `AgentDefinition`이다 — ForkAgent는 배치 불가라 후자에서 자연 제외된다.
  `view/commands/component_commands._bucket`이 `Agent`를 보는 덕에 두 종류 모두 `project.agents`에 들어간다
  (이 판정이 `project.skills`로 새면 저장·레지스트리·산출이 전부 어긋난다).
- ABC 규칙(CLAUDE.md): `StepSkill`·`ForkSkill`·`Agent`는 `kind`를 정의하지 않아 추상으로 남는다
  (`PluginComponent.kind`가 abstractmethod).
- dataclass 필드 순서 실측(2026-09-17): `config`를 `StepSkill`에서 선언해야 `…, when_to_use, config, body,
  transfer_on, call_agents` 순서가 유지되고, `body`를 `Agent`에 올리면 `AgentDefinition`에서 body가
  execution_policy 앞으로 올라가 순서가 깨진다 — 그래서 `body`는 두 구체 에이전트가 각자 선언한다.

### 배치 가능 판정 (`model/plugin/placement.py`)

**두 판정이다** — 하나로 합치면 참조 스킬 경로가 죽는다.

| 함수 | 질문 | True |
|------|------|------|
| `is_state_placeable(c)` | 그래프에 **SimpleState 노드**로 놓을 수 있는가 | `StepSkill`(절차형·fork 2종), 용도가 reference가 **아닌** `WrappedSkill`, `AgentDefinition` |
| `is_canvas_placeable(c)` | 캔버스에 놓을 수 있는가(상태 **또는** 참조 노드) | 위 + `is_reference_usage`(ReferenceSkill·용도 reference 랩핑) |

캔버스 드롭(`scene.py`)·레지스트리 드래그·"여기에 만들기"(`creation.NO_PLACE_KINDS`)·MCP `place_component`가
전부 이것을 부른다(음성 목록 3벌 → 양성 판정 2개, 원칙 1). `DeclarativeSkill`·`TransferSkill`·`ForkAgent`는 False다.
같은 모듈의 `fork_skills_using(agent, project)`는 **fork 역참조의 단일 진실**이다 — 에이전트 편집기의
"🍴 사용하는 fork 스킬" 패널·삭제 확인 다이얼로그·MCP `delete_component`의 `still_referenced_by`·`get_component`의
`used_by_fork_skills`·컴파일러의 fork 에이전트 "## Invocation Contract"가 전부 같은 목록을 말한다
(컴파일러는 뷰를 임포트할 수 없으므로 실체가 모델에 있어야 한다).

## SKILL_FIELD_MATRIX / AGENT_FIELD_MATRIX

`SKILL_FIELD_MATRIX`의 키는 **7종**이다 — `procedural`, `sync_fork`, `async_fork`, `declarative`, `wrapped`,
`transfer`, `reference`. `AGENT_FIELD_MATRIX`의 키는 **2종** — `agent`, `fork_agent`.
매트릭스에 없는 필드는 그 종류에 **없다**(부재 = 비적용).

- `context`·`agent`·`background` 세 행은 **fork 두 표에만** 있다(사용자 확정 2026-09-17). `context`는
  `FieldRule(F, fixed_value="fork")`, `background`는 `FieldRule(F, fixed_value=False|True)` — 종류가 곧 값이라
  편집기에 노출하지 않고 config에도 두지 않는다. `agent`는 REQUIRED(기본 `general-purpose`도 명시 배출).
- fork 표에는 `allowed_tools`가 **없다** — fork에서는 에이전트 도구가 이겨 스킬 쪽이 도구를 늘리지 못한다(실측).
- `fork_agent` 표 = `agent` 표에서 `background`·`isolation` 행을 뺀 것이다(`ForkAgentConfig`와 같은 사실).
  `MARKETPLACE_UNSUPPORTED_AGENT_FIELDS`·`agent_field_supported`는 **평면 유지** — 두 종류 모두 `agents/*.md`로
  나가므로 플러그인 제약이 똑같이 걸린다.

**표를 고르는 규칙의 실체는 `field_matrix.matrix_for(component)` 하나다 (단일 진실).** 키는 `component.config.kind`
이고(문자열 수술 금지), 컴파일러(`emit/agent.py`·`_skill_kind_key`)·MCP(`props.py`)·편집기
(`view/editors/kind_matrix.matrix_for` — 위젯 표를 짝지어 주는 **얇은 어댑터**)가 전부 이 함수를 부른다.
config가 없거나 kind가 어느 표에도 없으면 **`ValueError`로 이유(선택지 목록)를 말한다** — 예전의
`.get(kind, {})` 폴백은 한쪽 표면을 조용한 빈 폼으로 만들었다(원칙 5).

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility   # REQUIRED / OPTIONAL / DEFAULT / FIXED
    fixed_value: Any = None       # FIXED일 때 컴파일러가 강제할 출력값 (enum)
    default_value: Any = None     # 위젯 초기 표시용 (단일 진실은 config 선언 기본값)
    emit: FieldEmit = FieldEmit.FRONTMATTER  # 컴파일러 배출 위치 (FRONTMATTER/BODY/SETTINGS)
```

`FieldEmit`의 목적지는 **FRONTMATTER/BODY/SETTINGS 셋뿐이다**. WP-FF에서 `max_turns`/`background`/`isolation`이
프론트매터로 올라가면서 "호출 파라미터" 본문 단락과 그 emit 함수(`_invocation_section_agent`)가 삭제됐고,
소비자 없이 남아 있던 `INVOCATION` 멤버와 `frontmatter_panel`의 그룹 분기도 퇴역했다(WP-0c — 원칙 7).

`field_matrix.py`는 순수 모델(Qt 무관)이다. 편집 위젯 매핑은 view 측 `daedalus/view/editors/field_widgets.py`의 `FIELD_WIDGETS: dict[SkillField, type[QWidget]]`(1차원, kind 무관)과 `AGENT_FIELD_WIDGETS: dict[AgentField, type[QWidget]]`로 분리되어 있다. 프론트매터 키는 `SkillField.frontmatter_key` property가 제공한다 (kebab-case, `WHEN_TO_USE`는 None — description/본문 합류는 컴파일러 정책). `AgentField.frontmatter_key`는 **camelCase**(`permissionMode`/`disallowedTools`/`maxTurns`/`mcpServers`, WP-LA에서 확정) — 스킬 프론트매터의 kebab-case와 **규약이 다르므로 한쪽을 보고 다른 쪽을 유추하면 안 된다**. 이전에는 케이싱 미확정이라 kebab-case를 잠정값으로 썼는데, 그 키들은 CC가 인식하지 못해 조용히 무시된다(CC 공식 sub-agents 문서 필드 표 기준, 2026-08 확인). FIXED 필드는 편집기 비노출이며 `fixed_value`는 컴파일러 출력 시 강제(config에 미기록). `AGENT_FIELD_MATRIX`는 에이전트 종류별 표 2개(`agent`/`fork_agent`)다.

**표와 config는 같은 사실을 말한다 (2026-09-18).** 표에 있는 **비-FIXED** 필드는 그 종류의 config 클래스에 실제로 선언돼 있어야 한다 — 없으면 편집기가 위젯을 그려 주고 그 편집이 아무 데도 남지 않는 반면(유령 인스턴스 속성 → 저장 한 번에 소멸), MCP `list_component_fields`는 `hasattr`로 건너뛰어 **같은 종류에 대해 GUI와 MCP가 다른 필드 목록**을 말한다(원칙 1·2·5). `tests/model/plugin/test_field_matrix.py::test_every_editable_matrix_field_exists_on_the_config`가 전 종류를 전수 고정한다. 이 규칙으로 걸린 세 행(`declarative`/`reference`의 `shell`, `reference`의 `disable_model_invocation`)은 표에서 **삭제**했다 — 두 config는 그 필드를 선언한 적이 없고 직렬화도 그 키를 왕복하지 않는다(`ser.py`의 declarative/reference 분기).

## FieldType (통합 타입)

```python
class FieldType(Enum):
    STRING = "string"   # Variable / DynamicField 공용
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"
```

- `VariableType`과 `DynamicFieldType`을 통합한 단일 열거형
- `Variable.field_type: FieldType`, `DynamicField.field_type: FieldType`
- **블랙보드 필드는 스칼라 4종만**(WP-BT, 사용자 확정): `BLACKBOARD_FIELD_TYPES = (STRING, INT, FLOAT, BOOL)` — 컨테이너 형상은 CollectionType(none/list/set)이 전담한다("문자열 목록" = STRING × LIST). 편집기 콤보는 이 4종만 노출(legacy 값은 "(legacy)" 표시 유지), `invalid_blackboard_field_type` 경고가 구버전 필드를 짚는다. Variable은 종전 그대로 전 멤버 사용 가능.
- 구 `NUMBER` 멤버는 RF-1b에서 **삭제** — v1 파일의 `"number"`는 로드 시 `FLOAT`으로 마이그레이션된다(`_migrate_v1`). 매핑 정본은 `blackboard.py`의 `FIELD_TYPE_TO_JSON_SCHEMA`(INT→integer, FLOAT→number).

## 진입 의미론 tri-state + 진입점 프리셋 (A8)

**두 필드는 tri-state다:** `StepSkillConfig`(절차형·fork 2종 공통)/`WrappedSkillConfig`/`DeclarativeSkillConfig`의
`user_invocable: bool | None = None`, `disable_model_invocation: bool | None = None`.
`None` = **미지정**(프론트매터 키 생략 → CC 기본값 위임), `True`/`False` = 명시 지정.
순수 bool이면 "기본값을 쓴다"와 "기본값과 같은 값을 못 박았다"가 구분되지 않아,
프리셋 "일반 상태로"(두 필드 미지정)를 표현할 수 없었다.

- **컴파일은 기존 규칙 그대로다** — "OPTIONAL 값이 선언 기본값과 같으면 생략"에서
  선언 기본값이 None이 되므로 None은 생략되고 명시 True/False는 발행된다.
  `user-invocable: true`가 나가는 것은 **정상**이다(사용자가 진입점으로 못 박은
  선언). `_emit_skill_field`가 `value is None`을 이미 생략 처리하므로 emit 경로는
  변경 없음. FIXED 종류(transfer/reference)는 config를 읽지 않아 무영향.
- **직렬화:** 저장된 true/false는 **그대로 왕복**한다(스크럽 금지 — 사용자가 명시
  지정한 값이다). 키 부재 → None. `_deser_config`가 `d.get(...)`의 기본값을 뺀 것이 전부.
- **검증:** `mid_chain_user_invocable`(A3)의 판정은 **실효값 기준**이다 — `None`은
  키가 생략되어 CC 기본 **true**로 동작하므로 경고 대상이고(메시지에 "미지정(생략 시
  CC 기본값 true)" 병기), **명시 `False`만 통과**한다. 설계에서 선언하지 않았다는
  이유로 넘어가면 실제로는 `/스킬`로 시작할 수 있는 중간 노드가 조용히 남는다.
- **편집기:** `_OptionalRow` 체크 해제 = `_declared_default` → None(미지정)이라
  자연 적합. 다만 **명시 `False`도 "지정"**이므로 `_is_field_set`이 그 경우를
  살린다(선언 기본값이 None인 tri-state 필드에 한해 — `background: bool = False`
  처럼 선언 기본값이 False인 필드는 종전대로 미지정 취급).
- **MCP:** `set_component_field(..., value=None)` = 미지정으로 되돌리기.
  `bool | None` 등 **Optional 선언인 필드에서만** 받는다(아무 필드에나 null을
  허용하면 non-Optional 필드에 None이 들어가 타입 계약이 깨진다).

**진입점 프리셋 4종** — `view/actions/entrypoint.py`가 실체이고 캔버스 노드 우클릭
"진입점 설정" 서브메뉴와 스킬 에디터 프론트매터 "진입 설정" 콤보가 **같은 함수를
공유**한다:

| 프리셋 | user_invocable | disable_model_invocation | 뜻 |
|---|---|---|---|
| 진입점으로 | True | False | 유저도 모델도 시작 가능 |
| 유저 전용 진입점으로 | True | True | 슬래시로만 시작 |
| 순수 상태로 | False | False | 체인 중간 — 모델 인보크만 |
| 일반 상태로 | None | None | 미지정 — CC 기본값 위임 |

- 두 필드를 **따로 두지 않고 세트로 고르게 하는 이유**: 따로면 (False, True) 같은
  "아무 데서도 부를 수 없는 죽은 노드"를 실수로 만들 수 있고, 프론트매터만 봐서는
  무엇을 의도했는지 알기 어렵다.
- **적용은 `SetAttrCmd` 2개를 `MacroCommand`로 묶은 1 undo 단위**다 — 한 필드씩
  되돌아가면 중간에 그 의미 없는 조합을 거친다. 같은 프리셋을 다시 고르면
  아무것도 하지 않는다(값이 같은데 커맨드를 쌓으면 Ctrl+Z가 빈 단계를 센다).
- **노출은 매트릭스에서 두 필드가 OPTIONAL인 종류에만**(`supports_entry_presets`).
  FIXED 종류(transfer/reference)에 걸면 컴파일이 `fixed_value`를 강제해 "설정했는데
  아무 일도 일어나지 않는" 상태가 된다. 에이전트는 두 필드 자체가 없다.
- 어느 프리셋에도 맞지 않는 조합(반쪽만 지정)은 체크가 하나도 없고 콤보는
  "(직접 지정)"을 보인다 — 프리셋은 지름길이지 표현 가능한 상태의 전부가 아니다.
- **캔버스 뱃지:** `node_badges.badges_for`가 진입 의미론을 **한 뱃지로** 합친다 —
  명시 True면 🚪("진입점 — /스킬로 시작 가능", disable까지 True면 "유저 전용"
  병기), 명시 False면 ⛔. 미지정은 선언 기본값과 같아 뱃지 없음(노이즈 방지 원칙).
  🚫(모델 자동 호출 금지)는 🚪가 이미 그 사실을 말했으면 생략한다. A3 경고 규칙의
  시각적 짝이다.
- **캔버스 테두리(2026-09-12):** 유저 발동 진입점(🚪와 같은 기준 — `user_invocable`
  명시 True, `entrypoint.is_user_entry`)은 **외곽선만** 금색(`node_item._USER_ENTRY_BORDER`)
  으로 그린다. 배경·헤더 글자는 종류 색 그대로다(종류 구분을 잃지 않는다).

## ComponentConfig 계층

```
ComponentConfig(ABC)                              # model, effort, hooks 공통 필드
├── SkillConfig(ABC)                              # argument_hint, allowed_tools, paths
│   ├── StepSkillConfig(ABC)                      # disable_model_invocation·user_invocable(tri-state, A8), shell
│   │   ├── ProceduralSkillConfig                 kind "procedural"
│   │   └── ForkSkillConfig(ABC)                  # 추상 — + agent (기본 "general-purpose")
│   │       ├── SyncForkSkillConfig               kind "sync_fork"
│   │       └── AsyncForkSkillConfig              kind "async_fork"
│   ├── WrappedSkillConfig                        # source, usage, enabled (WP-WR)
│   ├── DeclarativeSkillConfig
│   ├── TransferSkillConfig
│   └── ReferenceSkillConfig
└── AgentConfigBase(ABC)                          # tools, disallowed_tools, permission_mode, max_turns,
    │                                             #   skills, mcp_servers, memory
    ├── AgentConfig                               kind "agent" — + background, isolation, color
    └── ForkAgentConfig                           kind "fork_agent" — + color (background·isolation 없음)
```

- **`config.kind`가 곧 매트릭스 키다**(단일 진실) — 컴파일러·MCP·편집기가 `matrix_for`로 같은 표를 고른다.
- `ForkSkillConfig`가 **추상**인 이유: 동기/비동기를 가르는 `background`는 매트릭스 전용 FIXED 필드라 config에
  두지 않는다. 즉 "어느 fork인가"는 구체 클래스(= `kind`)만이 답한다.
- `color`를 `AgentConfigBase`에 올리지 않는 이유: 두 구체 클래스가 각자 **마지막에** 선언해야 `AgentConfig`의
  필드 순서가 종전(`… memory, background, isolation, color`)과 같아진다(2026-09-17 실측).
- `ForkAgentConfig`에 `isolation`이 **아예 없는** 근거는 아래 실측 표 참조 — 없는 필드를 두면 설계자가 걸어 둔
  제약이 조용히 사라진다(원칙 5).

## fork 스킬 2종 + fork 에이전트 (사용자 확정 2026-09-13 / 2종 분리·종류 분리 2026-09-17)

CC의 `context: fork` 스킬은 SKILL.md 본문을 작업 지시로 삼아 `agent` 서브에이전트를 띄운다. 예전에는
절차형·선언형에 `context`·`agent` 필드가 따로 있어서, fork로 두고 agent를 비우거나 틀려도 아무도 짚지 않았고
CC는 **조용히 범용 에이전트로 돌렸다**. 그래서 fork를 **별도 스킬 종류**로 떼어 냈다 — 나머지 스킬은 fork·agent·
background를 지정할 수 없다.

### 왜 두 종류인가 (사용자 확정 2026-09-17)

`background`는 fork의 실행 형상을 통째로 바꾸는 값이다 — `false`면 부른 쪽이 보고를 기다리고(동기), `true`면
보고가 작업 알림으로 뒤늦게 온다(비동기). 그런데 예전에는 단일 fork 종류가 `background: false`만 배출해
"비동기 fork"라는 표현 수단이 아예 없었고, **미배치 fork는 키 자체가 안 나가 CC 기본값(백그라운드)으로** 돌았다.
값을 편집 필드로 열면 매트릭스·산출·검증·문구가 전부 런타임 분기가 되므로, 종류로 갈라
**`background`를 매트릭스 FIXED 필드**로 고정했다 — 노드 종류가 정하는 프론트매터(`context`·`background`)는
편집기에 노출하지 않는다.

- **모델:** `StepSkill` → `ForkSkill`(추상) → `SyncForkSkill`/`AsyncForkSkill`. 배치·포트·전이·본문 규칙은
  절차형과 같고, "fork인가"는 `isinstance(x, ForkSkill)`다. 새 필드는 `ForkSkillConfig.agent:
  str = "general-purpose"` 하나. 에이전트를 **소유하지 않는** 가벼운 종류다 — 컴파일러가 fork 때문에 에이전트
  파일을 새로 만드는 일은 없다.
- **fork 에이전트 = 별도 컴포넌트 종류(`ForkAgent`).** 전제는 "FSM 노드로 쓰이는 에이전트와 fork 스킬의
  실행 기반으로만 쓰이는 에이전트는 다른 물건"이다. 예전에는 "**배치되지 않은** 워크플로 에이전트"로 겸직을
  막았는데, 그 판정은 배치를 지우기만 하면 조용히 겸직이 생겼다(원칙 5). 이제 종류가 다르므로 워크플로
  에이전트를 fork 스킬의 `agent`로 지목하면 에러(`fork_agent_wrong_kind`)이고, 배치 여부는 보지 않는다.
  ForkAgent에는 fsm·transfer_on·call_agents·execution_policy·배치가 **없다** — 결과 분기는 그를 부르는
  fork 스킬의 보고 양식(`EXIT: … / NEXT: …`)이 정한다.
- **fork 에이전트 후보 세 종류** (`view/actions/fork_skill.fork_agent_choices` — 편집기 피커·MCP 검증·
  `create_skill(fork_agent=)`가 공유): ① 내장 `general-purpose`/`Explore`/`Plan`
  (`config.BUILTIN_FORK_AGENTS`) ② 사용 선언한 외부 플러그인의 에이전트(`플러그인:이름`, 카탈로그
  `used_plugin_agents`) ③ 프로젝트의 **ForkAgent 전부**(이름순). `validate_fork_agent`는 워크플로 에이전트
  이름을 받으면 그 사실을 이름으로 말하고 대안을 제시한다(원칙 5).
- **전환은 3-way다** — `procedural` ↔ `sync_fork` ↔ `async_fork`(`actions/fork_skill.KINDS`). 명시 액션이고
  (편집기 `kind_switch_row`의 버튼 3개·캔버스 우클릭 "종류 전환" 서브메뉴·MCP `convert_skill(to=)`), 실체는
  `convert_skill_kind` 하나다. 객체를 새로 만들지 않고 `config`와 `__class__`를 바꾸는 `SetAttrCmd` 2개를
  `MacroCommand` **1 undo**로 묶는다 — 그래프 참조·본문 문서·열린 탭이 끊기지 않는다(세 클래스의 필드
  레이아웃이 같아 가능하다).
  - 필드 복사는 **대상 config 클래스 기준**이다: `agent`는 `ForkSkillConfig`에만 있으므로 부모
    (`StepSkillConfig`) 기준으로 복사하면 sync↔async 전환에서 `agent`가 조용히 기본값으로 리셋된다
    (`dropped`에도 안 잡힌다).
  - 드롭은 **쌍**이 정한다: procedural → fork는 `allowed_tools`(fork에서 효과 없음), fork → procedural은
    `agent`. **sync ↔ async는 드롭이 없다**(`agent` 보존, `dropped == {}`).
  - 열려 있던 편집 탭의 프론트매터 폼과 레지스트리는 **같은 매크로 안에서** 다시 그린다
    (`view/commands/surface_commands.resync_bracket` 한 쌍을 매크로 양 끝에) — 재동기가 액션 함수에 있으면
    undo에 걸리지 않아, 되돌린 뒤에도 전환 후의 표로 그려진 폼이 남고 그 편집을 스테일 가드가 조용히
    버린다(2026-09-18).
- **마이그레이션 — format 2 유지, 내용 스니핑**(`migrate_skill_context` 선례). `serialize.migrate`의
  `needs_fork_split_migration`/`migrate_fork_split`:
  1. `kind: "fork_skill"` → `"sync_fork_skill"`, `config.kind: "fork"` → `"sync_fork"`. **배치된** fork는
     종전 산출이 `background: false`였으므로 동기가 곧 종전 동작이라 경고가 없다. **미배치** fork는 키가 없어
     CC 기본값(백그라운드)으로 돌았으므로 동작이 바뀐다 — 경고 1건("비동기가 필요하면 종류를 바꾸라").
  2. **에이전트 재분류**: 그래프 배치 id 집합에 없고(`graph.states[*].skill_ref`) 어떤 fork 스킬의
     `config.agent`가 이름으로 가리키는 에이전트 → `kind`/`config.kind`를 `fork_agent`로 바꾸고
     fsm·transfer_on·call_agents·execution_policy·reference_placements·graph_layout·edge_layout·
     config.background·config.isolation 키를 **드롭**한다(퇴역 개념의 잔재 금지, 원칙 7). 경고 1건.
     배치 + 참조는 건드리지 않는다(`fork_agent_wrong_kind`가 짚는다), 미배치 + 미참조는 워크플로 에이전트 그대로.
  3. 순서는 `_migrate_v1` 안에서 `migrate_skill_context` **뒤**다. 모든 dict 접근이 방어적이다 — pseudo
     상태에는 `skill_ref` 키가 아예 없고 `graph`·`config` 키 부재는 구버전 파일의 정상 입력이다.
  - 구 `SkillContext` enum·절차형/전이형의 `context`·`agent` 필드 퇴역은 종전대로
    `migrate_skill_context`가 흡수한다(절차형 `context: fork` → fork 스킬 / inline 키 드롭 / 전이형 fork는 경고 후 드롭).
- **미지 kind는 `ValueError`다** — `_deser_skill`/`_deser_config`/`_deser_agent`가 모르는 kind를 조용히
  DeclarativeSkill로 강등하지 않는다(`_deser_tool` 선례, 원칙 5).
- **편집기·캔버스:** 동기 fork는 구리색 `#c07a3a` 🍴, 비동기 fork는 진한 구리 `#8a5a2a` 🍴⏳
  (사용자 확정 2026-09-13 "색은 아예 별도 색상으로"). 레지스트리 탭은 🍴 SYNC FORK / 🍴⏳ ASYNC FORK /
  🧩 FORK AGENTS 셋이 늘었고 — 섹션 키·`tab_labels`·`_ICON` **세 표가 동시에** 커버해야 한다
  (`tab_labels[kind]`가 맨 첨자라 누락 시 레지스트리 패널 전체가 안 뜬다. 커버리지 테스트가 고정) —
  🧩 탭의 항목은 드래그 불가다. AGENT 피커(`ForkAgentComboBox` — 후보 밖 저장값도 보인다), 안내문
  "도구는 fork 에이전트가, 모델·effort는 이 스킬 값이(비우면 fork 에이전트 값)". ForkAgent 편집 탭은
  🧩 접두를 달고 출력/호출 포트 패널 대신 **"🍴 사용하는 fork 스킬"** 읽기 전용 패널을 보인다.
- 산출은 `compiler.md` 7-b·20·21번, 검증은 `validation.md`의 `fork_*`·`unused_fork_agent` 규칙,
  MCP는 `mcp-server.md`.

**실측 사실 (CC 2.1.268 — 실행 파일 + `claude -p` 실행 후 기록 파일의 실제 값으로 판정, 2026-09-13)**

| 항목 | 사실 |
|------|------|
| 스키마 | SKILL.md에 `context: inline\|fork`, `agent`, `background`, `hooks`가 있다 |
| `background` | fork 전용. 기본은 백그라운드(부른 쪽이 기다리지 않고 알림으로 보고). `false`면 부른 쪽이 기다린다. **`true`여도 강제로 인라인(동기) 실행되는 경우가 넷 있다**(공식 문서 확인 2026-09-17): ① 비대화 `claude -p` / Agent SDK 실행 ② `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` ③ 같은 스킬이 아직 도는 중의 재진입 호출 ④ 스케줄 작업이 발화한 실행. 그래서 산출 문구가 "메인은 기다리지 않는다"고 **단정하지 않는다** — 단정하면 인라인으로 돌아온 경우 메인이 오지 않을 작업 알림을 기다린다(`compiler.md` 20번) |
| agent 해석 | agentType **정확 일치**(대소문자 포함). 없으면 **조용히 general-purpose로 실행**(디버그 로그만) |
| 이름 형식 | 플러그인 에이전트는 `플러그인:이름`만 찾힌다. LOCAL(`.claude/agents`)은 `이름`으로 된다 |
| model·effort | 스킬에 값이 있으면 **스킬이 이긴다**(effort는 값을 뒤바꿔 두 번 확인). 스킬이 비면 **에이전트 값**이 쓰인다 |
| tools | **에이전트가 이긴다** — 스킬 `allowed-tools`는 도구를 늘리지 못한다 |
| 전달 구조 | 에이전트 본문 → 시스템 프롬프트, 스킬 본문 → 작업 지시. `$ARGUMENTS`는 치환된다 |
| fork 에이전트 설정 | `skills:` 프리로드·`maxTurns`는 **적용**, `isolation: worktree`는 **적용되지 않는다** (CC 2.1.268 실측 2026-09-13 → **CC 2.1.274 재실측 2026-09-18에서 동일** — 아래 재실측 기록). 그래서 `ForkAgentConfig`에 `isolation` 필드가 없고 경고 `fork_agent_isolation_ignored`는 퇴역했다 |
| 내장 이름 | `general-purpose` / `Explore` / `Plan` (`statusline-setup`도 있으나 후보에서 뺀다) |
| 도구 0개 에이전트 | 이 환경에 없는 도구만 준 에이전트로는 fork가 아무 일도 하지 못했다 |

**isolation 재실측 (CC 2.1.274, 2026-09-18 — 원칙 8: 공식 문서 뒷받침이 없는 유일한 항목이라, 되돌리기
비싼 결정(매트릭스 행·config 필드 삭제)을 얹기 전에 현재 설치 버전에서 다시 쟀다)**

| 경로 | 결과 |
|------|------|
| **FORK** (`claude -p "/fkiso"` — 에이전트 `isoprobe`에 `isolation: worktree`, 스킬 `fkiso`는 `context: fork`) | `pwd` = 프로브 디렉토리 그대로, `git rev-parse --show-toplevel` = 같은 경로, `git worktree list` = **항목 1개**(HEAD 65d2b58, master) → 워크트리가 만들어지지 않았다. **isolation 미적용** |
| **직접 스폰** (`claude -p "Use the isoprobe subagent (Agent tool, subagent_type isoprobe) …"`) | `pwd` = `…/.claude/worktrees/agent-ac9210af4c0c58fec`, `show-toplevel`도 그 경로, `git worktree list` = **항목 2개**(두 번째가 `worktree-agent-ac9210af4c0c58fec` 브랜치로 locked) → **isolation 적용** |

- 판정: 같은 에이전트가 **직접 스폰에서는 적용, fork 실행에서는 미적용**이다 — 2026-09-13(CC 2.1.268) 측정과 일치.
- 격리: 프로브 파일은 전부 세션 스크래치패드의 `iso-probe` 임시 디렉토리에서만 만들고 커밋했다.
  `C:\Users\Jooyo\source\Daedalus` 밑의 파일은 하나도 바뀌지 않았다.
- **결정: `ForkAgentConfig`에서 `isolation` 필드를 뺀 상태를 유지한다 — 오케스트레이터 확정 (2026-09-18).**
  재실측이 2026-09-13과 같은 결과를 냈으므로 필드와 경고(`fork_agent_isolation_ignored`)를
  되살릴 근거가 없다(원칙 7 — 퇴역 개념은 흔적 없이).
