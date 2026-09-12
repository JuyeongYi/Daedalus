# 훅 — 라이브러리·규격 드리프트 감시·전역 스코프

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 훅 (HookDef / hook_library)

**규격 정본은 SchemaStore의 `claude-code-settings.json`이다**(2026-09-06 스냅샷) — 공식 문서에는 훅의 전체 형식이 나오지 않는다. `$defs.hookMatcher` / `$defs.hookCommand` / `properties.hooks`를 보라. 그 스키마는 저장소에 **벤더링**되어 있고 대조 테스트가 드리프트를 잡는다 (아래 "스펙 드리프트 감시" 참조).

CC의 구조는 **3단**이다: 이벤트 → 그룹(matcher + 핸들러 목록) → 핸들러. `HookDef` 하나가 **그룹 하나**에 대응하고 `handlers: list[HookHandler]`가 그 안의 핸들러다(WP-HK 이전에는 훅 하나가 커맨드 하나였다).

- **이벤트 31종**(`HookEvent`) — 스키마 `properties.hooks`의 키 전체. matcher를 받지 않는 8종은 `NO_MATCHER_EVENTS`(스키마 description이 "does not support matchers"라고 명시한 것들), 여집합이 `MATCHER_EVENTS`(구 `TOOL_MATCH_EVENTS` 별칭은 RF-1b에서 삭제). 공식 문서에 없는 2종은 `UNDOCUMENTED_EVENTS`.
- **핸들러 5종**(`HookHandler` ABC + `CommandHook`/`PromptHook`/`AgentHook`/`HttpHook`/`McpToolHook`) — 공통 속성은 timeout / `condition`(→`if`, 예약어라 필드명이 다르다) / `status_message`(→`statusMessage`). command는 args·shell(`HookShell`)·`run_async`(→`async`)·`async_rewake`, prompt는 model·`continue_on_block`, http는 headers·`allowed_env_vars`, mcp_tool은 server·tool·`tool_input`(→`input`). `kind`가 CC `type` 값이자 다형성 태그이고, `to_json()`이 CC 스키마 객체를 만든다(빈 값 키 생략 — 결정적). `HOOK_HANDLER_TYPES`/`HOOK_HANDLER_LABELS`가 태그↔클래스↔표시문구의 단일 진실.
- `HookDef.to_json()`은 **matcher를 그 이벤트가 받을 때만** 배출한다 — 무시되는 키를 내보내면 설정한 사람은 걸린 줄 알지만 아무 일도 일어나지 않는다.
- `ComponentConfig.hooks: dict`는 **이름 참조**다 — 키=hook_library의 HookDef.name, 값=오버라이드(빈 dict면 정의 그대로). 선언 기본값은 `{}`가 아니라 `None`. **이 참조는 훅을 켜는 조건이 아니다**(아래 배출 규칙) — 전역 훅을 이 프로젝트로 끌어오는 선언이고, LOCAL 에이전트 프론트매터(WP-LA)의 대상 선정이다.
- `hook_presets.py`의 `BUILTIN_HOOK_PRESETS`는 복사해 출발점으로 쓰는 템플릿이며 `preset_copy`가 **핸들러까지 깊은 복사**한다(얕게 복사하면 한 프로젝트의 수정이 다른 쪽에 샌다). command 외 타입(prompt/agent)의 출발점도 포함한다.
- **`HookDef.enabled: bool = True`(사용자 확정 2026-09-07)** — 라이브러리에
  모아 둔 훅 중 **무엇을 빌드에 넣을지 고르는 스위치**다. 컴포넌트 참조로는
  켜고 끌 수 없고(규격상 그 역할이 아니다), 그렇다고 라이브러리를 무조건
  배출하면 "만들어 두고 아직 안 쓰는 훅"을 둘 자리가 없어진다. 이름 목록을
  프로젝트에 따로 두지 않은 이유는 개명 때 끊어지기 때문이다. 기본 True(만들면
  켜진다), 구버전 파일(키 부재)도 True.
- **컴파일러 — 무엇이 배출되나 (규격 확인 2026-09-07)**: **플러그인 훅은 전역이다**
  (공식 plugins-reference: `hooks/hooks.json`과 plugin.json의 `hooks`는 플러그인이
  **활성화되면 자동 동작**한다 — 컴포넌트가 참조해야 켜지는 것이 아니다). 그래서
  배출 대상은 `emit.hooks.emitted_hooks`가 정한다: **프로젝트 `hook_library`는
  참조 여부와 무관하게 전부**, **전역 훅(`~/.daedalus/hooks/`)은 `config.hooks`로
  참조된 것만**(다른 프로젝트가 쓰라고 둔 재사용 풀이라 명시 참조가 있어야 한다).
  예전에는 참조된 것만 실어 **부착을 잊은 훅이 산출에서 말없이 사라졌다**(사용자
  보고 — 그 전제로 만든 `orphan_hook` 규칙도 함께 퇴역).
  거기에 `enabled=False`인 훅은 빠진다(위 스위치).
  산출은 둘로 나뉜다 — ① 스크립트 파일 `hooks/scripts/<이름>.sh`(command 핸들러가
  있는 훅마다, `compile_hook_scripts`) ② 등록: MARKETPLACE는 `<out>/hooks/hooks.json`,
  LOCAL은 **파일을 만들지 않고** `.claude/settings*.json`의 `hooks` 섹션에 병합
  (`_wire_local_install` → `wire_workspace`). 이벤트 키=HookEvent 선언 순서,
  같은 이벤트 복수 훅=라이브러리 순서, 핸들러 0개인 훅은 배출 안 함.
- **에이전트 프론트매터 훅은 별개 경로다** — LOCAL 빌드에서 에이전트가
  `config.hooks`로 참조한 훅이 그 `.md` 프론트매터로 나간다(WP-LA, 컴파일 정책
  16번). **`enabled`를 보지 않는 것이 의도다**(사용자 확정): 그 스위치는 "전역
  훅으로 켤지"이고 여기는 그 에이전트 안에서만 도는 경로라, 전역으로는 끄고
  특정 에이전트에서만 쓰는 것이 정상이다(`_agent_hook_groups`를 `emitted_hooks`로
  바꾸지 마라). 스크립트 파일은 `hooks_needing_scripts`가 **두 경로의 합집합**
  으로 내므로, 꺼둔 훅을 에이전트가 써도 없는 파일을 가리키지 않는다.
  에이전트 참조는 LOCAL에서만 센다 — 마켓 빌드는 그 프론트매터를 배출조차
  하지 않아 쓰이지 않는 스크립트만 남는다.
- **서브에이전트 훅의 이벤트 제한 (공식 sub-agents 확인 2026-09-07)**: 이벤트
  종류에 제한은 **없다**(전 이벤트 지원). 다만 실용 용도는 `PreToolUse`/
  `PostToolUse`/`Stop`이고, **프론트매터의 `Stop`은 런타임에 `SubagentStop`으로
  자동 변환된다** — 설계자가 `SubagentStop`을 직접 걸면 의미가 겹칠 수 있으니
  `Stop`으로 두는 편이 낫다.
- **스킬에는 훅을 걸 수 없다**(사용자 확정 2026-09-07, 같은 규격 확인:
  SKILL.md 프론트매터 스키마에 hooks 키가 없다). `SKILL_FIELD_MATRIX`에서
  `SkillField.HOOKS`를 **전 종류에서 제거**해 배출·편집 노출을 끊었다
  (`_KIND_ABSENT_FIELDS`의 `_ABSENT_EVERYWHERE`가 계약으로 고정). MCP
  `set_component_hooks`는 스킬을 **거부**하고(에이전트 전용), 이미 저장된
  프로젝트에 남은 스킬 참조는 지우지 않고 `skill_hooks_ignored` 경고로
  짚는다 — 조용히 지우면 "설정한 게 사라졌다"가 되고 그냥 두면 "걸어 뒀는데
  안 걸린다"가 된다. 훅을 켜는 길은 둘뿐이다: 라이브러리 훅의 `enabled`
  (플러그인 전역), 또는 **에이전트** `config.hooks`.
- **직렬화**: 핸들러는 `kind` 태그로 다형성 왕복. v1 파일(`handlers` 키 없이 `command`/`timeout`)은 `_migrate_v1`이 `CommandHook` 하나로 감싼다(경고 없음). 미지 `kind`는 건너뛴다 — 미래 버전 파일을 열어도 죽지 않는다.
- **검증**: `empty_hook_command`는 핸들러 0개 또는 핸들러의 필수 값이 빈 경우다. 무엇이 필수인지는 타입마다 다르므로 `handler.summary()`가 `"("`로 시작하는지로 판정한다 — 타입이 늘어도 규칙이 따라간다. `hook_matcher_without_tool_event`는 이름만 예전 그대로이고 판정은 `MATCHER_EVENTS` 기준이다.
- **라이프사이클 피커 (A10)**: 이벤트 콤보 옆 "라이프사이클에서 선택…" 버튼이
  `widgets/lifecycle_picker.HookLifecycleDialog`를 연다 — CC 훅 라이프사이클
  다이어그램을 **QGraphicsScene으로 재구현**한 것이다(SVG를 렌더하지 않는다:
  박스마다 hover·클릭·툴팁·현재 선택 강조를 붙여야 하고, 원본
  `hooks-lifecycle-dark.svg`의 좌표·색은 `_LAYOUT`/팔레트 상수로 옮겼다).
  - **`_LAYOUT` 키는 `HookEvent` 멤버**(값 문자열이 아니다 — 개명이 조용히
    빠져나간다)이고, 키 집합이 `set(HookEvent)`와 **정확히 일치**해야 한다.
    `tests/view/widgets/test_lifecycle_picker.py`가 그것을 고정하므로 이벤트가
    늘거나 줄면 테스트가 깨져 다이어그램 갱신을 강제한다(드리프트 방지의 핵심).
    박스 겹침·캔버스 이탈·라벨=이벤트 값도 함께 고정한다.
  - 원본에서 **한 박스에 묶여 있던 이벤트들**(`PostToolUse / PostToolUseFailure`,
    `SubagentStart / SubagentStop`, `Stop / StopFailure`, 환경 반응 3종)은
    이벤트별로 쪼갰다 — footprint와 색은 그대로 두되 클릭 대상이 하나로 정해져야
    한다. `[tool executes]`와 그룹 라벨(EACH TURN / AGENTIC LOOP)은 **비선택 장식**이다.
  - 툴팁에 **matcher 지원 여부**(`NO_MATCHER_EVENTS` 8종은 "matcher 없음")와
    미문서화 여부(`UNDOCUMENTED_EVENTS` 2종)를 병기한다 — 받지 않는 이벤트에
    matcher를 넣으면 설정한 사람은 걸린 줄 알지만 CC는 무시한다.
  - 다이얼로그는 **재사용 위젯**이다: 훅 패널 버튼은 열고 결과를 콤보에 반영하는
    호출부일 뿐이고(모델 쓰기는 기존 `currentIndexChanged` → `_save_head` 경로),
    이벤트를 고르는 다른 표면이 생기면 같은 것을 쓴다.
- **UI**: `editors/hook_panel.HookLibraryPanel` — **상주 탭(인덱스 2)**. 모달 다이얼로그(`hook_editor.HookLibraryDialog`)는 3단 구조를 담을 수 없어 제거됐다(도구 메뉴 항목도 함께 — 탭이 늘 보이므로 지름길이 중복이다). 좌: 훅 목록(핸들러 없으면 ⚠). 우: 이벤트 콤보(matcher 미지원/미문서화를 문구에 표시) + matcher(받지 않는 이벤트면 잠금 + 이유 표시) + 핸들러 목록·폼(`_HandlerForm` — 타입이 바뀌면 통째로 다시 만든다). **"서브에이전트 프론트매터로 복사" / "hooks.json으로 복사"** 버튼이 이 프로젝트 밖의 파일에 붙여넣을 텍스트를 클립보드에 넣는다. `widgets/tag_input`의 `set_hook_name_provider`로 컴포넌트의 HOOKS TagInput이 훅 이름을 후보로 표시한다(A1 이후 **전역 훅 이름도 포함** — `app.set_project`가 `self.resolved_hooks()`를 등록). 전역 훅 표시는 아래 "전역 훅 2단 스코프 (A1)" 참조.
- **MCP**: `create_hook`/`update_hook`은 `handlers=[{...}]`로 CC 스키마 그대로 받는다(`command=` 인자는 커맨드 훅 하나를 만드는 지름길). 그 타입에 없는 속성은 **거부**한다 — 조용히 무시되면 왜 안 먹는지 알 수 없다. `list_hook_events`가 이벤트 31종과 matcher 지원 여부를, `hook_frontmatter_preview`가 서브에이전트 프론트매터 YAML을 돌려준다.

## 스펙 드리프트 감시 — 벤더링된 CC 규격 스냅샷 (A4)

`HookEvent` 31종·`NO_MATCHER_EVENTS`·`UNDOCUMENTED_EVENTS`·핸들러 `to_json` 키는
전부 외부 규격을 **손으로 옮겨 적은 것**이다. 상류가 바뀌어도 아무 신호가 나지 않는
것이 이 프로젝트의 최대 유지 부채였다 — **틀린 emit은 도구가 없는 것보다 나쁘다.
조용히 실패하기 때문이다**(설정한 사람은 훅이 걸린 줄 알지만, CC는 그 키를 무시하거나
`additionalProperties: false`에 걸려 항목을 통째로 거부한다).

- **스냅샷:** `tests/fixtures/specs/claude-code-settings.json` — SchemaStore
  <https://json.schemastore.org/claude-code-settings.json>를 **가공 없이 원본 바이트
  그대로** 받아 둔 것(2026-09-06, 230,217 B). 출처·날짜·해시·갱신 절차는 같은 폴더의
  `README.md`가 보유한다.
- **대조 테스트:** `tests/model/plugin/test_spec_drift.py` — ① `HookEvent` = 스냅샷
  `properties.hooks` 키(집합 **+ 선언 순서** — `compile_hooks_json`이 이벤트 키를 그
  순서로 배출한다) ② `NO_MATCHER_EVENTS` = description이 "does not support matchers"/
  "Matchers are ignored"/"no matchers"라 명시한 집합 ③ 핸들러 `to_json` 키 ⊆ 해당
  `$defs.hookCommand` 변종의 속성 집합(+ 필수 키 포함) ④ `UNDOCUMENTED_EVENTS`
  = description이 "UNDOCUMENTED"로 시작하는 집합.
  ③은 **모든 선택 필드를 채운 핸들러**로 검사한다 — 빈 값 키는 `to_json`이 생략하므로,
  안 채우면 `{"type": …}` 하나만 보고 통과한다.
- **테스트는 네트워크에 나가지 않는다.** 읽는 것은 벤더링된 스냅샷뿐이라 오프라인
  그린이 유지되고, 상류가 바뀌었다고 CI가 저절로 빨개지지도 않는다. **빨개지는 시점은
  사람이 스냅샷을 갱신했을 때**이고 그게 요점이다 — 갱신이 곧 리뷰 지점이 된다.
- **갱신:** `python scripts/refresh_cc_schema.py`(상류를 받아 **구조 diff만** 출력, 파일
  불변) → `--write`(원본 바이트로 덮어쓰기) → 대조 테스트 실행. 스크립트는 재직렬화하지
  않는다(우리 키 순서·들여쓰기로 다시 쓰면 상류와의 `git diff`가 무의미해진다).
  스크립트의 `NO_MATCHER_PHRASES`는 테스트의 같은 목록과 일치해야 한다 — 스크립트가
  보여 주는 diff와 테스트 실패가 같은 판정에서 나와야 한다.
- 실패가 나오면 그것이 진짜 드리프트다. **테스트를 느슨하게 고치지 말고**
  `hook.py`(필요하면 `view/widgets/lifecycle_picker.py`의 `_LAYOUT`, 컴파일러의 훅
  배출)를 새 규격에 맞춘다.

## 전역 훅 2단 스코프 (A1)

훅은 프로젝트를 넘어 재사용된다 — 같은 "커밋 전 포맷 검사"를 프로젝트마다 다시
만드는 것은 카탈로그(도구/MCP 후보) 이전과 똑같은 상황이었고, 해법도 같다:
**전역 `~/.daedalus/hooks/*.json` + 프로젝트 `hook_library`, 동명이면 프로젝트 우선.**

- **로더는 `model/plugin/hook_store.py` 하나뿐이다.** 파일 1개 = 훅 1개이고
  **파일명 stem이 이름의 단일 진실**(파일 안의 `name`은 무시 — 진실이 둘이면 파일을
  복사해 이름을 바꿨을 때 어느 쪽이 이겼는지 알 수 없다). 내용 형상은 `serialize`의
  훅 직렬화와 같아서(`kind` 태그 handlers) `_deser_hook`을 그대로 재사용하고,
  `hook_to_json`이 역방향(`name`/`id` 제외)이다. 깨진 파일은 stderr 경고 후 스킵
  (카탈로그 관례 — 파일 하나 때문에 앱이 안 뜨면 안 된다).
- **`resolve_hooks(project)`가 병합의 단일 진실**(전역 ← 프로젝트 순 `dict.update`).
  전역이 없으면 결과가 `hook_library` 그대로라 기존 산출이 바이트 단위로 불변이다.
- **검증기와 컴파일러는 파일시스템을 읽지 않는다 — 호출자가 주입한다.** 이것이
  이 설계의 핵심 경계다: 읽어 버리면 "이 프로젝트의 검증/컴파일 결과"가 **그것을
  실행한 사람의 홈 디렉토리에 따라 달라지는 것**이 코드에서 보이지 않게 된다.
  - 컴파일: `compile_project(..., resolved_hooks=)` → `compile_hooks_json` /
    `compile_hook_scripts` / `compile_agent`(LOCAL 프론트매터) / LOCAL settings 병합이
    전부 `emit.hooks.hook_library(project, resolved_hooks)`를 거친다. 생략하면
    `project.hook_library`만(하위 호환 게이트).
  - 검증: `Validator.validate_project(project, known_hook_names=)` — 주어지면 그것이
    `dangling_hook_ref`의 유효 집합이다. 생략하면 종전대로.
  - 주입 지점은 **`MainWindow.resolved_hooks()` 하나**다(F7·Ctrl+B·MCP
    `validate_project`/`compile_preview`/`set_component_hooks`가 전부 여기를 부른다).
    캐시하지 않는다 — 전역 폴더에 파일을 떨어뜨리고 곧바로 F7을 누르면 반영되는
    것이 기대 동작이고, 파일 몇 개짜리 glob이라 비용이 없다.
- **UI:** `HookLibraryPanel` 목록에 프로젝트 훅이 앞, 전역 훅이 뒤(🌐 + 회색,
  읽기 전용)로 붙는다. **동명 프로젝트 훅에 가려진 전역은 목록에서 뺀다** — 둘 다
  보이면 어느 쪽이 실제로 쓰이는지 화면만 봐서는 알 수 없다. 행 → 훅 매핑은
  `_entries: list[tuple[HookDef, bool]]`이고, 삭제는 인덱스가 아니라 **identity**로
  찾는다(목록에 전역이 섞여 있다). 전역 편집은 **"프로젝트로 복사"**(이름 유지 +
  `preset_copy` 깊은 복사)로 사본을 만든 뒤 그 사본을 고친다 — 전역 파일을 앱에서
  직접 고치게 하면 다른 프로젝트가 조용히 함께 바뀌고 어디서 고쳤는지 알 길이 없다.
  이름을 유지하는 이유는 병합 규칙이 그것을 요구하기 때문이다(이름을 바꾸면 참조가
  전역을 계속 가리켜 고친 사본이 아무 데도 쓰이지 않는다). 도구 메뉴 → **"전역 훅
  폴더 열기..."**가 폴더를 만들고 탐색기로 연다(전역 파일 편집 UI는 범위 밖).
- **테스트 격리:** 루트 `tests/conftest.py`의 autouse 픽스처가 `global_hooks_dir`를
  tmp 경로로 바꾼다 — 실제 홈을 읽으면 개발자가 거기 둔 훅에 따라 결과가 달라져
  그 사람의 머신에서만 통과하거나 실패하는 테스트가 된다.
