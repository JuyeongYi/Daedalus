# WP-MD3 — 찾기/바꾸기 + TOC (마크다운 에디터 마일스톤 마감)

## 마일스톤 위치

| WP | 범위 | 상태 |
|----|------|------|
| WP-MD1 | 코어 위젯 (하이라이터 + 편집 조작감) | 완료 (3c375c1) |
| WP-MD2 | 오버레이 UX (슬래시 메뉴·툴바·프리뷰) | 완료 (d10b1e2) |
| **WP-MD3 (이 문서)** | 찾기/바꾸기 바 + TOC 사이드바 | 진행 — 마일스톤 마감 |

포팅 정답지: `C:\Users\Jooyo\source\qmarkdowntextedit\qplaintexteditsearchwidget.cpp`
(652줄, MIT — 검색 바의 동작 정답지. WP-SB에서 약속한 네비게이션 보상이 TOC).

## Part A — 찾기/바꾸기 바

`daedalus/view/widgets/markdown_editor.py`에 `SearchBar(QWidget)` 추가 (모듈 응집 유지):

1. **표시/숨김**: `MarkdownEditor` 위쪽에 접히는 바(레이아웃 삽입은 SectionContentPanel
   이 담당 — Part C). Ctrl+F로 열림(선택 텍스트가 있으면 검색어로 프리필), Esc로 닫힘
   + 에디터로 포커스 반환. 닫힐 때 하이라이트 제거.
2. **구성**: 검색 QLineEdit + 이전(↑)/다음(↓) 버튼 + "Aa"(대소문자) 토글 + 바꾸기
   QLineEdit + "바꾸기"/"모두 바꾸기" 버튼 + 일치 수 라벨("3/12" — 현재/전체).
3. **동작**:
   - 타이핑 즉시 전체 일치를 `ExtraSelections`로 하이라이트(배경 #665522 계열,
     현재 일치는 더 밝게 구분), 일치 수 라벨 갱신. 검색어 비면 하이라이트 제거.
   - Enter/↓ = 다음, Shift+Enter/↑ = 이전 — 문서 끝에서 처음으로 랩어라운드.
   - "바꾸기" = 현재 일치 1건 치환 후 다음으로 이동. "모두 바꾸기" = 전체 치환
     (1 undo 단위, 치환 건수 라벨 표시).
   - 대소문자 토글은 즉시 재검색.
4. **키 배선**: `MarkdownEditor.keyPressEvent`에 Ctrl+F 분기 추가 —
   `search_requested` 시그널 방출(바 소유는 패널이므로 위젯 간 결합 금지).
   슬래시 메뉴가 열려 있으면 먼저 닫는다(기존 Ctrl 조합 규칙과 동일).

## Part B — TOC 사이드바

`markdown_editor.py`에 `TocPanel(QWidget)` 추가:

1. **파싱은 읽기 전용**: `toPlainText()`에서 ATX 헤딩(`^#{1,6}\s+`)만 정규식으로
   추출(코드 펜스 내부 줄은 제외 — 하이라이터의 펜스 상태(`userState`)를 재사용해
   판정). 마크다운을 되쓰지 않는다 — 왕복 파싱 아님.
2. **표시**: QTreeWidget — 헤딩 레벨로 들여쓰기 계층화, 클릭 시 해당 블록으로 점프
   (`setTextCursor` + `centerCursor`) 후 에디터 포커스.
3. **갱신**: textChanged마다 재파싱하되 300ms 디바운스(QTimer) — 타이핑 프레임 저하
   방지. 구조(헤딩 목록)가 같으면 트리 재구성 생략(in-place 원칙).
4. **토글**: `MarkdownToolbar`에 "☰" checkable 버튼 추가(👁 옆) — `toc_toggled`
   시그널만 방출(패널 소관). 기본 접힘.

## Part C — `SectionContentPanel` 통합

`body_editor.py`:

1. 레이아웃: 툴바 아래에 SearchBar(기본 숨김), 본문 스택 우측에 TocPanel(기본 숨김,
   QSplitter 또는 QHBoxLayout — 폭 ~180px).
2. `MarkdownEditor.search_requested` → SearchBar 열기. `MarkdownToolbar.toc_toggled`
   → TocPanel 표시/숨김. `show_body` 시 SearchBar 닫기 + TOC는 상태 유지(문서
   전환 시 재파싱).
3. 프리뷰 모드에서는 SearchBar/TOC 버튼 비활성(편집 표면 전용 — 프리뷰 중 편집
   버튼 잠금과 동일 정책).
4. 기존 공개 API·시그널 불변 — 소비처(component_editor 등) 무변경이 정상.

## Part D — 테스트

1. SearchBar: 검색 → 일치 수/하이라이트(ExtraSelections 수), 다음/이전 랩어라운드,
   대소문자 토글, 바꾸기 1건(커서 이동 포함), 모두 바꾸기(1 undo 단위 검증),
   Esc 닫힘 + 하이라이트 제거, Ctrl+F 프리필(선택 텍스트).
2. TOC: 헤딩 추출(레벨 계층·코드 펜스 내 `#` 제외), 클릭 점프(커서 블록 확인),
   디바운스 후 갱신(`QTimer` 처리 — `qapp.processEvents` + 대기 유틸), 빈 문서.
3. 패널 통합: Ctrl+F로 바 열림, 프리뷰 중 비활성, show_body 시 바 닫힘, 기존
   시그널·프리뷰·슬래시 메뉴 회귀 없음.
4. `python -m pytest tests/ -q` 전체 통과 (현재 1121 기준, 회귀 0).

## 비목표

- 정규식 검색, 단어 단위 옵션 (v1 제외 — 필요 시 후속)
- 프리뷰 내 검색, 여러 컴포넌트 횡단 검색
- TOC 드래그로 섹션 재배열 (읽기 전용 네비게이션만)

## 작업 관례

- 브랜치 `wp-md3` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- CLAUDE.md 갱신: widgets 항목(SearchBar/TocPanel), editors/body 항목(통합),
  마일스톤 완결 표기.
