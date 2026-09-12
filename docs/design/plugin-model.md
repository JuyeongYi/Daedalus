# 플러그인 컴포넌트 모델 — 스킬·에이전트 종류, 필드 매트릭스, 진입 의미론

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 스킬과 에이전트

| 종류 | 본질 | FSM 관계 |
|------|------|---------|
| ProceduralSkill | 작업 지침 | 자체 FSM을 가진 독립 워크플로우 |
| DeclarativeSkill | 배경 지식 | FSM 없음 |
| TransferSkill | 전이 시 실행되는 보조 지침 | 자체 FSM 보유 |
| ReferenceSkill | 참조 문서 | FSM 없음, 참조 노드로 복수 배치 |
| WrappedSkill | 다른 플러그인 스킬의 랩핑(WP-WR) | 본문 없음 — 정본은 config.source의 외부 스킬(런타임 참조). 배치·transfer_on은 procedural과 동일(단일 배치) |
| AgentDefinition | 별도 컨텍스트의 작업자 | **내부 FSM 퇴역(WP-AF)** — 절차는 본문, 결과 분기는 transfer_on |

## SKILL_FIELD_MATRIX

스킬 유형(procedural, declarative, transfer, reference)별로 프론트매터 필드의 `FieldRule`을 정의하는 매트릭스.

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
│   ├── ProceduralSkillConfig # disable_model_invocation·user_invocable(**tri-state**, A8), context, agent, shell 등
│   ├── DeclarativeSkillConfig
│   ├── TransferSkillConfig
│   └── ReferenceSkillConfig
└── AgentConfig               # tools, permission_mode, skills, isolation 등
```
