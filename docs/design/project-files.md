# 프로젝트 파일 — 템플릿·패키지·files/·skill-files/

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 시작 템플릿 (A7)

빈 캔버스에서 시작하면 단순한 플러그인 하나에도 노드·포트·진행 상태 규칙을 전부
손으로 놓아야 한다("배보다 배꼽"). 아키타입 3종을 시드로 두고 그 위에서 시작한다.

| id | 아키타입 | 담고 있는 것 |
|----|----------|--------------|
| `implementation-review` | 구현 → 리뷰 파이프라인 | 에이전트 2(implementer/reviewer) + 블랙보드 2클래스 + 리뷰 반려 루프 |
| `research-pipeline` | 리서치 파이프라인 | 병렬 조사 에이전트 1 + 블랙보드 3클래스 + 합성·전달 스킬 |
| `single-skill-reference` | 단일 스킬 + 참조 문서 | 사용자 호출 스킬 1 + ReferenceSkill(참조 노드 연결) + DeclarativeSkill |

- **파일은 `serialize_project`의 산출(format 2)이고 로드는 `deserialize_project`를
  그대로 탄다.** 전용 파서를 두면 정본 직렬화기와 어긋나는 순간(필드 추가·
  마이그레이션) 템플릿만 조용히 낡는다 — 같은 경로를 타므로 마이그레이션도 공짜다.
  파일 생성은 모델로 프로젝트를 조립해 직렬화한 결과를 커밋한 것이다.
- **표시 문구(제목·요약)는 파일이 아니라 `model/templates.py`에 있다.** 파일에
  사이드카 키를 섞으면 로드 경로가 특수해진다. id = 파일 stem이 이름의 단일 진실
  (전역 훅 저장소 A1과 같은 규약).
- **본문·설명·포트 description은 영어**다(A12) — 컴파일 산출로 **그대로** 나가는
  사용자 값의 출발점이기 때문이다. 이름·설명은 사용자가 갈아끼울 플레이스홀더이고,
  프로젝트 이름은 Ctrl+N과 같은 `new-plugin`이다.
- **노출은 Ctrl+N 통합 다이얼로그다**(`view/editors/new_project_dialog.NewProjectDialog`
  — 출발점 목록(0행=빈 프로젝트, 이후 템플릿) + 빌드 타깃 콤보, 사용자 확정).
  초기 A7은 "타깃 충돌·취소 이중화"를 이유로 별도 메뉴 항목이었으나, 충돌은 규칙
  하나로 풀었다: **생성 시 고른 타깃이 템플릿에 저장된 타깃을 항상 이긴다**(템플릿
  내용은 타깃 중립, 타깃은 사용자 소유). 취소는 한 겹 — 취소 = 생성 취소(WP-TG
  규약 그대로). 헤드리스 테스트 봉합선은 `SessionIO.exec_new_project_dialog`
  몽키패치(구 QInputDialog.getItem 스텁의 후임 — `_new_project`를 부르는 테스트는
  반드시 이것을 스텁해야 모달이 뜨지 않는다).
- 로드 후 **미저장 변경으로 표시**한다(`_mark_dirty`) — 빈 프로젝트와 달리 잃을
  내용이 있고 저장 경로는 아직 없다.
- **템플릿은 열자마자 F7 에러 0이어야 한다.** `tests/model/test_templates.py`가
  에러 0 + **경고 개수 스냅샷**(현재 전부 0) + 컴파일 게이트 통과 + 본문 한글 부재 +
  아키타입 형상(루프·포트·참조 배치)을 고정한다. 카탈로그 id 집합과 디스크 파일
  stem 집합이 어긋나도 빨강이다("메뉴에 있는데 안 열린다"의 사전 차단).

## 프로젝트 패키지 — 폴더가 곧 프로젝트 (WP-PK)

이미 절반은 그랬다. `files/`가 저장 파일 옆에 있고 `_sync_files_root`가 `parent`로 루트를 잡으니 프로젝트의 단위는 사실상 폴더였다. 다만 강제되지 않아 **같은 폴더의 `.daedalus.json` 둘이 `files/`를 말없이 공유하는 구멍**이 있었다. 폴더 = 프로젝트로 못 박으면 그 구멍은 정의상 사라진다.

- **`_current_path`는 여전히 안쪽 파일을 가리킨다.** 사용자에게 보이는 단위만 폴더로 바뀌고 저장 대상은 파일 그대로다 — 덕분에 `Path(_current_path).parent`로 계산하는 곳(FilePanel 루트·컴파일 `files_dir`·MCP 접속 정보·카탈로그 project_dir)이 **한 줄도 안 바뀌고**, 구버전 파일도 같은 코드 경로를 탄다. 이것이 이 변경의 파급을 작게 만든 유일한 결정이다.
- **`resolve_project_file`(저장 대상) vs `find_project_file`(열 대상)이 다르다.** 저장은 구버전 파일에 덮어쓸 때 그 이름을 유지하고(Ctrl+S가 형식을 말없이 갈아치우지 않는다 — 형식이 바뀌는 지점은 폴더를 고르는 "다른 이름으로 저장" 하나뿐), 열기는 폴더 안에서 정본을 찾고 없으면 구버전 `<이름>.daedalus.json` **하나**를 받아들인다(여럿이면 거절 — 조용히 하나를 고르면 나머지를 편집 중이라 착각하게 된다).
- **아직 없는 경로는 `is_dir()`로 판정할 수 없다.** 새 폴더에 저장하는 것이 정상 경로이므로 확장자로 가른다 — `.json`으로 끝나면 파일, 아니면 폴더. 이 판정이 없으면 "새 폴더에 저장"이 확장자 없는 파일 하나를 만들고 끝난다(테스트가 잡은 실제 버그).
- **Save As가 `files/`를 데려간다**(`SessionIO.carry_files_dir`). 폴더가 곧 프로젝트인데 동봉 파일이 옛 폴더에 남으면 반쪽짜리다 — 컴파일하면 파일이 빠지고 `dangling_file_ref`로야 뒤늦게 드러난다. 목적지에 이미 `files/`가 있으면 건드리지 않는다(덮어쓰기보다 아무것도 안 하는 편이 낫다).
- **`.ddpj` = 프로젝트 폴더를 묶은 zip.** 폴더 **내용**이 아카이브 루트에 놓인다(푸는 쪽이 목적지를 정하므로 폴더 이름을 한 겹 더 넣으면 중첩만 깊어진다). 압축은 결정적(항목 정렬 + 고정 타임스탬프 `(1980,1,1,0,0,0)`)이고, 푸는 쪽은 목적지가 비어 있어야 하며 zip slip(절대 경로·`..`)을 **쓰기 전에** 검사한다(절반 푼 폴더를 남기지 않는다). 압축 안에서 직접 편집하지는 않는다 — `files/` 드래그·컴파일·저장이 전부 특수 경로가 되어 득보다 실이 크다.
- **UI:** File → "폴더 열기"(Ctrl+O) / "파일에서 열기…"(구버전 직접 지정) / "패키지로 내보내기… (.ddpj)" / "패키지 가져오기…". 창 제목·최근 목록은 `display_name`(새 형식이면 폴더 이름 — 파일 이름이 전부 `.daedalus.json`이라 그대로 보이면 구분이 안 된다).
- **MCP:** `open_project`/`save_project`가 폴더를 받고, `export_package`가 **먼저 저장한 뒤** 묶는다(`open_project`와 같은 이유 — 메모리에만 있는 편집을 빼놓고 묶으면 받는 쪽은 그것이 최신인 줄 안다). `open_project`는 열 수 없는 경로면 **저장하기 전에** 거절한다(헛저장은 혼란만 남긴다).

## 파일 참조 (files/) — WP-FR

플러그인에 동봉할 파일(템플릿·체크리스트·데이터)을 프로젝트 옆 `files/` 폴더에 두면 트리로 보이고, 컴파일 시 산출물 하위로 그대로 복사되고, 마크다운 에디터에 드래그하면 참조 경로로 치환된다. 별도 모델 계층은 없다 — files/의 단일 진실은 파일시스템 자체이고, 프로젝트 저장 경로(`_current_path`)가 유일한 배선 지점이다.

- **소스 위치:** 프로젝트 저장 파일 옆(`<dir>/my.daedalus.json` + `<dir>/files/A/c.txt`). 미저장 프로젝트(`_current_path`가 None)는 기능이 비활성화되어 안내만 표시한다.
- **산출 위치:** `<out>/files/A/c.txt` — 구조 그대로 복사.
- **참조 토큰(확정):** `${CLAUDE_PLUGIN_ROOT}/files/A/c.txt` — CC 공식 문서(plugins-reference §Environment variables)가 스킬/에이전트 본문 어디서나 치환됨을 명시한다(`$PLUGIN_DIR`는 표준에 없음). 경로 구분자는 POSIX(`/`)로 정규화한다.
- **FilePanel(view/panels/file_panel.py):** `QTreeView` + `QFileSystemModel`(root = `<project_dir>/files`). files/ 부재 시 안내 라벨 + "files 폴더 만들기" 버튼, 새로고침 버튼(루트 생성 직후 재바인딩용). `app.py`의 `_setup_docks`가 독 위젯 "플러그인 파일 (공용)"으로 배치하고(WP-SF에서 레지스트리 아래 세로 스택으로 개편), `SessionIO.sync_files_root`(WP-RF-3e 이전에는 `app._sync_files_root` — 저장/열기/새 프로젝트 등 `_current_path` 변경 지점마다 호출)가 `set_project_dir`을 갱신한다. 드래그 소스는 `QFileSystemModel` 기본 mime(file URL) 그대로 사용.
- **드롭 치환(widgets/markdown/editor.py + widgets/markdown/providers.py):** `MarkdownEditor.dragEnterEvent`/`dragMoveEvent`/`dropEvent`(editor.py)가 mime의 file URL 중 현재 files/ 루트 하위인 것만 `_file_ref_token`(providers.py)으로 변환해 드롭 지점에 삽입(복수 파일이면 줄바꿈 구분). files 밖 파일·비파일 mime(일반 텍스트 드래그 등)은 토큰 후보가 없으므로 그대로 `super()`로 흘러 기존 QPlainTextEdit 기본 드롭 동작을 보존한다. 루트 주입은 TagInput의 도구/블랙보드 후보와 동일한 provider 패턴 — `set_files_root_provider(callable)`/`get_files_root()`(providers.py의 모듈 전역이 단일 진실. app은 파사드 경로 `widgets.markdown_editor`에서 임포트해 `_setup_docks`에서 `lambda: self._file_panel.files_root()`로 등록한다(등록은 배선 1회, 루트 재계산은 `SessionIO.sync_files_root`) — 전역 자체는 파사드로 복사되지 않으므로 반드시 이 함수들을 거쳐야 한다).
- **컴파일 복사(compiler/project_compiler.py):** `compile_project(project, out_dir, files_dir=None)` — files_dir가 실존 디렉토리면 게이트 통과 후(에러 시엔 복사도 스킵) `<out>/files/`로 정렬 순회 복사(`_copy_files_tree`, 결정적, 심볼릭 링크 미추종 — 디렉토리는 재귀 안 함·파일은 복사 안 함)한다. 기존 `<out>/files/`는 복사 전 삭제(out 전체가 아니라 files/만 — 스테일 잔존 방지). `CompileResult.copied_files`에 복사된 파일 경로 목록을 담는다. files_dir 생략(None) 시 기존 산출 파일/문자열이 완전히 불변이라 하위 호환이며, 헤드리스 `compile_project` 직접 호출부는 변경 없이 그대로 동작한다. `CompileActions.compile_project_dialog`(WP-RF-3e 이전에는 `app._compile_project_dialog`)가 `_current_path` 기준 `<project_dir>/files`를 전달.
- **dangling_file_ref 경고:** `_scan_dangling_file_refs`가 files_dir 지정 시(None이면 스캔 생략) 스킬/에이전트 body에서 `${CLAUDE_PLUGIN_ROOT}/files/<경로>` 패턴을 스캔해 files_dir에 실존하지 않는 참조를 `dangling_file_ref` 경고로 `CompileResult.warnings`에 추가한다(게이트 차단 아님). Validator가 아니라 컴파일러 소관 — 검증기는 파일시스템 무접근 순수성을 유지한다. `is_warning` 판정 일관성을 위해 rule 이름은 `validation/severity.py`의 `WARNING_RULES`에도 등록했다(실제 emit은 project_compiler.py — `tests/model/test_validation_severity.py`의 소스 introspection 완전성 테스트는 `_EXTERNALLY_EMITTED_RULES`로 이 예외를 명시).

## 스킬별 동봉 파일 (skill-files/) — WP-SF

스킬 하나에만 딸린 파일(참조 문서·스크립트)을 `<프로젝트 폴더>/skill-files/<스킬 이름>/`에 두면 컴파일 시
그 스킬의 **SKILL.md 옆으로** 복사되고, 본문은 `${CLAUDE_SKILL_DIR}/<상대경로>`로 참조한다. 근거(2026-08
공식 문서 확인): `${CLAUDE_SKILL_DIR}`는 CC 공식 변수(마켓플레이스/로컬 동일 동작 — `${ROOT}` 같은 타깃
중립화 불필요)이고, 스킬 디렉토리 보조 파일 + 상대 참조가 공식 progressive-disclosure 패턴이다.
**에이전트는 대상이 아니다** — 단일 .md라 전용 디렉토리·변수가 없다. 에이전트에 파일을 주려면 스킬에 실어
skills 프론트매터로 전달하거나(WP-AS 자동 합류 — declarative 전역/링크된 reference) 공용 `files/`를 쓴다.
WP-FR과 동일하게 모델 계층 없음 — 파일시스템이 단일 진실.

- **컴파일(project_compiler.py):** `compile_project(..., skill_files_dir=None)` — 하위 폴더명이 스킬 산출
  디렉토리명(=스킬 이름)과 일치할 때만 복사 계획(`kind="skill_file"`,
  `_iter_tree_files` 정렬 순회·링크 제외)에 합류한다. **계획 집합 합류가 곧 충돌 방어** — 'SKILL.md'라는
  이름의 동봉 파일은 기존 `compile_output_path_conflict` 게이트가 에러로 거부한다. LOCAL은 `.claude/skills/`
  밑으로 간다(cc_prefix 공유). 복사 결과는 `CompileResult.copied_files`. 생략 시 산출 완전 불변(하위 호환).
- **경고 3종:** `unknown_skill_files_dir`(스킬과 이름이 안 맞는 하위 폴더/루트 직속 파일 — rename 잔재 검출),
  `dangling_skill_file_ref`(본문 `${CLAUDE_SKILL_DIR}/…` 참조가 **그 스킬 자신의** 폴더에 없음 — 다른 스킬
  파일을 참조하는 실수도 잡힌다. 이상 2종은 컴파일러 emit, `_EXTERNALLY_EMITTED_RULES` 등록),
  `skill_dir_token_in_agent`(에이전트 본문의 이 토큰은 치환되지 않는다 — Validator 소관, 코드 표기 제외
  `_strip_markdown_code`, 빌드 타깃 무관).
- **UI(사용자 확정 — 전역과 스킬별은 동시에 떠 있는 별개 표면, 콤보 전환 아님):** 독의 `FilePanel`은
  공용 files/ 전용("플러그인 파일 (공용)"), 스킬별은 **스킬 에디터 우측 `SkillFilesPanel`**(전역 스킬만 —
  로컬은 산출 디렉토리명이 달라 제외). 공통 뼈대는 `_FileTreeBase`(트리 바인딩/안내/폴더 만들기/새로고침 +
  **"탐색기" 버튼** — `QDesktopServices.openUrl`로 OS 탐색기 열기, 루트 실존 시에만 활성).
  `SkillFilesPanel`은 에디터마다 생기므로 모듈 provider `set_project_dir_provider`/`get_project_dir`로
  프로젝트 폴더를 조회하고(component.name은 매번 읽어 rename 추적, showEvent마다 refresh),
  `FilePanel.files_root()`/`skill_files_root()`는 드롭 provider용으로 유지.
- **배치 개편(사용자 확정):** RegistryPanel의 종류별 섹션 세로 스택 → **QTabWidget 탭**(이모지 라벨 +
  전체 이름 툴팁). 파일 독은 레지스트리 **아래** 세로 스택(`splitDockWidget(..., Vertical)`) — 좌측 열이 좁아져
  에디터가 가로 공간을 가져간다. 탭 페이지는 비활성 시 항상 hidden이므로 노출 판정 테스트는 탭 가시성 기준.
- **드롭 치환:** `_skill_file_ref_token` — skill-files/<스킬>/ 하위 파일이면 `${CLAUDE_SKILL_DIR}/<스킬 폴더
  안 상대경로>`(첫 조각인 스킬 폴더명은 토큰에서 제거 — 런타임 SKILL_DIR가 그 폴더다). 루트 직속 파일은
  None(기본 드롭으로). `MarkdownEditor._token_for_path`가 files→skill-files 순으로 시도,
  `set_skill_files_root_provider`/`get_skill_files_root` provider는 files와 동일 패턴.
- **Save As 동반:** `SessionIO.carry_files_dir`가 files/와 skill-files/ 둘 다 데려간다(목적지에 있으면 불가침).
