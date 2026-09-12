# 스킬 랩핑 (WP-WR) — 외부 플러그인 스킬 재사용

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 스킬 랩핑 (WP-WR) — 절차 재사용

다른 플러그인의 스킬을 워크플로 단계로 감싼다(2026-09-06 사용자 발안). 이 문서가
확정 결정의 정본이다(초기 계획 문서는 설계가 여러 번 재확정돼 폐기, 2026-09-12).

- **런타임 참조(D1)**: 산출 본문 = 그래프 유도 단락 + 소스 스킬 지시.
  소스는 자기 플러그인에서 실행돼 경로 변수·프론트매터가 소스 기준 — 본문
  복사안의 변수 오동작이 원천 소멸.
- **외부 스킬은 서브에이전트에서만 쓴다**(사용자 확정 2026-09-12 — 실체
  `compiler/emit/wrapped.py`): 메인 컨텍스트에서 직접 인보크하면 우리 워크플로를
  모르는 그 스킬의 지시가 워크플로 한가운데로 샌다. state 용도 산출은 **둘**이다
  — `SKILL.md`(워크플로 단계 그대로, 절차 단락 = "에이전트 `<랩퍼>`에게 위임하라,
  `/플러그인:스킬`을 직접 인보크하지 마라") + `agents/<랩퍼>.md` 실행 서브에이전트
  (`skills: [플러그인:스킬]` 주입 + "주입 안 됐으면 Skill 도구로 인보크" 폴백 +
  "진행 기록·다른 단계 금지" + `## Exits`(transfer_on)). LOCAL은 `.claude/` 밑.
  에이전트 이름 = 랩퍼 이름(스킬·에이전트가 이미 한 이름 공간이라 충돌 불가 —
  접미사를 붙이면 사용자 에이전트와 부딪칠 새 경우가 생긴다). **model/effort는
  실행 에이전트로 옮긴다**(SKILL.md 프론트매터에서 빠진다 — 일하는 컨텍스트가
  거기다). 산출 판정의 단일 진실은 `needs_runner_agent`(state 용도·활성·source
  형식 일치) — 산출 계획(`kind="wrapped_runner"`)과 절차 단락이 공유한다.
  **`플러그인:스킬` 해석은 실측했다**(CC 2.1.268 바이너리, 공식 문서에는 없음):
  에이전트 `skills` 각 이름을 ① 정확한 명령 이름 → ② 에이전트의 플러그인 접두 +
  이름 → ③ `:이름` 접미 일치 순으로 찾는다. 못 찾거나
  `disable-model-invocation: true`인 스킬은 디버그 로그 경고만 남기고 건너뛴다.
- **프론트매터는 승계하지 않는다(D3)**: 랩퍼의 프론트매터는 백지에서 시작하는 우리
  소유다 — 소스 값 자동 승계 없음. 런타임 참조라 각 스킬이 자기 프론트매터로 동작한다.
- **source 규격**: `플러그인[@마켓]:스킬`(`parse_wrapped_source`). 프론트매터
  키가 아니라 본문 지시로 배출(SkillField.SOURCE.frontmatter_key == None).
- **의존성 배선 — 단일 진실은 사용 선언이다**(사용자 확정 2026-09-06):
  `PluginProject.external_plugins: list[str]`("이름[@마켓]", 직렬화 왕복 —
  사용 선언은 **프로젝트 단위** 저장)에서 MARKETPLACE는 plugin.json
  `dependencies`(스키마 확인 — bare name은 자기 마켓 해소, 의존 대상 자동
  활성화), LOCAL은 settings `enabledPlugins` `{"plugin@마켓": true}` 컴파일
  합성(WP-WS 베이크 합류, 모델 불변, `emit.manifest.external_plugin_ids`가
  단일 진실). **랩핑 스킬 source는 배선에 쓰이지 않는다** — 선언만으로 배선이
  나가고(플러그인이 활성화되면 스킬은 CC가 네이티브 로드 — WrappedSkill은
  워크플로 단계로 놓을 때만 필요), 어긋남은 경고 2종이 짚는다:
  `unused_external_plugin`(선언·미참조 — 의도적 활성화면 무시),
  `undeclared_external_plugin`(랩핑 소스가 미선언 플러그인 참조 — 배선이 안
  나가 런타임에 스킬을 못 찾는다). bare 선언은 enabledPlugins 불가라
  `external_plugin_no_marketplace` 경고(컴파일러 emit — out_dir 없는
  dry-run에서도 나온다, 폴더 무관 판정).
- **재사용은 랩퍼 복수로**(사용자 확정): 같은 source를 여러 랩퍼가 감싸는 것이
  정상이고, 랩퍼 자신은 단일 배치(no_duplicate_skill_ref — 레퍼런스형 복수
  배치는 "배치=FSM 위치" 의미론을 깨서 비채택).
- **용도 고정 — state vs reference**(사용자 확정 2026-09-07):
  `WrappedSkillConfig.usage` ""(미정)/"state"/"reference" — **최초 배치가
  고정**하고 한 스킬 두 용도는 금지다. state=워크플로 단계(단일 배치·SKILL.md
  산출, 현행). reference=**참조 노드 복수 배치 + 산출 파일 없음** —
  `_plan_outputs`가 SKILL.md를 내지 않고, 링크된 **스킬** 산출에
  `## Background Skills`(consult `/플러그인:스킬` 지시,
  `emit.sections._background_references_section`)가, 링크된 **에이전트**에는
  `skills` 프론트매터 `플러그인:스킬` 주입(`_agent_skills_list` 3단계 — 위
  실측으로 가능함이 확인돼 본문 단락을 대체했다, 2026-09-12)이 합류한다. 목록
  판정은 `linked_background_skills` 하나를 두 소비자가 공유한다. 판정의 단일 진실은
  `model/plugin/skill.is_reference_usage`(캔버스 드롭·링크·에디터·emit·검증
  공유). 후보/미정 wrapped의 캔버스 드롭은 `FsmScene._ask_wrapped_usage`
  팝업으로 묻고(테스트는 몽키패치 봉합선), 미정 고정+배치는 MacroCommand
  1 undo(따로면 undo가 배치만 되돌려 반쪽 상태). 직렬화: usage 키 항상 배출,
  키 부재(구버전)는 "state" 로드. 검증 `wrapped_usage_conflict` 경고(용도 ↔
  배치 어긋남 — MCP·구버전 파일 대비). MCP: `create_skill(usage=)`,
  `set_transfer_on`은 reference 용도 거절, `set_component_field("usage")`
  거절(배치가 고정 — 전환은 아래 전용 경로). 에디터: reference 용도는 포트
  패널 대신 `_ReferenceLinkPanel`, 원본 패널에 용도 표시.
- **용도 전환 — 배치를 걷어낸 뒤에만**(사용자 보고 2026-09-07): 지켜야 할
  불변식은 "**동시에** 두 용도로 쓰이지 않는다"이지 "영원히 못 바꾼다"가
  아니다(없으면 삭제·재생성뿐이라 이름·설명·프론트매터·source를 다시 넣어야
  한다). 실체는 `view/actions/wrapped_usage.change_wrapped_usage(window,
  component, usage, force=False)` — 배치가 없으면 SetAttrCmd 하나, 있으면
  **기본은 거부**하고 무엇을 지워야 하는지 말한다(전이가 말없이 사라지면 안
  된다). `force=True`면 `RemoveComponentCmd`와 **같은 조립**
  (`_canvas_cleanup_commands`)으로 참조 노드·전이·상태를 걷어내고 전환까지
  MacroCommand **1 undo**. 표면: 랩핑 편집기의 "용도를 …로 바꾸기" 버튼
  (배치가 있으면 QMessageBox로 확인) / MCP `set_wrapped_usage(name, usage,
  force=)`. **캔버스 시각 구분**(같은 보고): `node_item._TYPE_STYLE`에
  `wrapped_skill`(보라 + 🔗 — 없어서 빈 상태와 같은 기본 스타일로 그려졌다),
  `ref_node_item`은 모델 kind가 wrapped면 "🔗 EXT REFERENCE" + 보라(우리
  문서 참조는 산출 파일이 있고 외부 참조는 없다).
- **삭제 불가 — 대신 비활성화**(사용자 확정 2026-09-07): 랩핑 스킬은 **어느
  경로로도 지울 수 없다**(GUI 레지스트리·캔버스·MCP `delete_component` 전부
  거절 — 실체는 `ComponentActions.delete_component`가 지나는 한 지점).
  소스·프론트매터·배선을 다시 입력하는 비용이 크고, 지우면 이 프로젝트가 그
  외부 스킬을 한때 썼다는 사실 자체가 사라진다. "쓰지 않는다"는
  `WrappedSkillConfig.enabled`(기본 True, 직렬화 왕복, 키 부재=True)로 말하고
  판정의 단일 진실은 `model/plugin/skill.is_disabled_wrapped`다.
  - **끄면 빠지는 곳**: 산출 계획(state 용도 SKILL.md 미산출) / 참조 용도의
    `## Background Skills` consult 지시 / 외부 플러그인 참조 판정
    (`unused`·`undeclared` 둘 다 — 꺼둔 것은 쓰지 않는 것이다).
    **`external_plugins` 선언과 배선은 건드리지 않는다** — 선언은 사용자 소유다.
  - **배치는 걷어내지 않는다** — 끄는 것과 캔버스에서 치우는 것은 다른
    결정이고, 전이가 말없이 사라지면 안 된다(용도 전환이 force를 요구하는 것과
    같은 이유). 비활성인 채 배치가 남으면 `disabled_wrapped_placed` 경고.
  - 실체는 `view/actions/wrapped_usage.set_wrapped_enabled`(SetAttrCmd — undo,
    값이 같으면 no-op) 하나이고 표면 셋이 공유한다: 랩핑 편집기
    [비활성화]/[활성화] 버튼 / 레지스트리 우클릭(랩핑 행은 '삭제' 자리에 이
    항목이 온다 — 눌러 봐야 거절당하는 항목을 보이지 않는다) / MCP
    `set_wrapped_enabled(name, enabled)`.
- **본문 편집 없음**(사용자 확정): wrapped 에디터의 중앙은 본문 편집기가
  아예 없고 `_WrappedSourcePanel`(원본 경로 읽기 전용 + "원본 열기" 버튼 —
  `wrap_catalog.resolve_skill_file`로 카탈로그에서 SKILL.md 해석)이다 —
  프론트매터·연결선 정의만 여기서 한다. 매트릭스에 CONTEXT/AGENT/SHELL 없음
  — kind별 명시 부재는 test_field_matrix의 `_KIND_ABSENT_FIELDS`가 계약으로
  고정.
- **외부 플러그인 카탈로그(D2)**: `model/plugin/wrap_catalog.py`가 발견의
  단일 진실(파일시스템을 아는 모듈 — hook_store 지위. 검증기·컴파일러는
  임포트 금지, 필요하면 호출자 주입). **마켓플레이스 폴더** 등록은 전역
  `~/.daedalus/external_marketplaces.json`(`marketplaces_file` — 테스트는
  conftest `_isolate_external_marketplaces`가 격리), 발견은 폴더 밑 깊이 4까지
  `.claude-plugin/plugin.json` 탐색 + `skills/*/SKILL.md`(스킬 이름의 단일
  진실은 **디렉토리명**) + 동봉 `.mcp.json`/`plugin.json`의 `mcpServers` 키
  (`CataloguedPlugin.mcp_servers`). 마켓 이름 해소: 등록 시 명시 > 폴더
  `.claude-plugin/marketplace.json`의 name > bare. **GUI 창**은 도구 메뉴
  "외부 플러그인 카탈로그..."(`view/editors/wrap_catalog_dialog`) — 폴더→
  플러그인→스킬 트리, **플러그인 체크 = 이 프로젝트에서 사용 선언**
  (`external_plugins`에 SetAttrCmd — undo·저장 왕복), ✔=이미 랩핑됨. 체크
  토글의 트리 재구성은 singleShot(0, self, refresh)으로 미룬다(itemChanged를
  쏜 아이템을 같은 호출에서 clear()로 파괴하면 간헐 access violation — 실측.
  수신 컨텍스트 덕에 닫힌 다이얼로그에 발화하지 않는다). **이 창의 동작은
  등록·선언뿐이다**(사용자 확정 — 실제 랩핑은 빌드 소관이라 생성 버튼 없음).
  WrappedSkill 생성(워크플로 단계로 놓을 때만)의 실체는
  `actions/creation.create_wrapped_skill`(등록 전 source 대입 + 미선언이면
  **선언까지 MacroCommand 1 undo**, 이름 충돌 `-2` 접미) — 레지스트리 🔗
  탭·캔버스 "여기에 만들기"·MCP `create_skill(source=)`가 부른다.
- **외부 플러그인의 MCP 서버 활용**: 사용 선언된 플러그인의
  `mcp_servers`가 ① 에이전트 MCP_SERVERS TagInput 자동완성 후보
  (`tag_input.set_mcp_server_candidate_provider` — app.set_project가
  `used_plugin_mcp_servers(project) ∪ mcp_server_defs` 등록. **tools 후보에는
  넣지 않는다** — 개별 도구 목록 미지원, 사용자 확정) ② LOCAL 컴파일 주입
  `compile_project(provided_server_names=)`(compile_inputs 합류 — 플러그인
  활성화가 서버를 가져오므로 `missing_mcp_server_def` 대상에서 제외)로 쓰인다.
- **실물의 출처는 세 곳, 기준은 "설치했는가"가 아니라 "실물을 읽었는가"**
  (사용자 확정 2026-09-07 — "설치/미설치보다는 그냥 외부 플러그인으로 표시하고,
  클론 여부에 따라 아이콘을"): 마켓플레이스는 `marketplace.json`에 플러그인을
  **선언**만 하고 실물은 따로 온다(실측: 공식 마켓 291개 선언 / 저장소 동봉 40개).
  `CataloguedPlugin.files_from`이 출처를 말한다 — `"marketplace"`(저장소 동봉) /
  `"installed"`(**CC가 설치** — `~/.claude/plugins/cache/<마켓>/<이름>/<버전>/`,
  `cc_installed_dirs()`가 `installed_plugins.json`에서 읽는다) / `"cache"`(우리가
  클론) / `""`(못 읽음). `has_files` property가 그 판정이고, 어디서 왔든 스킬은
  `_scan_skills` 하나가 읽는다.
  - **마켓 저장소만 훑던 것이 버그였다**(사용자 보고) — CC는 마켓 저장소가 아니라
    별도 캐시에 푸므로, 사용자가 **실제로 설치한** 플러그인이 "미설치"로 나왔다.
  - 못 읽으면 `skills=[]`이라 랩핑(WrappedSkill)은 불가하지만 **사용 선언은 지금도
    된다**: plugin_id만 있으면 빌드가 dependencies/enabledPlugins를 내고 설치는
    CC가 한다. 매니페스트 없는 실물도 정상이다(스킬 없이 LSP·훅만 주는 플러그인 —
    실측 pyright-lsp. 없는 파일에 경고를 내면 목록을 열 때마다 시끄럽다).
  - 표면: 카탈로그 창은 아이콘으로 가르고(🧩 읽음 / ⬇ 받아야 함) 못 읽은 것은
    "⋯ 스킬 미확인 (N)" **접힌 그룹**으로 묶는다(수백 개가 쓸 수 있는 것을 덮지
    않도록). MCP는 `list_wrappable_skills(include_unfetched=False)`가 읽은 것만 +
    `unfetched_count`로 나머지를 알리고 각 항목에 `files_from`을 싣는다.
  - **창의 펼침 상태는 재구성을 견딘다** — 체크(사용 선언)마다 트리를 다시 그려
    폴더가 접히던 것을 고쳤다(사용자 보고). 체크 토글은 트리를 건드리지 않고
    상태 문구의 개수만 갱신하며(`_update_status_counts` — 모델 재스캔이 아니라
    **화면을 센다**), 펼침은 plugin_id·폴더 경로 키 집합으로 복원한다. 덤으로
    itemChanged를 쏜 아이템을 같은 호출에서 clear()로 파괴하던 플레이키 access
    violation의 뿌리도 사라졌다.
- **미설치 플러그인 실물 캐시**(사용자 확정 2026-09-07 — "그냥
  `~/.daedalus/cache/plugin/` 폴더에 클론하자"): `model/plugin/plugin_cache.py`가
  선언 `source`로 저장소를 **얕게 클론**해 캐시에 두고, 스킬 스캔은
  `wrap_catalog._scan_skills`를 **그대로 재사용**한다. 그래서 이름뿐 아니라
  **설명(SKILL.md 프론트매터)까지** 나오고, 같은 스킬을 어디서 읽었느냐에 따라
  목록이 달라질 여지가 없다. 초기 구현은 GitHub API로 디렉토리 목록만 훑었는데
  (이름만·GitHub 전용·익명 시간당 60회 한도) 클론으로 바꾸며 셋 다 해소됐다.
  - **`git clone --branch`가 아니라 init + `fetch --depth 1`**이다 — 선언에는
    커밋 SHA가 흔한데 `--branch`는 태그·브랜치만 받는다. `sha`가 있으면 `ref`
    보다 우선한다(태그는 옮겨 달릴 수 있고 SHA는 불변이라 캐시 키로 안전).
  - **언제 인터넷에 나가는가 — 사용자가 그 플러그인을 지목했을 때만이다.**
    카탈로그를 열거나 새로고침하는 것만으로는 절대 받지 않는다(291개 일괄
    클론은 디스크도 시간도 감당할 수 없다). 캐시 폴더 이름에 ref가 들어가므로
    같은 버전은 다시 받지 않고 버전이 바뀌면 새 폴더로 받는다.
  - 실패하면 받다 만 폴더를 **지운다** — 남기면 다음 호출이 그것을 "이미 받은
    것"으로 보고 빈 디렉토리를 스캔한다. git 부재는 stack trace 대신 안내 문구.
  - 클론할 주소가 없는 source(마켓 폴더 안 상대 경로 등)는 `None`을 돌려주고
    "설치 후 확인"으로 안내한다. git URL이면 **GitHub이 아니어도 된다**.
  - **받아 온 결과는 창이 아니라 카탈로그가 들고 있다**(사용자 보고 — "클론해도
    사용 가능한 wrapped 스킬로 표시 안 됨"): `discover_plugins`가 매 스캔마다
    `cached_path`(**절대 받지 않는 조회 전용**)로 캐시를 확인하므로, 받은 스킬은
    설치본과 완전히 같은 경로로 실려 레지스트리 🔗 후보·MCP 목록에도 곧바로
    나온다. 창 안 세션 dict에 담아 두면 받아왔는데도 어디서도 랩핑할 수 없다.
  - 표면: 카탈로그 창 "스킬 목록 받아오기" 버튼(이 창에서 인터넷에 나가는 유일한
    지점 — 클론 중 대기 커서) / MCP `fetch_plugin_skills(plugin_id,
    refresh=False)` — 실물이 이미 있으면 그 자리에서 읽어 받지 않는다.
    테스트는 `_shallow_clone`을 몽키패치해 **호출 횟수까지** 센다(언제 받느냐가
    이 기능의 계약이다) — 인터넷도 git도 쓰지 않는다.
- **레지스트리 후보 노출 + 드롭 생성**(사용자 확정 — "목록에 그냥 자동으로
  명시"): 사용 선언된 플러그인의 스킬 중 미랩핑 소스가 레지스트리 🔗 탭에
  **후보 행**(이탤릭·회색, 컴포넌트 아님)으로 자동 노출된다. 드래그 mime은
  `wrapped-source:<source>`(`WRAPPED_SOURCE_MIME_PREFIX` — creation.py 단일
  진실)이고 캔버스 드롭 시점에 `FsmScene.drop_wrapped_source` →
  `create_wrapped_skill(x, y)`로 생성+선언+배치가 MacroCommand 1 undo.
  카탈로그 스캔은 파일시스템이라 레지스트리가 선언 목록 키로 캐시한다
  (`_wrapped_candidates` — notify마다 재스캔 금지).
- **MCP 짝**(패리티): `list_wrappable_skills`(plugin_id·used·mcp_servers·
  source·already_wrapped)/`list_marketplace_folders`/`add_marketplace_folder`/
  `remove_marketplace_folder`(홈 설정 파일 — undo 비대상)/
  `set_external_plugins`(선언 통째 교체 — undo 가능) +
  `create_skill(kind="wrapped", source=, x=, y=)`(생성+선언+배치 1 undo —
  후보 드롭과 같은 경로, 다른 kind에 source는 거절). `get_project` meta에
  `external_plugins`.
