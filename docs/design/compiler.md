# 컴파일러 (compiler/) — 산출 구조와 컴파일 정책

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

`compile_project(project, out_dir=None, files_dir=None, resolved_hooks=None, dry_run=False) → CompileResult`. 순수 stdlib(Qt 무관, import 순수성 테스트로 고정).
`resolved_hooks`(A1)는 호출자가 주입하는 이름→HookDef 사전 — 컴파일러는 파일시스템에서 훅을 읽지 않는다("전역 훅 2단 스코프" 섹션 참조).
`dry_run`(G3)은 파일을 하나도 쓰지 않는 예행 — 컴파일 정책 18번 참조(`out_dir`는 이때만 생략 가능).

## 컴파일 참여자 — `CompileUnit` 12개 (WP-5)

**산출 종류 하나 = 단위 하나다.** 종전에는 산출 종류마다 지식이 세 자리에 흩어져 있었다 —
계획(`plan._plan_outputs`의 한 문단), 쓰기(`project_compiler`의 kind 사다리), 그리고 "이 kind는
`${ROOT}`를 확장하는가 / 토큰을 어떻게 세는가"의 튜플 두 개. 하나를 고치고 나머지를 잊으면
조용한 불일치가 됐다. 이제 단위가 자기 계획·자기 렌더·자기 쓰기 방식을 **전부** 말하고,
드라이버는 kind를 비교하지 않는다:

```
plan  = Planner(UNITS).plan(ctx)            # 선언 순서 = 계획 순서 = 쓰기 순서
write = UNIT_BY_ID[행.kind].emit(행, ctx, sink)
```

`compiler/units/`의 계약: `CompileUnit(ABC: plan/emit)` → `TextUnit`(하위는 `render`만) /
`CopyUnit` / `MergeUnit` · `CompileContext`(주입 인자 1:1, 원칙 4) · `Gate`(이름 규약) ·
`OutputSink`(쓰기·복사·병합·토큰 계상의 유일한 실행자 — `dry_run`·`${ROOT}` 확장·LF/UTF-8을
여기서만 안다) · `PlannedOutput`(계획 행).
**계획 kind 문자열의 소유자는 `compiler/plan_kinds.py` 하나**이고(`tests/test_kind_literals.py`가
AST로 강제) `emit/guides.py`의 `WORKFLOW_GUIDE_KIND`/`BLACKBOARD_GUIDE_KIND`/`GUIDE_KINDS`는
거기서 재-export한 것이다.

| # | 단위 | plan kind (= 단위 id) | 모드 | phase | 경로 | `${ROOT}` | token | `exclusive` | 계획 조건 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `ComponentUnit(SKILLS)` | `skill`, `wrapped_runner` | TEXT | WRITE | `<cc>/skills/<n>/SKILL.md`, `<cc>/agents/<n>.md` | ✔ | CONTEXT | ✔ | `c.emits_output()` (+ `needs_runner_agent`) |
| 2 | `ComponentUnit(AGENTS)` | `agent` | TEXT | WRITE | `<cc>/agents/<n>.md` | ✔ | CONTEXT | ✔ | `c.emits_output()` |
| 3 | `SkillFilesUnit` | `skill_file` | COPY_FILE | WRITE | `<cc>/skills/<d>/<rel>` | – | – | ✔ | `skill_files_dir.is_dir()` ∧ 폴더명이 산출 스킬 이름과 일치 |
| 4 | `HooksUnit` | `hooks_json`(MARKET만), `hook_script` | TEXT | WRITE | `hooks/hooks.json`, `hooks/scripts/<f>` | ✘ | TOTAL_ONLY | ✔ | `compile_hooks_json(...) is not None` — **계획 단계에서 1회 렌더해 `payload`에 메모** |
| 5 | `WorkspaceRuleUnit` | `workspace_rule` | TEXT | WRITE | `.claude/rules/<n>.md` | ✘ | CONTEXT | ✔ | LOCAL ∧ `doc.has_content()` |
| 6·7 | `GuideUnit` ×2 | `guide_workflow`, `guide_blackboard` | TEXT | WRITE | `guides/<플러그인>/…` | ✔ | CONTEXT(`is_guide`) | ✔ | `workflow_guide_referenced` / `blackboard_guide_referenced` |
| 8 | `SchemasUnit` | `schemas_json` | TEXT | WRITE | `schemas/<프로젝트>.json` | ✘ | TOTAL_ONLY | ✔ | `compile_schemas_json(...) is not None` |
| 9 | `ManifestUnit` | `plugin_manifest` | TEXT | WRITE | `.claude-plugin/plugin.json` | ✘ | TOTAL_ONLY | ✔ | MARKETPLACE |
| 10 | `FilesTreeUnit` | `files_tree` | COPY_TREE | WRITE | `files/` | – | – | **✘** | `files_dir.is_dir()` (`clear_first = not is_local`) |
| 11 | `LocalWiringUnit` | `local_wiring` | MERGE | **INSTALL** | `.mcp.json` + `.claude/<settings>` | – | – | **✘** | LOCAL |
| 12 | `ClaudeMdUnit` | `claude_md` | MERGE | **INSTALL** | `.claude/CLAUDE.md` | ✘ | CONTEXT | **✘** | LOCAL |

**`exclusive`**: 경로 충돌 게이트와 `skipped` 보고의 대상인가. 트리 복사·병합(10~12)은 "경로 하나 =
산출 하나"라는 계획의 전제를 만족하지 않아 `False`다 — 종전에도 계획 밖이라 검사를 받지 않았고
`skipped`에도 실리지 않았다(MCP `compile_check` 응답 형상 불변).

**`Phase`가 둘인 이유**: `WRITE`(1~10) 뒤, `INSTALL`(11~12) 앞에 **드라이버가 소유한 진단 스캔
2건**(`dangling_file_ref`/`dangling_skill_file_ref`)이 있다. 파일시스템을 읽는 판정이라 산출이
아니고, 한 루프로 합치면 경고 순서가 조용히 바뀐다(`tests/compiler/test_plan_order_golden.py`).

**`TokenKind`**: 계상 구간을 **계획 행이 선언한다**(`CONTEXT` 임계 판정 대상 / `TOTAL_ONLY` 총합만 /
`NONE` 계상 없음). 종전 `token_report.CONTEXT_KINDS`는 계획 kind의 사본이라 개명하면 리포트만
조용히 산출을 못 알아봤다.

**계획 파사드**: `compiler/plan.py`가 `_plan_outputs`(종전 시그니처)·`_PlannedOutput`·경로 헬퍼 6종을
`units/`의 **같은 객체**로 재-export하고 `project_compiler`가 다시 재-export한다(기존 임포트 경로 불변 —
`tests/compiler/test_plan_facade.py`가 고정). 파사드는 `out_dir`/`files_dir`를 모르므로 `files_tree`
행이 보이지 않는다 — 전체 계획은 `Planner().plan(CompileContext.build(...))`다.
`project_compiler.compile_project`에 남은 것은 검증 게이트 + 2단계 루프 + 진단 스캔뿐이다.

새 산출을 더하는 사람은 **단위 하나와 `UNITS` 한 줄**을 쓴다 — 드라이버·게이트·토큰 리포트는
고치지 않는다.

## 컴포넌트 산출 — `ComponentEmitter` 9개 + 절 적용 표 (WP-6)

**종류 하나 = emitter 하나다.** 종전에는 `compile_skill`/`compile_agent` 두 함수가 종류를
열거하는 if 사다리로 프론트매터·절 순서·산출 파일 개수를 한꺼번에 결정했다. 절 하나를 더하려면
두 함수를 읽고 "이 조건이 어느 종류를 뜻하는지"를 매번 역산해야 했다. 이제는

- **무엇을 내는가**(파일 0..N개·`OutputLocation`·계획 kind) → `ComponentEmitter.outputs()`
- **프론트매터** → `frontmatter_block()`
- **어떤 절을 어떤 순서로** → `section_plan.SECTION_PLANS`의 종류별 **순서 있는 튜플**
- **절 하나의 실체** → `section_plan.SECTION_PROVIDERS[SectionId]`

로 갈려 있고, `compile_skill`/`compile_agent`은 `emitter_for(c).render(c, project, resolved_hooks)`
**파사드**다. `EMITTERS`는 `KIND_REGISTRY`와 양방향 패리티다 — 산출이 있는 종류마다 emitter가
정확히 하나이고 `OUTPUT_LOCATION is NONE`인 종류에는 없다(`tests/test_kind_registry_parity.py`).
빠뜨린 종류·빠뜨린 절 provider는 **ValueError + 등록 목록**으로 시끄럽게 멈춘다(원칙 5).

**전역 절 순서 하나로는 두 산출을 만들 수 없다** — 스킬은 `REQUIREMENTS`가 `BLACKBOARD` 뒤,
에이전트는 `SETTINGS_NOTE`가 `BLACKBOARD` 앞이다. 그래서 순서는 전역이 아니라 종류가 갖는다.

| emitter | 절 순서 (프론트매터 뒤) | OUTCOME 양식 | 가이드 포인터 |
|---|---|---|---|
| `ProceduralEmitter` | RESUME · ENTRY_CONTEXT · BODY · FSM_PROCEDURE · TOOL_SHELF · BLACKBOARD · BACKGROUND_SKILLS · REQUIREMENTS_MCP · OUTCOME | NEXT_STEPS | MAIN_IF_PLACED |
| `SyncForkEmitter` | 위에서 RESUME 제외 | FORK_REPORT_SYNC | FORK_IF_PLACED |
| `AsyncForkEmitter` | 위에서 RESUME 제외 | FORK_REPORT_ASYNC | FORK_IF_PLACED |
| `DeclarativeEmitter` | RESUME · ENTRY_CONTEXT · BODY · BACKGROUND_SKILLS · REQUIREMENTS_MCP · OUTCOME | NEXT_STEPS | MAIN_IF_PLACED |
| `TransferEmitter` | BODY · TRANSFER_PROGRESS · BACKGROUND_SKILLS · REQUIREMENTS_MCP · OUTCOME | NEXT_STEPS | MAIN_IF_ANY_PLACEMENT |
| `ReferenceEmitter` | BODY · BACKGROUND_SKILLS · REQUIREMENTS_MCP · OUTCOME | NEXT_STEPS | NONE |
| `WrappedEmitter` | RESUME · ENTRY_CONTEXT · BODY · DELEGATED_PROCEDURE · BLACKBOARD · BACKGROUND_SKILLS · REQUIREMENTS_WRAPPED · OUTCOME | NEXT_STEPS | MAIN_IF_PLACED |
| `WorkflowAgentEmitter` | BODY · CALL_CONTRACT · DELEGATION · SETTINGS_NOTE · INTERNAL_WORKFLOW · EXITS · TOOL_SHELF · BLACKBOARD | – | MAIN_IF_PLACED |
| `ForkAgentEmitter` | BODY · FORK_BASE_CONTRACT · SETTINGS_NOTE · TOOL_SHELF · BLACKBOARD | – | NONE |

- **절 튜플에 없는 종류는 provider가 아예 돌지 않는다** — 종전 조립 분기의 배치 클래스 튜플이
  튜플 자체로 대체됐다. provider는 오늘의 조건식을 그대로 감싸고, 낼 것이 없으면 빈 목록
  (= 절 생략)을 돌려준다.
- **OUTCOME은 provider 하나다** — "다음 단계"·fork "## Report"·"## Finishing Up" 셋은 같은 갈래
  목록에서 나오고 서로 배타적이다. 나누면 placement·outgoing 계산이 세 벌이 된다.
- **진행 사슬에 끼는 종류는 절 표가 선언한다** (`SectionPlan.tracks_progress`, 기본 참). 거짓이면
  OUTCOME이 **자기 그래프 배치를 보지 않는다** — 진행 기록 갱신 지시(`--current`)도, 터미널
  "## Finishing Up"도 내지 않는다. `TransferEmitter`·`ReferenceEmitter` 둘만 거짓이다: 전이 스킬은
  배치가 아니라 엣지 위의 단계라 `current`를 소유하지 않고(정책 6-a-④), 참조 스킬은 여러 노드에
  링크되는 자료라 자기 placement가 없다. 종전 조립 분기의 `PLACEMENT not in (EDGE, REFERENCE)`
  게이트가 여기로 왔다 — GUI는 이 배치를 만들지 않지만 역직렬화는 `skill_ref`의 placement 역할을
  검사하지 않으므로(`serialize/deser_fsm.py`), 손편집·구버전 `.ddpj`에서 전이 스킬이 상태 노드에
  박혀 있으면 게이트 없이는 같은 파일이 '## Progress Record'와 정반대의 지시를 함께 낸다
  (`tests/compiler/test_emitters.py`).
- **`WrappedEmitter`만 산출이 둘이다**(SKILL.md + `agents/<랩퍼>.md` 실행 서브에이전트, WP-WR).
  러너는 절 표를 거치지 않는 손수 조립기(`compile_wrapped_runner`)를 **축자 호출**한다 —
  가이드 포인터가 붙지 않는 것이 오늘의 산출이고, 그 누락은 backlog D8이다.
- **프론트매터 제외도 종류가 정한다** — 랩핑 스킬의 `model`/`effort`는 실행 에이전트 쪽으로 가므로
  `WrappedEmitter.frontmatter_skip`이 뺀다(종전 `frontmatter.py`의 `kind_key == "wrapped"` 하드코딩).
- **emitter는 경로를 조립하지 않는다** — `EmittedFile`은 `OutputLocation`과 이름까지만 말하고
  `<cc>/skills/<n>/SKILL.md` 조립은 `units/paths.output_path`가 한다. `emit`은 `units`보다
  아래층이라(`units.context`가 `emit`을 임포트한다) 반대 방향 간선은 패키지 순환이 된다.
- **`emit/` 안의 임포트 방향**은 `tests/compiler/test_emit_import_acyclic.py`가 함수 안 지연 임포트와
  `TYPE_CHECKING` 블록까지 포함해 비순환으로 강제한다: `common`(리프) → `{frontmatter, sections}` →
  `{fork, wrapped}` → `{skill_sections, agent_sections}` → `section_plan` → `pointer_rules` →
  `guides` → `emitters` → `{skill, agent}`. 포인터 **판정**(`pointer_rules` — 절 표의
  `GuidePointerRule`을 읽는다)과 포인터 **문구**(`guides.guide_pointer_line`)가 다른 파일인 이유가
  그것이다(한 파일이면 `guides → section_plan → … → guides` 순환).

**출력 구조 (CC 플러그인 규약, `project.build_target == MARKETPLACE` — 기본):**
- `<out>/.claude-plugin/plugin.json` — 플러그인 매니페스트 (MARKETPLACE에서 항상 생성 — 이게 없으면 산출 디렉토리를 CC 플러그인으로 설치할 수 없다)
- `<out>/skills/<skill-name>/SKILL.md` — 산출되는 스킬 전부 (Declarative/Reference도 SKILL.md. 용도 reference 랩핑 스킬은 파일 없음 — WP-WR)
- `<out>/agents/<agent-name>.md` — 에이전트 **두 종류 모두**(워크플로 에이전트·fork 에이전트, `project.agents` 순회)
- `<out>/guides/<플러그인>/workflow.md`·`blackboard.md` — **공통 안내 파일**(WP-FK2 C3, 정책 21번). 루트 직하·플러그인 네임스페이스·`files/` 밖. 포인터가 1개 이상 나갈 때만 산출한다(고아 파일 없음)

**`build_target == LOCAL`(WP-TG/WP-MW)일 때 — 컴파일이 곧 설치:** out_dir는 스테이징이 아니라 대상 **작업 폴더**다. `<out>/.claude/skills/`·`<out>/.claude/agents/`(CC가 실제로 읽는 위치), `<out>/files/`·`<out>/schemas/`·`<out>/hooks/scripts/`(본문의 `${CLAUDE_PROJECT_DIR}/…` 참조 대상), `<out>/.mcp.json`·`<out>/.claude/settings.json` 또는 `settings.local.json`(컴파일 시 선택, 기본 `settings.json` — 생성/병합), `<out>/.claude/rules/<이름>.md`와 `<out>/.claude/CLAUDE.md`의 플러그인 구역(WP-WD), `<out>/guides/<플러그인>/workflow.md`·`blackboard.md`(공통 안내 파일 — 두 빌드 타깃 공통, 정책 21번). `plugin.json`·`hooks/hooks.json`·설치 스크립트는 만들지 않는다. 상세는 컴파일 정책 15번 항목 참조.

**컴파일 정책 (확정):**
1. **프론트매터**: 해당 kind 매트릭스에서 `emit==FRONTMATTER`인 필드만. 표를 고르는 것은 `matrix_for(component)`(`component.config.kind` — 모델의 단일 진실). 키는 `frontmatter_key`(kebab-case).
   FIXED는 `fixed_value` 강제 출력. `model==INHERIT`는 키 생략. OPTIONAL 값이 config 선언 기본값과 같으면 생략(잡음 제거).
   enum은 `.value`, bool은 `true`/`false`, 리스트는 flow-style `[a, b]`.
2. **when_to_use**: description과 합류 — `<description> Use when <when_to_use>` (description이 `.!?`로 끝나면 공백, 아니면 `. `로 연결).
3. **본문**: `body`(단일 마크다운 문자열)를 앞뒤 개행만 정리해 그대로 배출(공백뿐이면 블록 생략, WP-SB).
4. **ProceduralSkill FSM → 절차 단락**: initial_state부터 전이 BFS 순서로 번호 매긴 상태 목록(시작/종료 표지),
   각 SimpleState skill_ref는 "skill 이름 사용", CompositeState는 "에이전트 X에 위임", 전이별 트리거/가드 조건 + transfer_on 출력 이벤트.
   **상태 접근 선언(WP-BB):** State.reads/writes가 있으면 상태 항목 끝에 `(읽기: \`A.x\`, \`B\` / 쓰기: \`A.y\`)`
   접미사가 합류한다(reads/writes 각각 이름순 정렬, 선언 없으면 문구 생략 — 하위 호환).
5. (삭제됨 — WP-RF-1a) 위임(delegation) 노드 산출은 개념 퇴역과 함께 제거됐다. 위임 지시는 스킬 본문에 서술한다. (번호는 뒤 항목들의 교차 참조 보존을 위해 유지.)
6. **tool_shelf**: 참조 문서 단락으로만(실행 코드 생성은 미구현 — `docs/backlog.md` §3 Tier 2).
6-c. **전이 스킬(TransferSkill) 수행 지시 (A11)** — **프레이밍: TransferSkill은 전이 위에 놓인 1:1 중간 상태다**(사용자 확정). A→B 전이에 T가 붙으면 의미론은 A→T→B이고, T는 입력 하나(그 전이)·출력 하나(계속 진행)뿐인 통과 노드다. **모델 구조는 그대로다**(`Transition.skill_ref`) — 산출 의미론과 검증의 프레이밍이지 그래프에 실제 중간 노드를 만든다는 뜻이 아니다. 이 관점에서 아래 세 가지가 따라 나온다.
    ① **출발 스킬 "## Next Steps"**가 "follow transition skill `X` (`desc`), then …"로 시작한다(`_transfer_prefix`). 스킬 타깃·에이전트 위임·위임 인라인의 후속 전이 전부 해당 — T가 상태라면 당연히 나오는 문구다.
    **왜 출발 쪽인가:** 도착 스킬의 "## Entry Context"는 이미 "transition skill X has already been followed"를 전제하고 읽는데(그 문구는 그대로 유지), 정작 수행하라는 지시가 어디에도 없어 **아무도 전이 스킬을 실행하지 않는 구조**였다(A11 진단, 재현 확인). 지시를 만드는 쪽은 그 갈래를 건너는 출발 스킬이다. transfer가 없으면 기존 문구 그대로 — 하위 호환.
    ② **에이전트 `.md`의 "## Invocation Contract"**에 "The caller follows transition skill `X` (`desc`) before delegating — work from what that step produced."가 합류한다(`_call_contract_section`). **이것이 에이전트에게 유일한 채널이다**(A11-2, 사용자 실증): "## Entry Context"는 배치된 Procedural/Declarative 스킬 전용이라(WP-IC) **에이전트 도착에는 아예 없다** — 여기서 말하지 않으면 에이전트는 자기가 받는 입력의 전처리 상태를 영영 모르고 호출자에게서 바로 받은 것처럼 서술된다. 그래서 이름만이 아니라 **설명과 "그 산출물을 전제로 작업하라"까지** 함께 낸다. 포트 description이 문장부호 없이 끝나면 마침표를 보충한다(`_compose_description`과 같은 관례 — 없으면 두 문장이 붙는다).
    ③ **`transfer_skill_reused`는 특별 규칙이 아니다** — 하나의 상태가 두 자리에 동시에 있을 수 없다는 점에서 `no_duplicate_skill_ref`와 **같은 논리**다. 규칙 메시지가 그 논리와 대안(같은 지침이 여러 전이에 필요하면 Declarative 스킬로 만들어 각 전이 스킬이 참조)을 함께 담는다.
    ④ **진행 기록 정합:** TransferSkill의 "## Progress Record"는 "You are a step on the transition itself, not a position in the workflow: leave `current` … record what happened … in `note`"라고 못 박는다. `current`의 단위는 **플러그인 FSM(프로젝트 그래프 배치)의 위치**인데(WP-RS) T는 배치가 아니라 엣지 위의 단계이므로 `current`를 소유하지 않는다 — 출발 스킬이 "set `current` to the next target"이라 말하는 것과 이 지시가 정확히 짝을 이룬다(T가 자기를 `current`에 쓰면 두 지시가 충돌한다).

6-b. **다음 단계 (project.graph 기반)**: OUTCOME 절(`compile_skill(skill, project=...)`)이 `project.graph`에서 그 스킬 placement(skill_ref identity 일치)의 outgoing 전이를 모아 SKILL.md 본문 끝에 **`## Next Steps`** 단락을 배출한다(버그 2 — 인보크/전이 문구 누락 해소). 형식(산출은 영어 — A12): 스킬 타깃은 ``- [<조건>] → invoke skill `<skill>` ``, 에이전트 타깃은 ``delegate to agent `X` `` + **그 에이전트 placement의 outgoing을 한 단계 인라인**(``after the agent returns: [<조건>] → invoke skill `C` `` — 에이전트는 별도 컨텍스트라 자기 .md에 호출자 지침을 담을 수 없으므로 호출자 스킬 쪽에 후속 지시를 둔다). 조건은 `_transition_condition`(트리거+가드) 재사용, 무가드·무트리거 전이는 `always`. outgoing 0개면 단락 생략. **에이전트 .md에는 다음 단계 단락 없음**(스킬 + project 인수 있을 때만). EntryPoint outgoing(시작 스킬)은 v1에서 스킬별 단락에 영향 없음.
7. **에이전트**: `emit==FRONTMATTER`만 프론트매터,
   SETTINGS(hooks/mcp_servers)는 **MARKETPLACE 빌드에서만** `## Requirements` 언급으로 나간다. `config.tools`의 `mcp__<server>__` 접두에서
   추출한 서버 이름(WP-TM, 11번 항목과 동일 규칙)도 `mcp_servers` 선언과 합쳐(중복 제거·이름순) 같은 `MCP servers connected: …` 줄에 담는다 — 별도 단락을 추가하지 않는다.
   **LOCAL 빌드는 이 둘을 프론트매터로 실제 배출한다(WP-LA, 16번 항목)** — 그때는 `## Requirements` 단락을 내지 않는다(같은 사실을 두 번 말하는 데다 "설정 파일을 생성하지 않음" 문구가 거짓이 된다).
   프론트매터 매트릭스는 **종류가 고른다** — `matrix_for(agent)`가 `agent.config.kind`(`"agent"`/`"fork_agent"`)로 `AGENT_FIELD_MATRIX`의 표를 고르고,
   그 표에 없는 필드는 **부재 = 비적용**으로 건너뛴다(스킬 프론트매터와 같은 규약). fork 에이전트 표에는 `background`·`isolation` 행이 없어 그 두 키가 나오지 않는다.
   **`FieldEmit`은 FRONTMATTER/BODY/SETTINGS 세 목적지뿐이다** — WP-FF에서 `max_turns`/`background`/`isolation`이 프론트매터로 올라가면서
   "호출 파라미터" 본문 단락과 그것을 만들던 `_invocation_section_agent`(항상 빈 목록을 돌려주던 죽은 코드)는 **삭제됐고**,
   남아 있던 `FieldEmit.INVOCATION` 멤버도 퇴역했다(WP-0c).

7-b. **에이전트 종류별 본문 (WP-FK2 C2)**: 두 종류의 본문 구성은 **절 적용 표가 가른다**(WP-6 —
   종전의 `is_workflow` 분기, 그 전에는 `isinstance(agent, AgentDefinition)`) — fork 에이전트(`ForkAgent`)는
   `PLACEMENT=NONE`이고 fsm도 출력 포트도 배치도 없으므로, 그래프 유도 절이 그 종류의 튜플에 아예 없다
   (있으면 없는 필드를 역참조해 죽는다).
   - **워크플로 에이전트**: 본문 → "## Invocation Contract"(`_call_contract_section` — 그래프 도착 전이) → "## Delegation" → "## Requirements" →
     "## Internal Workflow"(legacy FSM) → "## Exits" → tool_shelf → 블랙보드. **fork 실행 기반 줄은 나오지 않는다** — 워크플로 에이전트는
     fork 에이전트가 될 수 없다(검증 `fork_agent_wrong_kind`).
   - **fork 에이전트**: 본문 → "## Invocation Contract"(`_fork_base_contract_section` — 자기를 실행 기반으로 쓰는 fork 스킬 줄만,
     `fork_skills_using`) → "## Requirements" → tool_shelf → 블랙보드. Delegation·Internal Workflow·Exits는 없다("## Exits"를 내면
     fork 스킬의 `EXIT/NEXT` 양식과 부딪힌다). 어느 fork 스킬도 가리키지 않으면 단락 자체가 생략되고 검증 경고 `unused_fork_agent`가 그것을 짚는다.
   `project=None`으로 불러도 두 종류 모두 예외 없이 컴파일된다(그래프 유도 단락이 전부 생략된다).
8. **컴파일 게이트**: `Validator.validate_project`의 에러(`is_warning=False`) 1건이라도 있으면 거부(파일 미생성, errors 반환). 경고는 통과(warnings 동봉).
   게이트 강화 3종(파일 쓰기 전 산출 계획 단계): ① 산출 이름이 되는 컴포넌트(스킬·에이전트) **및 프로젝트 이름**의 이름이
   `^[a-z0-9][a-z0-9-]*$` 불일치면 `compile_invalid_component_name` **에러로 승격** 거부 (F7 검증기에서는 경고 등급 유지 — 편집 중에는 경고가 맞다). 프로젝트 이름은 plugin.json의 `name`(플러그인 식별자)이 되므로 동일 규약을 적용한다.
   ② 전체 산출 경로 집합에 중복이 있으면 `compile_output_path_conflict` 에러로 거부 + 충돌 경로/원인 컴포넌트 보고 (조용한 덮어쓰기 방지).
   ③ **서로 다른 훅이 같은 스크립트 파일명으로 슬러그되면** `duplicate_hook_script` 에러로 거부 + 충돌 파일명·훅 이름 나열
   (`_hook_script_name_conflicts`). 훅 이름은 자유 문자열이지만 파일명은 `_slug`를 거쳐 '`run tests`'와 '`run-tests`'가
   `run-tests.sh` 하나로 겹친다 — `compile_hook_scripts`가 먼저 선언된 훅만 남기고 뒤의 것을 조용히 버리므로 훅 하나가
   말없이 사라진 산출물이 나간다. 경로 충돌 게이트(②)로는 못 잡는다: 드롭이 계획보다 먼저 일어나 계획에는 경로가 하나만
   올라오기 때문이다. 그래서 계획 수립 전에 라이브러리 쪽에서 판정한다(같은 훅 안의 중복은 `script_files`가 번호로 유일화하므로 대상 아님).
9. **plugin.json 매니페스트**: `compile_plugin_manifest(project)`가 `project.name`/`description`/`version`으로 `.claude-plugin/plugin.json`을 무조건 생성한다. 키 순서 `name`→`description`(빈 문자열이면 키 생략)→`version`.
10. **블랙보드 단락 (WP-BB / WP-FK2 C3)**: `_blackboard_section(project, component)`이 "## Shared State (Blackboard)" 단락을 배출한다 — 단계 스킬(fork 2종 포함)의 tool_shelf 단락 뒤·"Next Steps" 앞, state 용도 랩핑 스킬, 그리고 에이전트 `.md`(두 종류) 본문 마지막.
    **총론·CLI 사용법·규칙은 여기 없다** — 스킬마다 글자 하나 다르지 않게 반복되던 문장이라 `guides/<플러그인>/blackboard.md`로 뺐다(정책 21번). 여기 남는 것은 이 컴포넌트에만 해당하는 사실뿐이다: "This skill/agent reads: …" / "writes: …" 한두 줄 + 그 접근이 닿는 클래스의 `state/<플러그인>/<Class>.json` 파일 목록(description 병기).
    **return이 셋이다** — ① 블랙보드 `class_definitions`가 0개 ② 접근 선언(자체 FSM 재귀 + 그래프 placement의 reads/writes) 합집합이 비었다 → **둘 다 단락 자체를 생략**한다(가이드가 이미 전부 말하고 있어 덧붙일 고유 정보가 없다) ③ 본문. 예전의 "합집합이 비면 전 클래스 일반 안내" 폴백은 없어졌다.
    `component`는 **필수 위치 인자**다 — 기본값 None을 남기면 "컴포넌트를 빠뜨린 호출 = 단락이 통째로 사라짐"이 아무 말 없이 성립한다(원칙 5).
    CLI 명령·옵션 이름이 `daedalus/cli/blackboard.py`의 실제 파서와 일치하는지는 이제 `tests/compiler/test_guides.py`가 문자열 일치로 고정한다(cli는 model/emit을 임포트할 수 없어 상수 공유 대신 테스트로 드리프트를 막는다).
11. **`## Requirements` 자동 언급 (WP-TM)**: `_mcp_servers_from_tools(tools)`가 도구 문자열 목록에서 `mcp__<server>__` 접두의 서버 이름 집합을 추출한다(이름순 정렬 — 결정적). 스킬은 `skill.config.allowed_tools`를 스캔해 서버가 있으면(local 여부·project 인수 여부와 무관) `## Next Steps` 단락 앞에 신규 `## Requirements` 단락(`_mcp_requirement_section_skill`)을 배출한다(없으면 단락 생략). 에이전트는 `config.tools`에서 추출한 서버를 기존 SETTINGS `## Requirements` 단락(`_settings_note_agent`, 7번 항목)의 `mcp_servers` 선언과 합쳐 하나의 `MCP servers connected: …` 줄로 병합한다(중복 없음).
12. **작업 재개 (WP-RS / WP-FK2 C3)** — 저장 단위는 **플러그인 FSM(프로젝트 그래프 배치)의 위치**다(스킬 내부 FSM 상태는 다루지 않음 — 사용자 확정 설계). 규약 파일 `state/__progress__.json` — **최상위 키가 플러그인 이름**이고 그 아래에 항목(`current`/`completed`/`note`/`prev`/`updated`)이 온다(WP-NS/D13. `prev`는 WP-IC에서 추가된 직전 출처 스킬 이름). 파일은 `state/` 루트에 **하나로 남는다** — 블랙보드가 `state/<플러그인>/`로 갈라지는 것과 다른 이유는, 워크스페이스 전체를 한눈에 보는 것이 이 파일의 목적이고 스키마 밖 규약 파일이라 클래스 순회 대상도 아니기 때문이다. **갱신은 `daedalus-bb progress` 서브커맨드가 전담한다** — 공유 파일의 병합을 산문으로 시키면 모델이 한 번만 놓쳐도 남의 진행 기록이 통째로 사라진다.
    **규약의 산문(파일 구조·옵션 전부·exit 3의 뜻·수동 폴백·`note`에 갈래를 적는 이유·전이 스킬이 `current`를 소유하지 않는다는 규칙)은 워크플로 가이드 2절로 갔다**(정책 21번). 컴포넌트 산출에 남는 것은 **그 컴포넌트의 이름이 들어가는 줄**뿐이다.
    - **재개 프리앰블**: 프로젝트 그래프에 배치된 `ProceduralSkill`·`DeclarativeSkill`·state 용도 `WrappedSkill`(미배치·에이전트 .md 제외, **fork 2종 제외** — 서브에이전트는 재개 판단을 하지 않는다, 정책 20번)에 한해 `_resume_preamble_section`이 프론트매터·포인터 직후·본문 앞에 "## Resuming Work"를 배출한다. 잔여는 두 문장이다: `Run <cli> read first; this skill is <name>. Follow the resume rules in the workflow guide.` + `If it exits 3 (no entry for this plugin yet), this invocation is the start: <cli> set --current <name>.` **exit 3의 조건절을 잔여에 남긴다** — 조건을 떼고 명령만 남기면 가이드 3절의 일반형("항목이 없으면 지금 불린 스킬이 시작점이다")과 워크플로 중간 스킬의 `--current <나>` 기록이 충돌한다. placement 판정은 "Next Steps"(6-b번)와 같은 `_graph_placements`(skill_ref identity)를 공유한다.
    - **다음 단계 갱신 규칙**: 배치 스킬의 "## Next Steps" 끝에 `_progress_update_note(project)`가 합류한다 — **명령 1줄**(`set --completed <this skill> --current <next target> --prev <this skill> --note "<branch> — <handoff>"`) + 한 절(`If the branch delegates to an agent, run this twice — see the workflow guide.`). 에이전트 위임 갈래의 2회 갱신 단서를 **잔여에 남기는** 이유: 규칙을 통째로 가이드로 보내면 갈래 줄 바로 아래의 단일 템플릿이 그대로 실행돼 위임 갈래에서 조용히 한 번만 갱신된다.
    - **비동기 fork 인계 규약**: 그 스킬의 outgoing 갈래가 `AsyncForkSkill`을 가리키면 진행 명령 뒤에 `_async_fork_handoff_note` 1줄이 더 붙는다(`--current <that fork> --note "awaiting background fork"` — 정책 20번의 3단 규약 ①단계).
    - **터미널 배치**: **placement의 실제 outgoing 전이가 0개**인 배치는 "Next Steps" 대신 `_progress_terminal_section`이 "## Finishing Up"(자신을 `completed`에 추가 + `current`를 `"done"`으로) **명령 1줄**을 배출한다. 판정은 "다음 단계 문구 생성 실패"가 아니다 — outgoing 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안 나와도 터미널이 아니며 이때는 아무 단락도 배출하지 않는다.
    - **TransferSkill**: **project에 placement가 1개 이상**일 때 본문 끝에 "## Progress Record" 헤딩 + `_transfer_progress_note(project)` **명령 1줄**(`set --note "<what happened>"`)을 배출한다(진행 파일이 존재하지 않는 프로젝트에서의 고아 지시 방지). "`current`를 소유하지 않는다"는 규약 문장은 가이드 2절이 말한다.
    - **SessionStart 훅 합성**: `PluginProject.emit_progress_hook: bool = True`(직렬화 왕복, 구버전 키 부재 시 기본 True)이고 프로젝트 그래프에 placement가 1개 이상이면, `compile_hooks_json`이 `hook_library`를 오염시키지 않고 컴파일 시점에 SessionStart 이벤트에 진행 상태 주입 커맨드(`cat state/__progress__.json 2>/dev/null || true`)를 합성해 합류시킨다(사용자 정의 SessionStart 훅 뒤에 이어붙어 공존). `emit_progress_hook=False`이거나 placement가 0개면 합성 훅 미배출. 토글은 프로젝트 속성 다이얼로그의 "세션 시작 시 진행 상태 자동 주입 (SessionStart 훅)" 체크박스. 합성 커맨드는 POSIX 셸 전제(`cat`/`||`) — 비POSIX 환경에서는 토글로 끄는 것이 대응책(훅 프리셋과 동일한 전제).
12-a. **종류를 묻는 자리의 술어 (WP-2c)**: 산출 조립의 분기는 **컴포넌트 클래스가 아니라 능력 선언**을 본다 — 컴파일러에
    남은 컴포넌트 대상 `isinstance`는 0이다. 대응표: "산출 파일을 내는가"=`emits_output()`(파사드 `emits_output_file`) ·
    "fork 스킬인가"=`BUCKET is SKILLS ∧ RUNS_IN_SUBAGENT ∧ BODY_SOURCE is OWNED` · "단계 스킬인가"=`PLACEMENT is STATE ∧
    BODY_SOURCE is OWNED` · "랩핑 스킬인가"=`BODY_SOURCE is EXTERNAL` · "전이 스킬인가"=`effective_placement() is EDGE` ·
    "참조 노드인가"=`effective_placement() is REFERENCE` · "위임 대상인가"=`DELEGATION_TARGET` · "보고가 늦게 오는가"=
    `REPORTS_OUT_OF_BAND` · "배경 지식 스킬인가"=`PLACEMENT is NONE` · "워크플로 에이전트인가"=`PLACEMENT is STATE` ·
    "훅을 무엇을 참조하는가"=`hook_refs()` · "FSM이 있는가"=`state_machines()` · "포트가 무엇인가"=`output_ports()`/`call_ports()`.
    새 종류는 산출 코드를 고치지 않고 선언을 고른다.

13. **진입 맥락 + 호출 계약 (WP-IC/WP-IP/WP-CT)**: 배치된 전역 `StepSkill`(절차형·fork 2종)·`DeclarativeSkill`·state 용도 `WrappedSkill`에서 incoming 전이가 1개 이상이면, `_entry_context_section`이 "## Resuming Work" 프리앰블 뒤·본문 앞에 "## Entry Context" 단락을 배출한다. **도입은 한 문장이다** — `Check \`prev\` and the branch in \`note\`, then follow the matching entry below.`(예전의 5문장 도입 — 어디서 읽는가·여러 갈래를 어떻게 가르는가·에이전트 위임 뒤의 `prev` — 은 워크플로 가이드 4절로 갔다. 진행 파일을 직접 읽으라는 지시도 함께 사라져 CLI 경로로 통일됐다).
    항목은 출처 이름순으로 한 줄씩이다: `- entered from \`X\` [조건]`(+ 출처의 transfer_on description 병기, 전이 스킬 수행 완료 문구 합류). 출처가 **워크플로 에이전트**면 `- entered after agent \`X\` returned` + 위임 스킬 이름 병기(규약상 `prev`에는 에이전트가 아니라 위임 스킬이 남는다), **비동기 fork**면 `- entered when background fork \`X\` reported`(그 fork가 다음 단계를 부른 것이 아니라, 보고를 받은 메인이 시작시켰다). 동기 fork는 일반 출처와 문구가 같다. 포트 그룹 헤딩 없음, 그래프에서만 유도(WP-IP). incoming 0개 배치·미배치는 산출 변화 없음.
    `compile_agent`의 "## Invocation Contract"는 종류가 가른다 — 워크플로 에이전트는 `_call_contract_section`이 프로젝트 그래프의 incoming 호출 전이에서 유도하고(WP-CT — 수동 카드 없음), fork 에이전트는 `_fork_base_contract_section`이 자기를 실행 기반으로 쓰는 fork 스킬 줄만 낸다(7-b번).
14. **files/ 복사 + dangling_file_ref 경고 (WP-FR)**: `files_dir`가 실존 디렉토리면(게이트 통과 시에만) `_copy_files_tree`가 `<out>/files/`로 정렬 순회 복사한다(결정적, 심볼릭 링크 미추종 — 디렉토리는 재귀 안 함·파일은 복사 안 함). 기존 `<out>/files/`는 복사 전 삭제(out 전체가 아니라 files/만). 복사된 파일 경로는 `CompileResult.copied_files`에 담긴다. `files_dir`가 주어지면(실존 여부 무관) `_scan_dangling_file_refs`가 스킬·에이전트 body에서 `${CLAUDE_PLUGIN_ROOT}/files/<경로>` 참조 토큰을 스캔해 files_dir에 실존하지 않으면 `dangling_file_ref` 경고를 `CompileResult.warnings`에 추가한다(게이트 차단 아님). `files_dir` 생략(None) 시 복사·스캔 모두 생략되어 기존 산출 파일/문자열이 완전히 불변(하위 호환).
15. **빌드 타깃 — LOCAL 빌드 (WP-TG)**: `project.build_target`(기본 `MARKETPLACE`)에 따라 산출 계획이 갈린다(`CompileContext.is_local`/`cc_prefix`).
    - **MARKETPLACE**(기본): `plugin.json` + `skills/`·`agents/` 산출. **"현행과 바이트 동일"이라는 하위 호환 게이트는 WP-NS에서 폐기됐다** — `state/`에는 `${ROOT}` 토큰이 붙지 않아 작업 폴더 CWD 기준이라, 마켓플레이스 플러그인이 한쪽에만 끼어도 `state/<Class>.json`과 고정 파일명 `state/__progress__.json`이 충돌한다. 배포 전이라 지킬 대상이 없어 네임스페이스를 양쪽 타깃에 적용했다.
    - **LOCAL — 컴파일이 곧 설치 (WP-MW)**: out_dir가 대상 작업 폴더다. 스킬/에이전트는 `.claude/skills/`·`.claude/agents/`(CC가 실제로 읽는 위치)로 나가고, `plugin.json`과 이전의 `INSTALL.md`/`install.ps1`/`install.sh` 동봉은 폐기됐다(별도 설치 단계가 없다). `hooks/hooks.json` 파일도 만들지 않는다 — 훅은 설정 파일(`.claude/settings.json` 기본 / `settings.local.json` — Ctrl+B 때 고른다, `compile_project(settings_filename=)`)의 `hooks` 섹션에 병합된다(훅 스크립트 파일은 양쪽 타깃 모두 `hooks/scripts/`로 — LOCAL 커맨드가 `${CLAUDE_PROJECT_DIR}/hooks/scripts/…`를 가리킨다). MCP 배선: `referenced_mcp_servers(project)`(스킬 allowed_tools ∪ 에이전트 tools/mcp_servers, 이름순) ∩ `project.mcp_server_defs` 정의를 `<out>/.mcp.json`의 `mcpServers`에 병합하고 그 이름을 같은 설정 파일의 `enabledMcpjsonServers`에 올린다. 정의 조회는 `project.mcp_server_defs` 우선 + `compile_project(..., extra_server_defs=)`(호출 환경 주입 — 앱이 `CompileActions.known_server_defs()`로 자기 자신의 daedalus 서버를 넣는다. 서버 미기동이면 기본 포트) 폴백. 참조되지만 정의 없는 서버는 `missing_mcp_server_def` 경고, 깨진 기존 JSON은 건드리지 않고 `unmergeable_settings_json` 경고(수기 설정 보호). 병합은 추가/갱신만·동일 훅 그룹 중복 삽입 없음 — **재컴파일 멱등**. 병합 구현은 `compiler/wiring.py`의 `wire_workspace`가 단일 진실("Claude Code 실행" 메뉴와 공유). files/ 복사는 LOCAL에서 기존 `<out>/files/`를 **삭제하지 않고** 덮어쓰기만 한다(`_copy_files_tree(clear_first=False)` — 사용자 작업 폴더의 파일 삭제 위험 > 스테일 잔존). `${ROOT}` 확장·이름 규약 게이트·`schemas/<플러그인>.json` 산출 조건은 기존 그대로.

16. **LOCAL 에이전트 프론트매터 — hooks / mcpServers (WP-LA)**: CC는 **보안상 플러그인 서브에이전트의
    `hooks`/`mcpServers`/`permissionMode` 프론트매터를 무시한다**(공식 sub-agents 문서 명시). 즉 이 셋은
    `.claude/agents/`로 반입되는 LOCAL 빌드에서만 실제로 동작하며, 그것이 로컬 타깃을 고르는 이유다.
    - `_local_settings_frontmatter_lines(agent, project)`가 **LOCAL일 때만** 프론트매터에 `hooks`/`mcpServers`를
      덧붙인다(`compile_agent`가 `_frontmatter_lines_agent` 뒤에 이어 붙임). `project`가 없으면 MARKETPLACE
      취급이라 기존 호출부 산출은 불변(하위 호환).
    - `hooks` 값은 **settings.json의 hooks와 동일한 3단 중첩 구조**(이벤트 → 그룹[matcher + hooks] → 커맨드
      엔트리)다. `_agent_hook_groups`가 `compile_hooks_json`과 같은 규칙으로 만든다(matcher는 Pre/PostToolUse
      전용, timeout은 있을 때만, 이벤트 키 순서 = `HookEvent` 선언 순서, 같은 이벤트 복수 훅 = 라이브러리 순서).
      라이브러리에 없는 이름은 조용히 빠진다(`dangling_hook_ref`가 따로 짚는다). flow-style로는 표현할 수 없어
      `_yaml_block_lines`(제한된 블록 YAML 렌더러 — dict/list/스칼라만, 스칼라 표기는 `_yaml_scalar` 재사용)를 쓴다.
    - `mcpServers`는 **이름 참조 리스트**다(`- github`). 목록은 `_agent_mcp_server_names` = `config.mcp_servers`
      선언 ∪ `config.tools`의 `mcp__<server>__` 추출(이름순) — `## Requirements` 단락과 같은 합집합 규칙이라 본문과
      프론트매터가 서로 다른 목록을 말하지 않는다. 인라인 서버 정의는 모델에 서버 설정 자체가 없어 범위 밖.
    - `permissionMode`는 매트릭스가 이미 프론트매터로 내보내므로 별도 처리하지 않는다. 대신 마켓플레이스에서
      무시된다는 사실은 `unsupported_agent_field_in_marketplace_build` 경고가 알린다(MCP는
      `mcp_agent_in_marketplace_build`가 이미 짚으므로 이 규칙은 hooks·permissionMode만 본다 — 경고 중복 방지).

17. **토큰 비용 리포트 (A5-lite)**: `CompileResult.token_report: TokenReport`가 **실제로 쓴 산출 텍스트**의
    파일별 추정치(`path`/`kind`/`chars`/`tokens`)와 합계를 담는다. 측정 시점은 `${ROOT}` 확장 **후**다 —
    컨텍스트에 실리는 것이 그 텍스트다. 목적은 "자동 단락은 반복 실리는 사용료"(A12 논리)의 계기판이자
    점진 공개(A5) 착수 근거 수치 확보다.
    - **표시 전용이다.** 산출 파일 텍스트는 리포트의 유무와 무관하게 바이트 단위로 불변이고, 임계 초과는
      **검증 규칙이 아니다** — `WARNING_RULES`에 등록하지 않고 `ValidationError`도 만들지 않으며
      `warnings`/`errors`를 늘리지 않는다(컴파일을 막지도 않는다). 표면은 `TokenReport.notice()` 한 줄.
    - **추정은 휴리스틱**(순수 stdlib, 외부 토크나이저 의존 금지): ASCII 4자 ≈ 1토큰, 비ASCII 1.5자 ≈
      1토큰. 두 구간으로 나눈 이유는 산출의 자동 단락이 영어여도 사용자 값(body/description)은 한국어일
      수 있고, 한 구간으로 뭉치면 그 부분을 3배 가까이 과소평가하기 때문이다. 자릿수 감각용(±20% 수준).
    - **임계 `DEFAULT_FILE_TOKEN_THRESHOLD = 5000`은 파일당**이고 `TokenKind.CONTEXT`로 선언된
      행(skill/agent/wrapped_runner/workspace_rule/claude_md/가이드 2종)에만 적용한다 — `schemas.json`/`hooks.json`/`plugin.json`은 CC가 설정으로
      읽을 뿐 대화 컨텍스트에 실리지 않으므로 합계에는 넣되 임계로 재지 않는다. 5000의 근거: SKILL.md는
      스킬이 걸릴 때마다 통째로 실리고, Anthropic 스킬 저작 지침의 "500줄 안쪽" 권고 ≈ 20,000자 ≈
      5,000토큰이다(새 규범이 아니라 기존 권고의 토큰 환산).
    - `.claude/CLAUDE.md`는 **이 플러그인의 구역 본문만** 계상한다(파일 전체는 남이 쓴 내용까지 포함해
      이 컴파일이 만든 비용이 아니다). 복사만 하는 `files/`·`skill-files/`는 대상 아님.
    - 표시: 컴파일 상태바에 합계 + 임계 초과 시 안내창(`CompileActions.show_token_notice`), MCP
      `compile_preview`가 `chars`/`tokens`/`token_threshold`/`token_notice`, MCP `compile_check`가
      리포트 요약(`tokens.total_tokens`/`over_threshold`/`notice`).

18. **컴파일 dry-run (G3)**: `compile_project(..., dry_run=True)`는 **파일을 하나도 쓰지 않는다** —
    산출 텍스트 생성·계획 수립(`_plan_outputs`)·게이트 판정·참조 스캔·LOCAL 병합 판정은 전부
    그대로 돌리고 **쓰기·복사·JSON 병합만** 생략한다. `CompileResult.dry_run=True`이고
    `written`/`copied_files`는 "쓰였을/복사됐을" 경로다.
    - **왜 필요한가:** 컴파일러가 emit하는 경고 7종(`dangling_file_ref` /
      `unknown_skill_files_dir` / `dangling_skill_file_ref` / `missing_mcp_server_def` /
      `unmergeable_settings_json` / `unmergeable_claude_md` / `rule_body_frontmatter`)은
      `Validator.validate_project`에 나오지 않아 **실제 컴파일에서만** 드러났다 — MCP로만
      저작하면 GUI Ctrl+B를 누르기 전까지 영영 보이지 않는다(MCP 패리티 원칙 위반).
    - **LOCAL 병합류는 읽되 절대 쓰지 않는다.** `Phase.INSTALL` 단위 둘(`LocalWiringUnit` →
      `wire_workspace` · `ClaudeMdUnit`)은 `ctx.dry_run`에서 기존 파일을 읽어 병합을 메모리에서
      계산하므로 `unmergeable_*` 판정이 실제 배선과 같고, 대상 작업 폴더는 불변이다
      (`tests/compiler/test_dry_run.py`가 스냅샷으로 고정).
    - **`out_dir`는 dry-run일 때만 생략할 수 있다**(실제 컴파일에서 생략하면 `ValueError`).
      생략 시 계획 경로가 상대 경로가 되고, 대상 폴더를 읽어야 판정하는 경고 2종
      (`unmergeable_settings_json`/`unmergeable_claude_md`)만 건너뛴다 — files_dir/
      skill_files_dir 미지정 시 그 스캔을 생략하는 것과 같은 None 규약이다.
      `missing_mcp_server_def`는 폴더와 무관하므로 그대로 나온다.
    - **주입은 Ctrl+B와 공유한다** — `CompileActions.compile_inputs()`(files_dir/
      skill_files_dir/extra_server_defs/resolved_hooks의 단일 진실, `MainWindow.compile_inputs`
      한 줄 위임)를 컴파일 다이얼로그와 MCP `compile_check`가 함께 쓴다. 한쪽만 고치면
      "검사는 통과했는데 컴파일하면 경고가 뜬다"가 된다.
    - `FilesTreeUnit`(→ `units/sink._copy_files_tree`)은 dry-run에서도 **같은 순회 코드**로 목록을 만든다(열거를 따로
      구현하면 계획과 실행이 언젠가 어긋난다). 같은 작업에서 `CompileResult.copied_files`가
      files/ 복사분에 **대입**되어 skill-files/ 복사분을 지우던 버그도 고쳤다(이제 이어 붙인다).

19. **에이전트 위임 단락 (2026-09-12)**: 에이전트가 호출 포트(`call_agents`)로 다른 에이전트를
    부르면 `_agent_delegation_section(agent, project)`이 에이전트 `.md`에 **"## Delegation"**
    단락을 배출한다 — 스킬의 "## Next Steps"에 해당하는 자리다. 프로젝트 그래프에서 이 에이전트
    placement의 outgoing 중 **타깃이 에이전트인 전이**를 모아 `- \`포트\` → delegate to agent
    \`B\` [guard: …] — <포트 description>` 목록을 내고(포트 이름 → 에이전트 이름순, 결정적),
    도입 문구가 세 가지를 못 박는다: Agent 도구로 띄우고 **보고를 기다린다**(동기), 그 산출물의
    소유자는 부른 쪽이며 자기 출구를 그것으로 고른다, **중간 보고는 이 에이전트의 호출자에게
    가지 않으므로** 자기 최종 보고에 요약한다. 진행 기록은 지시하지 않는다 — 그것은 메인
    스레드에서 도는 스킬 소유다(`state/__progress__.json`). 호출 전이가 없으면 단락 생략.
    받는 쪽 에이전트의 "## Invocation Contract"(13번)는 호출자가 스킬이든 에이전트든 같은
    경로로 유도되므로 별도 처리가 없다.

20. **fork 스킬 2종 (2026-09-13, 2종 분리 2026-09-17, `emit/fork.py`)**: CC는 fork 스킬 본문을 `agent`
    서브에이전트의 작업 지시로 쓴다(모델·실측은 `plugin-model.md` "fork 스킬"). 종류는 `SyncForkSkill`(동기)와
    `AsyncForkSkill`(비동기) 둘이고, **산출을 가르는 것은 클래스가 아니라 매트릭스**다(`config.kind` →
    `sync_fork`/`async_fork`).
    - 프론트매터에 `context: fork`·`agent:`·`background:`를 낸다. 셋 다 매트릭스가 정하고(`context`·`background`는
      FIXED) `fork_frontmatter_lines`는 `agent:` **이름 해소만** 한다. 기본값 `general-purpose`도 **명시 배출**한다
      (결정적·읽는 사람에게 분명). 프로젝트 에이전트는 MARKETPLACE `플러그인:이름` / LOCAL `이름`
      (`resolve_fork_agent_name` → `emit/common.agent_invocation_name`: 위임 대상 이름은 컴포넌트가
      `delegated_agent_name()`으로 답하고 빌드 타깃이 접두를 정한다), 내장·외부는 저장된 문자열
      그대로다(정확 일치).
    - `background`는 **배치 여부와 무관하게 항상** 나간다 — 동기 fork `false`, 비동기 fork `true`. 키를 빼면
      CC 기본값(백그라운드)으로 돌아 산출이 침묵한다. 키 순서는 enum 선언 순서라 `context` → `agent` → `background`.
    - **서브에이전트는 다음 단계를 시작하지도, 진행 기록을 쓰지도 않는다** — fork 에이전트가 `Explore`/`Plan`이면 상태 파일
      쓰기가 어색하고, 메인에는 SKILL.md가 보이지 않는다. 대신 **보고가 지시가 된다**: 배치된 fork는
      "## Next Steps"/진행 갱신 규칙/"## Finishing Up" 대신 **"## Report"**(`fork_report_section`)를 낸다 —
      갈래 목록(Next Steps와 같은 줄) + 보고 첫 줄 `EXIT: <branch> / NEXT: /<skill>` + 끝에 메인이 실행할
      `daedalus-bb … progress set …` 명령. 터미널 배치면 `EXIT: done / NEXT: (end)` + `--current done`.
      갈래 목록·`EXIT/NEXT` 양식·진행 명령은 **두 종류가 같다**. 도입 문구와 선행 조건만 갈린다.
    - **비동기 fork의 도입 문구는 "메인은 기다리지 않는다"라고 단정하지 않는다**: `background: true`여도
      비대화 `claude -p`/Agent SDK, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, 같은 스킬이 아직 도는 중의 재호출,
      스케줄 작업 발화에서는 **강제로 인라인 실행**된다(공식 문서 2026-09-17 확인). 단정하면 인라인으로 돌아온 경우
      메인이 오지 않을 작업 알림을 기다린다. 그래서 두 경로를 다 말하고("normally … as a task notification (… it is
      delivered inline instead)") 지시는 하나로 준다("do not start the next step and do not update the progress file").
    - **비동기 fork가 도는 동안의 `current` 소유 — 3단 규약 — 오케스트레이터 확정 (2026-09-18).** 진행 파일은 플러그인당
      항목이 하나라 "지금 도는 비동기 단계"를 적을 자리가 없다. ① **호출자**는 비동기 fork로 넘기는 갈래가 있으면
      "## Next Steps" 진행 명령 뒤에 `--current <that fork> --note "awaiting background fork"` 규약 1줄을 받는다
      (`_async_fork_handoff_note`). ② **비동기 fork의 "## Report"**는 진행 명령 **앞에** 선행 조건 1줄을 둔다 —
      `run <cli> read first. Only if \`current\` is still \`<이 스킬>\` …; if it moved on, do not touch the progress
      file — report this result to the user and stop`(`_async_progress_precondition`). 없으면 뒤늦게 온 보고가 이미
      앞으로 나간 워크플로의 `current`를 과거로 되돌린다. **진행 파일 스키마는 불변이다**(항목 하나·같은 키).
      ③ **워크플로 가이드 3절**(재개 규칙)이 "`current`가 아직 도는 비동기 fork면 사용자 확인 대상이 아니다 —
      그 fork의 보고를 기다리는 중이라고 알리고 진행 파일은 건드리지 않는다"를 말한다(정책 21번).
    - **호출자 쪽 표기**: 비동기 fork를 가리키는 갈래 줄에 접미
      `(background fork — do not block on it; act on its report as soon as you have it, whether it comes back inline
      in this turn or later as a task notification)`가 붙는다. 비동기 fork **에서** 오는 진입 맥락 항목은
      `- entered when background fork \`X\` reported …`다(그 fork가 다음 단계를 부른 것이 아니라, 보고를 받은 메인이
      시작시켰다). 동기 fork는 양쪽 다 문구 변화가 없다.
    - "## Resuming Work"는 **두 종류 모두** 내지 않는다(서브에이전트는 사용자에게 되묻거나 진행 파일을 쓸 수 없다 —
      재개 판단은 부르는 메인 몫). "## Entry Context"·절차·tool_shelf·블랙보드 단락은 절차형과 같다. 미배치 fork는
      `background`는 나가고 "## Report"는 없다(분기할 그래프가 없다).
    - **가이드 포인터는 fork 전용 줄이다**(정책 21번) — 진행 기록·재개 규칙을 가리키는 일반 포인터를 fork에 주면
      fork 자신의 "## Report"("진행 파일을 네가 갱신하지 말라")와 정면으로 충돌한다.
    - fork 에이전트 산출은 7-b 항목 참조.

21. **공통 안내 파일 (WP-FK2 C3, `compiler/emit/guides.py` + 대상 판정 `compiler/emit/pointer_rules.py`)**: 워크플로 개념·진행 기록 규약·재개 규칙·진입 맥락
    읽는 법·fork 보고 양식·블랙보드 CLI 사용법은 스킬마다 **글자 하나 다르지 않은 같은 문장**이었다. 배치된 스킬이
    열이면 같은 산문이 열 번 산출되고 그 토큰은 걸릴 때마다 실린다(A12 — 반복은 곧 사용료). 그래서 공통 문장은
    파일 둘로 모으고 각 컴포넌트 산출에는 **포인터 1줄**만 남긴다.
    - **산출 위치**는 두 빌드 타깃 공통으로 `<out>/guides/<플러그인>/workflow.md`·`blackboard.md`다 —
      플러그인 이름으로 네임스페이스를 가르는 것은 `schemas/<플러그인>.json`과 같은 이유(WP-NS)고,
      `files/` 밖에 두는 것은 공용 files/ 트리 복사와 섞이지 않게 하기 위해서다. 본문 참조는 타깃 중립
      `${ROOT}/guides/<플러그인>/…`(ROOT 확장 대상 kind에 두 가이드 kind를 넣었다).
    - **계획 kind는 둘이다** — `plan_kinds.GUIDE_WORKFLOW`/`GUIDE_BLACKBOARD`(`emit/guides`의
      `WORKFLOW_GUIDE_KIND`/`BLACKBOARD_GUIDE_KIND`가 그것을 재-export한다). `PlannedOutput`에 구분 필드를 새로
      만들지 않는다: kind가 곧 그 행을 쓸 단위의 id이고, 모르는 kind는 `ValueError`로 컴파일을 죽인다
      (`units.registry.unit_for`). 두 행은 `token_kind=CONTEXT`·`is_guide=True`로 선언돼 리포트에 별도 줄로 실리고, `TokenReport.notice()`가 "공통 안내 파일 ≈N토큰은 포인터를 받은 컴포넌트가
      실행될 때마다 추가로 실린다"를 덧붙인다(파일당 임계 판정의 의미는 바꾸지 않는다 — 임계는 "SKILL.md 500줄"
      권고의 토큰 환산이고 가이드도 같은 기준의 파일이다).
    - **게이트**: workflow.md는 프로젝트 그래프에 배치 노드가 1개 이상일 때, blackboard.md는 블랙보드
      `class_definitions`가 1개 이상일 때 내용을 갖는다. 그 위에 **포인터가 하나도 나가지 않으면 파일을 만들지
      않는다**(고아 파일 없음 — 대상 집합은 `_plan_outputs`가 파일을 내는 집합과 **같은 함수**
      `emitted_components`로 센다 — 계획 쪽은 `ComponentUnit`이 같은 `emits_output()`을 본다).
    - **workflow.md 5절**: ① 이 워크플로가 도는 방식(스킬 = 단계, 출력 이벤트 = 갈래, 가드, 전이 스킬,
      에이전트 위임, fork sync/async, 선언형·참조·배경 스킬) ② 진행 기록(`state/__progress__.json` 구조,
      `progress read|set` 옵션 전부, exit 3의 뜻, `note`에 갈래를 적는 이유, 에이전트 위임 시 2회 갱신,
      전이 스킬은 `current`를 소유하지 않는다, 비동기 fork 인계, 수동 폴백) ③ 재개 규칙(current가 나 / 다른
      스킬이면 사용자 확인 / **도는 중인 비동기 fork면 확인 대상이 아니다** / exit 3이면 지금 불린 스킬이
      시작점) ④ 진입 맥락 읽는 법(`prev` + `note`의 갈래, 위임 복귀 시 `prev`) ⑤ fork 보고 양식
      (`EXIT: <branch> / NEXT: /<skill>` | `NEXT: agent <name>` | `NEXT: (end)` + 끝의 진행 명령).
      **2·3절 앞에 한 문장**이 "이 두 절은 메인 대화 전용이다 — 포크된 서브에이전트라면 진행 기록을 갱신하지도
      사용자에게 묻지도 말라"고 못 박는다. 다만 **읽기는 막지 않는다**: fork 산출에도 "## Entry Context"가
      나가고 그 지시를 이행할 유일한 수단이 `progress read`라, 읽기까지 금지하면 한 산출이 서로 모순되는 두
      지시를 낸다(원칙 5).
    - **blackboard.md**: 상태 파일 위치(`state/<플러그인>/<Class>.json`)와 전 클래스 목록(description 병기),
      `daedalus-bb` CLI 사용법(`command -v` 존재 확인 → `read`/`write --set`/`validate`, `--schemas`가 필수이고
      상태 폴더를 정한다, 설치 명령은 지시하지 않는다), 읽기-수정-쓰기 3줄 규칙.
    - **가이드 본문에는 `${ROOT}`도 어떤 CC 치환 변수도 쓰지 않는다.** 치환은 **스킬·에이전트 content에서만**
      일어나고(공식 plugins-reference 치환 표 확인 2026-09-17) 가이드는 모델이 Read 도구로 읽는 평범한 파일이라
      토큰이 리터럴로 보인다. 같은 문서가 "Bash로 실행하는 명령의 환경에도 없다"고 못 박으므로 Bash로도 해소되지
      않는다. 그래서 경로 자리에는 `<SCHEMAS>` 자리표시자를 쓰고 "너를 보낸 스킬/에이전트 파일에 적힌
      `--schemas <경로>`를 그대로 쓰라"고 말한다.
    - **그 대가로, 포인터를 받은 컴포넌트 산출에는 확장되는 실제 경로를 가진 명령이 최소 1줄 남는다.**
      배치된 단계 스킬은 진행 명령(`_progress_cli`)이 이미 그 역할을 하지만 에이전트 두 종류·랩핑 실행
      에이전트·미배치 스킬에는 진행 명령이 없다 — 그럴 때 포인터 줄에 `State CLI: \`daedalus-bb --schemas
      ${ROOT}/schemas/<플러그인>.json …\`` 한 줄을 덧붙인다. 판정은 **조립된 블록에서 직접** 한다(`--schemas
      ${ROOT}/schemas/` 접두가 이미 있는가) — 컴포넌트 종류로 다시 유도하면 산출과 판정이 언젠가 어긋난다.
    - **포인터 위치·대상**: 프론트매터 블록 **직후**(`blocks.insert(1, …)`), 다른 어떤 단락보다 앞.

      | 대상 | workflow.md | blackboard.md |
      |---|---|---|
      | 배치된 절차형·state 용도 랩핑 스킬 | ✅ 일반(`Before you start, read …`) | ✅ 클래스 1개 이상일 때 |
      | 배치된 선언형 | ✅ 일반 | — (단계 스킬이 아니다 — 정책 10번) |
      | 배치된 워크플로 에이전트 | ✅ 일반 | ✅ |
      | placement가 1개 이상인 프로젝트의 전이 스킬 | ✅ 일반 | — (단계 스킬이 아니다) |
      | 배치된 fork 스킬(sync/async) | ✅ **fork 전용 줄** — `section "Fork reports"`만 가리키고 "진행 기록과 재개 규칙은 메인 대화의 것이지 네 것이 아니다"라고 말한다 | ✅ |
      | fork 에이전트 | — | ✅ |
      | 미배치 스킬·용도 reference 랩핑 | — | 단계 스킬이면 ✅ (reference 랩핑은 —) |
      | 랩핑 실행 에이전트 | — | — (`compile_wrapped_runner`가 `_insert_guide_pointer`를 부르지 않는다) |

      fork를 일반 포인터 대상에 넣으면 가이드 2·3절이 fork 자신의 "## Report"와 정면으로 충돌한다 — 컴파일러가
      fork에서 "## Resuming Work"를 **일부러** 빼는 근거를 포인터가 도로 들여오는 셈이고, fork 서브에이전트는
      사용자에게 되물을 수도 없다.
    - **테스트**: `tests/compiler/test_guides.py`(본문·게이트·포인터 대상·CLI 문자열 파서 일치),
      `test_plugin_namespace.py`(가이드 경로 + 가이드 텍스트에 `${ROOT}`/`${CLAUDE_` 부재 + 블랙보드 포인터를
      받은 모든 컴포넌트에 확장된 `--schemas` 경로 1회 이상), `test_token_report.py`(두 계획 행이
      `TokenKind.CONTEXT`·`is_guide`로 선언되고 별도 항목으로 나타난다), `test_output_language.py`(가이드 픽스처).

출력은 결정적(같은 모델 → 같은 텍스트), LF 줄바꿈, UTF-8(BOM 없음). 텍스트 생성(`compile_skill`/`compile_agent`)은 파일시스템과 분리되어 문자열 단위 테스트 가능.

**산출 언어는 영어다 (A12).** 컴파일러가 **생성하는** 텍스트(헤딩·지시문·조건
문구·FSM 절차 서술·진행 상태 규칙·블랙보드 CLI 지시 …)는 전부 영어이고,
**사용자가 입력한 값**(body, description, when_to_use, transfer_on/call_agents
description, 블랙보드 클래스·필드 설명 …)은 손대지 않고 그대로 나간다 — 한국어
값이 영어 문장 안에 삽입되는 형태(`— <desc>` 병기)는 정상이다.

- **왜:** 산출을 읽는 소비자가 LLM이고, 자동 단락은 **모든 스킬에 반복해서**
  실려 토큰 비용이 곧 사용료다. 문구는 직역이 아니라 CC 스킬 지시문으로
  자연스러운 영어(명령형·간결·모호성 없음)로 재작성했다.
- **주요 헤딩 대응:** `## Next Steps` / `## Resuming Work` / `## Entry Context` /
  `## Shared State (Blackboard)` / `## Invocation Contract` / `## Exits` /
  `## Procedure` / `## Output Events` / `## Requirements` /
  `## Progress Record` / `## Finishing Up` / `## Report` /
  `## Internal Workflow` / `## Reference: Tool Shelf`.
- **제외(한국어 유지):** `ValidationError` 메시지와 컴파일 게이트 경고(설계자가
  읽는 것이지 산출에 나가지 않는다), 내부 예외 메시지, GUI 문자열, 사용자 정의
  훅 스크립트, `plugin.json` 값. `description`+`when_to_use` 합류 접속어
  (`Use when …`)는 원래부터 영어라 그대로다.
- **게이트 테스트:** `tests/compiler/test_output_language.py`가 **사용자 값을
  전부 영어로 채운 픽스처**를 컴파일해 산출 전체에 한글 유니코드가 없음을
  단언한다(스킬 4종·에이전트·전체 `compile_project`·LOCAL 빌드·schemas/hooks/
  plugin.json). 픽스처가 영어이므로 남는 한글은 정의상 컴파일러가 만든 것이다 —
  새 자동 단락에 한국어가 스미면 그 자리에서 깨진다. 같은 파일이 **사용자
  한국어 값은 그대로 통과하는지**도 함께 고정한다(영어화가 그것을 삼키면 안 된다).
