# WP-MD1 — MarkdownEditor 코어 위젯 (하이라이터 + 편집 조작감)

## 미니 마일스톤 개요

**마일스톤 목표: 마크다운 에디터 위젯의 완전 구현.** 현재 스킬/에이전트 본문 편집기는 맨
`QTextEdit` 평문 모드라 다른 도구(Obsidian/Typora/orca 계열)와 조작감이 판이하다는 사용자
의견이 있다. 이를 자립적인 공용 위젯으로 대체한다.

| WP | 범위 | 상태 |
|----|------|------|
| **WP-MD1 (이 문서)** | 코어 위젯: 문법 하이라이터 + Enter/Tab/단축키 편집 동작 + 다크 팔레트 + `SectionContentPanel` 통합 | 진행 |
| WP-MD2 | 오버레이 UX: `/` 슬래시 메뉴, 소형 툴바, 프리뷰 토글(`QTextDocument.setMarkdown` 읽기 전용) | 예정 |
| WP-MD3 | 찾기/바꾸기 위젯 + 마감 폴리시 | 예정 |

**패러다임 결정 (확정):** 완전 WYSIWYG(마커 숨김)가 아니라 **하이브리드**(마커 유지 + 스타일만
입힘)로 간다. WYSIWYG는 "문서 모델 ↔ 마크다운 텍스트" 왕복에서 파싱 불가 문법을 조용히
파괴하므로 3-way 병합·폴백 게이트 같은 방어 기계가 필수인데(orca 실측 — 에디터 코드 절반이
이 방어), 하이브리드는 텍스트가 곧 진실이라 왕복 자체가 없다.

**포팅 정답지:** `C:\Users\Jooyo\source\qmarkdowntextedit\` (MIT, Patrizio Bekerle,
QOwnNotes의 에디터). 아키텍처가 우리와 같은 세계(QPlainTextEdit + QSyntaxHighlighter)라
개념 손실 없이 1:1 대응된다. 구현 중 판단이 애매하면 이 저장소의 해당 부분을 읽고 따르라:

- `markdownhighlighter.cpp` (2,796줄) — 하이라이팅 규칙·순서의 정답지
- `qmarkdowntextedit.cpp` (2,432줄) — 리스트 이어쓰기·Tab·단축키 편집 동작의 정답지
- `qownlanguagedata.cpp` (7,301줄) — **포팅하지 않는다** (코드 블록 내부 언어별 하이라이팅
  데이터 — 우리 용도에 과잉, 코드 블록은 단색 배경 처리)

단, **1:1 축자 포팅이 아니다** — 아래 스펙에 명시된 부분집합만 구현한다. C++ 원본은 규칙의
디테일(정규식 경계 조건, 상태 전이)이 애매할 때 참조하는 정답지다.

## Part A — `daedalus/view/widgets/markdown_editor.py` (신규)

단일 모듈에 하이라이터 + 에디터 두 클래스. **순수 view 위젯 — model/ 의존 없음.**
모듈 docstring에 MIT 출처 고지를 넣는다:

```python
"""마크다운 에디터 위젯 — 하이브리드(마커 유지 + 스타일) 방식.

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
```

### A-1. 팔레트

모듈 상수 `MARKDOWN_PALETTE: dict[str, QColor]` — 앱 다크 스타일(`__main__._DARK_STYLE`,
배경 #1a1a2e/#1e1e32 계열)과 정합. 키와 값(확정):

```python
MARKDOWN_PALETTE = {
    "text":        QColor("#cccccc"),
    "heading":     QColor("#88aaff"),   # H1–H6 공통 색, 크기로 레벨 구분
    "marker":      QColor("#556699"),   # #, *, -, >, ``` 등 문법 마커
    "bold":        QColor("#eeeeee"),
    "italic":      QColor("#dddddd"),
    "strike":      QColor("#777777"),
    "code_fg":     QColor("#ffcc66"),
    "code_bg":     QColor("#252540"),   # 인라인 코드 배경
    "fence_bg":    QColor("#20203a"),   # 코드 펜스 블록 배경
    "quote":       QColor("#7a9a7a"),
    "list_marker": QColor("#6674cc"),
    "link_text":   QColor("#66aaff"),
    "link_url":    QColor("#555577"),
    "checkbox":    QColor("#cc8844"),
    "done_text":   QColor("#666666"),   # 체크된 태스크 항목 본문
    "hr":          QColor("#444455"),
}
```

기본 폰트: 에디터 본문 "Segoe UI" 10.5pt, 코드(인라인·펜스) "Consolas".

### A-2. `MarkdownHighlighter(QSyntaxHighlighter)`

블록 상태로 코드 펜스를 추적한다: `_STATE_NONE = 0`, `_STATE_CODE_FENCE = 1`
(`setCurrentBlockState`/`previousBlockState`).

`highlightBlock(text)` 적용 순서 (덮어쓰기 순서가 중요 — 나중 규칙이 이김):

1. **코드 펜스 상태 처리 (최우선).** 이전 블록 상태가 FENCE면: 이 줄이 닫는 펜스
   (```` ^\s{0,3}(```|~~~)\s*$ ````)인지 확인 — 닫는 펜스면 마커 색 + 상태 NONE, 아니면
   줄 전체에 `code_fg`+`fence_bg`+Consolas 적용 후 상태 FENCE 유지, **이후 규칙 전부 스킵.**
   이전 상태가 NONE이고 이 줄이 여는 펜스(```` ^\s{0,3}(```|~~~)[^`]*$ ````)면 마커 색 +
   상태 FENCE, 이후 규칙 스킵.
2. **블록 수준 규칙** (줄 시작 정규식, 하나 매치되면 나머지 블록 규칙 스킵):
   - 헤딩 `^(#{1,6})\s+.+$` — 줄 전체 `heading` 색 + 볼드 + 레벨별 크기 배율
     (H1 1.5× / H2 1.3× / H3 1.15× / H4–H6 1.0×, 기준 10.5pt), 마커(`#…` 부분)는 `marker` 색.
     닫는 `#`(trailing hashes)는 처리하지 않아도 된다.
   - 수평선 `^\s{0,3}([-*_])(\s*\1){2,}\s*$` — `hr` 색. (리스트보다 먼저 검사 —
     `- - -`가 리스트로 오인되지 않게.)
   - 인용 `^\s{0,3}(>\s?)+` — 마커는 `marker`, 줄 나머지는 `quote` 색 + 이탤릭.
   - 태스크 `^(\s*)([-*+])\s+\[([ xX])\]\s` — 불릿·괄호는 `checkbox` 색,
     체크 상태(`x`/`X`)면 항목 본문 전체 `done_text` + 취소선.
   - 순서 없는 리스트 `^(\s*)([-*+])\s+` — 마커만 `list_marker` 색.
   - 순서 있는 리스트 `^(\s*)(\d{1,9}[.)])\s+` — 마커만 `list_marker` 색.
3. **인라인 규칙** (블록 규칙과 병행 적용 가능. 단 헤딩 줄은 인라인 스킵):
   - 인라인 코드 `` `[^`\n]+` `` — `code_fg`+`code_bg`+Consolas. **먼저 매치해 범위를
     기록하고, 이후 인라인 규칙은 이 범위와 겹치는 매치를 무시한다** (코드 스팬 안의
     `**` 등이 강조로 오인되지 않게).
   - 이미지 `!\[([^\]]*)\]\(([^)\s]+)[^)]*\)` → 링크와 동일 처리(아래).
   - 링크 `\[([^\]]+)\]\(([^)]+)\)` — 대괄호 텍스트 `link_text`+밑줄, `(url)` 부분 `link_url`.
   - 볼드 `\*\*(?!\s)(.+?)(?<!\s)\*\*` 및 `__(?!\s)(.+?)(?<!\s)__` — `bold` 색+볼드,
     구분자는 `marker` 색.
   - 이탤릭 `(?<![*\w])\*(?!\s|\*)([^*\n]+?)(?<!\s)\*(?!\*)` 및 언더스코어 버전
     `(?<![_\w])_(?!\s|_)([^_\n]+?)(?<!\s)_(?!_)` — `italic` 색+이탤릭.
   - 취소선 `~~(?!\s)(.+?)(?<!\s)~~` — `strike` 색+취소선.

정규식 경계 조건이 애매하면 `markdownhighlighter.cpp`의 해당 규칙을 따른다. 성능:
정규식은 모듈 수준에서 `re.compile` 1회. `QTextCharFormat`도 팔레트 기반으로
`__init__`에서 1회 구성해 재사용.

### A-3. `MarkdownEditor(QPlainTextEdit)`

생성자: 폰트/배경(#1e1e32) 설정, `MarkdownHighlighter(self.document())` 부착,
`setTabChangesFocus(False)`.

**기존 `QTextEdit` 호환 API는 상속으로 자동 충족** — `setPlainText`/`toPlainText`/
`insertPlainText`/`textChanged`/`blockSignals`. 별도 재정의 불필요.

#### keyPressEvent 분기 (체감 품질의 핵심)

**Enter/Return** — 현재 블록 텍스트를 위에서부터 검사 (Shift+Enter는 분기 없이 기본 동작):

| 현재 줄 패턴 | 내용 있음 | 내용 없음 (마커만) |
|---|---|---|
| 태스크 `^(\s*)([-*+]) \[[ xX]\] (.*)$` | 개행 + `{indent}{bullet} [ ] ` 삽입 | 줄에서 마커 제거(빈 줄로) — "리스트 탈출" |
| 불릿 `^(\s*)([-*+]) (.*)$` | 개행 + `{indent}{bullet} ` | 마커 제거 |
| 번호 `^(\s*)(\d+)([.)]) (.*)$` | 개행 + `{indent}{n+1}{punct} ` | 마커 제거 |
| 인용 `^(\s*>\s?)(.*)$` | 개행 + 동일 인용 접두 | 접두 제거 |
| 그 외 | 기본 동작 | 기본 동작 |

구현은 `super().keyPressEvent(event)`를 부르지 않고 `QTextCursor`로 직접 삽입/치환
(undo 단위가 자연스럽도록 `beginEditBlock`/`endEditBlock` 사용).

**Tab / Shift+Tab(Backtab)** —
- 다중 줄 선택: 선택에 걸친 모든 줄을 일괄 들여쓰기/내어쓰기.
- 들여쓰기 폭: 그 줄이 리스트 항목(태스크/불릿/번호)이면 2칸, 아니면 4칸.
- 내어쓰기: 줄 앞 공백을 최대 해당 폭만큼 제거 (부족하면 있는 만큼).
- 코드 펜스 내부(하이라이터 블록 상태 FENCE): 항상 4칸.

**서식 단축키** — `_toggle_wrap(prefix, suffix)` 공용 헬퍼:
- 선택 영역이 이미 `prefix…suffix`로 감싸져 있으면(선택 내부 기준) 벗기고, 아니면 감싼다.
- 선택 없음: `prefixsuffix` 삽입 후 커서를 가운데로.
- Ctrl+B → `**`/`**`, Ctrl+I → `*`/`*`, Ctrl+Shift+X → `~~`/`~~`.
- Ctrl+K → 선택 텍스트를 `[선택](url)`로 감싸고 `url` 부분을 선택 상태로 (바로 타이핑해
  덮어쓰게). 선택 없으면 `[](url)` 삽입 + 대괄호 안에 커서.

#### 체크박스 클릭 토글

`mousePressEvent`(LeftButton): 클릭 위치를 `cursorForPosition`으로 블록·컬럼으로 변환,
해당 블록이 태스크 항목이고 컬럼이 `[ ]`/`[x]` 마커 범위(여는 대괄호~닫는 대괄호) 안이면
` `↔`x` 토글 후 이벤트 소비. 아니면 기본 동작. 토글 로직은 테스트 가능하도록
`_toggle_task_at(block) -> bool` 내부 메서드로 분리한다.

## Part B — `SectionContentPanel` 통합

`daedalus/view/editors/body_editor.py`:

```python
from daedalus.view.widgets.markdown_editor import MarkdownEditor
...
self._w_content = MarkdownEditor()          # 기존: QTextEdit()
```

시그널 배선(`textChanged` → `_save_content`)·`show_section`의 `blockSignals` 패턴·
`insert_variable`(`insertPlainText`)은 그대로 동작해야 한다. **다른 파일의 변경은
불필요해야 정상** — `component_editor.py` 등은 `SectionContentPanel`의 공개 API만 쓴다.
통합 후 앱 스타일시트가 위젯 배경을 덮지 않는지 확인하고, 필요하면 `MarkdownEditor`에
객체명 기반 QSS를 준다.

## Part C — 테스트

### 신규 `tests/view/test_markdown_editor.py`

기존 `tests/view/conftest.py`의 `qapp` 픽스처 사용. 하이라이터 검증은
`QTextDocument`+하이라이터를 직접 만들고 `block.layout().formats()`
(`QTextLayout.FormatRange`)에서 (start, length, format 속성)을 조회한다.

하이라이터 (최소 9케이스):
1. `# 제목` → 줄에 heading 색 + 볼드 + 확대 포맷 존재, `##` 마커는 marker 색
2. `**굵게**` → 내부 텍스트 볼드 포맷, 구분자 marker 색
3. `` `코드` `` → code_fg/code_bg 포맷
4. `` `**코드 안**` `` → 코드 스팬 안의 `**`가 볼드로 처리되지 **않음**
5. 코드 펜스 3줄(```` ``` ``/`x = 1`/`` ``` ````) → 가운데 줄 fence_bg + 블록 상태 전이
   (여는 줄 상태 FENCE, 닫는 줄 상태 NONE)
6. `- [x] 완료` → 본문 done_text + 취소선
7. `- 항목` → 마커 list_marker 색
8. `[텍스트](http://a)` → 텍스트 link_text + 밑줄, url은 link_url
9. `---` → hr 색 (리스트로 오인 안 됨)

에디터 동작 (최소 8케이스, `QTest.keyClick` 또는 `keyPressEvent` 직접 호출):
1. `- 항목` 끝에서 Enter → 다음 줄 `- ` 자동 삽입
2. `- ` (내용 없음)에서 Enter → 마커 제거, 리스트 탈출
3. `3. 항목`에서 Enter → 다음 줄 `4. `
4. `- [ ] 할일`에서 Enter → 다음 줄 `- [ ] `
5. 리스트 줄에서 Tab → 앞에 2칸, Shift+Tab → 제거
6. 일반 줄에서 Tab → 4칸
7. 선택 후 Ctrl+B → `**선택**`, 다시 Ctrl+B → 원복
8. `_toggle_task_at`으로 `[ ]`↔`[x]` 토글 왕복

통합 (최소 2케이스):
1. `SectionContentPanel._w_content`가 `MarkdownEditor` 인스턴스
2. `show_section` 후 타이핑 시 `content_changed` 방출 + `section.content` 갱신 (기존
   동작 회귀 없음)

### 기존 테스트

`python -m pytest tests/ -q` 전체 통과가 완료 조건이다 (현재 874개). `body_editor` 관련
기존 테스트가 `QTextEdit` 타입을 직접 단언하고 있다면 `MarkdownEditor`로 갱신한다.

## 비목표 (이 WP에서 하지 않음)

- 슬래시 메뉴·툴바·프리뷰(WP-MD2), 찾기/바꾸기(WP-MD3)
- 코드 블록 내부 언어별 하이라이팅(qownlanguagedata 포팅)
- setext 헤딩(`===`/`---` 밑줄), 표, 각주, reference-style 링크, frontmatter 하이라이팅
- WYSIWYG/마커 숨김, 링크 클릭 열기
- description/when_to_use 등 다른 텍스트 필드 교체 (본문 편집기만)

## 작업 관례

- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정한다.
- 커밋은 Part 단위(A/B/C 각각 이상), 메시지는 한국어. push 금지.
- CLAUDE.md의 view/widgets 항목에 markdown_editor 한 줄 반영.
