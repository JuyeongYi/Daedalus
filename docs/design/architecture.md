# 아키텍처 — 경계 계약과 모듈 지도

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 개요

**컴파일러 패턴:** 순수 모델(`model/`) → 컴파일러(`compiler/`) → 플러그인 파일.
GUI는 PySide6 노드 에디터(`view/`), 앱 내장 MCP 서버(`mcp/`)가 CC와의 협업 창구,
블랙보드 CLI `daedalus-bb`(`cli/`)가 설치 대상 작업 폴더에서 런타임 상태를 다룬다.

**경계 계약 (`tests/test_import_contracts.py`가 소스 AST로 강제):**
- core = `model/` + `compiler/` + `mcp/endpoint.py` + `cli/`. core는 Qt 바인딩
  (PySide6/PyQt6/shiboken6)·`daedalus.view`·MCP SDK(`mcp`)·`uvicorn`을 임포트할 수 없다
  (함수 안 지연 임포트도 금지 — 접두 매칭은 점 단위라 `daedalus.mcp` ≠ SDK `mcp`).
- `cli/`는 추가로 `daedalus.model`도 임포트할 수 없다 — 검증 정본이 컴파일 산출
  `schemas/<플러그인>.json` 파일 자체다(순수 stdlib).
- `mcp/tools/`는 core가 아니라 **GUI 어댑터**(MainWindow·VM·커맨드 스택 결합). `mcp/invoker.py`의
  Qt 의존, `mcp/service.py`의 SDK/uvicorn 의존은 의도된 설계. view→compiler 임포트는 정상.

**모듈 지도 (요약 — 파일 단위 상세는 아래 "파일 단위 모듈 지도"):**

| 경로 | 역할 |
|------|------|
| `model/fsm/` | 순수 FSM(상태·전이·가드·액션·블랙보드·Section/EventDef). 재귀 순회 단일 진실은 `walk.py` |
| `model/plugin/` | 플러그인 메타데이터 — config 계층·스킬/에이전트·도구·훅(`hook_store`는 파일시스템을 아는 유일한 훅 모듈)·필드 매트릭스·경로 변수·외부 플러그인 카탈로그(`wrap_catalog`/`plugin_cache`) |
| `model/project.py` | `PluginProject` 최상위 컨테이너 + 이름 변경/삭제/참조 판정 순수 함수 |
| `model/serialize/` | 모델↔JSON(format 2, 안정 ID) — `ser`←`migrate`←`deser_fsm`←`deser_plugin`←`deser` 단방향, `__init__`은 재-export 파사드 |
| `model/validation/` | Validator — `machine_rules` + `project_rules/`(그룹 믹스인), 등급은 `severity.WARNING_RULES` |
| `model/package.py`·`outline.py`·`templates.py` | 폴더=프로젝트/`.ddpj` · 본문 아웃라인 파생 인덱스 · 시작 템플릿 |
| `compiler/emit/` | 모델 → 텍스트(SKILL.md/agent .md/hooks/manifest/schemas, 랩핑 실행 에이전트 `wrapped.py`). 재-export 파사드 |
| `compiler/plan.py` | 산출 계획 — `_plan_outputs`(경로 집합) + 이름 규약·경로 충돌·훅 스크립트 이름 게이트 |
| `compiler/project_compiler.py` | `compile_project` — 검증 게이트 + (plan.py 계획) + 쓰기 + LOCAL 설치 배선. 계획 쪽 이름 재-export |
| `compiler/workspace.py`·`wiring.py`·`token_report.py` | CLAUDE.md 구역 병합·rules 렌더 · `.mcp.json`/settings 병합 · 토큰 리포트(표시 전용) |
| `mcp/` | 앱 내장 MCP 서버 — `tools/`(도메인 믹스인), `service.py`(HTTP 수명주기), `invoker.py`(메인 스레드 마샬링) |
| `cli/` | `daedalus-bb` — 블랙보드 read/init/write/validate/list + progress |
| `view/app.py` | MainWindow **골격** — 실체는 협력 객체 6종(`session_io`/`compile_actions`/`launch_actions`/`validation_actions`/`graph_io`/`component_actions`)에 있고 창에는 한 줄 위임만 |
| `view/actions/` | **UI 무관 편집 액션** — 캔버스 메뉴·에디터·MCP가 공유하는 기능의 실체 |
| `view/canvas/`·`commands/`·`editors/`·`panels/`·`viewmodel/`·`widgets/` | 노드 캔버스 · undo 커맨드 · 속성 편집기 · 독 패널 · VM(notify 채널) · 공용 위젯(마크다운 에디터 패키지, TagInput) |

## 테스트 봉합선과 위생 게이트

리팩토링이 **산출 바이트를 바꾸지 않았음**을 증명하는 장치와, 종류 분기가 다시
번지지 않게 막는 래칫이 여기 모여 있다. 전부 `tests/` 안에 살고 프로덕션 코드는
한 줄도 알지 않는다.

### 골든 스냅샷 (`tests/data/golden/`)

| 파일 | 무엇 |
|------|------|
| `corpus.py` | **코퍼스 2벌.** ① `dogfood.daedalus.json` — 실사용 프로젝트 `project/daedalus_cc_plugin/`의 **동결 사본**(살아 있는 작업 사본은 테스트가 읽지 않는다 — 사용자가 편집하면 골든이 무작위로 깨진다) ② 합성 프로젝트 — 9종 전부 × 배치/미배치 × 블랙보드 유/무 × 랩핑 스킬 3상태(state/reference/`enabled=False`) × async fork × fork 에이전트 × **훅을 가진 ReferenceSkill**. 실사용 코퍼스만으로는 `compile_wrapped_runner`·state 용도 랩핑 스킬·async fork가 0줄 커버라 두 벌이다. `_stamp_ids`가 uuid4 기본값을 결정적 id로 덮는다 |
| `trees/` | 복사 계획(`files_tree`/`skill_file`)을 태우는 **ASCII 전용** 픽스처. `.gitattributes`의 `-text`로 줄바꿈 정규화를 막는다 — 복사 바이트가 그대로 sha256에 들어간다 |
| `render.py` | 계산 쪽 **한 곳** — 테스트가 보는 것과 regen이 쓰는 것이 어긋날 수 없다(원칙 1) |
| `store.py` | 저장 형식 — `*.sha256`(`sha256sum` 형식, 키 정렬) · `plan/<코퍼스>-<타깃>.json` · `dogfood.project.json` |
| `regen.py` | 재생성 진입점 |

| 테스트 | 고정하는 것 |
|--------|-------------|
| `tests/compiler/test_golden_outputs.py` | 공개 파사드 9종(`compile_skill`/`compile_agent`/`compile_wrapped_runner`/`compile_hooks_json`/`compile_hook_scripts`/`compile_schemas_json`/`compile_plugin_manifest`/`compile_guide`/`render_rule`)과 `compile_project`가 쓴 **모든 파일**의 sha256. 파사드 9종이 전부 최소 1건의 산출을 냈는지도 함께 본다 |
| `tests/compiler/test_plan_order_golden.py` | 계획·쓰기 **순서** — `plan` / `written` / `copied_files` / `errors+warnings(rule, source)` / 게이트 실패 시 `skipped`. 기존 스위트는 순서를 거의 `set`으로만 비교해 "내용은 같은데 순서가 달라졌다"가 조용히 통과한다 |
| `tests/model/test_golden_project_json.py` | 동결 사본의 로드→저장 바이트 + 왕복 안정성(두 번째 저장도 같다) |

**골든 재생성 — 산출이 *의도적으로* 바뀐 커밋에서만:**

```bash
python -m tests.data.golden.regen            # 권장 (스크립트 진입점)
python -m pytest tests/ -q --regen-golden    # 같은 일을 pytest에서
python -m tests.data.golden.regen --refresh-dogfood   # 동결 사본 자체를 갈아끼울 때만
```

재생성 diff는 그 커밋의 리뷰 본문에 붙인다. **테스트를 통과시키려고 재생성하지
않는다** — 골든은 "바뀌었다"를 말해 주는 물건이지 자동으로 따라오는 물건이 아니다.
경로·정렬은 전부 정규화돼 있어(out_dir 기준 상대 POSIX 문자열, 키 정렬) 실행·플랫폼
간 결정적이다.

### 래칫 — 숫자는 내려가기만 한다

세 테스트가 소스 AST를 훑어 "종류 분기가 몇 군데인가"를 센다. **기준선은 이
저장소에서 실측한 값**이고(명세의 숫자를 베끼지 않았다) 각 리팩토링 WP는 그 수를
**내리기만** 한다 — 올리는 커밋은 리뷰가 거부한다. 기준선이 실측보다 크게 남아
있어도 실패한다(래칫은 조여야 의미가 있다).

| 테스트 · 표 | 세는 것 | 2026-09-19 실측 |
|---|---|---|
| `tests/test_polymorphism_ratchet.py` `RATCHET` ① | 컴포넌트/설정 클래스 29종을 두 번째 인자로 갖는 `isinstance` | **111 사이트 / 34 파일** |
| 〃 ② | 컴포넌트 형상 속성 12종(`config`/`body`/`fsm`/`transfer_on`/`call_agents`/`when_to_use`/`usage`/`enabled`/`reference_placements`/`source`/`output_events`/`output_event_defs`)을 문자열로 묻는 `getattr`/`hasattr`. 첫 인자가 `project`/`cfg`/`config`/`doc`이면 제외(컴포넌트 형상이 아니다) | **123 사이트 / 41 파일** |
| `tests/test_kind_literals.py` `RATCHET` ① | 컴포넌트 kind 16종이 `Compare` 피연산자·`dict` 키·`set`/`tuple`/`list` 원소로 쓰인 자리. 허용 파일 `model/serialize/migrate.py`(구버전 파일 문자열 해석이 정본)는 세지 않는다 | **157 사이트 / 26 파일** |
| 〃 ② plan kind | plan kind 14종. `agent`/`skill`이 컴포넌트 어휘와 겹치므로 `compiler/**`·`mcp/tools/query.py`에서만 센다. 최종 소유자는 WP-5가 신설할 `compiler/plan_kinds.py` 하나 | **22 사이트 / 3 파일** |

측정의 정직성: 짧은 kind 이름은 다른 어휘와 충돌한다 — `"agent"`는 훅 핸들러
종류·변수 컨텍스트·plan kind이기도 하고 `"reference"`는 랩핑 스킬의 `usage` 값
이기도 하다. 기준선에는 그런 자리도 섞여 있다. 래칫은 내려가기만 하면 되므로
섞임이 계약을 약하게 할 뿐 틀리게 하지는 않는다 — 숫자를 줄이는 WP가 실제 자리를
보고 판단한다. 면제는 줄 번호가 아니라 **`module::qualname`**으로 적는다(위아래
편집만으로 면제가 엉뚱한 자리로 미끄러지지 않도록). 오늘 면제는 0건이고, 사라진
자리를 면제가 붙잡고 있으면 테스트가 제거를 강제한다.

### 죽은 코드 게이트 (`tests/test_dead_code.py`)

`test_code_hygiene.py`(파일 크기 상한)·`test_import_contracts.py`(경계 계약)와
같은 결의 AST 소스 스캔이다. 앱을 임포트하지 않는다(헤드리스 안전).

- **규칙 A** — `daedalus/` 안 모든 최상위 `def`/`class`/모듈 레벨 상수와, 외부
  프레임워크를 상속하지 **않는** 클래스의 공개 메서드는 소비자가 있어야 한다.
- **규칙 B** — WP-RF 분해 파사드가 재-export하는 이름 중 **핀 목록(분해 시점
  스냅샷)에 없으면서** 소비자도 0인 것이 있으면 실패. 스냅샷은 기록이지 늘어나는
  레지스트리가 아니다.

참조로 치는 것: `ast.Name` · `ast.Attribute.attr` · import 별칭 · **문자열 상수**.
마지막이 중요하다 — MCP 도구 76종은 `mcp/service.py`의 `TOOL_NAMES` 문자열
튜플에서 `getattr`로 디스패치되고, `tests/compiler/test_purity.py`는 소스 문자열
안에서 임포트한다. 문자열을 참조로 세지 않으면 이 전부가 오탐이 된다.

자동 면제: dunder, 그리고 **외부 기저 클래스를 (간접적으로도) 상속한 클래스의
메서드** — Qt override(`paint`/`*Event`/`sizeHint`)가 여기 해당한다. 기저가 같은
이름을 정의하는지 알려면 PySide6를 임포트해야 하고 그건 헤드리스 계약을 깨므로,
기저를 소스에서 열거할 수 없는 클래스의 메서드는 전부 면제한다(보수적이지만
조용한 오탐보다 낫다).

`ALLOWLIST`는 `{심볼: (범주, 사유)}`이고 사유가 비면 실패한다. 범주 5종:
`framework-hook` · `entry-point` · `test-seam` · `contract-registry` ·
`facade-snapshot`. 오늘 등재는 셋뿐이다 — `COMPILER_ERROR_RULES`(게이트 rule
등급의 단일 진실, `test_gate.py`가 등가성을 양방향 강제) · `hook_to_json`(전역 훅
파일 포맷의 쓰기 반쪽, 네 테스트 모듈의 fixture 작성기) ·
`BodyDocumentRegistry.sync_from_model`(`editor.md:80`이 지정한 유일한 인가 경로).
목록은 **줄어들기만 한다** — 살아난 심볼을 붙잡고 있으면 테스트가 제거를 강제한다.

## 파일 단위 모듈 지도 (원문)

**컴파일러 패턴:** 순수 모델(model/) → 컴파일러(compiler/) → 플러그인 파일

현재 구현 범위: **model/ + view/ + compiler/ + mcp/ + cli/** (FSM 코어 + 플러그인 메타데이터 + PySide6 에디터 +
SKILL.md/agent .md/plugin.json/hooks/schemas 생성 + 앱 내장 MCP 서버(WP-MCP) + 블랙보드 CLI `daedalus-bb`(WP-BB1)).

**경계 계약 (WP-RF-2, B안 — 물리 이동 없음):** core = `model/` + `compiler/` + `mcp/endpoint.py` + `cli/`.
core는 Qt 바인딩(PySide6/PyQt6/shiboken6)·GUI 레이어(`daedalus.view`)·MCP SDK(`mcp`)·`uvicorn`을
임포트할 수 없다 — `tests/test_import_contracts.py`가 **소스 AST 기준**으로 강제한다(런타임 임포트 차단만으로는
함수 안 지연 임포트를 놓친다. 접두 매칭은 점 단위 — `daedalus.mcp`는 SDK `mcp`와 다르다). `mcp/tools/`는
core가 아니라 **GUI 어댑터**(MainWindow·VM·커맨드 스택 결합 표면 — 각 믹스인 모듈 docstring 명시)이고,
`mcp/invoker.py`의 Qt 의존과 `mcp/service.py`의 SDK/uvicorn 의존은 의도된 설계다. view→compiler 방향
임포트는 정상(컴파일러 패턴의 방향과 일치). **`cli/`는 core 금지 목록에 더해 `daedalus.model`도 임포트할
수 없다**(WP-BB1 — 설치 대상 프로젝트에서 도는 물건이라 검증 정본이 산출 `schemas/<플러그인>.json` 파일 자체다).

```
daedalus/
├── model/
│   ├── fsm/          # 순수 FSM 개념 (Claude 무관)
│   │   ├── event.py        # 이벤트 계층 (StateEvent, CompletionEvent, BlackboardTrigger)
│   │   ├── variable.py     # Variable + VariableScope/FieldType/ConflictResolution
│   │   ├── strategy.py     # EvaluationStrategy 계열 (Guard용) + ExecutionStrategy 계열 (Action용)
│   │   ├── guard.py        # Guard(evaluation: EvaluationStrategy)
│   │   ├── action.py       # Action(name, execution, output_variable)
│   │   ├── state.py        # State(ABC, reads/writes: list[str] 블랙보드 접근 선언 — WP-BB, "Class"/"Class.field" 문자열 참조), SimpleState, CompositeState, ParallelState, Region
│   │   ├── pseudo.py       # ChoiceState, TerminateState, EntryPoint, ExitPoint
│   │   ├── transition.py   # Transition + TransitionType
│   │   ├── join.py         # JoinStrategy (병렬 조인 전략 — 순수 FSM 개념. 정본 위치, 필요한 곳이 직수입)
│   │   ├── blackboard.py   # Blackboard, DynamicClass, DynamicField(FieldType 사용), FIELD_TYPE_TO_JSON_SCHEMA, BLACKBOARD_FIELD_TYPES(WP-BT — 블랙보드 필드 허용 타입 4종)
│   │   ├── section.py      # Section(자유 콘텐츠 계층 — 이제 v1 sections 트리 마이그레이션 입력으로만 쓰임),
│   │   │                   #   EventDef(transfer_on 출력 이벤트/에이전트 출력 포트 정의 — name/color/description),
│   │   │                   #   render_markdown(v1 sections→body 마이그레이션 헬퍼 — serialize._migrate_v1이 사용)
│   │   ├── machine.py      # StateMachine
│   │   └── walk.py         # 머신 재귀 순회 단일 진실(WP-RF) — iter_machines/iter_states/iter_transitions.
│   │                       #   CompositeState.sub_machine + ParallelState.regions[*].sub_machine 재귀 골격이
│   │                       #   6곳에 복제돼 있던 것을 모았다. 방문 순서가 곧 검증 경고·산출 항목 순서라
│   │                       #   docstring이 순서를 계약으로 명시하고 tests/model/fsm/test_walk.py가 고정한다:
│   │                       #   iter_machines=자기 자신 먼저+선언 순서 재귀, iter_states=깊이 우선 **전위**
│   │                       #   (상태 yield 직후 그 하위 머신 — iter_machines의 states를 이어붙인 것과 다르다),
│   │                       #   iter_transitions=iter_machines 순서의 머신 단위 묶음.
│   │                       #   **machine_rules._validate_machine은 의도적 예외** — path 누적(agent:/region:)이
│   │                       #   재귀 골격과 얽혀 있어 순회만 떼면 경로 라벨 불변을 보장할 수 없다(주석으로 명시).
│   ├── plugin/       # Claude 플러그인 메타데이터
│   │   ├── enums.py        # ModelType, EffortLevel, PermissionMode, AgentField, FieldEmit, BuildTarget(WP-TG) 등
│   │   ├── policy.py       # ExecutionPolicy (병렬 서브에이전트). JoinStrategy는 fsm/join.py에서 직수입 (re-export 없음 — RF-1b)
│   │   ├── config.py       # ComponentConfig(ABC) → SkillConfig(ABC) → StepSkillConfig(ABC) → ProceduralSkillConfig /
│   │   │                   #   ForkSkillConfig(ABC, +BUILTIN_FORK_AGENTS) → SyncForkSkillConfig·AsyncForkSkillConfig,
│   │   │                   #   WrappedSkillConfig, DeclarativeSkillConfig, TransferSkillConfig, ReferenceSkillConfig,
│   │   │                   #   AgentConfigBase(ABC) → AgentConfig(+background·isolation)·ForkAgentConfig
│   │   ├── base.py         # PluginComponent(ABC), WorkflowComponent(ABC)
│   │   ├── skill.py        # Skill(ABC) → StepSkill(ABC) → ProceduralSkill / ForkSkill(ABC) → SyncForkSkill·AsyncForkSkill(2026-09-17),
│   │   │                   #   WrappedSkill, DeclarativeSkill, TransferSkill, ReferenceSkill + is_reference_usage/is_disabled_wrapped
│   │   ├── agent.py        # Agent(ABC) → AgentDefinition(워크플로 — 캔버스 노드) / ForkAgent(fork 스킬 실행 기반, WP-FK2)
│   │   ├── placement.py    # 배치 가능 판정 **두 개**(is_state_placeable/is_canvas_placeable) + fork 역참조 fork_skills_using.
│   │   │                   #   캔버스 드롭·레지스트리 드래그·creation·MCP place_component·에이전트 편집기·삭제 확인·
│   │   │                   #   MCP still_referenced_by/used_by_fork_skills·컴파일러 fork 계약이 전부 여기를 부른다(원칙 1)
│   │   ├── tool.py         # Tool(ABC) + BuiltinTool/MCPTool/UserDefinedTool (tool_shelf 도구 단일 진실)
│   │   ├── hook.py         # HookDef + HookEvent(CC 9종) (hook_library 훅 단일 진실)
│   │   ├── hook_presets.py # BUILTIN_HOOK_PRESETS (복사용 훅 템플릿) + preset_copy(핸들러까지 깊은 복사)
│   │   ├── hook_store.py  # 전역 훅 저장소(A1) — ~/.daedalus/hooks/*.json 로더. global_hooks_dir/load_global_hooks/
│   │   │                  #   resolve_hooks(전역 ← 프로젝트 병합의 단일 진실)/hook_to_json. **파일시스템을 아는 유일한 훅 모듈**
│   │   ├── variables.py    # 본문 경로 변수(WP-RT) — ${ROOT} 타깃 중립 토큰, 타깃별 확장 매핑, 구버전 마이그레이션
│   │   │                   #   + SKILL_ONLY_VARIABLES(A6 — 스킬 본문에서만 치환되는 토큰 3종. skill_only_variable_in_body의 단일 진실)
│   │   ├── field_matrix.py # FieldRule(emit 포함), SKILL_FIELD_MATRIX(7종), AGENT_FIELD_MATRIX(agent/fork_agent)
│   │   │                   #   + **matrix_for(component)** — 표 선택의 단일 진실(키 = config.kind. 미지 kind는 ValueError)
│   │   └── workspace_doc.py# WorkspaceDoc(name, body, paths, id) — .claude/CLAUDE.md 구역과 .claude/rules/<name>.md의 편집 단위(WP-WD).
│   │                       #   값 동등성이고 id는 비교 제외 — 본문 undo 스택이 이름이 아니라 안정 식별자로 문서를 잡는다.
│   │                       #   paths(A13)는 규칙 전용 `paths:` 프론트매터 glob 목록 — 비면 프론트매터를 내지 않는다(항상 로드).
│   ├── project.py           # PluginProject (최상위 컨테이너, name+description+version — plugin.json 매니페스트 소스), ReferencePlacement, tool_shelf, hook_library, blackboard(최상위), graph(워크플로 백킹 머신)+graph_layout+edge_layout(WP-ER 엣지 웨이포인트, 키: Transition.id), emit_progress_hook(WP-RS SessionStart 진행 상태 훅 토글, 기본 True), build_target(WP-TG 빌드 타깃 — MARKETPLACE/LOCAL, 기본 MARKETPLACE), claude_md/rules(WP-WD 작업 폴더 문서 — LOCAL 전용 배출), mcp_server_defs(WP-MW — 이름→.mcp.json 서버 객체, LOCAL 설치 배선 소스)
│   │                       # + rename_component(project, component, new_name) — 이름 변경 + 문자열 참조 3종 일괄 갱신 (Qt 무관)
│   │                       # + remove_component(project, component) → list[str] — 모델 정리 (graph placement, skill_ref None화 등).
│   │                       #   undo 가능한 삭제는 view/commands의 RemoveComponentCmd가 이것을 감싼다(A2) — 이 함수 자체는 계속 순수 모델
│   │                       # + project_state_machines(project) — 그래프 + 각 스킬/에이전트 FSM(라벨 없음, 그래프 포함)
│   │                       # + blackboard_rename_ref_updates(project, old, new) → [(state, "reads"|"writes", 새 리스트)] —
│   │                       #   블랙보드 클래스 개명 시 갱신될 상태 접근 선언을 **계산만** 한다(모델 불변). GUI는 그대로 대입하고
│   │                       #   MCP는 같은 값으로 SetAttrCmd를 만들어 1 undo 단위로 묶는다 — 적용은 표면마다 달라도 판정은 한 곳
│   │                       # + blackboard_class_referrers(project, name) → list[str] — "name"/"name.field"를 참조하는 노드 이름(정렬)
│   ├── package.py           # 프로젝트 패키지(WP-PK) — 폴더가 곧 프로젝트. PROJECT_FILENAME(".daedalus.json")/ARCHIVE_SUFFIX(".ddpj"),
│   │                       #   resolve_project_file(저장 대상)/find_project_file(열 대상)/project_dir/display_name,
│   │                       #   pack(결정적 zip)/unpack(zip slip 방어). Qt 무관 순수 stdlib.
│   ├── outline.py           # 본문 아웃라인(WP-BO) — body 마크다운의 파생 인덱스. parse_outline(fence-aware 헤딩 파서)/
│   │                       #   find_section(제목·"## 제목" 레벨 지정·"부모 > 자식" 경로, 0개·복수 매칭 ValueError)/
│   │                       #   section_text/char_span/replacement_text(비교체 구간 바이트 보존). Qt 무관 순수 stdlib.
│   ├── templates.py         # 시작 템플릿 카탈로그(A7) — 아키타입 3종의 id/제목/요약(TEMPLATES) +
│   │                       #   list_templates/find_template/load_template(TemplateError) +
│   │                       #   **save_user_template/delete_user_template**(Save As Template) —
│   │                       #   현재 프로젝트를 ~/.daedalus/templates/에 저장한다. 형식은 저장 파일 그
│   │                       #   자체(serialize_project 산출)이고, source_dir에 동봉 파일이 있으면
│   │                       #   폴더형(<id>/.daedalus.json + files/·skill-files/ 복사)으로 — 그래야 첫
│   │                       #   저장 때 딸려 간다. id는 ^[a-z0-9][a-z0-9-]*$ 강제(파일 이름이 된다 —
│   │                       #   조용히 슬러그로 바꾸면 지은 이름과 목록의 이름이 달라진다), 동명은
│   │                       #   overwrite 명시 필요, 형식 전환 시 옛 형태 제거. 표면: File 메뉴
│   │                       #   "템플릿으로 저장…"(SessionIO.save_as_template_dialog) / MCP
│   │                       #   save_as_template·delete_user_template(홈 파일 쓰기라 undo 비대상).
│   │                       #   **두 경로가 함께 산다**: 내장은 패키지 데이터(pyproject package-data —
│   │                       #   재설치 때 갈린다), 사용자 템플릿은 홈에 남는다.
│   │                       #   **사용자 템플릿**: `~/.daedalus/templates/<id>.json`(저장 파일 그대로 복사)이
│   │                       #   카탈로그에 병합 — 동명 id는 사용자 우선, 제목=name·요약=description, 깨진 파일은
│   │                       #   stderr 스킵(전역 훅 규약). 영어·플레이스홀더 게이트 비대상. **폴더형**
│   │                       #   `<id>/.daedalus.json`도 인식(동명 공존 시 폴더형 우선 + 경고) — source_dir의
│   │                       #   files/·skill-files/가 첫 저장 때 프로젝트 폴더로 동반 복사된다
│   │                       #   (SessionIO.carry_template_assets — 원본 참조 방식, 소실 시 fail-soft 경고 1회,
│   │                       #   목적지 실존 시 불가침. 복사 루프는 carry_files_dir와 _copy_side_dirs 공용).
│   │                       #   테스트 격리는 conftest _isolate_user_templates. 실제 시드는
│   │                       #   `daedalus/templates/<id>.json`(serialize 산출 format 2)이고 로드는 기존
│   │                       #   deserialize_project를 그대로 탄다 — 전용 파서 없음. Qt 무관 순수 stdlib.
│   ├── serialize/           # 모델↔JSON dict 직렬화 (안정 ID 기반, format 2). 구 serialize.py(1,437줄)를 WP-SZ로
│   │   │                   #   패키지 분해(이동만·동작 불변). 의존 방향 ser ← migrate ← deser_fsm ← deser_plugin ← deser 단방향(순환 없음)
│   │   ├── __init__.py     #   재-export 파사드 — 분해 전 모듈의 모든 속성(public + 테스트가 쓰는 _ser_tool/_deser_tool
│   │   │                   #   등 _헬퍼 + 부수 임포트) 보존. `from daedalus.model.serialize import …` 기존 경로 무수정 동작
│   │   ├── ser.py          #   정방향 — serialize_project + _ser_* 전부. FORMAT_VERSION의 단일 진실(쓰는 쪽이 선언)
│   │   ├── migrate.py      #   v1→v2 단방향 마이그레이션 집약 — _migrate_v1/_promote_local_skills/_v1_all_machines/
│   │   │                   #   _v1_scrub_number + _deser_section(v1 sections 트리 전용이라 여기 — deser에 두면 순환)
│   │   │                   #   + migrate_skill_context/needs_skill_context_migration(스킬 context·agent 퇴역 — format 2에도 적용)
│   │   ├── deser_fsm.py    #   역방향 FSM 계층 — _Registry(id→객체, dangling 경고. 그것을 소비하는 최하위 계층이라
│   │   │                   #   여기 산다) + _to_enum/변수/전략/액션/가드/이벤트/블랙보드/상태/전이/머신
│   │   ├── deser_plugin.py #   역방향 플러그인 계층 — 본문/포트(EventDef)/config/정책/스킬/에이전트/참조 배치/
│   │   │                   #   훅/작업 폴더 문서/도구. deser_fsm만 수입(역방향 없음)
│   │   └── deser.py        #   역방향 오케스트레이터 — 2-pass deserialize_project. 두 형제의 이름을 전부
│   │                       #   재수입하므로 `serialize.deser` 경로와 파사드 항등(`serialize._deser_tool is
│   │                       #   deser._deser_tool`)이 분해 전과 동일하게 성립한다
│   └── validation/          # 모델 검증 (Qt·파일시스템 무관). 구 validation.py를 WP-RF-3d로 패키지 분해(이동만·동작 불변)
│       ├── __init__.py     #   재-export 파사드 + `Validator(_MachineRules, _ProjectRules)` 합성 — 분해 전 모듈의 모든 속성
│       │                   #   (public + 테스트가 쓰는 _헬퍼)과 `Validator._check_*` 이름 전부 보존(기존 임포트 무수정 동작)
│       ├── severity.py     #   ValidationError(rule/message/source/subject/path + is_warning) + WARNING_RULES(경고 등급 단일 진실)
│       ├── machine_rules.py#   머신 수준 규칙 18종(_MachineRules 믹스인 — validate/_validate_machine 재귀 + _STATE_ACTION_FIELDS)
│       │                   #   + SKIPPABLE_RULES(skip_rules 허용 이름)
│       └── project_rules/   #   프로젝트 수준 규칙(_ProjectRules 믹스인 — validate_project 오케스트레이터).
│                            #   A6에서 1,090줄 단일 모듈을 그룹별 믹스인 패키지로 분해(이동만·동작 불변).
│                            #   __init__.py = 재-export 파사드 + 믹스인 9종 합성(CC_BUILTIN_TOOLS·
│                            #   _strip_markdown_code·_ProjectRules 기존 임포트 무수정 동작).
│                            #   text.py(코드 스팬 제외) / scan.py(공용 순회 — graph_has_placements·
│                            #   project_machines·scan_state_access·scan_transitions **모듈 함수**가 실체,
│                            #   믹스인이 staticmethod로 재노출. 그룹끼리 _ProjectRules 경유로 부르면
│                            #   파사드와 순환) / naming / tools / hooks / blackboard / body_variables /
│                            #   build_target / workflow / fork(fork 에이전트 — fork_project_agent) / workspace
├── compiler/         # 순수 모델 → 플러그인 파일 (Qt 무관)
│   ├── emit/               # model → SKILL.md/agent .md/hooks.json 텍스트 (결정적, LF). 구 emit.py를 WP-RF-3a로 패키지 분해(이동만·동작 불변)
│   │   ├── __init__.py     #   재-export 파사드 — 분해 전 emit.py의 모든 속성(public + 테스트가 쓰는 _헬퍼) 그대로 제공,
│   │   │                   #   기존 `from daedalus.compiler.emit import …` 임포트 전부 무수정 동작(test_emit_facade.py가 고정)
│   │   ├── common.py       #   공용 헬퍼 — _enum_value/_config_default/_MISSING/_body_block/_join_blocks/_build_target/_is_local_build/_graph_placements(_any)
│   │   ├── frontmatter.py  #   YAML 표기(_yaml_scalar/_yaml_list/_yaml_block_lines) + 스킬 프론트매터(_frontmatter_lines_skill)·_compose_description
│   │   ├── sections.py     #   공용 단락 — 가드/트리거·FSM 절차 서술(_describe_fsm)·요구 환경 MCP(referenced_mcp_servers)·블랙보드(_blackboard_section)·tool_shelf
│   │   ├── skill.py        #   SKILL.md 조립 — 다음 단계·작업 재개(WP-RS)·진입 맥락(WP-IC) + compile_skill
│   │   ├── agent.py        #   에이전트 .md 조립 — 프론트매터(skills 합류·LOCAL hooks/mcpServers)·호출 계약·출구 + compile_agent
│   │   ├── wrapped.py      #   랩핑 스킬 산출 — 위임 절차 단락 + 실행 서브에이전트(compile_wrapped_runner/needs_runner_agent/parse_wrapped_source)
│   │   ├── fork.py         #   fork 스킬 산출(2종, 2026-09-17) — resolve_fork_agent_name(타깃별 agent 이름)/
│   │   │                   #   fork_frontmatter_lines(agent: 이름 해소만 — context·background는 매트릭스 FIXED)/
│   │   │                   #   fork_report_section("## Report", 종류별 도입·async 선행 조건)/
│   │   │                   #   fork_skills_using(model.plugin.placement 재-export 껍데기)
│   │   ├── guides.py       #   공통 안내 파일(WP-FK2 C3) — compile_workflow_guide/compile_blackboard_guide/compile_guide,
│   │   │                   #   포인터 판정(workflow_pointer_kind: ""|"main"|"fork" / blackboard_pointer_wanted)과
│   │   │                   #   guide_pointer_line/_insert_guide_pointer, guide_rel_path, GUIDE_KINDS.
│   │   │                   #   가이드 본문에는 ${ROOT} 등 치환 변수를 쓰지 않는다(<SCHEMAS> 자리표시자)
│   │   ├── hooks.py        #   compile_hooks_json/compile_hook_scripts (진행 상태 합성 훅 포함)
│   │   └── manifest.py     #   compile_plugin_manifest/compile_schemas_json + 경로 변수 확장(expand_root_token)
│   ├── plan.py             # 산출 계획(WP-FK2 C0 분해, 이동만) — _PlannedOutput/_plan_outputs/_hook_script_name_conflicts/
│   │                       #   _iter_tree_files/_is_link_like/_skill_dir_name/SKILL_FILES_DIRNAME/_OUTPUT_NAME_RE.
│   │                       #   "무엇이 어디로 나가는가"와 계획 단계 게이트(이름 규약·경로 충돌·훅 스크립트 이름)만 담는다.
│   │                       #   project_compiler가 전부 재-export한다(기존 임포트 경로 불변 — tests/compiler/test_plan_facade.py가 고정).
│   ├── project_compiler.py # compile_project(project, out_dir=None, files_dir=None, resolved_hooks=None, dry_run=False) → CompileResult
│   │                       #   (검증 게이트 + 파일 쓰기. 계획은 plan.py)
│   │                       # files_dir(WP-FR, 선택): 실존 디렉토리면 <out>/files/ 정렬 순회 복사(_copy_files_tree, 심볼릭 링크 미추종) +
│   │                       #   dangling_file_ref 스캔(_scan_dangling_file_refs). 생략 시 기존 산출 완전 불변(하위 호환).
│   │                       # LOCAL 빌드는 컴파일이 곧 설치(WP-MW) — .claude/ 반입 + _wire_local_install(컴파일 정책 15번 참조).
│   │                       # dry_run(G3): 파일을 하나도 쓰지 않는 예행 — 컴파일 정책 18번 참조.
│   ├── workspace.py        # merge_claude_md(existing, plugin, title, body) → (새 내용|None, 경고|None) (WP-WD) — .claude/CLAUDE.md의
│                           #   `<!-- daedalus:<플러그인> open/close -->` 구역만 갈아끼운다. 구역 밖 불가침·플러그인 여럿 공존·재빌드
│                           #   멱등. 손상된 표식(close 없음/open 중복/순서 뒤바뀜)은 **건드리지 않고** 경고만 낸다 — 구역의 끝을
│                           #   추측하면 그 뒤의 사용자 내용을 통째로 날린다. 순수 stdlib.
│                           # + render_rule(doc) — .claude/rules/<이름>.md 최종 텍스트(A13). paths가 있으면 `---\npaths: [...]\n---`를
│                           #   앞에 붙이고 비면 본문만(필드 도입 전과 바이트 동일). 원소는 항상 따옴표(_quoted_flow_list — glob의
│                           #   중간 `[`/`,`는 YAML flow 지시자라 무따옴표면 스칼라가 끊긴다). has_manual_frontmatter(body)는
│                           #   본문 수기 프론트매터 충돌 판정(rule_body_frontmatter 경고) — 판정만 하고 본문은 손대지 않는다.
│   ├── wiring.py           # wire_workspace(target, server_entries, hooks_map, dry_run=False) → WireResult (WP-MW) — 작업 폴더의
│   │                       #   .mcp.json mcpServers + .claude/<settings_name> enabledMcpjsonServers/hooks 병합(settings_name 기본
│   │                       #   settings.local.json — 앱 메뉴 경로. LOCAL 컴파일은 선택한 settings.json/settings.local.json을 넘긴다). 추가/갱신만·멱등·
│   │                       #   깨진 JSON 불가침. LOCAL 컴파일과 앱 "Claude Code 실행" 메뉴가 공유하는 단일 진실. 순수 stdlib.
│   │                       #   dry_run(G3): 읽고 병합을 메모리에서 계산하되 **쓰지 않는다** — written/unmergeable 판정은 동일.
│   └── token_report.py     # 토큰 비용 리포트(A5-lite) — estimate_tokens(문자수 휴리스틱)/TokenEstimate/TokenReport/
│                           #   DEFAULT_FILE_TOKEN_THRESHOLD/CONTEXT_KINDS. **표시 전용**이다: 산출 텍스트 불변,
│                           #   임계 초과는 검증 규칙이 아니라 정보성 1줄(notice()). 순수 stdlib(외부 토크나이저 금지).
│                           #   **임계 판정은 리포트만 한다** — TokenEstimate는 값만 들고, 항목 단위 판정 property를
│                           #   두면 모듈 상수를 봐서 TokenReport.threshold와 진실이 둘이 된다. 리포트 전체를 dict로
│                           #   내는 직렬화도 두지 않는다(소비자가 생기면 그 호출 지점에서 만든다).
├── mcp/              # 앱 내장 MCP 서버 (WP-MCP) — CC와 협업하는 창구
│   ├── endpoint.py         # 접속 정보(~/.daedalus/mcp-endpoint.json) + 포트 탐색 + .mcp.json 스니펫 (Qt 무관 순수)
│   ├── invoker.py          # MainThreadInvoker — uvicorn 워커 스레드 → Qt 메인 스레드 마샬링(시그널+Event, 타임아웃)
│   ├── tools/              # DaedalusTools — 도구 구현(조회·편집·세션·본문 부분 접근(WP-BO)). 메인 스레드 실행 전제.
│   │   │                   #   **GUI 어댑터**(WP-RF-2) — MainWindow·VM·커맨드 스택 결합 표면, core 경계 계약 대상 아님.
│   │   │                   #   구 단일 모듈 tools.py를 WP-RF-3b로 도메인별 믹스인 패키지로 분해(이동만·동작 불변)
│   │   ├── __init__.py     #   재-export 파사드 + DaedalusTools 합성 클래스(믹스인 8종 상속) — 메서드 이름·시그니처·
│   │   │                   #   docstring 분해 전과 동일(SDK 입력 스키마 원료 — service._wrap의 functools.wraps 경로),
│   │   │                   #   기존 `from daedalus.mcp.tools import DaedalusTools` 무수정 동작(test_tools_facade.py가 고정)
│   │   ├── _base.py        #   _BaseTools — 공통 헬퍼(_project/_vm/_find_component/_find_state_vm/_scope/_reject_duplicate_name
│   │   │                   #     + _hook_summary — 훅 **개요**. QueryTools와 HookTools가 함께 쓰므로 소유가 여기다
│   │   │                   #     + _visible_global_hooks — 가려지지 않은 전역 훅(A1, G7). 같은 이유로 여기 산다
│   │   │                   #     + _scene — 프로젝트 캔버스 씬. CanvasTools(참조 노드)와 PropsTools(생성+배치 G14)가
│   │   │                   #       함께 쓴다)
│   │   ├── query.py        #   조회(get_project/get_selection/focus_node/select_nodes/get_component/validate_project/
│   │   │                   #     compile_preview/compile_check/list_tool_candidates) + undo 스택(undo/redo/get_history).
│   │   │                   #     focus_node/select_nodes(G16)는 get_selection의 **쓰기 짝**이고 undo 비대상 —
│   │   │                   #     실체는 ValidationActions.focus_in_project_canvas / FsmScene.select_state_vms.
│   │   │                   #     get_project의 hook_library는 **개요만**(전문은 get_hook), 전이 요약은 guard 서술(컴파일러
│   │   │                   #     _describe_guard 재사용)과 waypoint_count를 포함한다. get_project(sections=)로 구획만
│   │   │                   #     받을 수 있다(Q4 — meta/components/canvas/blackboard/hooks, 생략 시 전체 하위호환).
│   │   │                   #     meta의 workspace_docs는 작업 폴더 문서 존재 신호(Q6 — {claude_md, rules} 개수).
│   │   │                   #     get_component의 config는 비기본값만(Q3 — type(config)()와 비교).
│   │   │                   #     validate_project(severity=, component=)로 걸러 받는다(Q5 —
│   │   │                   #     component 판정은 actions/warnings.findings_for 재사용, total_* 개수 병기).
│   │   │                   #     compile_check(G3)는 파일을 쓰지 않는 컴파일 예행 — 컴파일러 emit 경고 7종을 미리 본다.
│   │   │                   #     list_tool_candidates(G9)는 catalogue_loader.candidate_strings 재사용 — TagInput과 같은 산출
│   │   ├── session.py      #   세션(save_project/open_project/new_project/import_package/export_package/
│   │   │                   #     list_recent_projects/list_project_templates — G11·G12).
│   │   │                   #     _save_before_switch가 "먼저 저장" 게이트의 단일 실체(open_project·new_project 공용)
│   │   ├── canvas.py       #   캔버스 구조(place/create_state/move/rename/delete/connect/disconnect/set_transition/참조 노드).
│   │   │                   #     set_transition(create_transfer=) — TransferSkill 생성+할당 1 undo(G15, 씬과 같은 커맨드 조립).
│   │   │                   #     move_reference(G13 — move_state의 짝, MoveRefCmd)/
│   │   │                   #     set_transition_waypoints(G10 — 경유점 전체 교체 1종, Clear+Add를 MacroCommand로)
│   │   ├── ports.py        #   포트(set_transfer_on/add_agent_call/remove_agent_call)
│   │   ├── blackboard.py   #   블랙보드(create/update/delete_blackboard_class + set_blackboard_fields/set_state_access)
│   │   ├── hooks.py        #   훅 라이브러리(create/update/delete_hook/set_component_hooks/get_hook/list_hook_events/hook_frontmatter_preview/
│   │   │                   #     list_hook_presets/copy_global_hook — G7·G8).
│   │   │                   #     _hook_detail(전문 = 개요 + 핸들러 CC 스키마 + 스크립트 본문)은 get_hook과 편집 결과에서만
│   │   ├── body.py         #   본문(set_component_body/get_body_outline/get_body_section/set_body_section — WP-BU/WP-BO 경로)
│   │   ├── props.py        #   생성·속성(create_skill/create_agent/rename_component/description/when_to_use/field/project_properties/set_mcp_server_def).
│   │   │                   #     팩토리는 actions/creation.make_component 직호출(S1 — 자체 dict 2벌 폐기),
│   │   │                   #     create_skill/create_agent의 x·y는 create_and_place로 생성+배치 1 undo(G14)
│   │   ├── wrap.py         #   외부 플러그인 카탈로그(WP-WR D2) — list_wrappable_skills/list_marketplace_folders/
│   │   │                   #     add_marketplace_folder/remove_marketplace_folder(홈 파일 — undo 비대상)/
│   │   │                   #     set_external_plugins(프로젝트 사용 선언 — undo). 실체는 model/plugin/wrap_catalog +
│   │   │                   #     actions/creation.create_wrapped_skill(GUI 카탈로그 창과 공유)
│   │   └── workspace.py    #   작업 폴더 문서(WP-WD) — list_workspace_docs/get_workspace_doc/set_claude_md/create_rule/
│   │                       #     set_rule_body/set_rule_paths(A13)/rename_rule/delete_rule. 본문은 BodyTools와 같은
│   │                       #     QTextDocument 경로(WP-BU), 구조 편집은 GUI 패널과 같은 모델 직접 기록.
│   └── service.py          # DaedalusMCPService — MCPServer 구성(_server_factory가 mcp 1.x/2.x 흡수) + uvicorn 데몬 스레드 수명주기
├── templates/        # 시작 템플릿 시드 파일(A7) — `<id>.json` 3개. **손으로 쓴 JSON이 아니라
│                     #   serialize_project의 산출(format 2)**이고 model/templates.py가 읽는다.
│                     #   패키지 데이터라 pyproject의 [tool.setuptools.package-data]에 등재돼 있다.
├── cli/              # 블랙보드 CLI (WP-RF-2 신설 → WP-BB1 구현) — C+A 설계: uv tool install로 앱과 함께 설치되고,
│   │                 #   컴파일 산출의 블랙보드 지시가 런타임에 이 CLI를 호출해 work 폴더의 state/를 읽고 쓴다.
│   │                 #   core 경계 소속 — Qt·view·MCP SDK·uvicorn 금지 + **daedalus.model도 금지**(순수 stdlib).
│   ├── blackboard.py # daedalus-bb 진입점·인자 계약·스키마·상태 IO (pyproject [project.scripts] 등록 완료).
│   │                 #   read/init/write/validate/list + 최소 JSON Schema 검증기
│   │                 #   (type/properties/required/items/uniqueItems) + 원자적 쓰기·낙관적 잠금.
│   │                 #   상세는 "블랙보드 CLI (WP-BB1)" 개념 섹션 참조.
│   └── progress.py   # progress read/set — state/__progress__.json (WP-NS/D13). 최상위 키가 플러그인
│                     #   이름인 **공유 파일**이라 병합을 코드가 보장한다. blackboard의 쓰기·잠금 재사용
│                     #   (순환 회피로 blackboard 쪽 dispatch만 지역 임포트).
└── view/             # PySide6 기반 노드 에디터
    ├── recent.py           # 최근 프로젝트 목록(WP-RP) — ~/.daedalus/recent.json 읽기/쓰기 (Qt 무관 순수 stdlib).
    │                       #   load/save/push/remove/clear + MAX_RECENT. 기록 실패는 삼킨다(endpoint.py와 같은 정책).
    │                       #   실존 검사는 하지 않는다 — 메뉴를 열 때마다 stat을 때리면 네트워크 드라이브에서 UI가 멈춘다.
    ├── app.py              # 메인 윈도우 **골격** (WP-RF-3e 분해 후 — 줄 수는 `docs/backlog.md` §7 표가 단일 진실) — 탭·독·메뉴 배선 + 컴포넌트 편집 진입.
    │                       #   나머지는 협력 객체 6종에 위임(Mixin 아님 — 상속으로 섞으면 이름 충돌과 self의 정체가 흐려진다):
    │                       #   session_io.py / compile_actions.py / launch_actions.py / validation_actions.py /
    │                       #   graph_io.py / component_actions.py (아래 각 항목).
    │                       #   **협력 객체가 실체이고 MainWindow에는 같은 이름의 한 줄 위임 메서드만 남는다** — 테스트와 MCP 도구가
    │                       #   window._save_to_path(...)처럼 윈도우의 내부 메서드를 직접 부르기 때문이다(tests/view/test_app_collaborators.py가 고정).
    │                       #   **위임은 한 방향이다** — 협력 객체끼리·자기 자신의 후속 단계는 self.update_title()처럼 협력 객체 쪽을
    │                       #   직접 부르고 window의 동명 위임으로 되돌아가지 않는다(실체를 파사드 경유로만 닿게 만들면 방향이 꼬인다).
    │                       #   따라서 window._update_title 등을 인스턴스 레벨로 가로채도 협력 객체 내부 호출에는 걸리지 않는다(현재
    │                       #   그렇게 하는 코드는 없다 — 부수효과를 얹으려면 협력 객체 쪽 메서드를 고친다).
    │                       #   **상태(_project/_current_path/_mcp_service/_status_label …)의 단일 진실은 계속 윈도우**이고 협력 객체는
    │                       #   그것을 복제하지 않고 self._w.<attr>로 직접 읽고 쓴다(복제하면 두 곳이 어긋나는 순간 "저장했는데 다른
    │                       #   파일이 열린다"가 된다). 협력 객체는 위젯 배선보다 **먼저** 생성한다 — _setup_menus가 최근 목록을 채우며
    │                       #   곧바로 _session_io를 부른다. QFileDialog/QInputDialog는 app.py에 임포트를 남긴다(테스트가
    │                       #   `daedalus.view.app.QFileDialog...` 경로로 몽키패치 — 클래스 속성 패치라 협력 객체에도 그대로 걸린다).
    │                       # 메뉴: Ctrl+N "새 프로젝트"(기본 이름 "new-plugin", 빌드 타깃 선택 다이얼로그 — WP-TG, 취소 시 생성 취소),
    │                       #   F7 "프로젝트 검증", Ctrl+B "컴파일", 파일→"프로젝트 속성...", 도구→"MCP 서버 정보..."/"Claude Code 실행".
    │                       # 컴포넌트 생성·이름 변경·삭제는 component_actions.py로 이관(아래 항목) — 창에는 한 줄 위임만.
    │                       # 탭 구조(WP-BB/WP-HK/WP-WD): 0=프로젝트 FSM 캔버스, 1=블랙보드(BlackboardPanel), 2=훅 라이브러리(HookLibraryPanel),
    │                       #   3=CLAUDE.md 구역(ClaudeMdPanel), 4=규칙(RulesPanel), 5=작업 폴더 설정(WorkspaceSettingsPanel — WP-WS)
    │                       #   — 상주·닫기 불가 고정 6개. _close_tab이 여섯 인덱스를
    │                       #   모두 거부하고, load_project의 탭 정리 루프는 _LAST_FIXED_TAB_INDEX 다음부터 닫는다.
    │                       #   **LOCAL 전용 탭 표시(WP-WS)**: 탭 3·4·5는 빌드 타깃이 LOCAL일 때만 보인다 —
    │                       #   _refresh_target_dependent_tabs가 setTabVisible로 **숨긴다**(제거 아님 — 인덱스가
    │                       #   보존돼야 고정 탭 체계·_open_tabs가 흔들리지 않는다). set_project와
    │                       #   _on_project_vm_changed(빌드 타깃 변경 notify)가 갱신, 프로젝트 없으면 보임(기능 발견).
    │                       #   set_project가 blackboard_panel.set_project(project) + tag_input.set_blackboard_candidate_provider(...)를 배선.
    │                       # 파일 독(WP-FR): _setup_docks가 FilePanel을 "플러그인 파일 (공용)" 독으로 배치하고
    │                       #   markdown_editor.set_files_root_provider(lambda: self._file_panel.files_root())를 등록.
    │                       # 미저장 변경: _dirty 플래그 + _mark_dirty/mark_clean/confirm_discard_changes.
    │                       #   상세는 "미저장 변경 확인" 개념 섹션 참조.
    ├── session_io.py       # SessionIO(window) — 저장/열기/최근 목록/패키지(.ddpj) (WP-RF-3e에서 app.py로부터 추출).
    │                       # 프로젝트 패키지(WP-PK): 열기/저장이 **폴더** 단위. open_project_dialog(폴더 선택)/open_file_dialog(구버전 파일 직접)/
    │                       #   save_project_as(폴더 선택 — 형식이 새 형식으로 바뀌는 유일한 지점)/export_package_dialog/import_package_dialog.
    │                       #   save_to_path가 package.resolve_project_file로 폴더→정본 파일 해석 + 없는 폴더 생성 + carry_files_dir(다른 폴더로
    │                       #   저장 시 files/·skill-files/ 동반 복사). open_path는 package.find_project_file로 폴더→파일 해석.
    │                       #   window._current_path는 계속 **파일**을 가리킨다.
    │                       # sync_files_root(_current_path 기준 project_dir/files 재계산 + MCP 접속 정보 갱신)를 save_to_path/open_path/
    │                       #   new_project 끝에서 호출 — _current_path가 바뀌는 지점이 여기 하나로 모여 배선 지점도 하나다.
    │                       # 최근 프로젝트(WP-RP): File→"최근 프로젝트" 서브메뉴(window._recent_menu). remember_recent(open_path/save_to_path
    │                       #   성공 경로에서 호출)가 recent.push + rebuild_recent_menu. 항목 클릭 → open_recent(사라진 파일은 그 자리에서
    │                       #   목록에서 제거), "목록 지우기" → clear_recent. 라벨은 **모듈 수준 순수 함수** recent_label(&1 파일명 — 상위폴더,
    │                       #   & escape; MainWindow._recent_label이 staticmethod로 재노출 — 테스트가 클래스에서 직접 호출한다), 툴팁=전체 경로.
    │                       # 프로젝트 생성/속성: new_project(Ctrl+N — **통합 다이얼로그** NewProjectDialog: 출발점(빈|템플릿 3종) +
    │                       #   빌드 타깃을 같이 선택, 취소=생성 취소. 사용자 확정으로 A7의 별도 메뉴 항목을 흡수. **생성 시 고른
    │                       #   타깃이 템플릿 저장 타깃을 이긴다**. 테스트 봉합선은 SessionIO.exec_new_project_dialog 몽키패치 —
    │                       #   구 QInputDialog.getItem 스텁의 후임)/edit_project_properties
    │                       #   → ProjectPropertiesDialog(name/description/version + emit_progress_hook 체크박스, 이름 규약 미강제).
    │                       #   project_has_content("새 프로젝트" 확인과 MCP open_project의 저장 강제가 공유하는 단일 판정).
    │                       #   템플릿 로드 후 _mark_dirty()(잃을 내용이 있고 저장 경로가 없다), 실패는 상태바 보고 + 현 프로젝트 보존.
    ├── compile_actions.py  # CompileActions(window) — Ctrl+B 컴파일 (WP-RF-3e에서 추출).
    │                       #   compile_project_dialog: 출력 폴더 선택(LOCAL이면 "설치 대상 작업 폴더" — WP-MW) 후 compile_project 실행.
    │                       #     에러면 window._show_validation_dock().
    │                       #   compile_inputs()(G3): compile_project에 넘길 **환경 주입 인자의 단일 진실** — _current_path 기준
    │                       #     files_dir/skill_files_dir(미저장이면 None) + extra_server_defs + resolved_hooks. Ctrl+B와 MCP
    │                       #     compile_check(dry-run)가 **같은 것**을 주입해야 같은 경고가 나온다(window.compile_inputs 한 줄 위임).
    │                       #   known_server_defs: 앱이 스스로 아는 daedalus 서버 정의(서버 미기동이면 기본 포트) — extra_server_defs로 주입.
    │                       #   show_token_notice(result)(A5-lite): 상태바에 합계(`≈N토큰`)를 **항상** 붙이고, 파일당 임계를 넘은
    │                       #     산출이 있을 때만 QMessageBox 안내(검증 패널을 쓰지 않는다 — 고칠 의무가 있는 경고와 섞이면 안 된다).
    ├── launch_actions.py   # LaunchActions(window) — MCP 서버 수명주기 + Claude Code 실행 (WP-RF-3e에서 추출).
    │                       #   start_mcp_service(port)(__main__.main만 호출 — 테스트가 MainWindow를 수십 개 만들어 자동 기동은 포트 충돌)/
    │                       #   stop_mcp_service(MainWindow.closeEvent가 호출)/show_mcp_info(McpInfoDialog — 정보 전부 즉시 표시.
    │                       #     스니펫은 읽기 전용 QPlainTextEdit + "스니펫 복사" 버튼(ActionRole이라 눌러도 안 닫힘) — QMessageBox
    │                       #     본문은 Qt 기본 스타일 힌트상 선택 불가라 붙여넣을 텍스트를 긁어갈 수 없다)/
    │                       #   launch_claude_code(프로젝트 저장 폴더에서 새 콘솔로 claude 실행. 미저장·서버 미기동이면 상태바 안내 후 중단)/
    │                       #   ensure_daedalus_mcp_json(wiring.wire_workspace로 daedalus 서버를 .mcp.json/settings.local.json에 배선).
    ├── validation_actions.py  # ValidationActions(window) — F7 검증 + 결과 항목 → 노드 포커스 (WP-RF-3e에서 추출).
    │                       #   run_validation(Validator.validate_project → ValidationPanel + dock 표시)/show_validation_dock(컴파일 경로와 공용)/
    │                       #   find_validation_dock/on_validation_item_activated → focus_in_project_canvas | focus_in_agent_tab.
    │                       #   탭 인덱스 상수(_FSM_TAB_INDEX)는 app.py 소유라 **메서드 안에서 지역 임포트**한다(최상단이면 순환 임포트).
    ├── graph_io.py         # GraphIO(window) — 프로젝트 그래프 ↔ 캔버스 VM 왕복 (app.py로부터 추출).
    │                       #   load_project_graph(project.graph + graph_layout/edge_layout → state_vms/transition_vms/
    │                       #     reference_vms/reference_links 재구성 + notify. WP-EP: EntryPoint와 그에 닿는 전이는 VM을 만들지 않는다)/
    │                       #   save_graph_layout(VM 좌표 → project.graph_layout[state.id] + waypoints → project.edge_layout[Transition.id]).
    │                       #   창에는 _save_graph_layout 한 줄 위임만 남는다(SessionIO 저장 경로가 직접 부른다) — set_project는 GraphIO.load_project_graph를 직접 부른다.
    ├── component_actions.py  # ComponentActions(window) — 컴포넌트 생성·이름 변경·삭제 (app.py로부터 추출).
    │                       #   ask_unique_name(이름 입력+중복 검증)/make_fsm/make_agent_fsm(백킹 FSM 팩토리)/register_component
    │                       #     (CreateComponentCmd)/on_new_component/on_component_renamed(중복 거부 + RenameComponentCmd)/
    │                       #   on_delete_component(확인 다이얼로그) → delete_component(공용 실체 — MCP도 이것을 부른다.
    │                       #     본문 문서 캐시 정리 + 탭 닫기 + RemoveComponentCmd 실행. **GraphIO.load_project_graph를 부르지 않는다**).
    │                       #   **컴포넌트 팩토리는 actions/creation.make_component 하나뿐이다** — 레지스트리 경로와 캔버스
    │                       #     "여기에 만들기" 경로가 같은 5키 dict를 문자 그대로 중복 보유하던 것을 해소했다(한쪽만 고치면
    │                       #     어디서 만들었느냐에 따라 다른 물건이 된다). FSM 생성은 creation이 다시 window._make_fsm/
    │                       #     _make_agent_fsm을 부르므로 팩토리의 단일 진실이 유지된다.
    │                       #   창에는 _make_fsm/_make_agent_fsm/_register_component/_on_new_component/
    │                       #     _on_component_renamed/_on_delete_component/delete_component 한 줄 위임 + _COMPONENT_TITLES 별칭이 남는다
    │                       #     (context_menus.py·actions/creation.py·MCP props.py가 창에서 직접 부른다).
    ├── actions/            # **UI 무관 편집 액션** (A8/A9) — 기능의 실체. 캔버스 우클릭 메뉴와 에디터 위젯은 둘 다 여기를
    │                       #   부르는 **호출부**일 뿐이다(한쪽에 로직을 넣고 다른 쪽이 흉내 내면 같은 조작의 결과가 표면마다 달라진다 —
    │                       #   wire_workspace 공유와 같은 결). 입력은 모델/뷰모델, 편집은 CommandStack 경유. 테스트는 액션 함수 단위로 쓰고
    │                       #   호출부는 "이 함수를 부르는가"만 확인한다.
    │   ├── entrypoint.py   #   진입점 프리셋 4종(A8) — EntryPreset/ENTRY_PRESETS/supports_entry_presets/current_entry_preset/
    │   │                   #     apply_entry_preset. 상세는 "진입점 프리셋 (A8)" 개념 섹션 참조.
    │   ├── preview.py      #   컴파일 미리보기(A9-1) — preview_text/preview_title(테스트 대상) + show_preview_dialog(표시).
    │   │                   #     파일은 쓰지 않는다. 산출은 **원문 그대로** 보인다(렌더하면 프론트매터가 사라진다).
    │   ├── model_effort.py #   모델/effort 지정(A9-2) — MODEL_CHOICES/EFFORT_CHOICES(표시 순서 단일 진실) + set_model/set_effort.
    │   │                   #     새로 만드는 것은 UI가 아니라 **쓰기 경로의 단일 진실**이다(에디터 콤보와 같은 SetAttrCmd 경로).
    │   ├── wrapped_usage.py#   랩핑 용도 전환(WP-WR) — change_wrapped_usage/placement_counts/describe_placements.
    │   │                   #     배치 없으면 SetAttrCmd 하나, 있으면 거부(force면 _canvas_cleanup_commands로 정리 + 전환 1 undo).
    │   │                   #     GUI 버튼과 MCP set_wrapped_usage의 공용 실체
    │   ├── fork_skill.py   #   fork 스킬(2026-09-13) — fork_agent_choices(fork 에이전트 후보 세 종류)/validate_fork_agent/skill_kind_of/
    │   │                   #     KINDS(3-way: procedural/sync_fork/async_fork)/convert_skill_kind(대상 config 클래스
    │   │                   #     기준 필드 복사, config·__class__ 교체 + resync_bracket을 묶어 1 undo). 피커·캔버스 메뉴·MCP 공용 실체
    │   ├── creation.py     #   생성+배치 — NO_PLACE_KINDS(= model/plugin/placement.is_canvas_placeable의 음성 거울
    │   │                   #     상수 — 판정의 실체는 placement 쪽이고 레지스트리·캔버스도 그 함수를 부른다)/create_wrapped_skill(WP-WR —
    │   │                   #     생성+선언+배치 1 undo, WRAPPED_SOURCE_MIME_PREFIX)/
    │   │                   #     ("여기에 만들기" 빈 캔버스 메뉴(A9-9)·CREATABLE_KINDS는 퇴역 — 정확한 이름 타이핑 요구, 사용자 확정)/
    │   │                   #     make_component(창의 _make_fsm 재사용 — 레지스트리와 같은 물건이어야 한다)/create_and_place.
    │   │                   #     생성(CreateComponentCmd)+배치(CreateStateCmd 또는 CreateRefCmd)를 MacroCommand로 묶어 1 undo 단위.
    │   │                   #     **MCP props.py도 이 둘을 직접 부른다**(S1/G14) — 자체 팩토리 dict를 들고 있던 것을
    │   │                   #     환원해 "어디서 만들었느냐에 따라 다른 물건"을 없앴다. description 인자는 그 합류의 산물.
    │   ├── transitions.py  #   전이 트리거 지정(A9-8) — trigger_choices(출발 노드의 transfer_on + call_agents)/current_trigger/
    │   │                   #     set_trigger. **CompletionEvent를 새로 만들어** 넣는다(제자리 수정이면 SetAttrCmd의 old/new가 같은
    │   │                   #     객체가 되어 undo가 죽는다). 지금까지 트리거 변경 GUI가 없어 전이를 지우고 다시 긋는 수밖에 없었다.
    │   ├── references.py   #   참조 노드(A9-6/7) — linked_state_vms/linkable_state_vms(캔버스 드래그와 같은 **스킬 기준** 중복
    │   │                   #     방지)/reference_vms_for/add_reference_link(씬의 create_reference_link 경유 — 링크 생성은 모델
    │   │                   #     reference_placements 재구성 sync가 따라붙어야 하고 그 함수는 씬이 쥐고 있다).
    │   ├── agent_links.py  #   에이전트 호출자 유도(A9-4) — callers_of(agent, project) → CallerRef 목록(호출자·포트·설명·
    │   │                   #     포커스 대상 노드), 호출자 이름·포트 순. 정렬·유도가 컴파일 "## 호출 계약"과 **같아야** 화면과
    │   │                   #     산출이 같은 말을 한다. 누가 부르는지는 모델에 없고 그래프에서 유도할 뿐이다(WP-CT).
    │   └── warnings.py     #   컴포넌트별 검증 결과 필터(A9-3) — findings_for(errors, component, project). subject==컴포넌트 /
    │                       #     path 루트(`skill:<이름>`) / **그래프 placement 노드** 세 경로를 모두 본다 — placement를 빼면
    │                       #     mid_chain_user_invocable처럼 subject가 노드인 규칙을 통째로 놓친다. dock 표시는
    │                       #     ValidationActions.show_component_findings가 계속 전담(검증 패널을 채우는 경로는 하나여야 한다).
    ├── canvas/             # GraphicsView/Scene, NodeItem, EdgeItem, RefNodeItem, RefEdgeItem, sync(VM→모델 동기화 — Qt 무관)
    │                       # context_menus.py(A8/A9): 컨텍스트 메뉴 조립을 FsmScene에서 떼어 낸 모듈(코드 위생 상한 —
    │                       #   메뉴 항목이 늘며 씬이 1,200줄을 넘었다). 씬에는 같은 이름의 **한 줄 위임**만 남는다(테스트와
    │                       #   호출부가 scene._add_component_actions_menu(...)처럼 씬 메서드를 직접 부른다). 여기 함수는
    │                       #   메뉴를 조립해 {QAction: 콜러블} 디스패치 표를 돌려줄 뿐이고 편집 로직은 전부 view/actions/에 있다.
    │                       # 엣지 리루트(WP-ER): TransitionEdgeItem.update_path가 TransitionViewModel.waypoints(경유점)를 경유하는
    │                       #   구간별 베지어 곡선을 그린다. 선택 시 자식 WaypointHandleItem(작은 원)을 표시 — 더블클릭/컨텍스트 메뉴로
    │                       #   추가(nearest_segment_index), 드래그 이동, 우클릭/Delete로 제거. 프로젝트 캔버스(FsmScene) 전용 —
    │                       #   에이전트 내부 FSM 캔버스(AgentFsmScene)는 WP-AF로 함께 퇴역했다.
    │                       # 노드 우클릭 메뉴(A8/A9): '진입점 설정' 서브메뉴(_add_entry_preset_menu — 스킬 placement에만) +
    │                       #   컴파일 미리보기·모델/effort 서브메뉴·관련 경고 보기(_add_component_actions_menu — placement 전반).
    │                       #   전부 view/actions/를 부르는 **호출부**다(로직 없음). 메뉴는 항목이 많아 exec 반환값 elif 사슬이
    │                       #   아니라 {QAction: 콜러블} **디스패치 표**를 쓴다. 창이 필요한 액션은 main_window()(views()[0].window())로
    │                       #   거슬러 올라간다 — 씬은 MainWindow를 참조하지 않는다.
    │                       # node_badges: badges_for(component)(뱃지 로직) + state_access_badges(state)(WP-BB — State.reads/writes → ✏쓰기/📖읽기
    │                       #   뱃지, 선언 있을 때만 렌더). StateNodeItem.paint가 badges_for(ref)+state_access_badges(model)를 합류해 렌더.
    │                       # 입력 포트(WP-IP/RF-1b): 노드당 1개 고정 — input_port_scene_pos()(인자 없음)가 그 한 점을 돌려주고
    │                       #   들어오는 모든 전이가 자연히 수렴한다(입력 포트 선언·도착 포트 지정은 개념째 삭제).
    │                       # draggable.py(WP-DM): DraggableItemMixin — 드래그 이동 가능 아이템 3종(StateNodeItem/ReferenceNodeItem/
    │                       #   WaypointHandleItem)의 공통 수명주기. 서브클래스는 mousePressEvent에서 begin_drag(), mouseReleaseEvent에서
    │                       #   end_drag()를 호출하고 vm_position()/make_move_command()를 구현한다(ABC 아님 — Qt 메타클래스와 충돌.
    │                       #   믹스인을 QGraphicsItem 앞에 둔다). 상세는 "캔버스 드래그 이동" 항목 참조.
    ├── commands/           # Undo/Redo 커맨드 (state, transition — Add/Move/Remove/ClearWaypointsCmd(WP-ER) 포함, exit_point,
    │                       #   component — Create/RenameComponentCmd(WP-CE 1차) + RemoveComponentCmd(A2 — MacroCommand 서브클래스.
    │                       #     `_bucket`(+_DetachComponentCmd의 같은 판정)이 `isinstance(c, Agent)`로 **에이전트 두 종류를 모두**
    │                       #     project.agents로 보낸다 — ForkAgent가 project.agents에 들어가는 **유일한 경로**다(좁히면 skills로
    │                       #     새어 저장·레지스트리·검증·산출이 전부 어긋난다).
    │                       #     캔버스 정리는 기존 DeleteRef/DeleteTransition/DeleteStateCmd 조립, 모델 잔여분만 _DetachComponentCmd),
    │                       #   attr — SetAttrCmd/AppendToListCmd/RemoveFromListCmd(WP-CE 범용 폼 편집. 편집마다 클래스를 만들지 않고
    │                       #     "속성 하나 바꾸기"+"리스트 넣고 빼기" 둘로 환원한다. SetAttrCmd는 최초 execute에서만 old를 잡는다 —
    │                       #     redo가 old를 덮으면 undo가 깨진다. 값은 복사하지 않으므로 호출자가 새 객체를 넘겨야 한다),
    │                       #   surface — ResyncSurfacesCmd/resync_bracket: 모델을 바꾸지 않고 열린 편집 탭의 프론트매터 폼과
    │                       #     레지스트리만 현재 종류로 다시 그린다. 종류 전환(convert_skill_kind)의 재동기를 액션 함수에 두면
    │                       #     undo에 걸리지 않아 되돌린 뒤에도 스테일 폼이 남는다 — MacroCommand의 **양 끝**에 한 쌍을 두어
    │                       #     execute/undo 어느 방향이든 마지막 한 번이 확정된 상태를 본다(MacroCommand.undo는 역순이다))
    ├── editors/            # 속성 편집기 (skill + 그 분해 패널 3종(frontmatter_panel/transfer_on_panel/reference_link_panel),
    │                       #   agent, hook, body, body_documents, component, variable_loader, catalogue_loader, field_widgets,
    │                       #   field_adapters, kind_matrix, kind_switch_row, project_properties, blackboard_editor, workspace_editor)
    │                       # skill_editor(WP-RF): 구 단일 모듈(1,172줄 — 프론트매터 폼·출력 포트 카드·참조 링크 세 책임)을 형제
    │                       #   모듈 3개로 분해(이동만·동작 불변). skill_editor.py에는 SkillEditor만 남고 **재-export 파사드**로
    │                       #   `from …skill_editor import _FrontmatterPanel` 등 기존 언더스코어 임포트 경로가 전부 무수정 동작한다
    │                       #   (component_editor·agent_editor + 테스트 10여 파일이 그 경로를 쓴다. test_skill_editor_facade.py가 고정). 구획:
    │                       #     frontmatter_panel.py   — _FIELD_ATTR_MAP/_FIELD_ENUM_MAP/_LIST_FIELDS/_TOOL_CANDIDATE_FIELDS + 그리드 열
    │                       #                              상수 + _OptionalRow + _FrontmatterPanel. 쓰기 게이트 `_writable`은 **표를 먼저**
    │                       #                              본다(`matrix_for` → 없거나 FIXED면 스테일 위젯이라 조용히 버리고, 표에 있는데
    │                       #                              config에 없으면 AttributeError) — `hasattr`를 먼저 물으면 같은 계열 config가
    │                       #                              속성 이름을 공유해 스테일 write-back이 그대로 통과한다.
    │                       #                              **위젯 어댑터 표 `_WIDGET_ADAPTERS`**(실체는 field_adapters.py, 여기서 재-export)가
    │                       #                              단일 진실 — (위젯 타입, 읽기, 쓰기, 변경 시그널 이름) 한 줄이 값 로드(_apply_value)·
    │                       #                              값 읽기(_read_widget_value)·시그널 연결(_connect_widget_signal) 세 경로를 함께
    │                       #                              채운다(분해 전에는 같은 isinstance 사슬이 세 벌이라, 한 곳을 빠뜨리면 "값은
    │                       #                              채워지는데 편집이 저장되지 않는" 반쪽 고장이 조용히 생겼다). **표의 줄 순서가 곧
    │                       #                              우선순위**다 — isinstance는 서브클래스에도 참이라 순서를 바꾸면 동작이 바뀐다.
    │                       #     transfer_on_panel.py   — _COLOR_PRESETS + _ColorPickerPopup + _EventCard + _TransferOnPanel
    │                       #     reference_link_panel.py— _ReferenceLinkPanel
    │                       #     kind_switch_row.py     — 절차형 ↔ 동기/비동기 fork **3-way** 전환 버튼·안내 행
    │                       #                              (build_kind_switch_row, 800줄 예산 때문에 분리)
    │                       #     kind_matrix.py         — matrix_for(component) → (규칙 표, 위젯 표, is_agent). **얇은 어댑터**다 —
    │                       #                              표 선택의 실체는 model.plugin.field_matrix.matrix_for이고(컴파일러는 뷰를
    │                       #                              임포트할 수 없다) 여기서는 뷰에만 있는 위젯 표를 짝지어 준다. 800줄 예산 분리
    │                       #     field_adapters.py      — _WIDGET_ADAPTERS 표(위 설명) + _adapter_for. WP-E에서 frontmatter_panel에서
    │                       #                              떼어냈다(이동만·동작 불변, 재-export 파사드 — 800줄 예산 분리)
    │                       # **필드 행 정렬 규칙**: 라벨|필드 행은 열 폭을 공유하는 레이아웃에 넣는다 — skill_editor._FrontmatterPanel은
    │                       #   QGridLayout(0=체크박스·1=라벨(우측 정렬)·2=값 위젯, 스팬 행은 헤더/그룹 구분 라벨/버튼 행), 나머지는
    │                       #   QFormLayout(hook_panel·property_panel·project_properties·workspace_editor). ad-hoc HBox로 행을
    │                       #   나열하면 열 폭이 공유되지 않아 라벨 길이만큼 값 위젯 시작 x가 어긋난다(실측: 에이전트 패널 x 8종 → 1종).
    │                       #   _OptionalRow는 **행의 3번째 칸**이고 체크박스·라벨 셀을 소유해 place_in()으로 0·1열에 놓는다 —
    │                       #   값 위젯의 부모는 여전히 _OptionalRow다(호출부·테스트가 widget.parent()로 행을 찾는다). 잠금(WP-EL)은
    │                       #   set_locked()가 세 칸을 함께 끈다(체크박스가 살아 있으면 "켤 수는 있는데 아무 일도 안 일어나는" 상태).
    │                       # workspace_editor(WP-WD): ClaudeMdPanel(탭 3 — 구역 제목 H1 + 본문) / RulesPanel(탭 4 — 좌 규칙 목록
    │                       #   _RuleTree(QTreeWidget — 최상위 행=규칙, 자식 행=적용 경로 흐림 표시, 빈 경로는 이탤릭 "(항상 로드)".
    │                       #   QListWidget 시절 행 API(count/currentRow/setCurrentRow/item) 호환 유지 — 패널·테스트가 "규칙=행
    │                       #   인덱스"로 계속 말한다. 경로 자식 클릭은 부모 규칙 선택으로 재매핑, paths 편집은 update_row_paths
    │                       #   제자리 갱신) + 우 "적용 경로" TagInput(A13 paths — ClaudeMdPanel에는 없다)
    │                       #   (＋/삭제/더블클릭 이름변경) | 우 본문). 둘 다 SectionContentPanel을 재사용하므로 WorkspaceDoc.id 덕에
    │                       #   본문 undo 스택(WP-BU)이 그대로 붙는다. 구조 편집은 모델 직접 기록 + notify(블랙보드 패널과 같은 정책).
    │                       #   변수 삽입 배선의 단일 진실은 body_editor의 make_variable_popup/toggle_variable_popup —
    │                       #   ComponentEditor와 이 패널이 **같은 함수**를 부른다(한쪽에만 있으면 같은 버튼이 표면마다 다르게
    │                       #   동작한다. 실제로 workspace_editor가 variable_insert_requested를 연결하지 않아 무동작이었다).
    │                       #   **변수 팝업은 컨텍스트별 필터**(사용자 확정 매트릭스, variable_loader.variables_for): 스킬=풀 지원 /
    │                       #   에이전트·작업 폴더 문서=루트 변수 2종(${CLAUDE_PLUGIN_ROOT}·${CLAUDE_PROJECT_DIR})만 / LOCAL 빌드는
    │                       #   ${CLAUDE_PLUGIN_ROOT} 사용 불가(로컬 설치엔 플러그인 디렉토리가 없다). variables_fn을 받은 팝업은
    │                       #   **열 때마다** 목록을 다시 만든다 — 빌드 타깃은 set_build_target_provider(app.set_project 등록,
    │                       #   SkillFilesPanel의 provider 패턴)로 호출 시점 조회라 프로젝트 속성 변경이 다음 열기부터 반영된다.
    │                       #   사용자 정의(global/project yaml) 변수는 전 컨텍스트 노출 — 자기 토큰의 범위는 자기가 안다.
    │                       # catalogue_loader: 도구/MCP 카탈로그 로더(WP-TM) — ~/.daedalus/catalogue/*.json(글로벌) + <프로젝트>/.daedalus/catalogue/*.json(프로젝트, 이름 충돌 시 우선)
    │                       #   병합. 파일 1개=항목 1개(CatalogueEntry: name=파일명 stem, description, tools="tool" 키, mcp="mcp" 키). expanded_mcp()가 mcp 항목을
    │                       #   mcp__<entry.name>__<도구>로 확장(이미 mcp__ 접두면 그대로). candidate_strings(entries, project)가 CC_BUILTIN_TOOLS(정렬)+카탈로그 tool/expanded_mcp+
    │                       #   프로젝트 에이전트 Agent(이름)을 합성(중복 제거)해 TagInput 자동완성 후보를 만든다. 파싱 실패/스키마 불일치 파일은 stderr 경고 후 스킵.
    │                       # body: SectionContentPanel = MarkdownToolbar + SearchBar(찾기/바꾸기 바, WP-MD3, 기본 숨김) + QStackedWidget(0=MarkdownEditor 편집,
    │                       #   1=QTextBrowser 프리뷰 — setMarkdown 1회 렌더) + TocPanel(TOC 사이드바, WP-MD3, 기본 숨김, 폭 180px) 가로 배치.
    │                       #   MarkdownEditor.search_requested → search_bar.open(prefill), MarkdownToolbar.toc_toggled → toc_panel 표시/숨김.
    │                       #   show_body(component)가 편집 모드로 리셋 + 찾기 바 닫힘 + TOC 즉시 재파싱(refresh() — blockSignals로 억제된
    │                       #   textChanged를 TOC가 못 받으므로 명시 호출), 프리뷰 중 편집 버튼·변수 삽입·TOC 토글 잠금 + 찾기 바 닫힘.
    │                       # WP-SB: 수동 섹션 트리 편집(SectionTree/BreadcrumbNav, find_path/section_depth/MAX_DEPTH)은 마크다운 에디터로 대체되어 제거 —
    │                       #   component_editor.ComponentEditor는 좌(FrontmatterPanel) | 중(SectionContentPanel, component.body 단일 편집) | 우(옵션) 2~3분할로 단순화
    │                       # blackboard_editor.py(WP-BB): BlackboardPanel(QWidget) — 프로젝트 최상위 블랙보드(class_definitions) 편집 상주 탭. 좌: 클래스
    │                       #   목록(＋/삭제/더블클릭 이름변경), 우: description(QLineEdit) + 필드 테이블(name/FieldType/CollectionType/required/default,
    │                       #   ＋필드/필드 삭제). 편집은 project.blackboard.class_definitions를 직접 갱신 + notify(structure 채널 — undo 커맨드화 범위
    │                       #   밖, hook_panel 폼 정책과 동일). blackboard_candidate_strings(project)가 "클래스"+"클래스.필드" 후보 문자열을 만든다.
    │                       #   **이름 변경은 모델 blackboard_rename_ref_updates로 상태 reads/writes 참조를 함께 갱신한다** — MCP
    │                       #   update_blackboard_class와 같은 판정(표면마다 결과가 다르면 안 된다). refresh_external은 목록을 새로 그린 뒤
    │                       #   현재 행을 명시적으로 다시 로드한다(같은 행이면 setCurrentRow가 시그널을 내지 않아 설명·테이블이 스테일로 남는다).
    ├── panels/             # PropertyPanel, RegistryPanel, HistoryPanel, ValidationPanel (F7 검증 결과), FilePanel(WP-FR), ScriptListenerPanel
    │                       # RegistryPanel: component_delete_requested/component_preview_requested 시그널 + _RegistrySection 우클릭
    │                       #   "컴파일 미리보기…"/"삭제" 컨텍스트 메뉴. 미리보기는 캔버스 메뉴와 같은 실체(actions/preview) —
    │                       #   트랜스퍼 스킬은 엣지에 붙어 placement 메뉴가 닿지 않으므로 레지스트리가 전 컴포넌트 공통 진입점
    │                       #   (전이 엣지 메뉴에도 transfer 부착 시 같은 항목).
    │                       #   종류별 섹션은 QTabWidget 탭(WP-SF 배치 개편 — 이모지 라벨+툴팁)
    │                       # FilePanel(WP-FR/WP-SF): _FileTreeBase(트리+안내+생성+새로고침+"탐색기" 버튼) 기반 전역 files/ 독("플러그인 파일 (공용)",
    │                       #   레지스트리 아래 세로 스택). set_project_dir(path|None) — 저장/열기/새 프로젝트 시 app이 호출. files_root()/skill_files_root()가
    │                       #   실존 시에만 경로 문자열 반환(드롭 provider 단일 진실). SkillFilesPanel(WP-SF): 스킬 에디터 우측 — skill-files/<스킬>/ 트리,
    │                       #   set_project_dir_provider/get_project_dir 모듈 provider로 프로젝트 폴더 조회(에디터마다 생겨 직접 배선 불가)
    │                       # PropertyPanel.show_state(WP-BB): reads/writes TagInput 2개 — get_blackboard_candidates()로 자동완성 후보(호출 시점
    │                       #   스냅샷, get_tool_candidates와 동일 정책), tags_changed → state.reads/writes 직접 기록(커맨드화 범위 밖) + notify. 프로젝트
    │                       #   캔버스 placement에서 편집한다(에이전트 그래프 탭은 WP-AF로 퇴역).
    ├── viewmodel/          # ProjectViewModel(notify structure/content 채널), StateViewModel (모델↔뷰 중간 계층)
    └── widgets/            # ComboWidgets, TagInput, markdown/(마크다운 에디터 패키지 — WP-RF-3c로 구 단일 모듈 markdown_editor.py를 분해.
                            #   markdown_editor.py 모듈 경로는 **재-export 파사드**로 유지되어 기존 임포트가 무수정 동작한다. 구획:
                            #     syntax.py      — MARKDOWN_PALETTE·폰트 상수·정규식 전부(_FENCE_*_RE/_HEADING_*_RE/_TASK_RE/… )·_make_format·_detect_line_marker.
                            #                      **모듈 간 공유 상수의 단일 진실**(복제 금지) — model/outline.py의 펜스 정규식이 이 파일을 미러한다.
                            #     highlighter.py — MarkdownHighlighter(블록 상태 _STATE_NONE/_STATE_CODE_FENCE로 코드 펜스 추적)
                            #     providers.py   — files/·skill-files/ 루트 provider 4함수 + _file_ref_token/_skill_file_ref_token(드롭 참조 토큰 계산).
                            #                      provider 전역은 여기가 단일 진실 — 파사드는 함수만 재-export한다(가변 전역 복사는 스테일).
                            #     slash.py       — SlashItem/SLASH_CATALOG/_SlashMenu (`/` 오버레이)
                            #     editor.py      — MarkdownEditor + 단축키 판정표(_HEADING_DIGIT_*/_MARKER_SHORTCUT_*)·_heading_digit_from_event/_line_marker_from_event
                            #     toolbar.py     — MarkdownToolbar / search.py — SearchBar / toc.py — TocEntry+TocPanel
                            #   MarkdownHighlighter+MarkdownEditor — 하이브리드 마크다운 하이라이팅·편집, SectionContentPanel 본문에 통합
                            #   + `/` 슬래시 메뉴(_SlashMenu — 에디터 viewport 자식 오버레이, Qt.Popup 아님) + MarkdownToolbar(서식 버튼 행 + toc_toggled/preview_toggled 시그널))
                            #   찾기/바꾸기 + TOC(WP-MD3, 마크다운 에디터 마일스톤 마감): SearchBar(QLineEdit 검색·바꾸기 + 이전/다음 + Aa 대소문자
                            #   토글 + 일치 수 라벨 — 평문 부분 문자열 매칭, QTextDocument.find 미사용. search_next/prev는 랩어라운드, replace_current는
                            #   치환 후 다음 일치로 이동, replace_all은 beginEditBlock/endEditBlock로 1 undo 단위. MarkdownEditor.search_requested
                            #   (Ctrl+F, 선택 텍스트 프리필)로 열리고 Esc(eventFilter)로 닫히며 닫을 때 ExtraSelections를 지운다) +
                            #   TocPanel(QTreeWidget — ATX 헤딩을 레벨별로 계층화, 코드 펜스 내부는 MarkdownHighlighter._STATE_CODE_FENCE
                            #   블록 상태로 판별해 제외. textChanged마다 300ms 디바운스(QTimer) 후 재파싱, 구조 불변 시 트리 재구성 생략.
                            #   클릭 시 setTextCursor+centerCursor로 점프. refresh()로 디바운스 우회 즉시 재파싱 — 문서 전환용)
                            #   TagInput(WP-TM): set_candidates(list[str])로 QCompleter(부분 일치·대소문자 무시) 부착. 칩은 QLineEdit라
                            #   **제자리 편집 가능**(editingFinished 커밋, 빈 값·중복은 되돌림 — 삭제는 x 버튼만. 칩 편집에도 같은 completer). 모듈 수준
                            #   provider 3쌍(tool/blackboard/hook_name)이 동적 후보를 주입한다 — 전부 같은 패턴이고 **후보는 위젯
                            #   생성 시점 스냅샷**이다(라이브러리가 바뀌어도 열려 있는 위젯은 갱신되지 않는다. 이름은 자유 입력이라
                            #   목록에 없어도 넣을 수 있고, 탭을 다시 열면 새 후보가 붙는다).
                            #   set_tool_candidate_provider/get_tool_candidates —
                            #   app.py의 set_project가 프로젝트 로드 시 catalogue_loader.candidate_strings(...)를 등록. skill_editor._FrontmatterPanel이
                            #   ALLOWED_TOOLS/TOOLS/DISALLOWED_TOOLS 필드 생성 시 후보를 부착(_wire_tool_candidates) — PATHS/SKILLS/MCP_SERVERS는 제외
                            #   set_blackboard_candidate_provider/get_blackboard_candidates(WP-BB, 동일 provider 패턴)는 State.reads/writes TagInput
                            #   (PropertyPanel)의 "클래스"/"클래스.필드" 후보 — app.py의 set_project가 blackboard_candidate_strings(project)를 등록.
                            #   set_hook_name_provider/get_hook_names는 HOOKS TagInput의 훅 이름 후보 — app.py의 set_project가
                            #   resolved_hooks()(전역 훅 포함, A1)를 등록. 원래 widgets/preset_picker.py에 있었는데 그 모듈의
                            #   체크리스트 위젯(HookPresetPicker/McpPresetPicker/PresetPicker)이 TagInput으로 대체되어 전부 죽은
                            #   코드가 됐고, 남은 provider를 후보를 쓰는 위젯 옆으로 옮기며 모듈을 삭제했다.
                            #   파일 드롭 치환(WP-FR): markdown/providers.py의 set_files_root_provider/get_files_root(동일 provider 패턴) — MarkdownEditor.
                            #   dragEnterEvent/dragMoveEvent/dropEvent가 mime의 file URL 중 현재 files/ 루트 하위인 것만 _file_ref_token으로
                            #   변환해 드롭 지점에 삽입(복수 파일=줄바꿈 구분). files 밖·비파일 mime은 super()로 흘려 기존 QPlainTextEdit
                            #   기본 드롭(텍스트 드래그 등)을 보존한다. app.py의 _setup_docks가 등록.
                            #   코드 인용 + 단축키 확장(WP-MK): MarkdownEditor.toggle_inline_code()(`toggle_wrap("`", "`")` 재사용)/
                            #   toggle_code_block()(줄 단위 — 선택은 줄 경계로 확장, 이미 펜스면 벗김, 선택 없고 빈 줄이면 빈 펜스
                            #   3줄+가운데 커서, 그 외엔 현재 줄을 펜스로 감쌈. 언어 태그 없음(v1). 1 undo 단위) 공개 API 추가.
                            #   `_dispatch_key` 단축키: Ctrl+`(인라인 코드) / Ctrl+Shift+C(코드 블록) / Ctrl+1~6(헤딩 레벨) /
                            #   Ctrl+0(본문 복귀) / Ctrl+Shift+8(불릿) / Ctrl+Shift+7(번호) / Ctrl+Shift+9(체크리스트) /
                            #   Ctrl+Shift+.(인용). 숫자·기호 조합은 event.key()가 플랫폼별로 다르게 올 수 있어 모듈 수준 순수 함수
                            #   `_heading_digit_from_event`/`_line_marker_from_event`가 event.key()/event.text() 양쪽을 판정(폴백).
                            #   MarkdownToolbar에 `<>`(인라인 코드)/`{}`(코드 블록) 버튼 추가(B/I/S 뒤, 구분선), 기존 버튼 프리뷰 비활성화
                            #   정책(_edit_buttons)에 자동 편입. SLASH_CATALOG에 "인라인 코드" 항목(` `` `, cursor_back=1) 추가.
```
