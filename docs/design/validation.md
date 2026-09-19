# Validator 규칙

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## Validator 규칙 (재귀 적용)

**모듈 배치(WP-RF-3d):** `model/validation/`은 패키지다 — `severity.py`(ValidationError·WARNING_RULES) /
`machine_rules.py`(`_MachineRules` 믹스인 — 머신 수준 규칙 + `validate`/`_validate_machine` + SKIPPABLE_RULES) /
`project_rules/`(**A6에서 다시 패키지로 분해** — `_ProjectRules`는 그룹 믹스인 9종(naming/tools/hooks/
blackboard/body_variables/build_target/workflow/fork/workspace)을 합성한 오케스트레이터이고, 공용 순회
헬퍼는 `scan.py`의 **모듈 함수**가 실체다(그룹끼리 `_ProjectRules.<헬퍼>`로 부르면 파사드와 순환).
파사드가 CC_BUILTIN_TOOLS·`_strip_markdown_code`·`_ProjectRules`를 그대로 재-export한다).
`Validator`는 `__init__.py`가 두 믹스인을 상속해 합성한 클래스이며, `__init__`이 재-export 파사드라
`from daedalus.model.validation import …`와 `Validator._check_*` 이름이 분해 전과 동일하게 동작한다.
새 규칙은 해당 그룹 모듈에 `_check_*` staticmethod로 추가하고 오케스트레이터(`_validate_machine` /
`validate_project`)에 한 줄 등록한다 — 등급 지정을 빼먹으면 `tests/model/test_validation_severity.py`가
깨진다(패키지 **전 모듈** 소스를 합쳐 `rule=` 리터럴을 introspect한다 — 열거는
`pkgutil.walk_packages` **재귀**라, 이후 규칙을 하위 *패키지*로 한 겹 더 나눠도
커버리지가 따라간다. 비재귀 `iter_modules`였다면 중첩 모듈의 등급 미분류가 조용히
통과한다 — A/B 스모크로 실측 확인).

`ValidationError` 필드: `rule`, `message`, `source`(기존) + `subject: object | None`(문제 객체, 검증 결과 → 노드 포커스에 쓰인다 — `compare=False`이므로 identity 비교로 조회) + `path: tuple[str, ...]`(중첩 경로, 예: `("agent:Writer", "region:r1")`). 기본값이 있어 기존 생성자 호환. `validate_project`는 최상위 FSM 오류에 root path(`"skill:<이름>"`/`"agent:<이름>"`)를 주입한다.

`ValidationError.is_warning` property — 규칙이 경고 등급이면 True, 에러 등급이면 False. `WARNING_RULES: frozenset[str]` 모듈 상수가 경고 등급 규칙 집합을 단일 진실로 보유 (view에서 rule 이름 하드코딩 금지). `invalid_component_name`은 빈 이름=에러/불일치=경고를 `is_warning`에서 메시지 내용으로 세분화한다.

### 머신 수준 (18규칙명)

| 규칙 | 설명 |
|------|------|
| `initial_state_in_states` | `sm.initial_state ∈ sm.states` (identity 기준) |
| `final_states_in_states` | `sm.final_states ⊆ sm.states` |
| `no_nested_agent` | CompositeState 안에 CompositeState 불가 |
| `no_agent_to_agent` | Agent → Agent 직접 전이 **경고**(2026-09-12 에러에서 완화 — CC가 서브에이전트 중첩 스폰을 허용한다). 금지가 아니라 "그 구간의 중간 결과는 메인 컨텍스트에 남지 않아 진행 기록·재개가 약해진다"는 알림이다. 하드 제약은 프로젝트 수준의 `agent_chain_too_deep`/`agent_calls_higher_model`이 에러로 잡는다 |
| `missing_required_input` | LOCAL scope 필수 input이 data_map에 없으면 경고 |
| `pseudo_state_hooks` | 의사 상태에 lifecycle 훅 설정 시 경고 |
| `completion_event_on_composite` | Composite/ParallelState 출발 전이에 CompletionEvent 없으면 경고 |
| `no_duplicate_skill_ref` | 동일 스킬/에이전트의 중복 배치 금지 |
| `transfer_on_not_empty` | ProceduralSkill/Agent transfer_on 최소 1개 (ExitPoint 폴백은 RF-1b에서 삭제 — transfer_on 단일 진실) |
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

### 프로젝트 수준 (36종)

`Validator.validate_project(project)` — 전체 FSM 검증 후 추가:

| 규칙 | 설명 |
|------|------|
| `duplicate_component_name` | skills/agents 전체에서 동명 컴포넌트 에러 (컴파일 디렉토리 충돌) |
| `invalid_component_name` | 이름이 `^[a-z0-9][a-z0-9-]*$` 불일치 시 경고, 빈 이름은 에러 |
| `dangling_string_reference` | `AgentConfigBase.skills`(에이전트 종류 전부), `PluginProject.reference_placements.skill_name`의 문자열 참조 실존 검사 (스킬 이름은 전역 skills 기준). fork 스킬 `agent`는 내장 이름도 가리킬 수 있어 여기서 보지 않는다 — `fork_agent_missing`이 맡는다 |
| `duplicate_tool_name` | `tool_shelf` 내 동명 Tool 에러 (이름 참조 모호) |
| `empty_tool_definition` | UserDefinedTool 본문(body) 빈 값 / MCPTool server·tool_name 빈 값 경고 |
| `dangling_tool_ref` | FSM의 ToolEvaluation/ToolExecution.tool이 `tool_shelf ∪ CC_BUILTIN_TOOLS`에 없으면 경고 (빈 문자열은 스킵). 참조 수집은 상태 훅·custom_events·전이 가드/액션 체인 + Composite 중첩 + sub_machine/Region 재귀 |
| `duplicate_hook_name` | `hook_library` 내 동명 HookDef 에러 (이름 참조 모호) |
| `empty_hook_command` | HookDef.command 빈 값 경고 |
| `hook_matcher_without_tool_event` | matcher가 있는데 event가 Pre/PostToolUse가 아니면 경고 (matcher는 도구 이벤트 전용) |
| `dangling_hook_ref` | config.hooks 키가 hook_library에 없으면 경고 (스킬·에이전트 전부 검사) |
| `hook_matcher_matches_nothing` | MCP matcher가 서버 이름까지만이면 어떤 도구와도 맞지 않으므로 경고 (정규식이 아니라 정확한 문자열 비교 — `server__.*`를 쓰라고 안내, WP-HS) |
| `dangling_blackboard_ref` | State.reads/writes의 `"Class"`/`"Class.field"` 문자열 참조가 프로젝트 최상위 블랙보드 class_definitions에 없으면 경고 (재귀 — sub_machine/Region + 프로젝트 그래프 포함, 빈 문자열은 스킵) |
| `orphan_blackboard_field` | 블랙보드 필드 중 어떤 상태의 reads/writes에도 등장하지 않으면 경고 (클래스 전체 참조는 그 필드 전부 커버로 간주, 프로젝트 전체에 접근 선언이 하나도 없으면 스킵 — 경고 폭주 방지) |
| `invalid_blackboard_field_type` | 블랙보드 필드 타입이 허용 집합(BLACKBOARD_FIELD_TYPES — 스칼라 4종) 밖이면 경고 (컨테이너 형상은 CollectionType 전담, WP-BT) |
| `mcp_agent_in_marketplace_build` | `project.build_target == MARKETPLACE`인데 에이전트 config.tools에 `mcp__` 도구가 있거나 mcp_servers 선언이 있으면 경고 (CC는 플러그인 배포 에이전트의 MCP 사용을 미지원 — LOCAL 빌드면 무경고, WP-TG) |
| `unsupported_agent_field_in_marketplace_build` | MARKETPLACE 빌드인데 에이전트가 `hooks` 또는 기본값 아닌 `permissionMode`를 쓰면 경고 (CC가 보안상 무시 — MCP는 위 규칙이 전담, WP-LA) |
| `plugin_root_in_local_build` | `project.build_target == LOCAL`인데 스킬/에이전트 본문에 플러그인 전용 변수(`${CLAUDE_PLUGIN_ROOT}`·`${CLAUDE_PLUGIN_DATA}` — `variables.PLUGIN_ONLY_VARIABLES`)가 남아 있으면 경고. CC는 이 변수를 플러그인 스킬에서만 치환한다. files/ 참조는 타깃 중립 `${ROOT}/files/`를 쓰므로 **예외가 없다**. 코드 표기(인라인 코드·코드 펜스)는 검사하지 않는다 — 규격을 설명하는 문서 스킬의 언급을 영구 경고로 만들지 않기 위해서다 (WP-TG/WP-RT) |
| `skill_dir_token_in_agent` | 에이전트 본문에 `${CLAUDE_SKILL_DIR}`가 있으면 경고 — 이 변수는 스킬 전용이라 에이전트 .md에서 치환되지 않는다 (코드 표기 제외, 빌드 타깃 무관, WP-SF) |
| `skill_only_variable_in_body` | 스킬 전용 변수(`$ARGUMENTS`(=`$ARGUMENTS[N]` 접두)·`${CLAUDE_SESSION_ID}`·`${CLAUDE_SKILL_DIR}`)가 **에이전트 본문 또는 작업 폴더 문서**(`.claude/CLAUDE.md` 구역·`rules/`)에 있으면 경고 (A6) — 치환되지 않고 리터럴로 산출에 나간다. 변수 팝업 컨텍스트 필터(`variable_loader.variables_for`)의 검증기 짝이고, 토큰 단일 진실은 `model/plugin/variables.SKILL_ONLY_VARIABLES`. **에이전트의 `${CLAUDE_SKILL_DIR}`만 제외**한다 — `skill_dir_token_in_agent`가 전담 메시지로 이미 짚으므로 중복 경고 금지(작업 폴더 문서는 그 규칙의 대상이 아니라 세 토큰 모두 검사). `$N` 단축형은 셸 위치 인수와 구분할 수 없어 제외. 코드 표기 제외, 빌드 타깃 무관 |
| `transfer_skill_reused` | 한 TransferSkill이 **2개 이상 전이**에 붙으면 **에러** (A11). TransferSkill은 전이 위에 놓인 **1:1 중간 상태**이므로 전이 하나에만 속한다 — 하나의 상태가 두 자리에 동시에 있을 수 없다는 점에서 `no_duplicate_skill_ref`와 **같은 논리**다(특별 규칙이 아니다). 메시지가 그 논리와 대안(공통 지침은 Declarative 스킬로 빼고 각 전이 스킬이 참조)을 함께 담는다. 순회 범위는 프로젝트 그래프 + 각 스킬/에이전트 FSM(`_scan_transitions` 재귀 — sub_machine/Region 포함). 메시지에 붙은 위치를 전부 나열한다(어디를 고쳐야 하는지 알아야 한다) |
| `duplicate_rule_name` | 작업 폴더 규칙 문서의 동명 에러 — 상세는 "작업 폴더 문서 (WP-WD) #### 검증" 표 |
| `invalid_rule_name` | 규칙 문서 이름 규약 경고 (컴파일 게이트가 에러로 승격) — 같은 표 |
| `workspace_doc_in_marketplace_build` | MARKETPLACE 빌드인데 작업 폴더 문서에 내용이 있으면 경고 — 같은 표 |
| `external_source_missing` | **외부 정본을 선언한 컴포넌트**의 source 빈 값·형식 불일치 경고 (`플러그인[@마켓]:이름`). 대상은 `c.external_source is not None`인 것 전부다 — WP-2b에서 랩핑 전용 `wrapped_source_missing`을 **개명·일반화**했다(Q34). 종류를 묻지 않으므로 외부 정본을 갖는 새 종류는 선언 한 줄로 이 검사를 받는다(WP-9 `ExternalAgent`가 그 첫 사례이고 WP-EX의 `ExternalForkAgent`가 두 번째다 — 둘 다 검증 코드를 한 줄도 고치지 않고 합류했다). 실존(카탈로그 해소)은 파일시스템 소관이라 보지 않는다. 위임 지시 자리는 **이름을 지어내지 않는 대신 고치라는 표시**로 나간다(`compiler/emit/common.delegate_to_phrase`) |
| `unused_external_plugin` | 외부 플러그인을 사용 선언했는데 어떤 **컴포넌트도** 참조하지 않음 — 배선은 그대로, 경고만 (WP-WR). 참조 판정은 `c.external_plugin_refs()`(Q15)이고 꺼 둔 컴포넌트·형식이 깨진 source는 그 안에서 이미 빠진다 |
| `undeclared_external_plugin` | **컴포넌트의** 외부 참조가 미선언 플러그인을 가리킴 — 배선이 안 나가 런타임에 못 찾는다 (WP-WR). 대상 판정은 `external_plugin_refs()` 하나이고 종류를 묻지 않는다 — 외부 정본을 선언하는 종류가 같은 술어로 합류한다. WP-EX에서 fork 쪽 에러 규칙(`fork_agent_undeclared_plugin`)이 사라져 **미선언은 이 한 갈래뿐**이다 |
| `external_source_role_conflict` | 같은 `external_source` **원문**을 가진 컴포넌트가 2개 이상이면 전부에 **에러** (WP-EX, 사용자 확정 2026-09-19). 외부 플러그인 에이전트의 역할(그래프 노드 / fork 실행 기반)은 등록 시점에 고정되므로, 같은 정본을 두 번 등록하면 어느 쪽이 정본인지 아무도 답할 수 없다 — 이름 충돌이 아니라 역할 충돌이라 `duplicate_component_name`은 잡지 못한다. 매칭은 원문 정확 일치(`alpha@mkt:x` ≠ `alpha:x`)이고 빈/깨진 source는 제외한다(`external_source_missing` 소관 — 편집 중인 빈 칸 둘을 충돌로 보고하지 않는다). 종류를 묻지 않으므로 외부 정본을 갖는 새 종류가 선언 한 줄로 합류한다 |
| `external_plugin_no_marketplace` | 마켓 표기 없는 bare 선언은 enabledPlugins 배선 불가 경고 (컴파일러 emit, WP-WR) |
| `agent_chain_too_deep` | 프로젝트 그래프의 **에이전트 → 에이전트 호출 체인**이 `MAX_AGENT_CHAIN`(3)을 넘으면 **에러** (2026-09-12). CC는 주 대화 기준 3계층까지만 중첩을 허용하고 한계에 닿은 서브에이전트에게서 Agent 도구를 회수하므로, 더 깊은 체인은 **설계대로 돌지 않고 조용히 달라진다**(마지막 에이전트가 혼자 처리). 스킬은 메인 스레드에서 도니 중간에 스킬을 끼우면 깊이가 1부터 다시 시작한다. 보고는 **체인 시작점에서 한 번**(노드마다 반복 금지), 순환(A→B→A)은 깊이 무한이라 같은 규칙이 다른 메시지로 잡는다. **fork 스킬은 에이전트 1계층 호출자로 센다**(2026-09-13 — 서브에이전트에서 돈다) |
| `agent_calls_higher_model` | 에이전트가 **자기보다 상위 모델**의 에이전트를 호출하면 **에러** (사용자 확정 2026-09-12). **산출 파일이 없는 callee(외부 플러그인 에이전트 — `OUTPUT_LOCATION is NONE`)는 건너뛴다**(WP-9): 그 모델은 남의 플러그인 파일이 정하고 우리 `config.model`은 어디로도 나가지 않아, 비교하면 우리가 적어 본 값으로 남의 에이전트를 판정하는 셈이다. 깊이 규칙(`agent_chain_too_deep`)에서는 **빼지 않는다** — 그 노드를 거치는 체인은 실제로 한 계층 깊어진다. 티어 표의 단일 진실은 `model/plugin/enums.MODEL_TIER`(haiku<sonnet<opus<fable). 어느 한쪽이 `INHERIT`면 물려받는 값이라 상위/하위가 성립하지 않아 건너뛴다. 스킬 → 상위 모델 에이전트는 대상이 아니다(메인 스레드가 부르는 것이라 중첩이 아니다). 단 **fork 스킬은 호출자로 본다** — 티어는 실효 모델(스킬이 `INHERIT`면 fork 에이전트로 쓰는 프로젝트 에이전트 값) |
| `fork_agent_missing` | fork 스킬 `agent`가 내장도 프로젝트 에이전트도 아니면 **에러** (2026-09-13) — CC는 못 찾은 에이전트를 조용히 general-purpose로 돌린다. 정확 일치(대소문자 포함). **WP-EX 이후 `플러그인:이름` 원문도 여기 걸린다**: 다른 플러그인의 에이전트도 `external_fork_agent` 컴포넌트로 등록한 뒤 이름으로 고르므로, 등록되지 않은 원문은 자체 fork 에이전트를 잘못 적은 것과 같은 사실이다. 종전 별도 등급 `fork_agent_undeclared_plugin`(에러)은 같은 사실을 `undeclared_external_plugin`(경고)과 두 등급으로 말하던 비대칭이라 함께 퇴역했다 |
| `fork_agent_wrong_kind` | fork 스킬 `agent`가 **fork 실행 기반이 될 수 없는 에이전트**(`IS_FORK_BASE`를 선언하지 않는 종류 = 오늘의 `AgentDefinition`)를 가리키면 **에러** (WP-FK2) — 워크플로 에이전트는 캔버스 노드로 불리는 종류라 fork 에이전트가 될 수 없다. 배치 여부와 무관하다(퇴역한 `fork_agent_placed`는 배치를 봤다). 메시지가 대안(fork 에이전트 종류로 만들기 / 다른 에이전트 고르기)을 말한다 |
| `fork_model_overrides_agent` | 스킬과 fork 에이전트로 쓰는 프로젝트 에이전트 **양쪽에 model(또는 effort)이 있고 다르면** 경고 — fork에서는 스킬 값이 이긴다(실측). 스킬이 비면 에이전트 값이 쓰이므로 정상 |
| `unused_fork_agent` | 어떤 fork 스킬도 부르지 않는 **fork 실행 기반**(`IS_FORK_BASE` — `ForkAgent`·`ExternalForkAgent`) 경고 (WP-FK2/WP-EX) — `agents/<이름>.md`로 산출은 되지만 아무도 실행하지 않는다(조용한 무동작 방지). 역참조 판정은 `model/plugin/placement.fork_skills_using` 한 곳이다(편집기 패널·삭제 확인·MCP `still_referenced_by`와 같은 실체). 워크플로 에이전트는 대상이 아니다 |
| `workspace_settings_in_marketplace_build` | 작업 폴더 설정(WP-WS)이 있는데 빌드 타깃이 MARKETPLACE면 경고 — 베이크 불가 (상세는 `workspace-and-build-target.md`) |
| `mid_chain_user_invocable` | 프로젝트 그래프에 배치된 StepSkill(절차형·fork 2종) 중 **incoming 전이가 1개 이상**인데 `config.user_invocable`의 **실효값**이 true면 경고 (A3 + A8 tri-state — `None`(미지정)은 CC 기본 true이므로 경고 대상이고 메시지에 병기, **명시 `False`만 통과**) — user-invocable은 진입점으로 기능할 노드만 true여야 한다(중간 노드로 사용자가 맥락 없이 진입하는 사고 방지. false여도 모델 인보크는 되므로 체인은 안 끊긴다). incoming 0개(진입점 후보)·미배치 스킬(독립 스킬)은 대상 아님. **EntryPoint 출발 전이는 incoming으로 세지 않는다** — 그것이 곧 "여기서 시작한다"는 선언이다(WP-EP로 캔버스에 그리지 않을 뿐 구버전 파일의 시작 전이는 모델에 남아 있다) |

**규칙의 술어는 종류가 아니라 능력 선언이다 (WP-2b).** 위 표의 "어떤 종류에 적용되는가"는 전부 컴포넌트가 선언한 능력에서 나온다 — `transfer_on_not_empty`는 `REQUIRES_OUTPUT_PORTS`, `trigger_unknown_event`의 합법 이벤트 집합은 `known_outgoing_events()`(`None` = 검사 스킵), `transfer_skill_reused`의 대상은 `effective_placement() is EDGE`, `unused_fork_agent`/`fork_agent_wrong_kind`는 `IS_FORK_BASE`, 외부 참조 규칙 3종은 `external_source`/`external_plugin_refs()`, `dangling_hook_ref`의 참조 수집은 `hook_refs()`, `dangling_string_reference`의 스킬 이름 참조는 `config.name_refs(Bucket.SKILLS)`다. 표의 "오늘 걸리는 종류" 문구는 **설명**이고 정본은 선언이다 — 새 종류는 선언을 고르는 것으로 규칙에 합류한다.

**종류 전용으로 남은 좁힘은 오늘 1곳**이다(WP-10 — `# WRAPPED-ONLY` 태그 5곳은 랩핑 스킬과 함께 사라졌다): `_agent_call_edges`의 caller가 `BODY_SOURCE is OWNED`로 좁혀 **외부 플러그인 에이전트를 제외**한다. 넓히면 `agent_chain_too_deep` 깊이와 `agent_calls_higher_model`이 조용히 달라지고(우리가 만들지 않은 파일의 model 값을 우리 경고가 단정한다), 그것은 이 규칙이 아니라 사용자 확정이 필요한 변경이라 `docs/backlog.md`에 올려 두었다.

도구 모델(`tool.py`): `Tool(PluginComponent, ABC)` 단일 진실 + `BuiltinTool`/`MCPTool`/`UserDefinedTool`. shelf = 프로젝트(`PluginProject.tool_shelf`) 소유, FSM은 `Tool.name` 문자열로 참조(fsm/는 plugin 무관 — 객체 참조 금지, Validator가 실존 검증). `CC_BUILTIN_TOOLS`는 `validation/project_rules/tools.py` 모듈 frozenset이다(파사드 재-export로 `daedalus.model.validation`에서도 임포트 가능 — Read/Write/Edit/Bash/Glob/Grep/WebFetch/WebSearch/Agent/Task/TodoWrite/NotebookEdit/SlashCommand/PowerShell).

블랙보드 접근 선언 검증(`dangling_blackboard_ref`/`orphan_blackboard_field`, WP-BB): 상태
reads/writes 순회는 `Validator._scan_state_access(sm, visit)` 공용 헬퍼(재귀 골격은
`model/fsm/walk.iter_states`)를 쓰며, project.skills(fsm)/project.agents(fsm)/project.graph
세 축을 모두 검사한다.
