# 편집기 동작 — 캔버스·본문·undo·저장 확인

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 본문 부분 접근 (WP-BO) — 파생 인덱스, 저장 불변

- **저장의 단일 진실은 `body: str` 그대로다**(사용자 확정, A안). 저장을 헤딩 트리로 바꾸면 마크다운↔트리
  무손실 왕복 파서가 필요해지는데("저장했더니 본문이 미묘하게 달라짐" 류 버그가 최악), 구조는 항상
  **파생으로만** 만든다. 필요 시 확장 경로: B안(인텍스트 헤딩 속성 `{#id key=val}` — 저장은 여전히 텍스트),
  C안(섹션 일급 객체화 — 섹션 공유 요구가 실재할 때만).
- `model/outline.py`: `parse_outline(body)`(ATX 헤딩, 코드 펜스 제외 — 펜스 정규식은 view
  `widgets/markdown/syntax.py`의 `_FENCE_OPEN/CLOSE_RE` **미러**, 어긋나면 TOC와 섹션 집기가
  달라진다. 하이라이터·에디터도 같은 syntax.py 상수를 임포트하므로 정본은 그 한 곳이다),
  `find_section`(제목/`"## 제목"` 레벨 지정/`"부모 > 자식"` 경로 — 0개·복수 매칭은 ValueError, 조용히
  하나를 고르지 않는다), `section_text`/`char_span`/`replacement_text`. 텍스트 연산은
  전부 `split("\n")` 기반이라 비교체 구간이 바이트 그대로 보존된다. 교체는 QTextCursor
  경로(char_span+replacement_text) 하나뿐이고, 그것과 등가임을 보는 순수 문자열 오라클은
  테스트가 소유한다(`tests/model/test_outline._replace_section`).
- **MCP 도구 3종(부분 접근):** `get_body_outline`(구조만 — 본문 전송 없음)/`get_body_section`/
  `set_body_section`(섹션 교체 — `set_component_body`와 같은 문서 경로(WP-BU)라 undo 가능, text에
  자기 헤딩 줄을 포함해야 섹션으로 남는다). 읽기는 `BodyDocumentRegistry.peek`(열린 문서가 있으면
  그쪽이 진실이되, 읽기가 문서를 **만들지는 않는다**)를 쓴다.

## 연결선 리루트 — 엣지 웨이포인트 (WP-ER)

- **역할:** 루프 전이 등 노드를 가로질러 그려지는 엣지를 사용자가 손으로 정리할 수 있도록 경유점(waypoint)을 추가·드래그·제거하는 기능. 자동 라우팅(장애물 회피 등)은 비목표 — v1은 수동 경유점만.
- **저장 모델:** `PluginProject.edge_layout: dict[str, list[list[float]]]`(2026-09-19 — `AgentDefinition`의 동명 필드는 퇴역했다: 에이전트는 그래프에 놓이는 노드이지 그래프를 소유하지 않는다) — 키는 **Transition.id**(graph_layout의 state.id 규약과 동일), 값은 `[x, y]` 목록(소스→타깃 순서). 웨이포인트는 뷰 관심사이므로 fsm 모델(Transition)에는 넣지 않는다. `remove_component`가 배치 삭제 시 연결 전이와 함께 `edge_layout`의 해당 키도 정리한다(graph_layout 정리와 동일 위치).
- **뷰 모델:** `TransitionViewModel.waypoints: list[tuple[float, float]]`(기본 빈 리스트, 뷰 전용). 저장 직전 `app._save_graph_layout`이 `transition_vms`를 순회해 `project.edge_layout`에 기록하고, 로드 시 `GraphIO.load_project_graph`가 `edge_layout.get(trans.id, [])`로 `TransitionViewModel(waypoints=...)`를 복원한다(graph_layout과 완전히 동일한 저장/복원 시점 미러링).
- **렌더 (`edge_item.py`):** `TransitionEdgeItem.update_path`가 `_route_points()`(소스 포트 → waypoints → 타깃 포트)를 구해 각 구간을 기존과 동일한 베지어 곡선(`_add_curve_segment`)으로 잇는다. 각 구간의 끝점이 정확히 경유점이므로 경로가 그 점을 통과함이 보장된다. 경유점이 없으면 구간이 하나뿐이라 기존 렌더와 완전히 동일(하위 호환 — 회귀 판정은 `test_edge_paint.py`/`test_input_ports.py`/`test_scene_rebuild.py` 무수정 통과). 화살촉은 기존 로직 그대로 `_ARROW_SPACING` 간격으로 **경로 전체에 반복 배치**되고(마지막 구간 전용이 아님 — master와 동일), 라벨도 기존 위치 로직 그대로다.
- **상호작용:** 엣지 더블클릭 또는 컨텍스트 메뉴 "경유점 추가" → `edge.nearest_segment_index(scene_pos)`(구간별 곡선을 샘플링해 최근접 구간 판정) 위치에 삽입. 자식 `WaypointHandleItem`(작은 원, 선택 엣지 색 `#88aaff`)은 **항상 표시**하고 엣지 비선택 시 흐리게만 그린다(`_sync_handles`, opacity `_HANDLE_IDLE_OPACITY`) — `setVisible(False)`로 숨기면 Qt가 마우스 그랩·선택 가능성까지 잃어 드래그가 죽고, 이를 우회하려 `mousePressEvent`에서 super를 건너뛰면 Qt가 드래그 기준 좌표를 기록하지 못해 다음 이동이 화면 왼쪽 위로 튄다(사용자 보고 2건이 같은 뿌리) — 엣지는 절대 이동하지 않으므로(pos()가 항상 원점) 자식 로컬 좌표가 곧 씬 좌표다. 핸들은 Qt 기본 `ItemIsMovable`로 드래그되고 `itemChange(ItemPositionHasChanged)`가 실시간 미리보기(`edge.update_waypoint_preview`, undo 없음)를 반영하며, release 시 `scene.handle_items_moved`(노드·참조 노드와 **같은 단일 진입점**)가 undo 가능한 커맨드를 커밋한다(노드 드래그 관례와 동일 결). **핸들의 좌클릭 press/release는 `super()`를 반드시 호출한다** — Qt가 거기서 드래그 기준 좌표를 기록하므로 우회하면 다음 이동이 스테일 오프셋으로 계산돼 아이템이 화면 왼쪽 위로 튄다(사용자 보고). 단일 클릭 선택 규칙이 엣지 선택을 해제해도, 핸들을 항상 표시하는 위 정책 덕에 마우스 그랩이 유지되므로 수동 선택 조작은 필요 없다(초기 구현은 super를 건너뛰고 선택을 직접 조작했으나, 그게 바로 좌상단 튐의 원인이었다 — `c3d7f39`에서 폐기). 핸들 우클릭 "경유점 제거" 또는 핸들 선택 후 Delete(씬 Delete 처리는 선택에 핸들이 있으면 **경유점만 제거하고 엣지/노드 삭제 분기를 건너뛴다** — 한 키에 전이까지 지워지는 것 방지), 엣지 컨텍스트 메뉴 "경유점 모두 제거"(직선 복원)도 제공.
- **undo:** `AddWaypointCmd`/`MoveWaypointCmd`/`RemoveWaypointCmd`/`ClearWaypointsCmd`(`view/commands/transition_commands.py`) — `MoveStateCmd`와 동일한 관례로 `TransitionViewModel.waypoints`를 직접 변경(모델 sync_fn 불필요, 저장 시점에만 project.edge_layout으로 평탄화). 프로젝트 캔버스(`FsmScene`) 전용 — 에이전트 내부 FSM 캔버스는 WP-AF로 퇴역했다.

## 캔버스 드래그 이동 (WP-DM)

- **문제:** 이동 가능 아이템 3종(`StateNodeItem`/`ReferenceNodeItem`/`WaypointHandleItem`)에
  공통 베이스가 없어 드래그 로직이 세 번 중복 구현됐고, 다중 선택 처리는 `StateNodeItem`
  경로에만 있었다. 러버밴드 다중 선택 도입 후 증상이 드러났다.
- **고장 메커니즘(실측):** 드래그 *도중*에는 Qt가 선택된 이동 가능 아이템을 전부 정상적으로
  함께 옮긴다(상태·레퍼런스 노드는 `mouseMoveEvent`에서 `super()`를 호출하고, 웨이포인트
  핸들은 아예 오버라이드하지 않아 Qt 기본 구현이 그대로 움직인다) — **이 단계는 버그가 아니다.**
  진짜 고장은 release *이후*다. release 이벤트는 잡은(grabbed) 아이템 하나에만 배달되므로
  구 핸들러는 그 하나만 커맨드화해 vm을 갱신하고, 이어지는 `execute()` → notify →
  `_rebuild()`의 `item.setPos(vm.x, vm.y)`가 **커맨드를 못 받은 passenger 아이템을 원좌표로
  스냅백**시킨다. 무엇을 잡았느냐에 따라 튕기는 대상이 달라진다.
  → **검증은 반드시 release 완료 후 vm 좌표로** 해야 한다. 드래그 도중이나 화면 좌표
  (`item.pos()`)로 단언하면 고장이 있어도 통과한다.
- **해결:** `DraggableItemMixin`(`canvas/draggable.py`) 공통 수명주기 +
  `FsmScene.handle_items_moved(grabbed, old, new)` 단일 진입점 — 선택된 모든 draggable을 모아
  하나의 `MacroCommand`로 묶는다. **씬에 아이템 타입 분기를 두지 않는다** — 커맨드 생성
  지식은 각 아이템의 `make_move_command()`에 있고 씬은 수집·묶기만 한다.
  **release 진입점은 이 하나뿐이다** — 노드·참조 노드·경유점 핸들이 전부
  `end_drag()` → `handle_items_moved`를 탄다. 옛 종류별 진입점 3종
  (`handle_node_moved`/`handle_waypoint_moved`/`handle_ref_node_moved`)은 전부
  삭제됐다: `handle_ref_node_moved`는 WP-DM에서, 나머지 둘은 2026-09-19에
  (위임 래퍼로 존치한 사유가 "기존 호출부 호환"이었는데 **그 호출부가 없어졌다** —
  퇴역 개념의 호환 잔재, 원칙 7). 함께 사라진 `TransitionEdgeItem.handle_at`은
  `handle_waypoint_moved`의 인덱스→핸들 변환 전용이었다.
- **press 시점 스냅샷(`snapshot_drag_positions`)이 필요한 이유:** `WaypointHandleItem`은
  `itemChange`에서 pos() 변경마다 `transition_vm.waypoints`를 실시간 미리보기 갱신한다
  (`update_waypoint_preview`). Qt의 그룹 드래그는 passenger에게도 `itemChange`를 실시간으로
  쏘므로, release 시점에 `vm_position()`을 다시 읽으면 **이미 새 값**이라 `old == new`로
  오판되어 커맨드가 만들어지지 않고 **undo 불가능한 변경이 조용히 커밋**된다. 그래서
  `begin_drag()`가 press 시점에 선택된 모든 draggable의 vm 좌표를 미리 떠 두고,
  `handle_items_moved`가 passenger의 old를 그 스냅샷에서 우선 조회한다(없으면
  `vm_position()` 폴백 — press를 안 거친 직접 호출 경로 호환). 이동 없이 끝난 클릭은
  `clear_drag_positions()`로 스냅샷을 닫는다.
- **회귀 금지:** `WaypointHandleItem`의 `mousePressEvent`/`mouseReleaseEvent`에서 `super()`
  호출을 제거하면 Qt가 드래그 기준 좌표를 기록하지 못해 다음 드래그가 좌상단으로 튄다
  (WP-ER에서 겪은 버그). 핸들 `setVisible(False)`도 금지(마우스 그랩 소실).

## 본문 undo 스택 (WP-BU)

- **스택이 둘이라는 것이 설계다.** 캔버스 구조 편집은 `CommandStack`(Ctrl+Z, HistoryPanel,
  스크립트 리스너)이고, 컴포넌트 **본문(body)은 그와 분리된 자체 undo 스택**을 갖는다. 본문
  타이핑이 노드 이동·전이 생성과 한 스택에 섞이면 Ctrl+Z가 무엇을 되돌릴지 예측할 수 없다 —
  포커스가 에디터면 그 문서의 undo가, 캔버스면 CommandStack의 undo가 동작하는 것이 기대 동작이다.
- **고장:** `SectionContentPanel.show_body`가 `setPlainText`로 내용만 갈아끼웠다. 이 호출은
  문서의 undo 이력을 지우므로, 다른 컴포넌트를 잠깐 열었다 돌아오면 본문 되돌리기 이력이
  통째로 사라져 있었다(탭을 닫아도 소실).
- **해결:** `editors/body_documents.py`의 `BodyDocumentRegistry`(모듈 전역 `registry()`)가
  컴포넌트 **id별로 `QTextDocument`를 보관**하고, `show_body`가 `MarkdownEditor.attach_document`로
  문서를 통째로 교체한다. 각 문서가 자기 undo 스택을 들고 있으므로 탭을 옮겨다녀도 이력이 유지된다.
  `document_for`는 문서가 이미 있으면 **모델과 비교하지 않고 그대로 돌려준다** — 모델을 다시
  밀어넣으면 이력이 날아가기 때문. 모델이 외부 경로로 바뀐 경우에만 `sync_from_model`을 쓴다
  (이때는 이력 초기화가 의도된 동작).
- **문서가 편집 중 진실이고 모델은 미러다.** `textChanged` → `_save_body`가 `component.body`를
  계속 따라가며, undo/redo도 `textChanged`를 발생시키므로 되돌린 내용이 모델에 자동 반영된다.
- **Qt 함정 2종(둘 다 실측):** ① 맨 `QTextDocument()`는 `QPlainTextEdit`이 거부한다
  ("Document set does not support QPlainTextDocumentLayout") — 생성 시
  `doc.setDocumentLayout(QPlainTextDocumentLayout(doc))`가 필수. ② `QSyntaxHighlighter`는 생성 시
  넘긴 **문서를 부모로 삼기 때문에**, 문서를 교체하면 이전 문서와 함께 파괴된다
  ("Internal C++ object (MarkdownHighlighter) already deleted"). `MarkdownEditor.__init__`이
  `self._highlighter.setParent(self)`로 부모를 에디터로 옮겨 두는 이유다.
- **수명주기 배선:** `app.set_project`가 `registry().clear()`(프로젝트 전환),
  `app._on_delete_component`가 `discard(component)`.
- **검증 함정:** 왕복 없이 undo만 확인하면 고장이 있어도 통과한다 — 반드시 **다른 컴포넌트로
  전환했다 복귀한 뒤** undo를 검증해야 한다(`tests/view/editors/test_body_documents.py`).
  타이핑 시뮬레이션도 `setPlainText`가 아니라 `QTextCursor.insertText`여야 한다(전자는 undo 스택을 지운다).

## 컴포넌트 삭제 커맨드 (A2)

삭제만 undo가 안 되던 이유는 `remove_component`의 정리 범위가 넓어서였다 —
되돌리려면 그 내역 전부를 기록·복원해야 하고, 부분 복원 커맨드는 없느니만 못하다.

- **수제 스냅샷 대신 기존 커맨드 조립.** `RemoveComponentCmd`(MacroCommand 서브클래스)는
  캔버스 정리를 `DeleteRefCmd` → `DeleteTransitionCmd` → `DeleteStateCmd` 순서로
  조립하고(`_canvas_cleanup_commands`), **모델 전용 잔여분만** `_DetachComponentCmd`가
  맡는다. 순서 덕에 잔여분이 작아진다 — 캔버스 커맨드가 placement를 먼저 떼어내므로
  `remove_component`가 그 단계에서 할 일이 남아 있지 않고, 남는 것은 목록 제거·잔여
  reference_placements·다른 FSM의 skill_ref None화 셋뿐이다.
- **재사용이 나은 실질적 이유는 뷰모델 identity 보존이다.** undo가 **같은**
  `StateViewModel`/`TransitionViewModel` 객체를 되돌려 놓으므로 노드 좌표·엣지
  경유점이 layout dict 왕복 없이 그대로 살아난다. 모델만 복원하고 VM을 새로 만들면
  전이 VM이 캔버스에 없는 유령 노드를 가리켜 엣지가 허공에 그려진다.
- **그래서 `delete_component`는 `GraphIO.load_project_graph()`를 부르지 않는다.** 부르면
  VM이 통째로 새 객체로 갈리고, undo가 되돌려 놓을 옛 VM과 캔버스의 VM이 서로 다른
  물건이 된다. 레지스트리 갱신도 따로 하지 않는다 — `execute`의 notify가
  `_on_project_vm_changed` → `set_placed_ids` → `_rebuild`를 태우고, 그 rebuild가
  프로젝트 목록을 처음부터 다시 읽으므로 undo 복원도 같은 경로로 반영된다.
- **이름 참조는 건드리지 않는다.** `AgentConfig.skills` / `ProceduralSkillConfig.agent`에
  남은 이름은 `remove_component`도 지우지 않으므로 커맨드도 지우지 않는다 — 지우면
  되돌려도 참조가 돌아오지 않는 비대칭이 된다. MCP `delete_component`가 그 목록을
  `still_referenced_by`로 보고하고, `dangling_string_reference` 경고가 F7에서 짚는다.
- **graph_layout/edge_layout의 스테일 키는 남는다**(캔버스 커맨드가 dict를 건드리지
  않으므로). 무해하다 — `_save_graph_layout`이 저장 직전 VM으로부터 dict를 **통째로
  새로 만들어** 대입하므로 저장 시점에 사라진다.
- **본문 문서 캐시(WP-BU)는 삭제 시 버린다.** 되돌리면 본문 자체는 모델에 살아
  돌아오고 탭을 다시 열 때 문서가 새로 만들어진다 — 잃는 것은 본문 편집 이력뿐이다.
  닫힌 편집 탭도 undo로 다시 열리지는 않는다.

## 탭 배선 — `view/editor_tabs.py` (WP-7 ①)

- **역할:** 고정 탭 6개(0 FSM 캔버스 · 1 블랙보드 · 2 훅 · 3 CLAUDE.md · 4 규칙 · 5 설정) 구축과
  컴포넌트 편집 탭의 수명주기(열기·닫기·제목 동기화·종류 전환 후 폼 재생성·포트 포커스),
  그리고 탭 전환이 좌우하는 활성 undo 스택 배선이 `EditorTabs(window)` 하나에 모인다.
  `MainWindow`의 협력 객체다(Mixin 아님 — `session_io`/`component_actions`와 같은 관례).
- **왜 나왔나:** `app.py`가 1,072줄로 분해 예산(~800줄)을 넘겼고, 탭에 관한 것이 한 덩어리로
  떨어져 나올 수 있었다(코드 위생 — "기능을 더하기 전에 먼저 쪼갠다"). WP-7 ②가 여기에
  `KIND_UI` 조회를 얹는다.
- **소유·위임:** 탭 인덱스 상수(`_FSM_TAB_INDEX` … `_FIXED_TAB_INDEXES`·`_LOCAL_ONLY_TAB_INDEXES`·
  `_LAST_FIXED_TAB_INDEX`)와 `_tab_prefix`의 **소유자는 이 모듈**이고, `app.py`는 **같은 객체**를
  재-export한다(테스트·`validation_actions`가 `daedalus.view.app` 경로로 임포트해 왔다 — 복제하면
  두 벌이 되어 인덱스가 갈린다). 창에는 `_open_component`/`_close_tab` 등 한 줄 위임만 남는다 —
  테스트와 MCP 도구가 창의 내부 메서드를 직접 부른다.
- **상태의 단일 진실은 계속 윈도우다**(`_tabs`/`_open_tabs`/`_fsm_scene`/고정 패널들) —
  협력 객체는 복제하지 않고 `self._w.<attr>`로 직접 읽고 쓴다.

## 종류의 뷰 표면 — `view/kind_ui.py` (WP-7 ②)

- **역할:** "이 종류가 화면에서 어떻게 보이고 무엇으로 편집되는가"의 등록 지점.
  한 행(`KindUI`)이 아이콘·섹션 라벨·색·탭 라벨·캔버스 노드 스타일·다이얼로그 제목·
  편집기 팩토리·탭 접두·종류 전환 라벨/툴팁·활성 토글 여부·최초 배치 질문을 들고,
  레지스트리 팔레트·캔버스 노드·편집 탭·전환 메뉴가 **같은 행**을 읽는다.
- **왜 하나인가:** 예전에는 뷰 안에서만 열다섯 벌이었다(`_ICON`·`_sections`·
  `tab_labels`·`_rebuild` isinstance 사다리·`_TYPE_STYLE`·`_COMPONENT_TITLES`·
  `KIND_LABELS`/`KIND_NOUNS`/`_KIND_TOOLTIPS`·편집기 클래스 전수 열거·`_tab_prefix`·
  `NO_PLACE_KINDS`). 표가 여럿이면 새 종류는 예외 없이 **조용히** 빠진다 — 아이콘
  없는 행, **빈 상태와 구분되지 않는 회색 노드**(한 종류가 실제로 겪었다,
  사용자 보고 2026-09-07), 열리지 않는 편집 탭.
- **거절은 시끄럽다:** `ui_for(component)`는 표에 없는 종류에 **이름과 등록된 종류
  목록을 담은 ValueError**를 낸다(원칙 5). `tests/test_registry_failure_is_loud.py`가
  행 하나를 지우고 팔레트 구축이 그 이름을 찍고 죽는지 본다.
- **모델이 아니라 뷰에 있는 이유:** `QColor`·위젯 팩토리는 Qt이고 core는 Qt를
  임포트할 수 없다(import 계약). 두 레지스트리는 **kind 문자열로만** 연결되고
  방향은 view → model 한쪽이다. 그래서 등록 지점은 최소 둘이고(모델 `KIND_REGISTRY`
  + 뷰 `KIND_UI`), 두 집합이 같은지는 `tests/test_kind_registry_parity.py`가
  **양방향 등식**으로 고정한다 — 한쪽만 등록하면 좋은 실패가 난다.
- **자동 생성 금지:** 모델 레지스트리를 순회해 기본값을 만들어 주면 "UI가 없는
  종류"가 회색 기본 스타일로 조용히 그려진다 — 없애려는 바로 그 실패 양식이다.
- **위젯 클래스를 값으로 들지 않는다:** `editor_factory`는 호출 가능 객체이고
  편집기 임포트는 그 안에서 지연된다.

## 레지스트리 도크의 탭 구성 — `view/panels/registry_panel.py` (WP-C)

탭은 세 갈래이고 **전부 파생**이다(손으로 적은 탭 목록이 없다).

1. **종류 섹션** — `config_kinds_in(SKILLS) + config_kinds_in(AGENTS)` 순서가 곧 탭
   순서다(결정성). 섹션 하나가 종류 **여럿**을 담을 수 있다: `KindUI.section_group`이
   같은 종류는 한 탭을 나눠 쓰고, 라벨·색·탭 라벨은 **선언 순서상 첫 멤버**의 행에서
   온다(표를 하나 더 두지 않는다). 오늘 유일한 그룹은 🔌 EXTERNAL AGENTS(외부
   그래프 노드 + 외부 fork 기반)다. `_section_of_kind`가 종류 → 섹션 배정표이고
   `tests/view/test_component_mgmt_ui.py`가 "어느 종류도 갈 곳이 없지 않다"를 고정한다.
2. **🔌 탭 하단의 미등록 목록** — 컴포넌트가 아닌 **카탈로그 항목**이다
   (`view/panels/external_registry.UnregisteredAgentsList`). 담는 종류가 전부
   `BODY_SOURCE=EXTERNAL`이고 버킷이 AGENTS인 섹션에만 붙는다(선언 파생).
3. **🧷 EXTERNAL SKILLS 탭** — 종류 섹션 뒤에 하나 더 붙는 카탈로그 섹션
   (`ExternalSkillsSection`). 컴포넌트가 아니므로 `_sections`에 들지 않는다.

- **섹션 파생은 `__init__` 시점**이다 — 모듈 상수로 접으면 `KIND_UI` 행이 빠진 종류의
  거절이 임포트 실패로 번져 이유를 잃는다(`test_registry_failure_is_loud`는 팔레트
  **구축**이 그 종류 이름을 찍고 죽는지를 본다).
- **"+"의 뜻이 갈린다** — 외부 정본만 담는 섹션은 이름을 물어 만들 수 없어
  카탈로그 창을 열고(`catalog_requested`), 나머지는 종전대로 이름 다이얼로그
  (`new_component_requested`)다. 판정은 `BODY_SOURCE` 선언이지 종류 목록이 아니다.
- **패널은 실체를 들지 않는다** — 등록·추가는 시그널로 창에 올리고 창이
  `view/actions/external_registration`을 부른다(MCP와 같은 함수). 목록을 무엇으로
  채울지도 모델 함수가 답한다(`unregistered_plugin_agents`/`used_plugin_skill_refs`/
  `skill_ref_users`).
- **카탈로그 스캔은 캐시된다** — `set_project`(프로젝트 교체)와 `refresh_catalog`
  (카탈로그 창 닫힘)에서만 `scan_catalog()`를 부르고 결과를 유도 함수에 주입한다.
  `_rebuild`는 구조 notify마다 도므로 여기서 폴더를 훑으면 편집 중 화면이 멈춘다.

## 컴파일 미리보기 (A9-1) — 진입점 넷, 실체 하나

"그래서 이게 어떤 파일로 나가는데?"를 여는 표면은 넷이다 — 캔버스 노드 우클릭
(`view/canvas/context_menus.add_component_actions_menu`), 레지스트리 우클릭
(`view/panels/registry_panel` → `MainWindow._on_preview_component`), 프론트매터
패널의 "미리보기" 버튼(`view/editors/frontmatter_panel`), 그리고 전이 엣지 우클릭
(`view/canvas/scene._handle_transition_edge_menu`) — 전이 스킬은 캔버스 노드가 아니라
엣지에 붙어 placement 메뉴가 닿지 않기 때문이다.

**넷 다 같은 함수를 부른다** — `view/actions/preview.show_preview_dialog` →
`compiler/preview.preview_component`. 텍스트·경로·토큰 구간의 실체는 컴파일러 쪽
하나이고(WP-6), MCP `compile_preview`도 같은 함수다(MCP 패리티). 뷰에 남은 것은 Qt
다이얼로그와 제목 문자열뿐이다: 제목의 파일명은 `compiler/preview.preview_path`가
`OUTPUT_LOCATION`에서 유도한다(종전에는 `isinstance(component, Agent)`였다).

**액션 비활성 판정도 공용이다** — `compiler/preview.can_preview(component)`. 잠그는
대상은 산출 **자리**가 아예 없는 종류(`OUTPUT_LOCATION is NONE`)뿐이다.
`emits_output()`으로 걸면 안 된다: 이번 빌드에 파일이
나가지 않는 컴포넌트도 "무엇으로 컴파일되는가"는 볼 수 있고, 실사용 프로젝트의 컴포넌트가
전부 그 경로다. `tests/compiler/test_preview.py`가 양방향으로 고정한다(진입점 **넷
전부**가 `can_preview`를 쓰고 `emits_output`을 쓰지 않음을 AST로 본다 —
`_PREVIEW_ENTRY_POINTS`의 파일 수가 이 절의 진입점 수와 같아야 한다).

## 미저장 변경 확인

편집 결과는 저장 전까지 **메모리에만** 있다. MCP로 편집하고 GUI를 그냥 닫아
통째로 잃은 사고가 세 번 났다 — `closeEvent`가 확인 없이 닫았기 때문이다.

- **더티 판정은 notify 양 채널 구독이다.** `MainWindow._dirty`를 `_setup_central`이
  `ProjectViewModel`의 **structure + content 두 채널 모두**에 `_mark_dirty`로 등록해
  올린다. `notify("content")`는 content 리스너만 부르므로(구조 리스너에게 전파되지
  않는다) 한쪽만 등록하면 **본문 타이핑이 통째로 새어 나간다**. 본문 편집은
  `body_documents`의 QTextDocument → `SectionContentPanel.content_changed` →
  content 채널을 타므로 이 등록이 그것을 잡는 유일한 경로다.
- **내리는 지점은 둘뿐이다.** `SessionIO.save_to_path` 성공 직후(제목 갱신 **전** —
  같은 호출에서 `*`가 지워져야 한다)와 `MainWindow.load_project` **끝**. 후자가
  로드 뒤인 이유는 로드 과정의 notify가 `_mark_dirty`를 깨우기 때문이고, 호출자
  (`open_path`/`new_project`)마다 내리게 하면 새 경로가 생길 때 빠뜨린다.
- **제목의 `*`**: `SessionIO.update_title`이 dirty면 앞에 붙인다. `_mark_dirty`는
  이미 dirty면 즉시 반환해 키스트로크마다 `setWindowTitle`이 돌지 않게 한다.
- **`confirm_discard_changes()`가 종료 가부를 돌려준다**(저장/버리기/취소). "저장 후
  종료"인데 저장이 실패하거나 경로 선택을 취소해 여전히 dirty면 **False** —
  저장하겠다고 답한 사용자의 변경을 버리는 것이 바로 이 기능이 막으려던 사고다.
  취소로 닫기를 막으면 MCP 서버도 내리지 않는다(세션이 계속되므로).
- **테스트 함정:** 편집 직후 `window.close()`를 부르는 테스트가 수십 개라 확인
  다이얼로그가 그대로 뜨면 헤드리스 스위트가 멈춘다. 루트 `tests/conftest.py`의
  autouse 픽스처가 `MainWindow.confirm_discard_changes`를 항상 True로 덮어쓴다.
  확인 로직 자체를 검증하는 `tests/view/test_unsaved_changes.py`는 **모듈 임포트
  시점**에 잡아 둔 원본 함수를 직접 호출한다(임포트가 픽스처보다 먼저 돈다).
