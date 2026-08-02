# WP-FR — 파일 참조 관리자

## 배경 (사용자 요청)

플러그인에 동봉할 파일(템플릿, 체크리스트, 데이터)을 프로젝트 옆 `files/` 폴더에
두면: ① 트리 뷰로 보이고 ② 컴파일 시 산출물 `files/` 하위로 그대로 복사되고
③ 마크다운 편집기에 드래그 앤 드롭하면 참조 경로로 치환된다.

## 규약

- **소스 위치**: 프로젝트 저장 파일 옆 `files/` — `<dir>/my.daedalus.json` +
  `<dir>/files/A/c.txt`. 미저장 프로젝트는 기능 비활성(안내 표시).
- **산출 위치**: `<out>/files/A/c.txt` — 구조 그대로 복사.
- **참조 토큰 (확정)**: `${CLAUDE_PLUGIN_ROOT}/files/A/c.txt` — CC 공식 문서
  (plugins-reference §Environment variables)가 **스킬/에이전트 본문 어디서나
  치환됨**을 명시. `$PLUGIN_DIR`는 표준에 없음. 플러그인 루트의 임의 폴더
  (files/)는 설치·캐시 복사 시 함께 보존됨(공식 확인).

## Part A — 파일 독 패널 (view)

1. `daedalus/view/panels/file_panel.py` 신규 — `FilePanel(QDockWidget 내용물)`:
   `QTreeView` + `QFileSystemModel`(root = `<프로젝트 dir>/files`).
   - files/ 부재 시: 안내 라벨 + "files 폴더 만들기" 버튼.
   - 드래그 소스 활성(`QFileSystemModel` 기본 mime — file URL).
   - 새로고침 버튼(파일시스템 변경 반영 — QFileSystemModel은 자동 감시하지만
     루트 생성 직후 재바인딩 필요).
2. `app.py`: 독 위젯 "파일"로 배치(레지스트리 독 관례 참조). 프로젝트
   저장/열기 시(`_current_path` 변경 시점) root 재설정. 경로 없으면 비활성 안내.

## Part B — 마크다운 에디터 드롭 치환

`MarkdownEditor`에 `dragEnterEvent`/`dragMoveEvent`/`dropEvent`:

1. mime에 file URL이 있고 그 경로가 **현재 프로젝트 files/ 루트 하위**면 수락 —
   files 루트 대비 상대경로를 POSIX 구분자로 계산해
   `<TOKEN>/files/A/c.txt`를 커서(드롭 지점)에 삽입. 복수 파일이면 줄바꿈 구분.
2. files 밖 파일·비파일 mime은 기존 동작(무시/기본 처리)으로 흘린다 — 텍스트
   드래그 등 QPlainTextEdit 기본 드롭은 깨지 말 것.
3. files 루트 주입은 provider 패턴(도구 후보/블랙보드 후보와 동일):
   `set_files_root_provider(callable)` — app이 `_current_path` 기준으로 등록.

## Part C — 컴파일: files/ 복사

1. `compile_project(project, out_dir, files_dir: Path | None = None)` — files_dir가
   실존 디렉토리면 `<out>/files/`로 **트리 복사**(정렬 순회 — 결정적 로그,
   CompileResult에 복사 파일 목록/수 추가). 심볼릭 링크는 따라가지 않음.
   기존 `<out>/files/`는 복사 전 삭제(스테일 잔존 방지 — out 전체가 아니라
   files/만).
2. `app._compile` 경로가 `_current_path` 기준 `files/`를 전달. 헤드리스 사용
   (compile_project 직접 호출)은 files_dir 생략 시 기존과 동일 — 하위 호환.
3. **참조 실존 경고**: 컴파일 시 스킬/에이전트 body에서 `<TOKEN>/files/<경로>`
   패턴을 스캔해 files_dir에 실존하지 않으면 `dangling_file_ref` **경고**를
   CompileResult.warnings에 추가(게이트 차단 아님). files_dir가 없으면 스캔 생략.
   (Validator가 아닌 컴파일러 소관 — 검증기는 파일시스템 무접근 순수성 유지.)

## Part D — 테스트

1. FilePanel: files 루트 표시/부재 안내/폴더 만들기, 트리 항목 구조 일치.
2. 드롭: files 하위 파일 URL 드롭 → 토큰 경로 삽입(중첩 경로·복수 파일),
   files 밖 파일 무시, 일반 텍스트 드롭 기존 동작 유지.
3. 컴파일: 트리 복사(중첩 구조·바이트 동일), files_dir 생략 하위 호환(기존 산출
   불변), 스테일 files/ 정리, dangling_file_ref 경고/실존 시 무경고.
4. `python -m pytest tests/ -q` 전체 통과 (회귀 0).

## 비목표

- 파일 편집기(뷰어) 내장 — 트리·드래그만
- files/ 버전 관리·감시 알림
- 에이전트 로컬 스킬 전용 파일 스코프

## 작업 관례

- 브랜치 `wp-fr`. master 직접 작업 금지. `python -m pytest tests/ -q`.
- Pyright 스테일 — 런타임 판정. 커밋 한국어, push 금지. PySide6, QTest ASCII.
- CLAUDE.md 갱신: files/ 규약(소스·산출·토큰), FilePanel, 드롭 치환, 컴파일 복사.
