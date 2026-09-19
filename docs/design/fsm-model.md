# FSM 모델 — 상태·전이·그래프·본문·직렬화

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## CompositeState (순수 FSM 개념)

- `sub_machine: StateMachine`을 포함하는 UML composite state — fsm/ 레이어의 순수 개념으로 존치
  (Region과 함께). **에이전트 개념과의 대응은 WP-AF로 끊어졌다** — 에이전트는 더 이상 내부 FSM으로
  설계하지 않는다.

## Region = 병렬 실행 트랙

- `ParallelState` 내 독립 실행 단위
- `sub_machine: StateMachine`을 포함 — 각 Region은 자신만의 FSM을 가짐
- **조인 전략:** `ParallelState.join: JoinStrategy = ALL` + `join_count: int | None`. ALL=전 Region, ANY=하나, N_OF=`join_count`개 완료 시 join. `JoinStrategy`는 순수 FSM 개념이라 `model/fsm/join.py`가 정본이며 필요한 곳이 직수입한다(RF-1b에서 policy.py re-export 삭제, 2026-09-19에 `policy.py`·`ExecutionPolicy` 자체가 퇴역 — 지금 소비자는 `ParallelState`뿐이다).

## FSM + Blackboard 하이브리드

- **로컬 데이터:** Transition.data_map으로 상태 간 명시적 전달 (`{src_output: tgt_input}`)
- **공유 데이터:** Blackboard.variables (Variable.scope = BLACKBOARD)
- **동적 상태 파일:** Blackboard.class_definitions (DynamicClass) — 설계 시 정의, 런타임에 work 폴더 state/에 생성

## 본문(body) / Section / EventDef

- **본문의 단일 진실은 `body: str`(단일 마크다운 문자열)** — 스킬 7종(절차형·fork 2종·선언형·전이·참조·랩핑)과 에이전트 2종(`AgentDefinition`·`ForkAgent`) 전부 동일 필드(WP-SB, 기본값 `""`. 랩핑 스킬만 항상 빈 값 — 정본이 외부 스킬이다). 마크다운 에디터(WP-MD1/MD2/MD3, **완료** — 코어 위젯+오버레이 UX+찾기/바꾸기+TOC)가 헤딩·리스트·슬래시 메뉴를 네이티브로 다루면서 수동 섹션 트리 편집의 존재 의의가 사라져 단일 텍스트로 통일했다.
- `Section`(`model/fsm/section.py`)은 자유 콘텐츠 계층(H1–H6, `children: list[Section]` 재귀 트리)으로, 이제 **v1 sections 트리 마이그레이션의 입력**으로만 쓰인다(RF-1b — 계약 카드 용도(caller_contracts)는 필드째 삭제, `commands/section_commands.py`도 함께 제거). 모듈이 남는 이유는 아래 `render_markdown`과 `EventDef`가 여기 살기 때문이다.
- `render_markdown(sections, depth=1) -> str`(section.py): v1(sections 트리) 파일을 로드할 때 `body`로 평탄화하는 단방향 마이그레이션 헬퍼. `serialize._migrate_v1`이 `body` 키 부재 + `sections` 키 존재 시에만 호출한다(경고 없음 — 정상 마이그레이션 경로).
- `EventDef`: TransferOn 스킬의 출력 이벤트 정의. 노드 출력 포트에 대응 (`name`, `color`, `description`)

## 입력 포트 퇴역 (WP-IP) — 인터페이스 선언은 값을 만드는 쪽에만

- **원칙(사용자 확정):** 함수(도착 노드)가 자기 입력 경로를 알 필요가 없다 — 호출하는 쪽이 맞춘다.
  (출처, 트리거)가 이미 경로를 특정하므로 `entry_paths`(입력 포트 선언)와 `Transition.target_port`는
  **퇴역**했다. 계약 카드 퇴역(WP-CT)과 같은 원칙이다: 갈래의 의미는 출발 스킬이 자기 `transfer_on`
  description에 적고, 경로별 대응은 도착 스킬 본문에 쓴다. 실증: unreal-profiler 실사용 세션이 쓴
  target_port 6개 전부가 (출처, 트리거) 쌍으로 특정되는 정보의 이름표 중복이었다.
- **호출 시 정보가 담긴다(컴파일):** ① 출발 스킬 "## 다음 단계" 항목에 그 갈래의 transfer_on
  description 병기("— <desc>"). ② `_progress_update_note(project)`가 `note`에 **어느 갈래(출력 이벤트
  이름)**를 기록하도록 지시 — 도착 스킬은 (`prev`, `note`의 갈래)로 진입 경로를 판별한다.
  ③ 도착 스킬 "## 진입 맥락"은 그래프에서만 유도(포트 그룹 헤딩 없음, 출처 이름순 항목 + 출처의
  transfer_on description 병기).
- **잔재 처리:** 모델 필드(`entry_paths`/`target_port`)는 RF-1b에서 **삭제**됐다 — v1 파일의 해당
  키는 로드 시 조용히 드롭된다(`_migrate_v1`, 퇴역 개념이라 경고 불필요). 렌더는 입력 포트 항상
  1개(`input_port_scene_pos()` 인자 없음), 검증의 `dangling_target_port` 규칙도 삭제. 편집 UI
  ("⇤ 입력 경로" 패널) 제거. MCP는 `set_entry_paths` 도구 자체를 제거했고 `set_transition`/
  `connect_states`에서 target_port 파라미터도 사라졌다(조회 출력에서도 제외).

## PluginProject.graph = 워크플로 백킹 머신

- **역할:** 프로젝트 캔버스(탭 0)의 노드/전이를 담는 정식 `StateMachine`. 각 캔버스 노드는 "정식 FSM 상태"이며 백킹 머신에 들어가 **직렬화·컴파일·검증의 단일 진실**이 된다 (캔버스 VM은 그 투영). 이전에는 fsm=None 경로로 도메인 모델에 들어가지 않아 저장/컴파일에서 누락됐다.
- **기본값:** `default_factory=_make_project_graph` — `EntryPoint(name="start")`를 `initial_state`로 갖는 빈 머신(states 포함). `StateMachine.initial_state`는 required 유지(Optional 완화 없음), 직렬화 포맷도 불변.
- **EntryPoint 격하 (WP-EP):** CC 플러그인에는 단일 진입점이 없다 — user_invocable 스킬은 전부 `/skill`로 독립 시작 가능하고 모델 자동 인보크도 있어, FSM 관념의 "시작점"이 성립하지 않는다. 따라서 **프로젝트 캔버스(탭 0)는 EntryPoint와 그에 닿는 전이를 그리지 않는다** — `GraphIO.load_project_graph`가 `graph.states`에서 EntryPoint 인스턴스를 스킵하고(VM 미생성), EntryPoint에 닿는 전이도 VM이 없어 자연히 렌더되지 않는다(구버전 파일의 시작 전이도 경고 없이 조용히 숨는다). 모델은 불변 — `project.graph.initial_state`는 여전히 EntryPoint이고 구버전 파일의 시작 전이도 저장 왕복 시 보존된다. `FsmScene`의 EntryPoint 삭제-방어 코드(`_delete_state`/컨텍스트 메뉴/keyPress)는 그대로 두지만, 프로젝트 캔버스에서는 VM이 없어 자연히 죽은 경로가 된다(에이전트 내부 FSM 캔버스는 WP-AF로 퇴역했으므로 이제 그 코드를 공유하는 씬도 없다).
- **placement:** 배치된 스킬/에이전트는 `SimpleState(skill_ref=...)`로 그래프에 들어간다 (에이전트도 SimpleState로, CompositeState 승격 없음). `FsmScene.set_project`가 `_target_fsm = project.graph`로 배선해 Create/Delete/Transition 커맨드가 그래프에 동기화된다 (undo/redo 일관). `_target_fsm`이 배선되는 씬은 이제 이 하나뿐이다 — 에이전트 내부 FSM 캔버스는 WP-AF로 퇴역했다.
- **graph_layout:** `dict[str, list[float]]` — 키는 **state.id**(이름 변경 안전). 소유자는 `PluginProject` 하나다(2026-09-19 — `AgentDefinition`의 동명 필드 퇴역). 저장 직전 `app._save_graph_layout`이 VM 좌표를 기록, 로드 시 `GraphIO.load_project_graph`가 graph+graph_layout으로 캔버스 VM을 재구성(실체는 둘 다 `view/graph_io.GraphIO`). EntryPoint는 캔버스 VM이 없으므로 `graph_layout`에도 그 키가 기록되지 않는다(WP-EP).
- **블랙보드 배선:** `project.graph.blackboard.parent = project.blackboard` — `PluginProject.__post_init__`(생성 경로)과 `deserialize_project`(역직렬화 생성 경로) 양쪽에서 보장.

## CompletionEvent

세 가지 완료를 통합적으로 표현:
- SimpleState 작업 완료 → 부모 FSM에 완료 신호
- CompositeState sub_machine이 final_state 도달 → 부모 FSM에 완료 신호
- ParallelState는 `ParallelState.join` 전략에 따라 완료 (ALL=전 Region, ANY=하나, N_OF=join_count개) → 부모 FSM에 완료 신호

`Transition.trigger = CompletionEvent(name="done")` 으로 설정.

## 전략 패턴 (Guard / Action 공통)

```
EvaluationStrategy(ABC)        ExecutionStrategy(ABC)
├── LLMEvaluation              ├── LLMExecution
├── ToolEvaluation             ├── ToolExecution
├── MCPEvaluation              ├── MCPExecution
├── ExpressionEvaluation       └── CompositeExecution
└── CompositeEvaluation
```

## 안정 ID + 직렬화 (model/serialize/)

- **안정 ID:** `State`(베이스)/`Transition`/`StateMachine`/`Region`/`Variable`/`Skill`(베이스)/`AgentDefinition`에 `id: str = field(default_factory=lambda: uuid4().hex, kw_only=True)`. kw_only로 다중 상속 필드 순서 제약을 회피한다. eq=False 클래스는 identity 동등성/해시를 유지(id는 `__eq__`/`__hash__` 무관)하고, 값 동등성 클래스(Variable/Skill/Agent)는 `compare=False`로 값 비교에서 제외한다.
- **직렬화 원칙:** `serialize_project`/`deserialize_project`는 JSON 호환 dict(`"format": 2` 버전 키)를 만든다. **소유 객체는 인라인, 참조는 ID 문자열로 평탄화**한다 — Transition.source/target(state id), SimpleState.skill_ref·Transition.skill_ref(component id), StateMachine.initial_state/final_states(state id). 다형성은 `kind` property를 태그로 재사용. enum은 `.value`↔타입 복원. 역직렬화는 2-pass(객체 생성+id 레지스트리 → 참조 해소)이고 dangling id는 None+경고. `Blackboard.parent`는 ID가 아니라 sub_machine 소유 구조로 재연결한다. serialize 패키지는 순수 모델(Qt 무관).
- **패키지 분해 (WP-SZ):** 구 단일 모듈 `serialize.py`(1,437줄 — 위생 허용 목록의 마지막 등재)를 `model/serialize/`로 쪼갰다(이동만·동작 불변, 최상위 정의 66개 AST 동등 검증). 구획은 `ser.py`(정방향 + `FORMAT_VERSION` 단일 진실) / `migrate.py`(v1→v2) / `deser_fsm.py`+`deser_plugin.py`+`deser.py`(역방향 2-pass — 계층별 형제 3개)이고 의존 방향은 **ser ← migrate ← deser_fsm ← deser_plugin ← deser 단방향**이다 — `_deser_section`이 `migrate.py`에 있는 이유가 이것이다(`sections` 트리는 v1 파일에만 있고 유일한 호출자가 `_migrate_v1`이라, deser에 두면 순환이 생긴다). **역방향 재분해(2차)**: 800줄 예산을 넘긴 `deser.py`를 FSM 계층/플러그인 계층/오케스트레이터로 다시 쪼갰다(최상위 정의 33개 AST 동등 검증). `_Registry`는 그것을 **소비**하는 최하위 계층(`deser_fsm`)에 두었다 — 오케스트레이터에 남기면 FSM 계층이 상위 모듈을 임포트해야 해서 방향이 뒤집힌다. `deser.py`가 두 형제의 이름을 전부 재수입하므로 `__init__` 파사드는 한 줄도 바뀌지 않았고 `serialize._deser_tool is deser._deser_tool` 항등도 그대로다. **하위 패키지(`deser/`)가 아니라 형제 모듈인 이유**는 `test_split_modules_are_within_soft_budget`이 `pkg.glob('*.py')` 비재귀라 중첩하면 800줄 예산 커버가 사라지기 때문이다. `__init__.py`는 **재-export 파사드**로 분해 전 모듈의 속성 138개를 전부 보존해 `from daedalus.model.serialize import _ser_tool` 같은 기존 임포트가 무수정 동작한다(`tests/model/test_serialize_facade.py`가 파사드 완전성·의존 방향·모듈 크기를 고정). 이 분해로 `tests/test_code_hygiene.py`의 ALLOWLIST가 비었다 — 다시 채우는 것은 규칙 위반이다.
- **컴포넌트·설정 직렬화의 선언화 (WP-4, 2026-09-19 — 동작 불변, JSON 바이트 동일):** 설정의 `_ser_config`/`_deser_config`는 종류별 `isinstance`/`kind ==` 사다리였고, 컴포넌트의 `_ser_skill`/`_ser_agent`는 형상 `isinstance` 가드였다. 셋 다 **선언**으로 바뀌었다.
  - **설정** — 각 `ComponentConfig` 서브클래스가 `SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]]`를 선언하고 기저의 `to_dict()`/`from_dict()`가 그것만 본다. `FieldSpec(name, codec, missing)`과 코덱 8종은 `model/plugin/serial_fields.py`에 있다. **MRO 역순 누적이 아니라 각 클래스가 명시 튜플을 선언한다** — 누적이면 `AgentConfig`의 저장 키 순서(`… memory, color, background, isolation`)가 dataclass 필드 순서(`… memory, background, isolation, color`)와 다르다는 사실을 표현할 수 없다. **선언 순서 = JSON 키 순서**다. `tests/model/plugin/test_serialize_symmetry.py`가 `{f.name for f in fields(cls)} == {s.name for s in cls.SERIALIZED_FIELDS}`를 9종 전부에 강제한다 — 필드를 더하고 선언을 잊으면 그 값이 저장에서 **조용히 사라지던** 구멍(M8)이 구조적으로 막혔다.
  - **부재 의미론은 선언이 소유한다.** `FieldSpec.missing`은 "키가 없을 때의 값"이고 dataclass 기본값과 **다를 수 있다**. 오늘 다른 것은 둘이다: `model` 부재 → `None`(선언 기본값은 `ModelType.INHERIT` — 오늘의 결함이고 고치면 저장 파일 해석이 바뀌므로 **보존**한다. `docs/backlog.md` D10) · `usage` 부재 → `"state"`(구버전 파일에는 state 용도만 있었다). 센티널 `_USE_DEFAULT`면 그 키를 생성자에 아예 넘기지 않는다 — 기본값을 복제하면 `default_factory`(빈 리스트)가 모든 인스턴스에 공유되는 함정이 열린다.
  - **컴포넌트** — `model/serialize/component_fields.py`가 표 셋으로 답한다. `KEY_ORDER[bucket]`(**버킷마다 키 순서가 다르다**: 스킬은 `… when_to_use, body, config, fsm, …`, 에이전트는 `… description, config, body, fsm, …`) · `DESER_ORDER`(**부수효과** 순서 — config dict 파싱 → fsm 해소 → config 강등 → 나머지. `_Registry.warnings`가 쌓이는 순서가 곧 사용자가 보는 경고 순서라 키 순서와 일부러 다르다) · `COMPONENT_MISSING = {"transfer_on": list}`(부재값이 dataclass 기본값과 다른 **유일한** 필드 — `StepSkill`/`WrappedSkill`의 선언 기본값은 `[EventDef("done")]`이라, 표 없이 기본값으로 떨어지면 키 없는 파일에 출력 포트가 **발명**되고 `transfer_on_not_empty`가 에러에서 조용한 통과로 뒤집힌다. `tests/model/test_component_missing_keys.py`가 직접 고정). "이 종류가 fsm/포트/when_to_use를 갖는가"는 종류 목록이 아니라 `dataclasses.fields`가 답한다.
  - **임포트 방향** — `component_fields`는 serialize 패키지의 **새 리프**다(형제를 하나도 임포트하지 않는다). FSM/EventDef/config 코덱은 호출자가 주입한다(`ser.py`가 `_ser_machine`을, `deser_plugin.py`가 `_deser_machine`·`_coerce_config`를 준다) — 직접 임포트하면 `ser → component_fields → ser` 순환이다. `_to_enum`은 설정 코덱과 FSM 역직렬화가 **같은** enum 복원 규칙을 써야 해서 `plugin/serial_fields.py`로 올라갔고, `deser_fsm`이 이름으로 수입해 경로(`deser_fsm._to_enum`)와 파사드를 보존한다.
  - `_ser_config`/`_ser_skill`/`_ser_agent`/`_deser_config`/`_build_component`는 **이름을 유지한 한 줄 파사드**다 — 호출자·테스트 무수정.
- **포맷 v2 + `_migrate_v1` (RF-1b):** `serialize_project`는 항상 `"format": 2`를 쓴다. `deserialize_project`는 format 1(또는 키 부재 구버전)을 받으면 **`_migrate_v1` 한 함수로 집약된 단방향 마이그레이션**을 태운 뒤 v2로 읽는다(왕복 보존 없음 — 열면 v2로 저장된다). 미지의 상위 format은 명시 에러. `_migrate_v1`이 다루는 축(입력 dict는 deepcopy로 불변): ① delegations 드롭(경고 — WP-RF-1a. 위임을 가리키던 placement skill_ref는 dangling 경고와 함께 None으로 정리) ①-b 에이전트 로컬 스킬 → **전역 스킬 승격**(WP-RF-1c, `_promote_local_skills` — 이름 충돌(전역 스킬·에이전트·먼저 승격된 스킬) 시 `<agent>--<name>` 개명 + 재충돌 시 `-2` 접미 유일화 + 개명 시 소유 에이전트 config.skills 참조 치환, 승격마다 경고 1건, id 보존이라 transfer skill_ref 해소 유지. 승격 dict는 data["skills"]에 합류해 이후 단계·역직렬화에서 전역 스킬과 같은 경로. **format 2 파일도 에이전트 dict에 `skills` 키가 있으면 같은 승격을 탄다** — RF-1b 시점 코드가 저장한 v2 파일의 인라인 로컬 스킬이 경고 없이 드롭되는 것 방지) ② sections 트리→body 평탄화(render_markdown) + `${CLAUDE_PLUGIN_ROOT}/files/`→`${ROOT}/files/` 치환(WP-RT) ③ 퇴역 키 조용히 드롭 — entry_paths/caller_contracts/전이의 target_port(WP-IP/WP-CT, 경고 불필요) ④ 에이전트 transfer_on 부재 시 내부 FSM ExitPoint 이름·색 승계(WP-AF) ⑤ 구버전 훅(커맨드 하나짜리)을 handlers 목록으로 감싸기 + 핸들러 command→script(WP-HK/WP-HS) ⑥ `field_type: "number"`→`"float"`(FieldType.NUMBER 퇴역). 픽스처 고정은 `tests/model/test_migrate_v1.py`(v2 왕복 항등 포함).
- **`SimpleState.skill_ref`의 타입은 `PluginComponent | None`이다**(WP-2b, Q35) — 종류 유니온이 아니다. 예전 `StepSkill | DeclarativeSkill | AgentDefinition`은 배치 가능한 `WrappedSkill`이 빠져 있어도 아무것도 실패하지 않는 낡은 선언 표였다(스멜 ⑤). 실체 판정은 `c.effective_placement() is PlacementRole.STATE`이고, 새 종류는 `fsm/**`를 한 줄도 건드리지 않는다 — `tests/model/fsm/test_state_is_kind_neutral.py`가 소스에 구체 컴포넌트 클래스 이름이 없음을 고정한다.
- **그래프 노드가 될 수 있는 컴포넌트**는 `model/plugin/placement.is_state_placeable`가 정한다(WP-FK2) — `StepSkill`(절차형·fork 2종), 용도가 reference가 아닌 `WrappedSkill`, `AgentDefinition`. `ForkAgent`는 fsm·포트가 없고 fork 스킬이 부르는 실행 기반이라 **노드가 될 수 없다**. 캔버스·MCP·"여기에 만들기"가 모두 같은 함수를 부른다 — 상세는 `plugin-model.md` "배치 가능 판정".
- **프로젝트 그래프 직렬화:** `serialize_project`는 `graph`(`_ser_machine` 재사용)와 `graph_layout`을 왕복한다. 그래프 placement의 skill_ref는 component id로 평탄화되고, 역직렬화 시 pass1에서 등록된 skills/agents를 pass2가 해소한다(그래프 `_deser_machine`은 pass1에서 호출). 하위 호환: `"graph"` 키 부재(구버전 파일) → `_make_project_graph()`로 빈 그래프 생성(경고 없음). graph.blackboard.parent는 역직렬화 시 프로젝트 블랙보드로 재연결.
- `PluginProject.graph_layout`의 키는 state.name이 아니라 **state.id**다 (이름 변경 시 레이아웃 유실 방지).
