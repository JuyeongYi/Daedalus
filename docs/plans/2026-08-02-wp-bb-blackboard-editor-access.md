# WP-BB — 블랙보드 편집 탭 + 상태 접근 선언

## 배경·확정 설계 (사용자 결정)

블랙보드(전역 공유 상태)는 직렬화·컴파일(schemas.json + 지침 단락)이 완비돼 있지만
**편집 UI가 전무**하고, 어떤 상태가 무엇을 읽고 쓰는지가 본문 산문에만 암묵적으로
존재한다. 이번 WP로:

1. **블랙보드 편집 탭** — 모달 다이얼로그가 아니라 Project FSM과 동급의 **상주
   최상위 탭**(항상 존재, 닫기 불가)으로 프로젝트 블랙보드를 편집한다.
2. **상태 접근 선언** — 선언 위치는 **`State` 베이스**("각각의 상태가 접근"),
   **필드 수준**(`"ReviewFindings.files"`) 허용. 캔버스 뱃지·컴파일 구체화·검증이
   이 선언을 소비한다.

## Part A — model: State 접근 선언

1. `model/fsm/state.py`의 `State` 베이스에 추가:
   ```python
   reads: list[str] = field(default_factory=list)    # "Class" 또는 "Class.field"
   writes: list[str] = field(default_factory=list)
   ```
   fsm 레이어 순수성 유지 — 블랙보드 객체 참조 금지, 문자열 참조(Tool 관례와 동일,
   실존은 Validator가 검증). dataclass 필드 순서 제약은 기존 구조(id kw_only 등)를
   확인하고 하위 클래스(CompositeState 등)가 깨지지 않는 위치에 둔다 — 전 테스트가
   판정 기준.
2. `serialize.py`: `_ser_state`/`_deser_state`에 reads/writes 왕복. 구버전 키 부재
   → 빈 리스트(경고 없음).

## Part B — view: 블랙보드 상주 탭

1. `daedalus/view/editors/blackboard_editor.py` 신규 — `BlackboardPanel(QWidget)`:
   - 좌측: 클래스 목록(QListWidget) + "＋ 클래스"/"삭제" 버튼, 더블클릭 이름 변경.
   - 우측: 선택 클래스의 description(QLineEdit) + **필드 테이블**(QTableWidget
     5열 — name / FieldType 콤보 / CollectionType 콤보 / required 체크 / default)
     + "＋ 필드"/"필드 삭제".
   - 편집은 `project.blackboard.class_definitions`를 직접 갱신하고 notify
     **structure 채널**로 전파(자동완성 후보·검증에 영향). 콤보는 enum 순회
     (combo_widgets 관례). 편집 중 위젯 파괴 금지 — in-place 동기화 원칙.
   - `set_project(project)` API — 프로젝트 교체 시 재바인딩.
2. `app.py`: 탭 인덱스 1에 "블랙보드" 고정 탭 삽입(항상 존재). `_close_tab`이
   Project FSM(0)과 블랙보드(1) 둘 다 거부하도록 방어 + `_open_tabs` 인덱스
   보정 로직이 고정 탭 2개 전제로 동작하는지 확인·갱신. `set_project`가
   `BlackboardPanel.set_project` 호출.

## Part C — view: 상태 속성의 접근 선언 편집 + 뱃지

1. 상태 선택 시 속성 편집 UI(현재 상태 속성이 노출되는 곳 — PropertyPanel 또는
   상태 편집 다이얼로그, 구현 전 실경로 확인)에 **reads/writes TagInput 2개** 추가.
   자동완성 후보 = 프로젝트 블랙보드의 `클래스` + `클래스.필드` 전체(WP-TM의
   `TagInput.set_candidates` 재사용). 블랙보드 변경 시 후보 갱신(provider 패턴).
   프로젝트 캔버스 placement·스킬 FSM 상태·에이전트 FSM 상태 모두 같은 경로로
   편집 가능해야 한다.
2. 캔버스 뱃지: `node_badges.py`에 `state_access_badges(state) -> list[tuple[str, str]]`
   신설 — writes 있으면 `("✏", "블랙보드 쓰기: <목록>")`, reads만 있으면
   `("📖", "블랙보드 읽기: <목록>")`. `NodeItem`이 기존 컴포넌트 뱃지에 합류해
   렌더(노이즈 방지 — 선언 있을 때만).

## Part D — compiler: 선언 기반 구체화

1. **FSM 절차 단락**(`_describe_fsm`): 상태 항목에 접근 주석 합류 — 형식:
   `N. **state** — ...기존 서술... (읽기: \`A.x\`, \`B\` / 쓰기: \`A.y\`)`.
   reads/writes 각각 이름순 정렬(결정적). 선언 없으면 현행 문구 그대로.
2. **블랙보드 단락 구체화**(`_blackboard_section` 계열): 스킬(및 에이전트)의 FSM
   전 상태(sub_machine/Region 재귀 포함) + 프로젝트 그래프의 해당 placement에서
   선언 합집합을 구해:
   - 합집합이 비어 있지 않으면: "이 스킬이 읽는 것: …" / "쓰는 것: …" 명시 +
     파일 목록은 **관련 클래스만** 나열.
   - 합집합이 비면: 현행(전 클래스 일반 안내) 유지 — 하위 호환, 기존 산출 불변.
3. 출력은 결정적(정렬), 기존 단락 순서 불변.

## Part E — validation: 규칙 2종 (WARNING_RULES 등재)

1. `dangling_blackboard_ref` — 모든 머신(재귀)과 프로젝트 그래프의 상태
   reads/writes 문자열을 `"Class"`/`"Class.field"`로 파싱해 프로젝트 최상위
   블랙보드 class_definitions에 실존하는지 검사. 미존재 → 경고(subject=해당 상태,
   path 재귀 규약 준수). 빈 문자열은 스킵.
2. `orphan_blackboard_field` — 블랙보드 필드 중 어떤 상태의 reads/writes에도
   등장하지 않으면 경고. 단 **프로젝트 전체에 접근 선언이 하나도 없으면 스킵**
   (선언 기능 미사용 프로젝트에 경고 폭주 방지).

## Part F — 테스트

1. model/serialize: reads/writes 왕복 + 구버전 부재 → 빈 리스트.
2. view: 블랙보드 탭 존재·닫기 거부, 클래스 추가/이름변경/삭제 → 모델 반영,
   필드 테이블 편집 → DynamicField 반영, notify structure 방출.
3. view: 상태 선택 → TagInput 후보에 클래스·필드 등장, 입력 → State.reads/writes
   반영, 뱃지 렌더(선언 유/무).
4. compiler: 절차 단락 접근 주석(정렬 포함), 블랙보드 단락 구체화(관련 클래스만),
   선언 0개 시 기존 산출 **문자열 불변**(하위 호환 게이트).
5. validation: dangling 검출(클래스/필드 각각), orphan 검출, 선언 전무 시 orphan
   스킵, 에이전트 FSM 재귀 검출.
6. `python -m pytest tests/ -q` 전체 통과 (현재 1000 기준, 회귀 0).

## 비목표

- 에이전트 로컬 블랙보드 편집 UI (parent 스코핑 상속 조회로 충분 — 후속)
- Blackboard.variables(Variable) 편집 (class_definitions만 — 변수는 후속)
- 데이터플로 오버레이(read/write 연결선 렌더)
- 런타임 검증/실행 코드

## 작업 관례

- 브랜치 `wp-bb` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- CLAUDE.md 갱신: 아키텍처 트리(editors/blackboard_editor, 탭 구조), 블랙보드
  단락(접근 선언), Validator 규칙 표(2종 추가), 컴파일 정책(구체화) 반영.
