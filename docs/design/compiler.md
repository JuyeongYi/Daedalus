# 컴파일러 (compiler/) — 산출 구조와 컴파일 정책

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

`compile_project(project, out_dir=None, files_dir=None, resolved_hooks=None, dry_run=False) → CompileResult`. 순수 stdlib(Qt 무관, import 순수성 테스트로 고정).
`resolved_hooks`(A1)는 호출자가 주입하는 이름→HookDef 사전 — 컴파일러는 파일시스템에서 훅을 읽지 않는다("전역 훅 2단 스코프" 섹션 참조).
`dry_run`(G3)은 파일을 하나도 쓰지 않는 예행 — 컴파일 정책 18번 참조(`out_dir`는 이때만 생략 가능).

**출력 구조 (CC 플러그인 규약, `project.build_target == MARKETPLACE` — 기본):**
- `<out>/.claude-plugin/plugin.json` — 플러그인 매니페스트 (MARKETPLACE에서 항상 생성 — 이게 없으면 산출 디렉토리를 CC 플러그인으로 설치할 수 없다)
- `<out>/skills/<skill-name>/SKILL.md` — 스킬 4종 전부 (Declarative/Reference도 SKILL.md)
- `<out>/agents/<agent-name>.md` — 에이전트

**`build_target == LOCAL`(WP-TG/WP-MW)일 때 — 컴파일이 곧 설치:** out_dir는 스테이징이 아니라 대상 **작업 폴더**다. `<out>/.claude/skills/`·`<out>/.claude/agents/`(CC가 실제로 읽는 위치), `<out>/files/`·`<out>/schemas/`·`<out>/hooks/scripts/`(본문의 `${CLAUDE_PROJECT_DIR}/…` 참조 대상), `<out>/.mcp.json`·`<out>/.claude/settings.json` 또는 `settings.local.json`(컴파일 시 선택, 기본 `settings.json` — 생성/병합), `<out>/.claude/rules/<이름>.md`와 `<out>/.claude/CLAUDE.md`의 플러그인 구역(WP-WD). `plugin.json`·`hooks/hooks.json`·설치 스크립트는 만들지 않는다. 상세는 컴파일 정책 15번 항목 참조.

**컴파일 정책 (확정):**
1. **프론트매터**: 해당 kind 매트릭스에서 `emit==FRONTMATTER`인 필드만. 키는 `frontmatter_key`(kebab-case).
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

6-b. **다음 단계 (project.graph 기반)**: `compile_skill(skill, project=...)`이 `project.graph`에서 그 스킬 placement(skill_ref identity 일치)의 outgoing 전이를 모아 SKILL.md 본문 끝에 **"## 다음 단계"** 단락을 배출한다(버그 2 — 인보크/전이 문구 누락 해소). 형식: 스킬 타깃은 `- [<조건>] → \`<skill>\` 스킬을 인보크하라`, 에이전트 타깃은 `에이전트 \`X\`에게 위임하라` + **그 에이전트 placement의 outgoing을 한 단계 인라인**("위임 완료 후: [조건] → \`C\` 스킬을 인보크하라" — 에이전트는 별도 컨텍스트라 자기 .md에 호출자 지침을 담을 수 없으므로 호출자 스킬 쪽에 후속 지시를 둔다). 조건은 `_transition_condition`(트리거+가드) 재사용, 무가드·무트리거 전이는 "무조건". outgoing 0개면 단락 생략. **에이전트 .md에는 다음 단계 단락 없음**(스킬 + project 인수 있을 때만). EntryPoint outgoing(시작 스킬)은 v1에서 스킬별 단락에 영향 없음.
7. **에이전트**: `emit==FRONTMATTER`만 프론트매터, INVOCATION(max_turns/background/isolation)은 "호출 파라미터" 본문 단락,
   SETTINGS(hooks/mcp_servers)는 **MARKETPLACE 빌드에서만** "요구 환경" 언급으로 나간다. `config.tools`의 `mcp__<server>__` 접두에서
   추출한 서버 이름(WP-TM, 11번 항목과 동일 규칙)도 `mcp_servers` 선언과 합쳐(중복 제거·이름순) 같은 "MCP 서버 연결" 줄에 담는다 — 별도 단락을 추가하지 않는다.
   **LOCAL 빌드는 이 둘을 프론트매터로 실제 배출한다(WP-LA, 16번 항목)** — 그때는 "요구 환경" 단락을 내지 않는다(같은 사실을 두 번 말하는 데다 "설정 파일을 생성하지 않음" 문구가 거짓이 된다).
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
10. **블랙보드 사용 지침 단락**: 프로젝트 최상위 블랙보드에 `class_definitions`가 1개 이상이면, `ProceduralSkill`의 tool_shelf 단락 뒤·"다음 단계" 단락 앞, 그리고 에이전트 `.md` 본문 마지막에 `_blackboard_section(project, component)`이 "## Shared State (Blackboard)" 단락(`state/<플러그인>/<ClassName>.json` 파일 목록 + 읽기-수정-쓰기 규칙)을 배출한다. 정의가 0개면 단락 생략.
    **접근 선언 기반 구체화(WP-BB):** component(스킬/에이전트)가 주어지고 그 자체 FSM(재귀) + 프로젝트 그래프
    placement의 reads/writes 합집합(`_component_access_union`)이 비어있지 않으면, "이 스킬/에이전트가 읽는
    것/쓰는 것" 문구를 추가하고 파일 목록을 관련 클래스만으로 좁힌다. 합집합이 비면(또는 component 미지정)
    기존 전 클래스 일반 안내 그대로 — 하위 호환, 접근 선언 0개 프로젝트의 산출 문자열은 불변이다.
    **CLI 우선 지시 (WP-BB2):** 단락이 배출될 때(정의 1개 이상) 기존 3줄 규칙(읽기-수정-쓰기/없으면
    생성/required) 바로 앞에 `command -v daedalus-bb`로 CLI 존재를 확인해 있으면 파일을 직접 만지지
    말고 CLI(`daedalus-bb read`/`write`/`validate` — write는 `--set 필드=값`, 컬렉션은
    `--append`/`--remove`)로 읽고 쓰라는 지시가 합류한다(CLI가 없으면 기존 3줄 규칙대로 직접 편집).
    - **스키마 경로를 반드시 명시한다.** `--schemas`는 **필수**이고(WP-NS/D10) 상태 폴더도 그것에서
      유도되므로, 지시문이 `--schemas ${ROOT}/schemas/<플러그인>.json`을
      함께 적는다 — 타깃 중립 토큰(WP-RT)이라 MARKETPLACE→`${CLAUDE_PLUGIN_ROOT}` /
      LOCAL→`${CLAUDE_PROJECT_DIR}`로 확장되고, `schemas/<플러그인>.json`은 양쪽 타깃 모두 그 루트
      밑에 산출되므로 토큰 하나가 둘 다 맞는다(빌드 타깃 분기 불필요).
    - **설치 명령은 지시하지 않는다.** `daedalus`는 PyPI 배포 패키지가 아니므로
      `uv tool install daedalus`는 동명의 무관한 패키지를 깔거나 실패한다 — 어느 쪽이든
      `daedalus-bb`는 생기지 않는다. 지시문은 "Daedalus 배포에 함께 들어 있다, 임의로 설치하지
      마라"까지만 말한다.
    - **`command -v`는 POSIX 셸 전제다**(컴파일 정책 12번 SessionStart 합성 훅의 `cat`/`||`과 같은
      전제). 비POSIX 셸에서는 판정이 실패하지만 **fail-open** — 지시문이 "판정할 수 없으면 CLI가
      없는 것으로 보고 아래 규칙대로 직접 편집하라"고 못 박아, 최악의 결과가 기존(직접 편집)
      동작이다.
    명령·옵션 이름은 `tests/compiler/test_blackboard_section.py`가 `daedalus/cli/blackboard.py`의
    실제 파서와 문자열 일치로 고정한다(cli는 model/emit을 임포트할 수 없어 상수 공유 대신 테스트로
    드리프트를 막는다). `_blackboard_section`은 return이 **둘**(접근 선언 union 분기 / 일반 분기)이라
    두 분기 모두에서 CLI 지시를 고정하는 테스트가 있다 — 한쪽만 검사하면 다른 쪽이 통째로 비어도
    초록이다. 정의 0개 프로젝트는 단락 자체가 없으므로 산출 완전 불변.
11. **요구 환경 자동 언급 (WP-TM)**: `_mcp_servers_from_tools(tools)`가 도구 문자열 목록에서 `mcp__<server>__` 접두의 서버 이름 집합을 추출한다(이름순 정렬 — 결정적). 스킬은 `skill.config.allowed_tools`를 스캔해 서버가 있으면(local 여부·project 인수 여부와 무관) "다음 단계" 단락 앞에 신규 "## 요구 환경" 단락(`_mcp_requirement_section_skill`)을 배출한다(없으면 단락 생략). 에이전트는 `config.tools`에서 추출한 서버를 기존 SETTINGS "요구 환경" 단락(`_settings_note_agent`, 7번 항목)의 `mcp_servers` 선언과 합쳐 하나의 "MCP 서버 연결" 줄로 병합한다(중복 없음).
12. **작업 재개 (WP-RS)** — 저장 단위는 **플러그인 FSM(프로젝트 그래프 배치)의 위치**다(스킬 내부 FSM 상태는 다루지 않음 — 사용자 확정 설계). 규약 파일 `state/__progress__.json` — **최상위 키가 플러그인 이름**이고 그 아래에 항목(`current`/`completed`/`note`/`prev`/`updated`)이 온다(WP-NS/D13. `prev`는 WP-IC에서 추가된 직전 출처 스킬 이름). 파일은 `state/` 루트에 **하나로 남는다** — 블랙보드가 `state/<플러그인>/`로 갈라지는 것과 다른 이유는, 워크스페이스 전체를 한눈에 보는 것이 이 파일의 목적이고 스키마 밖 규약 파일이라 클래스 순회 대상도 아니기 때문이다. **갱신은 `daedalus-bb progress` 서브커맨드가 전담한다** — 공유 파일의 병합을 산문으로 시키면 모델이 한 번만 놓쳐도 남의 진행 기록이 통째로 사라진다(CLI를 못 쓰는 환경용 폴백 지시는 '자기 키만 고치라'까지 못 박는다).
    - **재개 프리앰블**: 프로젝트 그래프에 배치된 `ProceduralSkill`/`DeclarativeSkill`(미배치·에이전트 .md 제외)에 한해, `_resume_preamble_section`이 프론트매터 직후·본문 앞에 "## 작업 재개" 단락(현재 스킬 이름 삽입 + 파일 없을 때 생성 규칙, JSON 예시에 `"prev": ""` 포함)을 배출한다. Declarative 포함 이유: 배치되면 "다음 단계"를 받으므로 갱신 규칙이 빠지면 진행 사슬이 끊긴다. placement 판정은 "다음 단계"(6-b번 항목)와 동일한 `_graph_placements`(skill_ref identity) 로직을 공유한다.
    - **다음 단계 갱신 규칙**: 배치 스킬의 "## Next Steps" 단락 끝에 `_progress_update_note(project)`(완료 시 `completed`/`current`/`note`/`updated` 갱신 + `prev`에 자신(이 스킬 이름)을 기록[WP-IC] + 에이전트 위임 전이는 2단 갱신: 위임 직전 에이전트 이름, 완료 후 후속 스킬로 — 이때도 `prev`는 위임한 스킬 이름)이 합류한다.
    - **터미널 배치**: **placement의 실제 outgoing 전이가 0개**인 배치는 "다음 단계" 대신 `_progress_terminal_section`이 "## 작업 완료" 단락(자신을 `completed`에 추가 + `current`를 `"done"`으로)을 배출한다. 판정은 "다음 단계 문구 생성 실패"가 아니다 — outgoing 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안 나와도 터미널이 아니며 이때는 아무 단락도 배출하지 않는다.
    - **TransferSkill**: **project에 placement가 1개 이상**일 때 본문 끝에 "## Progress Record" 헤딩 + `_transfer_progress_note(project)`(전이 중 note 기록 지시)를 배출한다(진행 파일이 존재하지 않는 프로젝트에서의 고아 지시 방지).
    - **SessionStart 훅 합성**: `PluginProject.emit_progress_hook: bool = True`(직렬화 왕복, 구버전 키 부재 시 기본 True)이고 프로젝트 그래프에 placement가 1개 이상이면, `compile_hooks_json`이 `hook_library`를 오염시키지 않고 컴파일 시점에 SessionStart 이벤트에 진행 상태 주입 커맨드(`cat state/__progress__.json 2>/dev/null || true`)를 합성해 합류시킨다(사용자 정의 SessionStart 훅 뒤에 이어붙어 공존). `emit_progress_hook=False`이거나 placement가 0개면 합성 훅 미배출. 토글은 프로젝트 속성 다이얼로그의 "세션 시작 시 진행 상태 자동 주입 (SessionStart 훅)" 체크박스. 합성 커맨드는 POSIX 셸 전제(`cat`/`||`) — 비POSIX 환경에서는 토글로 끄는 것이 대응책(훅 프리셋과 동일한 전제).
13. **진입 맥락 + 호출 계약 (WP-IC/WP-IP/WP-CT)**: 배치된 전역 `ProceduralSkill`/`DeclarativeSkill`에서 incoming 전이가 1개 이상이면, `_entry_context_section`이 "## 작업 재개" 프리앰블 뒤·본문 앞에 "## 진입 맥락" 단락을 배출한다("`state/__progress__.json`의 `prev`를 확인하고 아래에서 해당 출처 항목을 따르라" 도입 + 출처 이름순 항목["- `<출처>`에서 [조건]로 진입" + 출처의 transfer_on description 병기, 전이 스킬(TransferSkill) 지침 수행 문구·에이전트 출처의 "위임 완료 후" 문구 합류] — 포트 그룹 헤딩 없음, 그래프에서만 유도(WP-IP)). incoming 0개 배치·미배치·로컬은 산출 변화 없음. `compile_agent`의 "## 호출 계약"은 `_call_contract_section`이 프로젝트 그래프의 incoming 호출 전이에서 유도한다(WP-CT — 수동 카드 없음).
14. **files/ 복사 + dangling_file_ref 경고 (WP-FR)**: `files_dir`가 실존 디렉토리면(게이트 통과 시에만) `_copy_files_tree`가 `<out>/files/`로 정렬 순회 복사한다(결정적, 심볼릭 링크 미추종 — 디렉토리는 재귀 안 함·파일은 복사 안 함). 기존 `<out>/files/`는 복사 전 삭제(out 전체가 아니라 files/만). 복사된 파일 경로는 `CompileResult.copied_files`에 담긴다. `files_dir`가 주어지면(실존 여부 무관) `_scan_dangling_file_refs`가 스킬·에이전트 body에서 `${CLAUDE_PLUGIN_ROOT}/files/<경로>` 참조 토큰을 스캔해 files_dir에 실존하지 않으면 `dangling_file_ref` 경고를 `CompileResult.warnings`에 추가한다(게이트 차단 아님). `files_dir` 생략(None) 시 복사·스캔 모두 생략되어 기존 산출 파일/문자열이 완전히 불변(하위 호환).
15. **빌드 타깃 — LOCAL 빌드 (WP-TG)**: `project.build_target`(기본 `MARKETPLACE`)에 따라 `_plan_outputs`의 산출 계획이 갈린다.
    - **MARKETPLACE**(기본): `plugin.json` + `skills/`·`agents/` 산출. **"현행과 바이트 동일"이라는 하위 호환 게이트는 WP-NS에서 폐기됐다** — `state/`에는 `${ROOT}` 토큰이 붙지 않아 작업 폴더 CWD 기준이라, 마켓플레이스 플러그인이 한쪽에만 끼어도 `state/<Class>.json`과 고정 파일명 `state/__progress__.json`이 충돌한다. 배포 전이라 지킬 대상이 없어 네임스페이스를 양쪽 타깃에 적용했다.
    - **LOCAL — 컴파일이 곧 설치 (WP-MW)**: out_dir가 대상 작업 폴더다. 스킬/에이전트는 `.claude/skills/`·`.claude/agents/`(CC가 실제로 읽는 위치)로 나가고, `plugin.json`과 이전의 `INSTALL.md`/`install.ps1`/`install.sh` 동봉은 폐기됐다(별도 설치 단계가 없다). `hooks/hooks.json` 파일도 만들지 않는다 — 훅은 설정 파일(`.claude/settings.json` 기본 / `settings.local.json` — Ctrl+B 때 고른다, `compile_project(settings_filename=)`)의 `hooks` 섹션에 병합된다(훅 스크립트 파일은 양쪽 타깃 모두 `hooks/scripts/`로 — LOCAL 커맨드가 `${CLAUDE_PROJECT_DIR}/hooks/scripts/…`를 가리킨다). MCP 배선: `referenced_mcp_servers(project)`(스킬 allowed_tools ∪ 에이전트 tools/mcp_servers, 이름순) ∩ `project.mcp_server_defs` 정의를 `<out>/.mcp.json`의 `mcpServers`에 병합하고 그 이름을 같은 설정 파일의 `enabledMcpjsonServers`에 올린다. 정의 조회는 `project.mcp_server_defs` 우선 + `compile_project(..., extra_server_defs=)`(호출 환경 주입 — 앱이 `_known_server_defs()`로 자기 자신의 daedalus 서버를 넣는다. 서버 미기동이면 기본 포트) 폴백. 참조되지만 정의 없는 서버는 `missing_mcp_server_def` 경고, 깨진 기존 JSON은 건드리지 않고 `unmergeable_settings_json` 경고(수기 설정 보호). 병합은 추가/갱신만·동일 훅 그룹 중복 삽입 없음 — **재컴파일 멱등**. 병합 구현은 `compiler/wiring.py`의 `wire_workspace`가 단일 진실("Claude Code 실행" 메뉴와 공유). files/ 복사는 LOCAL에서 기존 `<out>/files/`를 **삭제하지 않고** 덮어쓰기만 한다(`_copy_files_tree(clear_first=False)` — 사용자 작업 폴더의 파일 삭제 위험 > 스테일 잔존). `${ROOT}` 확장·이름 규약 게이트·`schemas/<플러그인>.json` 산출 조건은 기존 그대로.

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
      선언 ∪ `config.tools`의 `mcp__<server>__` 추출(이름순) — "요구 환경" 단락과 같은 합집합 규칙이라 본문과
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
    - **임계 `DEFAULT_FILE_TOKEN_THRESHOLD = 5000`은 파일당**이고 `CONTEXT_KINDS`(skill/agent/
      workspace_rule/claude_md)에만 적용한다 — `schemas.json`/`hooks.json`/`plugin.json`은 CC가 설정으로
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
    - **LOCAL 병합류는 읽되 절대 쓰지 않는다.** `wire_workspace(..., dry_run=True)`와
      `_merge_claude_md_region(..., dry_run=True)`는 기존 파일을 읽어 병합을 메모리에서
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
    - `_copy_files_tree`는 dry-run에서도 **같은 순회 코드**로 목록을 만든다(열거를 따로
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

20. **fork 스킬 (2026-09-13, `emit/fork.py`)**: CC는 fork 스킬 본문을 `agent` 서브에이전트의 작업 지시로
    쓴다(모델·실측은 `plugin-model.md` "fork 스킬").
    - 프론트매터에 `context: fork`(매트릭스 FIXED)와 `agent:`를 낸다. 기본값 `general-purpose`도 **명시
      배출**한다(결정적·읽는 사람에게 분명). 프로젝트 에이전트는 MARKETPLACE `플러그인:이름` / LOCAL `이름`
      (`resolve_fork_agent_name`), 내장·외부는 저장된 문자열 그대로다(정확 일치).
    - 배치된 fork는 `background: false` — 기본은 백그라운드라 부른 쪽이 보고를 기다리지 않고, 그러면 보고로
      분기를 고를 수 없다.
    - **서브에이전트는 다음 단계를 시작하지도, 진행 기록을 쓰지도 않는다** — fork 에이전트가 `Explore`/`Plan`이면 상태 파일
      쓰기가 어색하고, 메인에는 SKILL.md가 보이지 않는다. 대신 **보고가 지시가 된다**: 배치된 fork는
      "## Next Steps"/진행 갱신 규칙/"## Finishing Up" 대신 **"## Report"**(`fork_report_section`)를 낸다 —
      갈래 목록(Next Steps와 같은 줄) + 보고 첫 줄 `EXIT: <branch> / NEXT: /<skill>` + 끝에 메인이 실행할
      `daedalus-bb … progress set …` 명령. 터미널 배치면 `EXIT: done / NEXT: (end)` + `--current done`.
    - "## Resuming Work"는 내지 않는다(서브에이전트는 사용자에게 되묻거나 진행 파일을 쓸 수 없다 — 재개 판단은
      부르는 메인 몫). "## Entry Context"·블랙보드 단락은 그대로다. 미배치 fork는 `background`·Report가 없다.
    - fork 에이전트로 쓰이는 프로젝트 에이전트 `.md`의 "## Invocation Contract"에 `- Execution base of fork skill \`X\` …`
      줄이 유도된다(`fork_skills_using`) — 캔버스에 선이 없으니 여기서 말하지 않으면 그 쓰임을 모른다.
      캔버스에 놓이지 않고 fork 에이전트로만 쓰이는 에이전트는 "## Exits"를 내지 않는다 — 분기할 그래프가 없고,
      보고 첫 줄은 fork 스킬의 `EXIT/NEXT` 양식이 정한다(두 지시가 부딪히면 `EXIT: done`으로 잘못 적는다).

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
  `## Invocation Parameters` / `## Progress Record` / `## Finishing Up` / `## Report` /
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
