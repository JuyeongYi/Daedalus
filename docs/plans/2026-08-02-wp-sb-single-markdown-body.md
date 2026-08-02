# WP-SB — 본문 단일 마크다운화 (sections 트리 → body 문자열)

## 배경

마크다운 에디터(WP-MD1/MD2)가 헤딩·리스트·슬래시 메뉴를 네이티브로 다루면서 수동
섹션 트리 편집(SectionTree/브레드크럼/타이틀 필드/＋섹션 버튼)은 이중 장부가 됐다.
사용자 피드백: "마크다운 편집기 개편으로 수동 편집 섹션 기능의 존재 의의가 사라졌다."
본문 구조의 진실을 마크다운 텍스트 하나로 통일한다.

**불가침 (절대 변경 금지)**:
- `Section`/`EventDef` 클래스 자체 (`model/fsm/section.py`)
- `AgentDefinition.caller_contracts: list[Section]` — 잠금 계약 카드
  (`_ContractPanel`/`_ContractCard`, scene.py의 call_agent 연결 시 자동 추가/제거,
  `commands/section.py`의 커맨드가 이를 사용) — 직렬화 왕복 포함 전부 그대로
- transfer_on/call_agents(EventDef 목록), when_to_use/description 필드

## Part A — model: body 필드 도입

1. 다음 5개 클래스의 `sections: list[Section]` 필드를 `body: str = ""`로 교체:
   `ProceduralSkill`/`DeclarativeSkill`/`TransferSkill`/`ReferenceSkill`
   (`model/plugin/skill.py`) + `AgentDefinition`(`model/plugin/agent.py`).
   기존 default_factory(`[Section("Instructions")]` 등)는 제거 — 새 컴포넌트의
   body 기본값은 빈 문자열이다.
2. `Skill` 베이스 docstring의 "본문의 단일 진실 공급원은 sections" 문구를 body로
   갱신 (감사 2-8 참조 유지).
3. `model/fsm/section.py`에 `render_markdown(sections: list[Section], depth: int = 1)
   -> str` 신설 — 현재 compiler `emit.py`의 `_render_sections` 로직을 **그대로
   이관**한다(빈 content 처리·헤딩 깊이·블록 join 규약까지 동일). 반환은 기존
   컴파일 파이프라인이 이 블록들을 join했을 때와 같은 문자열이어야 한다
   (아래 Part C 동일성 게이트가 이를 검증).

## Part B — serialize: 단방향 마이그레이션

`model/serialize.py`:

1. `_ser_skill`/`_ser_agent`: `"sections"` 키 대신 `"body"` 키(str) 기록.
   `"caller_contracts"` 왕복은 불변.
2. `_deser_skill`/`_deser_agent`: `"body"` 키가 있으면 그대로 사용. 없고
   `"sections"` 키가 있으면(구버전 파일) `render_markdown`으로 평탄화해 body에
   담는다 — **경고 없음**(정상 마이그레이션 경로). 둘 다 없으면 `""`.
3. `"format"` 버전 키는 1 유지 (키 부재 기반 하위 호환으로 충분 — 기존 관례).

## Part C — compiler: body 직접 배출

`compiler/emit.py`:

1. `compile_skill`/`compile_agent`의 `_render_sections(...)` 블록 배출을 body
   배출로 교체 — body가 공백뿐이면 블록 생략, 아니면 앞뒤 개행을 정리해 단일
   블록으로 추가. FSM 절차·위임·tool_shelf·블랙보드·다음 단계 등 시스템 생성
   단락의 상대 위치·순서는 불변.
2. `_render_sections`는 삭제하고 필요 시 `section.py`의 `render_markdown`을
   임포트 (남는 사용처가 없으면 임포트도 불필요).

**동일성 게이트 (이 WP의 핵심 완료 조건)**: 구버전 직렬화 dict(섹션 트리 보유
스킬 + 에이전트)를 `deserialize_project`로 로드해 `compile_skill`/`compile_agent`한
산출 텍스트가, 같은 섹션 트리를 마이그레이션 없이 직접 렌더하던 기존 방식의 산출과
**문자열 동일**해야 한다. 테스트 픽스처는 헤딩 4단(H1~H4)·빈 content 섹션·자식
중첩을 포함할 것.

## Part D — view: 편집 표면 단일화

1. `editors/body_editor.py`:
   - `SectionTree`/`BreadcrumbNav` 클래스와 `find_path`/`section_depth`/`MAX_DEPTH`
     등 트리 전용 헬퍼 삭제 (다른 사용처가 없는지 grep로 확인 후).
   - `SectionContentPanel`을 body 문자열 편집 패널로 단순화: 타이틀 QLineEdit·
     "＋하위 섹션" 버튼 제거. 유지: 변수 삽입 버튼+`VariablePopup`, MarkdownToolbar,
     에디터/프리뷰 QStackedWidget, content 채널 notify.
   - 새 바인딩 API: `show_body(component)` — component의 `body`를 에디터에 표시
     (blockSignals 패턴 유지), `textChanged` → `component.body` 갱신 +
     `content_changed` 방출. 프리뷰 리셋 동작(WP-MD2) 유지.
2. `editors/component_editor.py`: SectionTree 배선·브레드크럼·섹션 선택/추가/삭제
   흐름 제거, 본문 패널 단일 표시로 재구성. `show_contract_section`은 사용처를
   확인해 caller_contracts 경로가 아니면 제거.
3. `editors/skill_editor.py`/`editors/agent_editor.py`: 위 API 변경 반영.
   `_ContractPanel`(caller_contracts)은 그대로.
4. `commands/section.py`의 섹션 커맨드 중 caller_contracts가 쓰지 않는 것(본문
   트리 전용)이 있으면 삭제, 쓰는 것은 유지 — 사용처 grep으로 판별.
5. `__main__._demo_project`의 `sections=[Section(...)]` 인자 → `body="..."` 문자열.
6. TreePanel 등 다른 패널이 sections를 참조하면 함께 정리 (grep `\.sections`).

## Part E — 테스트

1. **동일성 게이트** (Part C) — 구버전 dict 픽스처 → 로드 → 컴파일 산출 문자열
   비교. 스킬 4종 중 최소 Procedural/Declarative + 에이전트 1종.
2. serialize: body 왕복 / 구버전 sections 평탄화 / body·sections 모두 없는 dict /
   caller_contracts 왕복 불변.
3. view: `show_body` 후 타이핑 → `component.body` 갱신 + `content_changed` 방출,
   프리뷰·슬래시 메뉴 회귀 없음 (기존 `test_markdown_editor.py` 통합 케이스를 새
   API로 갱신).
4. **기존 테스트 전수 갱신**: `sections=`/`\.sections` 사용 지점을 grep으로 전수
   찾아 `body=`로 갱신한다 (compiler/model/view 테스트 다수 — 이 WP에서 가장
   손이 많이 가는 부분. 테스트의 검증 의도를 유지하며 표현만 바꿀 것).

`python -m pytest tests/ -q` 전체 통과(현재 945 기준, 회귀 0)가 완료 조건.

## 비목표

- Section/EventDef/caller_contracts/계약 카드 UI 변경 (전부 존치)
- TOC 사이드바 (WP-MD3에 편입 예정)
- 마크다운 → 섹션 역파싱 (왕복 파싱 함정 — 하지 않는다)
- `"format"` 버전 증가

## 작업 관례

- 브랜치 `wp-sb` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- CLAUDE.md 갱신: Section/sections 서술(아키텍처 트리의 section.py 항목, "Section /
  EventDef" 단락, 컴파일 정책 3번)을 body 의미론으로 갱신 + editors/body 항목 반영.
