# WP-MK — 마크다운 에디터 코드 인용 + 단축키 확장

## 배경 (사용자 요청)

1. **코드 인용 기능** — 현재 인라인 코드(`` `x` ``) 단축키가 없고, 코드 블록은
   슬래시 메뉴에만 있다. 코드는 스킬 본문에서 가장 자주 쓰는 서식인데 손이 제일
   많이 간다.
2. **단축키 추가** — 헤딩·리스트·인용에 단축키가 없어 툴바/슬래시 메뉴를 거쳐야
   한다.

현재 단축키: Ctrl+B(볼드) / Ctrl+I(이탤릭) / Ctrl+Shift+X(취소선) / Ctrl+K(링크) /
Ctrl+F(찾기). 공개 API는 `toggle_wrap`/`insert_link`/`set_heading_level`/
`toggle_line_marker`가 이미 있으므로 대부분 배선만 하면 된다.

## Part A — 코드 인용

`MarkdownEditor`에 공개 메서드 2개 (툴바·슬래시 메뉴가 재사용):

1. `toggle_inline_code()` — 선택을 `` ` ``로 감싸기/벗기기. `toggle_wrap("`", "`")`
   재사용. 선택 없으면 백틱 쌍 삽입 후 가운데 커서.
2. `toggle_code_block()` — **여러 줄 인식**이 핵심:
   - 선택 있음: 선택 줄들을 ```` ``` ````/```` ``` ````로 감싼다(줄 단위 — 선택이
     줄 중간에서 시작/끝나도 그 줄 전체를 포함). 이미 펜스로 감싸져 있으면 벗긴다.
   - 선택 없음: 현재 줄이 비어 있으면 빈 펜스 3줄 삽입 + 가운데 커서, 아니면
     현재 줄을 펜스로 감싼다.
   - 언어 태그는 넣지 않는다(v1) — 여는 펜스 뒤에 커서를 두면 사용자가 바로 칠 수
     있는 위치가 되도록(선택 없음+빈 줄 케이스에서만).
   - 1 undo 단위(beginEditBlock).
3. 하이라이터는 이미 인라인 코드·펜스를 처리하므로 렌더 변경 없음.

## Part B — 단축키 확장

`_dispatch_key`에 분기 추가. 기존 분기·슬래시 메뉴·검색 배선을 깨지 말 것
(Ctrl 조합이 슬래시 메뉴를 닫는 기존 규칙 유지).

| 단축키 | 동작 | 근거 |
|---|---|---|
| **Ctrl+`** | `toggle_inline_code()` | VSCode/Obsidian 관례 |
| **Ctrl+Shift+C** | `toggle_code_block()` | 코드 블록 |
| **Ctrl+1 … Ctrl+6** | `set_heading_level(1..6)` | 범용 관례(재입력 시 해제는 기존 의미론) |
| **Ctrl+0** | `set_heading_level(0)` | 본문 복귀 |
| **Ctrl+Shift+8** | `toggle_line_marker("- ")` | 불릿 (MS Word 관례) |
| **Ctrl+Shift+7** | `toggle_line_marker("1. ")` | 번호 |
| **Ctrl+Shift+9** | `toggle_line_marker("- [ ] ")` | 체크리스트 |
| **Ctrl+Shift+.** | `toggle_line_marker("> ")` | 인용 |

주의: 숫자 키는 `Qt.Key.Key_0`~`Key_6`, `Ctrl+Shift+8` 등은 **shift 조합 시 키가
문자로 오는 플랫폼 차이**가 있다 — `event.key()`와 `event.text()` 양쪽을 보고
견고하게 판정하라(테스트로 고정).

## Part C — 툴바·슬래시 메뉴 반영

1. `MarkdownToolbar`에 코드 버튼 2개 추가: `<>`(인라인 코드) / `{}`(코드 블록) —
   B/I/S 그룹 뒤, 구분선으로 분리. 툴팁에 단축키 표기. 기존 버튼들의 프리뷰 중
   비활성화 정책(`_edit_buttons`)에 편입.
2. 슬래시 메뉴 카탈로그에 "인라인 코드" 항목 추가(`` ` ` ``, cursor_back=1).
   기존 "코드 블록" 항목은 유지.
3. 기존 툴바 버튼 툴팁에도 단축키를 병기(H1–H3, 리스트 3종, 인용).

## Part D — 테스트

1. 인라인 코드: 선택 감싸기/벗기기 왕복, 선택 없음 삽입+커서, 이미 코드 안일 때.
2. 코드 블록: 단일 줄 감싸기, 여러 줄 선택 감싸기(줄 경계 확장), 벗기기,
   빈 줄에서 빈 펜스+가운데 커서, 1 undo 단위.
3. 단축키 전수: 표의 8종이 각각 대응 동작을 호출(QTest.keyClick, ASCII만).
   Ctrl+숫자·Ctrl+Shift+기호는 `event.text()` 폴백 경로도 커버.
4. 회귀: 기존 단축키(B/I/K/Shift+X/F)·Enter 이어쓰기·Tab·슬래시 메뉴·프리뷰 불변.
5. 툴바: 신규 버튼 2개 존재·클릭 동작·프리뷰 중 비활성.
6. `python -m pytest tests/ -q` 전체 통과 (회귀 0).

## 비목표

- 코드 블록 언어 선택 UI/자동완성 (v1 제외)
- 코드 블록 내부 언어별 하이라이팅 (WP-MD1에서 명시적으로 뺀 범위)
- 사용자 정의 키맵 설정

## 작업 관례

- 브랜치 `wp-mk`. master 직접 작업 금지. `python -m pytest tests/ -q`.
- Pyright 스테일 — 런타임 판정. 커밋 한국어, push 금지. PySide6, QTest ASCII.
- CLAUDE.md 갱신: widgets 항목에 코드 인용·단축키 표 반영.
