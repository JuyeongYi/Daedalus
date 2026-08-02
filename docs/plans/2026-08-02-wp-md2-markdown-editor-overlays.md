# WP-MD2 — MarkdownEditor 오버레이 UX (슬래시 메뉴 + 툴바 + 프리뷰)

## 마일스톤 위치

| WP | 범위 | 상태 |
|----|------|------|
| WP-MD1 | 코어 위젯: 하이라이터 + 편집 조작감 + 패널 통합 | **완료** (머지 3c375c1) |
| **WP-MD2 (이 문서)** | `/` 슬래시 메뉴, 서식 툴바, 프리뷰 토글 | 진행 |
| WP-MD3 | 찾기/바꾸기 위젯 + 마감 폴리시 | 예정 |

전제: `daedalus/view/widgets/markdown_editor.py`의 `MarkdownEditor(QPlainTextEdit)` +
`MarkdownHighlighter`가 WP-MD1로 존재한다. WP-MD1 명세
(`2026-08-02-wp-md1-markdown-editor-core.md`)와 현재 코드를 먼저 정독하라.
orca 조사 결론: **툴바보다 슬래시 메뉴가 "현대적" 체감을 만든다** — 슬래시 메뉴 품질에
가장 공을 들여라.

## Part A — 공개 편집 API (`markdown_editor.py` 확장)

툴바/슬래시 메뉴가 쓸 공개 메서드를 `MarkdownEditor`에 추가한다 (기존 내부 메서드는
공개 래퍼로 노출하거나 이름을 승격하되, 기존 테스트가 깨지지 않아야 한다):

- `toggle_wrap(prefix: str, suffix: str) -> None` — 기존 `_toggle_wrap` 공개 래퍼.
- `insert_link() -> None` — 기존 `_insert_link` 공개 래퍼.
- `set_heading_level(level: int) -> None` — **현재 줄** 대상. 기존 `#{1,6}\s+` 접두를
  제거한 뒤, `level`이 1–6이면 `"#" * level + " "`을 붙인다. 현재 접두 레벨과 같은
  level을 다시 적용하면 접두 제거(본문 복귀). `level == 0`은 접두 제거만.
- `toggle_line_marker(marker: str) -> None` — 선택에 걸친 모든 줄(선택 없으면 현재 줄)
  대상. marker는 `"- "` / `"1. "` / `"- [ ] "` / `"> "` 중 하나.
  각 줄에 대해: 이미 같은 종류의 마커면 제거, 다른 리스트/인용 마커면 교체, 없으면
  들여쓰기 뒤에 삽입. 번호 리스트는 선택 범위 안에서 1부터 재번호. 빈 줄은 건너뛴다.
  전체가 하나의 undo 단위(beginEditBlock).

Enter/Tab/서식 단축키 등 기존 동작은 변경하지 않는다.

## Part B — `/` 슬래시 메뉴

### 구조

`markdown_editor.py`에 `_SlashMenu(QListWidget)` 추가 — **`Qt.Popup`이 아니라
에디터 viewport의 자식 오버레이**로 구현한다(포커스는 에디터가 유지, IDE 자동완성
패턴). 항목 데이터:

```python
@dataclass(frozen=True)
class SlashItem:
    label: str        # 표시 텍스트 (예: "제목 1")
    keywords: str     # 필터 매칭 대상 (label + 영문 별칭, 예: "제목 1 h1 heading")
    snippet: str      # 삽입 텍스트
    cursor_back: int  # 삽입 후 커서를 끝에서 뒤로 물릴 문자 수 (기본 0)
```

카탈로그 (순서 고정):

| label | snippet | cursor_back |
|-------|---------|-------------|
| 제목 1 | `# ` | 0 |
| 제목 2 | `## ` | 0 |
| 제목 3 | `### ` | 0 |
| 불릿 리스트 | `- ` | 0 |
| 번호 리스트 | `1. ` | 0 |
| 체크리스트 | `- [ ] ` | 0 |
| 인용 | `> ` | 0 |
| 코드 블록 | ```` ```\n\n``` ```` | 4 (가운데 빈 줄) |
| 구분선 | `---\n` | 0 |
| 링크 | `[](url)` | 6 (대괄호 안) |

keywords에는 영문 별칭을 포함하라 (h1/h2/h3, list, number, check/task, quote,
code, hr/divider, link) — 한/영 어느 쪽으로 쳐도 필터되게.

### 동작 규칙

- **열림**: `/` 입력 시 커서 앞(같은 블록)이 공백뿐이면 — `/`는 문서에 정상 삽입하고
  메뉴를 커서 아래(`cursorRect()` 기준)에 연다. 슬래시 위치(`_slash_start`)를 기억.
- **필터**: 메뉴가 열린 동안 입력되는 문자는 문서에 그대로 들어가고, `_slash_start+1`
  ~커서 텍스트를 필터로 항목을 갱신(대소문자 무시 부분 일치). 첫 항목 자동 선택.
  매치 0개면 빈 목록 유지(Enter 무동작).
- **탐색/확정**: ↑/↓ 항목 이동, Enter/Tab 확정 — `_slash_start`~커서를 snippet으로
  치환하고 `cursor_back`만큼 커서를 물린 뒤 메뉴 닫기. 한 undo 단위.
- **닫힘**: Esc, Backspace로 `/`까지 지웠을 때, 커서가 `_slash_start` 앞으로 이동,
  포커스 아웃, 마우스 클릭. 닫힐 때 문서는 건드리지 않는다(쳐 둔 `/filter` 텍스트 유지).
- 메뉴가 열려 있는 동안 ↑/↓/Enter/Tab/Esc는 메뉴가 소비하고, 그 외 키는 에디터
  기본 처리로 흘린다 (`keyPressEvent`에서 분기).
- 스타일: 다크(#252540 배경, #ccc 텍스트, 선택 #334/#88aaff) — 앱 톤과 정합.

## Part C — 서식 툴바

`markdown_editor.py`에 `MarkdownToolbar(QWidget)` 추가:

- `__init__(self, editor: MarkdownEditor, parent=None)` — 에디터 인스턴스에 배선.
- 버튼 행 (QPushButton, 고정 폭·플랫, 툴팁 필수):
  `H1 H2 H3 │ B I S │ • 1. ☑ │ " 🔗 │ 👁`
  - H1/H2/H3 → `set_heading_level(1|2|3)` (같은 레벨 재클릭 = 해제, Part A 의미론)
  - B → `toggle_wrap("**", "**")`, I → `toggle_wrap("*", "*")`, S → `toggle_wrap("~~", "~~")`
  - • → `toggle_line_marker("- ")`, 1. → `toggle_line_marker("1. ")`, ☑ → `toggle_line_marker("- [ ] ")`
  - " → `toggle_line_marker("> ")`, 🔗 → `insert_link()`
  - 👁 (checkable) → `preview_toggled = Signal(bool)` 방출만 (프리뷰 자체는 패널 소관)
- 버튼 클릭 후 에디터로 포커스 반환 (`editor.setFocus()`).

## Part D — 프리뷰 토글 + `SectionContentPanel` 통합

`body_editor.py`의 `SectionContentPanel`:

1. 본문 영역을 `QStackedWidget`으로 감싼다: 페이지 0 = 기존 `MarkdownEditor`,
   페이지 1 = `QTextBrowser`(읽기 전용 프리뷰).
2. 타이틀 아래·본문 위에 `MarkdownToolbar(self._w_content)` 배치.
3. `preview_toggled(True)` → `browser.document().setMarkdown(editor.toPlainText())`
   후 페이지 1 표시. `False` → 페이지 0 복귀. 프리뷰 중 편집 불가(자연히 보장).
   프리뷰 렌더는 표시 시점 1회 갱신이면 충분(라이브 동기화 불요).
4. QTextBrowser 다크 스타일: 배경 #1e1e32, 텍스트 #ccc, `setOpenExternalLinks(False)`.
5. 기존 공개 API(시그널 3종, `show_section`, `insert_variable`, `set_title_locked`,
   `_btn_variable` 접근)는 그대로 유지 — `component_editor.py` 등 소비처 무변경.
   `show_section`은 프리뷰 상태를 편집 모드로 리셋한다(👁 체크 해제 포함).

## Part E — 테스트 (`tests/view/test_markdown_editor.py`에 추가)

공개 API (5): set_heading_level 적용/재클릭 해제/레벨 교체, toggle_line_marker
불릿 토글/번호 재번호(3줄 선택 → `1. 2. 3.`).

슬래시 메뉴 (6): ① 빈 줄 `/` → 메뉴 열림 + 문서에 `/` 존재 ② 줄 중간(비공백 뒤)
`/` → 안 열림 ③ 필터 타이핑(`co`) → 코드 블록만 남음 ④ Enter 확정 → `/co` 치환 +
펜스 3줄 + 커서 가운데 줄 ⑤ Esc → 메뉴 닫힘 + `/필터` 텍스트 잔존 ⑥ Backspace로
`/` 삭제 → 메뉴 닫힘.

툴바 (4): B 버튼이 선택을 `**…**`로, H2 버튼 적용/해제, 체크리스트 버튼 토글,
👁 클릭 → preview_toggled(True) 방출.

패널 통합 (3): 👁 토글 → 스택이 프리뷰로 전환 + `# 제목`이 H1로 렌더(문서
`toMarkdown`이 아니라 렌더된 rich text 확인 — `browser.document().toPlainText()`에
`#` 마커가 없어야 함), 해제 → 편집기 복귀 + 내용 보존, `show_section` 호출 시
프리뷰 상태 리셋.

기존 테스트(896) 전부 통과 유지. QTest 타이핑 입력은 ASCII만(비ASCII는 qasciikey
어설션) — 한글 스니펫 검증은 `insertPlainText`/직접 호출로 우회하라.

## 비목표

- 이모지 피커, 위키링크 `[[`, 수식, mermaid, TOC, 링크 버블 (orca 기능이지만 범위 밖)
- 찾기/바꾸기 (WP-MD3)
- 프리뷰 라이브 동기화·스크롤 동기화
- description/when_to_use 등 다른 필드의 툴바/프리뷰

## 작업 관례

- 브랜치 `wp-md2` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- CLAUDE.md의 view/widgets·editors 항목에 슬래시 메뉴/툴바/프리뷰 한 줄 반영.
