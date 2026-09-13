# 빌드 타깃과 작업 폴더 산출 (WP-TG/WP-WD/WP-WS)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## BuildTarget = 빌드 타깃 (마켓플레이스 / 로컬 플러그인) (WP-TG)

- **배경:** MCP를 쓰는 에이전트는 CC 정책상 마켓플레이스 플러그인으로 배포할 수 없다(`mcpServers` 등 프론트매터 미지원) — 사람들이 파일 복사로 우회하는 문제를 프로젝트 수준 빌드 타깃으로 해결한다(로컬 에이전트 타입안은 폐기, 이 설계가 상위 개념).
- **모델:** `model/plugin/enums.py`의 `BuildTarget(Enum)`: `MARKETPLACE`(기본) / `LOCAL`. `PluginProject.build_target: BuildTarget = BuildTarget.MARKETPLACE`.
- **직렬화:** `.value` 왕복. 구버전 파일(키 부재)·미지 값은 `MARKETPLACE`로 조용히 폴백(경고 없음) — 하위 호환 게이트.
- **생성 흐름:** `app._new_project`(Ctrl+N)가 통합 다이얼로그(`NewProjectDialog` — 출발점(빈|템플릿) + 빌드 타깃, A7 섹션 참조)로 타깃을 고르게 한다. 취소하면 새 프로젝트 생성 자체가 취소된다(기존 프로젝트 유지). 표시 문구·enum 매핑은 `view/editors/project_properties.py`의 `BUILD_TARGET_LABELS`가 단일 진실. `ProjectPropertiesDialog`에도 콤보로 노출해 생성 후 변경 가능.
- **컴파일:** MARKETPLACE는 `plugin.json`을 생성한다(산출 구조는 LOCAL과 다르되 `state/`·`schemas/` 네임스페이스 규약은 공유 — WP-NS/D12). LOCAL은 **컴파일이 곧 설치**(WP-MW) — out_dir가 대상 작업 폴더이고 산출이 `.claude/` 밑으로 바로 나간다. 상세는 컴파일 정책 15번 항목 참조.
- **검증:** `mcp_agent_in_marketplace_build`/`plugin_root_in_local_build` — Validator 프로젝트 수준 규칙 표 참조.

## 작업 폴더 문서 — `.claude/CLAUDE.md` · `.claude/rules/` (WP-WD)

LOCAL 플러그인이 설치 대상 작업 폴더에 남기는 **항상 컨텍스트에 있는 지침**이다.
스킬은 필요할 때 로드되지만 CLAUDE.md와 `paths:` 없는 rules는 매 세션 로드된다
(공식 문서 확인 2026-09-04). **편집만 제공한다**(사용자 확정) — 생성 로직도 자동
합성도 없고, 사람이 쓴 마크다운이 그대로 나간다.

- **모델:** `WorkspaceDoc(name, body, paths, id)`. `PluginProject.claude_md`는 단일
  필드라 "최대 하나"가 구조로 보장되고, `rules`는 리스트다(파일 하나가 문서 하나).
  `name`의 뜻이 둘 사이에서 다르다 — 규칙에서는 **파일명**, CLAUDE.md에서는 구역
  안 맨 앞의 **H1 제목**이다.
- **UI:** 상주 탭 **2개**(3=CLAUDE.md, 4=규칙). 하나로 묶지 않은 것은 사용자 확정 —
  CLAUDE.md는 하나뿐이고 규칙은 여럿이라 성격이 다르다. 규칙 탭은 선택 목록을 갖는다.
- **rules는 파일이 곧 문서라 공존이 공짜다.** 반면 `.claude/CLAUDE.md`는 고정
  경로라 **구역 병합**이 필요하다(아래).
- **MARKETPLACE에서는 배출되지 않는다** — 플러그인은 설치 대상 작업 폴더의
  `.claude/`에 쓸 수 없다. 내용이 있는데 타깃이 마켓플레이스면
  `workspace_doc_in_marketplace_build` 경고 + 패널 안내.

### 규칙의 `paths:` 프론트매터 (A13)

**초기 WP-WD 설계를 뒤집은 결정이다**(사용자 확정). 원래는 "필드로 두지 않는다 —
본문 맨 위에 직접 쓴다"였는데, raw text로 두면 편집자가 YAML 문법을 손으로 맞춰야
하고 오타가 컴파일까지 조용히 흘러간다. 이제 `WorkspaceDoc.paths: list[str]`가
정식 필드이고 빌드가 프론트매터를 기입한다.

- **규칙 전용이다** — `.claude/CLAUDE.md` 구역에는 paths 개념 자체가 없으므로
  `ClaudeMdPanel`은 이 필드를 노출하지 않는다(모델은 문서 표현 하나를 공유하고
  claude_md에서는 항상 빈 리스트다).
- **비어 있으면 프론트매터를 아예 내지 않는다** — 그때 규칙은 매 세션 로드되고,
  산출은 필드 도입 전과 **바이트 단위로 같다**(하위 호환 게이트). 값이 있으면:

  ```markdown
  ---
  paths: ["src/**/*.ts", "lib/**"]
  ---
  <본문>
  ```

- **원소는 항상 큰따옴표로 감싼다**(`workspace._quoted_flow_list`). `emit._yaml_list`를
  재사용하지 않는 이유는 그쪽이 **선두** 특수문자만 보기 때문이다 — glob은
  `,`·`[`·`]`·`{`·`}`를 문자열 중간에 흔히 갖고(`src/[Tt]est*.ts`), 그 문자들은 YAML
  flow 문맥에서 어디에 있든 지시자라 따옴표가 없으면 스칼라가 거기서 끊긴다.
- **본문이 자기 프론트매터를 갖고 있는데 paths 필드도 차 있으면** `---` 블록이 둘
  나가 뒤의 것이 본문으로 읽힌다. `rule_body_frontmatter` 경고를 내되 **본문은
  건드리지 않는다** — 합치려면 사용자의 키를 해석해야 하고, 조용한 변형은 "내가 쓴
  게 사라졌다"로 돌아온다. 필드가 비어 있으면(본문에 직접 적는 기존 방식) 충돌이
  아니므로 경고하지 않는다.
- 산출 텍스트 조립은 `compiler/workspace.render_rule(doc)`, 충돌 판정은 같은 모듈의
  `has_manual_frontmatter(body)`다(둘 다 순수 stdlib).
- 편집 UI는 규칙 탭 본문 위의 `TagInput`("적용 경로 (비우면 항상 로드)") — 선택 시
  `set_tags`로 로드하고(시그널을 쏘지 않으므로 로드가 모델을 되쓰지 않는다), 편집은
  모델 직접 기록 + `notify("content")`(규칙 탭의 기존 구조 편집 정책과 동일).

### CLAUDE.md 구역 병합 (D9)

```markdown
<!-- daedalus:my-plugin open -->
# my-plugin

...본문...
<!-- daedalus:my-plugin close -->
```

- 1줄 HTML 주석 2개로 구역을 만든다. **CC가 컨텍스트 주입 전에 블록 HTML 주석을
  제거하므로 표식의 토큰 비용은 0이다**(공식 문서).
- 구역이 있으면 **제자리 교체**(위치 보존), 없으면 파일 끝에 덧붙임, 파일 자체가
  없으면 만든다. **새로 만들 때도 표식을 반드시 남긴다** — 안 남기면 다음 빌드가
  그 파일을 남의 것으로 보고 구역을 또 덧붙인다.
- 본문이 비면 구역을 제거한다(플러그인 이름이 키라 멱등).
- 본문이 이미 `# `로 시작하면 H1을 덧붙이지 않는다(제목 중복 방지).
- **손상된 표식은 절대 건드리지 않는다** — open만 있고 close 없음 / open 2개 이상 /
  close가 open보다 앞이면 `unmergeable_claude_md` 경고만 내고 물러난다. 구역의 끝을
  추측하면 그 뒤의 사용자 내용을 통째로 날린다.
- 구현은 `compiler/workspace.py`의 순수 함수 `merge_claude_md`이고, 파일 읽기·쓰기는
  `project_compiler._merge_claude_md_region`이 한다. **산출 계획(`_plan_outputs`)에
  넣지 않는 이유**: 이 파일은 쓰기 전에 읽어야 하고 결과가 기존 내용에 달려 있어
  "경로 하나 = 산출 하나"라는 계획의 전제와 맞지 않는다(`.mcp.json` 병합이
  `_wire_local_install`에 따로 있는 것과 같은 이유).

### 검증

| 규칙 | 등급 | 설명 |
|------|------|------|
| `duplicate_rule_name` | 에러 | 이름이 곧 파일명이라 서로 덮어쓴다 |
| `invalid_rule_name` | 경고 | 컴포넌트와 같은 이름 규약. 컴파일 게이트가 에러로 승격 |
| `workspace_doc_in_marketplace_build` | 경고 | 내용이 있을 때만(빈 문서는 잃을 것이 없다) |
| `workspace_settings_in_marketplace_build` | 경고 | 작업 폴더 설정(WP-WS)이 있는데 마켓 타깃 — 베이크 불가 |
| `unmergeable_claude_md` | 경고 | 손상된 표식 — 컴파일러 emit |
| `rule_body_frontmatter` | 경고 | paths 필드 + 본문 수기 프론트매터 충돌(A13) — 컴파일러 emit |

### MCP

`list_workspace_docs` / `get_workspace_doc` / `set_claude_md` / `create_rule` /
`set_rule_body` / `set_rule_paths` / `rename_rule` / `delete_rule`. 본문은
`BodyTools`와 같은 QTextDocument 경로(WP-BU)라 에디터에 즉시 반영되고 Ctrl+Z로
되돌릴 수 있다. `set_rule_paths`는 빈 목록으로 지우고(항상 로드), 조회 2종은
`paths`를 함께 돌려준다. `delete_rule`은 **이미 산출된 파일을 지우지 않는다**
(컴파일은 쓰기만 한다).

## 작업 폴더 설정 (WP-WS) — settings.json / settings.local.json 베이크

LOCAL 플러그인이 설치 대상 작업 폴더의 설정 파일(`.claude/settings.json` 기본 또는
`settings.local.json` — 아래 "베이크")에 베이크하는
설정이다(permissions.deny 등 — 훅 차단보다 강한 선언적 강제의 자리). 보류됐던
WP-WS를 사용자가 별도 리포로 만든 **QClaudeCodeSettingEditorWidget**(external/
서브모듈, SchemaStore 스키마 구동 — 전 키 자동 생성)이 UI를 채우며 재개했다.

- **모델**: `PluginProject.workspace_settings: dict`(JSON 호환, 직렬화 왕복, 키
  부재→빈 dict). **hooks 키는 두지 않는다** — 훅 정본은 hook_library다. 편집
  다이얼로그가 훅 카테고리를 제외(`Category.ALL & ~Category.HOOKS`)하고, 패널
  저장(`strip_hooks`)·베이크(`wire_workspace`)·MCP(`set_workspace_settings` 거부)
  3층이 방어한다.
- **UI**: 상주 탭 5 "⚙ 설정"(`view/editors/workspace_settings_panel.py`) — 위젯을
  모델에 배선하는 어댑터. 편집은 모델 직접 기록 + notify("content")(블랙보드
  패널 정책). **편집 위젯은 지연 생성**(showEvent/ensure_editor) — 스키마 구동
  전 키 UI가 무거워(첫 구축 ~0.8s 실측) 즉시 만들면 MainWindow를 수십 개 만드는
  스위트가 60초 → 타임아웃으로 폭주했다(실측). 첫 탭 진입 멈춤은 **유휴
  프리웜**(app._schedule_settings_prewarm — 창이 보이고 _SETTINGS_PREWARM_MS 뒤
  구축)이 흡수한다. isVisible 가드가 핵심 — 창을 안 띄우는 테스트에서는 절대
  발동하지 않는다. 위젯 미설치(서브모듈 미초기화)면 안내 자리 표시자.
- **베이크**: LOCAL 컴파일이 `wire_workspace(extra_settings=)`로 설정 파일에 **깊은 병합** —
  산출 파일은 빌드 시 선택한다(사용자 확정): `.claude/settings.json`(기본, 공유) 또는
  `.claude/settings.local.json`(개인). `compile_project(settings_filename=)` ←
  Ctrl+B의 `CompileActions.prompt_settings_filename`(취소=컴파일 취소) / MCP
  `compile_check(settings_filename=)`. 훅·enabledMcpjsonServers 병합도 **같은 파일**로
  간다(wire_workspace 단일 쓰기). wire_workspace 자체의 기본값은 하위 호환상
  local("Claude Code 실행" 메뉴 배선 불변) — 컴파일 경로가 명시적으로 넘긴다.
  병합 정책 — dict는 하위 키 병합, 리스트는 없는
  원소만 순서 보존 추가, 스칼라는 갱신(추가/갱신만·멱등 — 수기 키 불가침).
  dry-run(G3) 경로 그대로 통과(디스크 불변). MARKETPLACE는 배출 없음 +
  `workspace_settings_in_marketplace_build` 경고.
- **왜 마켓 빌드에는 못 싣나 (공식 문서 확인 2026-09-07)**: 플러그인도 루트
  `settings.json`으로 "활성화 시 적용될 기본 설정"을 실을 수 있긴 하다. 다만
  **허용 키가 `agent`와 `subagentStatusLine` 둘뿐**이라 우리가 다루는
  `permissions` 등은 적용되지 않는다 — 그래서 workspace_settings는 LOCAL 전용이
  맞고 위 경고도 정당하다(설정을 아예 못 싣는 게 아니라 **그 키들이 allowlist
  밖**이라는 것이 정확한 이유다). 참고로 plugin-dev의 `plugin-settings`
  스킬이 문서화하는 `.claude/<플러그인>.local.md` 설정 패턴은 **공식 문서에
  없다**(비공식 관습) — 그것을 배경 지식으로 들이면 존재하지 않는 표면을
  설계하게 되므로 랩핑 대상에서 제외한다.
- **MCP**: `get_workspace_settings`/`set_workspace_settings`(통째 교체,
  SetAttrCmd로 undo, hooks 키 거부) — 패리티 원칙에 따라 같은 WP에서 동반.
- **위젯 수명 함정(테스트)**: 위젯의 0ms 디바운스(`singleShot(0, _flush_change)`)가
  위젯 파괴 후 발화하면 stale row 접근으로 죽는다 — 부모 없는 패널을 쓰고
  버리는 테스트는 살아 있는 동안 processEvents로 타이머를 소진해야 한다
  (tests/view/test_workspace_settings.py의 make_panel 픽스처).
- **조율점**: 위젯이 번들한 스키마와 A4 드리프트 감시 스냅샷은 같은 상류의
  별도 사본 — 갱신 시점이 어긋날 수 있다(위젯 갱신 시 A4 스크립트도 확인).
