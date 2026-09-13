# 플러그인 컴포넌트 모델 — 스킬·에이전트 종류, 필드 매트릭스, 진입 의미론

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 스킬과 에이전트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| ForkSkill | 서브에이전트에서 도는 작업 지침 (2026-09-13) | 절차형의 하위 종류 — 배치·포트·전이는 같고, 본문이 `config.agent` 서브에이전트의 작업 지시가 된다(아래 "fork 스킬") |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| TransferSkill | 전이 시 실행되는 보조 지침 | 자체 FSM 보유 |
| ReferenceSkill | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| WrappedSkill | 다른 플러그인 스킬의 랩핑(WP-WR) | 본문 없음 — 정본은 config.source의 외부 스킬(런타임 참조). 배치·transfer_on은 procedural과 동일(단일 배치) |
| AgentDefinition | 별도 컨텍스트의 작업자 | **내부 FSM 퇴역(WP-AF)** — 절차는 본문, 결과 분기는 transfer_on |

## SKILL_FIELD_MATRIX

스킬 유형(procedural, fork, declarative, transfer, reference, wrapped)별로 프론트매터 필드의 `FieldRule`을 정의하는 매트릭스. 매트릭스에 없는 필드는 그 종류에 없다 — `context`·`agent`는 fork 전용이고, fork에는 `allowed_tools`가 없다.

```python
@dataclass
class FieldRule:
    visibility: FieldVisibility   # REQUIRED / OPTIONAL / DEFAULT / FIXED
    fixed_value: Any = None       # FIXED일 때 컴파일러가 강제할 출력값 (enum)
    default_value: Any = None     # 위젯 초기 표시용 (단일 진실은 config 선언 기본값)
    emit: FieldEmit = FieldEmit.FRONTMATTER  # 컴파일러 배출 위치 (FRONTMATTER/BODY/INVOCATION/SETTINGS)
```

`field_matrix.py`는 순수 모델(Qt 무관)이다. 편집 위젯 매핑은 view 측 `daedalus/view/editors/field_widgets.py`의 `FIELD_WIDGETS: dict[SkillField, type[QWidget]]`(1차원, kind 무관)과 `AGENT_FIELD_WIDGETS: dict[AgentField, type[QWidget]]`로 분리되어 있다. 프론트매터 키는 `SkillField.frontmatter_key` property가 제공한다 (kebab-case, `WHEN_TO_USE`는 None — description/본문 합류는 컴파일러 정책). `AgentField.frontmatter_key`는 **camelCase**(`permissionMode`/`disallowedTools`/`maxTurns`/`mcpServers`, WP-LA에서 확정) — 스킬 프론트매터의 kebab-case와 **규약이 다르므로 한쪽을 보고 다른 쪽을 유추하면 안 된다**. 이전에는 케이싱 미확정이라 kebab-case를 잠정값으로 썼는데, 그 키들은 CC가 인식하지 못해 조용히 무시된다(CC 공식 sub-agents 문서 필드 표 기준, 2026-08 확인). FIXED 필드는 편집기 비노출이며 `fixed_value`는 컴파일러 출력 시 강제(config에 미기록). `AGENT_FIELD_MATRIX`는 에이전트 전용 1차원 매트릭스.

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

**두 필드는 tri-state다:** `ProceduralSkillConfig`/`DeclarativeSkillConfig`의
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
ComponentConfig(ABC)          # model, effort, hooks 공통 필드
├── SkillConfig(ABC)          # argument_hint, allowed_tools, paths
│   ├── ProceduralSkillConfig # disable_model_invocation·user_invocable(**tri-state**, A8), shell
│   │   └── ForkSkillConfig   # + agent (기본 "general-purpose")
│   ├── WrappedSkillConfig    # source, usage, enabled (WP-WR)
│   ├── DeclarativeSkillConfig
│   ├── TransferSkillConfig
│   └── ReferenceSkillConfig
└── AgentConfig               # tools, permission_mode, skills, isolation 등
```

## fork 스킬 (사용자 확정 2026-09-13)

CC의 `context: fork` 스킬은 SKILL.md 본문을 작업 지시로 삼아 `agent` 서브에이전트를 띄운다. 예전에는
절차형·선언형에 `context`·`agent` 필드가 따로 있어서, fork로 두고 agent를 비우거나 틀려도 아무도 짚지 않았고
CC는 **조용히 범용 에이전트로 돌렸다**. 그래서 fork를 **별도 스킬 종류**로 떼어 냈다 — 나머지 스킬은 fork·agent를
지정할 수 없다.

- **모델:** `ForkSkill(ProceduralSkill)` / `ForkSkillConfig(ProceduralSkillConfig)`. 절차형의 하위 클래스라
  배치·포트·전이·본문 규칙이 같고, fork만 달라야 하는 곳은 `ForkSkill`을 **먼저** 검사한다. 새 필드는
  `agent: str = "general-purpose"` 하나. 매트릭스 `"fork"`: `context` FIXED `"fork"`, `agent` REQUIRED,
  `allowed_tools` 없음(fork에서는 에이전트 도구가 이긴다). 에이전트를 **소유하지 않는** 가벼운 종류다 — 컴파일러가
  에이전트 파일을 새로 만드는 일은 없다.
- **퇴역:** `SkillContext` enum, 절차형·전이형의 `context`/`agent` 필드. 구파일은
  `serialize.migrate.migrate_skill_context`가 흡수한다 — 절차형 `context: fork` → fork 스킬(agent가 비면
  `general-purpose`, `allowed_tools`는 버리고 경고) / inline 키는 조용히 드롭 / 전이형 fork는 경고 후 드롭.
  format 2 파일에도 적용된다(`needs_skill_context_migration` 게이트).
- **fork 에이전트 세 종류** (`view/actions/fork_skill.fork_agent_choices` — 편집기 피커와 MCP 검증이 공유):
  ① 내장 `general-purpose`/`Explore`/`Plan`(`config.BUILTIN_FORK_AGENTS`) ② 사용 선언한 외부 플러그인의
  에이전트(`플러그인:이름`, 카탈로그 `used_plugin_agents`) ③ **캔버스에 배치되지 않은** 프로젝트 에이전트.
  배치된 에이전트는 워크플로 단계라 fork 에이전트를 겸하면 캔버스에 안 보이는 연결("점프")이 생겨 뺀다.
- **전환:** 절차형 ↔ fork는 명시 액션이다(편집기 버튼 `kind_switch_row`·캔버스 우클릭·MCP `convert_skill`, 실체
  `convert_skill_kind`). 객체를 새로 만들지 않고 `config`와 `__class__`를 바꾸는 `SetAttrCmd` 2개를
  `MacroCommand` **1 undo**로 묶는다 — 그래프 참조·본문 문서·열린 탭이 끊기지 않는다. 버린 값(fork로:
  `allowed_tools`, 절차형으로: `agent`)은 `dropped`로 보고한다. 필드 구성은 탭을 닫았다 열면 바뀐다.
- **편집기·캔버스:** 구리색 `#c07a3a` 노드(🍴), 레지스트리 🍴 FORK 탭, AGENT 피커(`ForkAgentComboBox` — 후보 밖
  저장값도 보인다), 안내문 "도구는 fork 에이전트가, 모델·effort는 이 스킬 값이(비우면 fork 에이전트 값)".
- 산출은 `compiler.md` 20번, 검증은 `validation.md`의 `fork_*` 규칙.

**실측 사실 (CC 2.1.268 — 실행 파일 + `claude -p` 실행 후 기록 파일의 실제 값으로 판정, 2026-09-13)**

| 항목 | 사실 |
|------|------|
| 스키마 | SKILL.md에 `context: inline\|fork`, `agent`, `background`, `hooks`가 있다 |
| `background` | fork 전용. 기본은 백그라운드(부른 쪽이 기다리지 않고 알림으로 보고). `false`면 부른 쪽이 기다린다 |
| agent 해석 | agentType **정확 일치**(대소문자 포함). 없으면 **조용히 general-purpose로 실행**(디버그 로그만) |
| 이름 형식 | 플러그인 에이전트는 `플러그인:이름`만 찾힌다. LOCAL(`.claude/agents`)은 `이름`으로 된다 |
| model·effort | 스킬에 값이 있으면 **스킬이 이긴다**(effort는 값을 뒤바꿔 두 번 확인). 스킬이 비면 **에이전트 값**이 쓰인다 |
| tools | **에이전트가 이긴다** — 스킬 `allowed-tools`는 도구를 늘리지 못한다 |
| 전달 구조 | 에이전트 본문 → 시스템 프롬프트, 스킬 본문 → 작업 지시. `$ARGUMENTS`는 치환된다 |
| fork 에이전트 설정 | `skills:` 프리로드·`maxTurns`는 **적용**, `isolation: worktree`는 **적용되지 않는다** |
| 내장 이름 | `general-purpose` / `Explore` / `Plan` (`statusline-setup`도 있으나 후보에서 뺀다) |
| 도구 0개 에이전트 | 이 환경에 없는 도구만 준 에이전트로는 fork가 아무 일도 하지 못했다 |
