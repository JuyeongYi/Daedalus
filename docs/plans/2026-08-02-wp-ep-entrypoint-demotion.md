# WP-EP — 프로젝트 그래프 EntryPoint 격하 (CC 의미론 정합)

## 배경

CC 플러그인 최상위에는 단일 진입점이 없다 — user_invocable 스킬은 전부 `/skill`로
독립 시작 가능하고 모델 자동 인보크도 있다. 프로젝트 캔버스의 EntryPoint("start"
마커 + 시작 전이 긋기)는 FSM 관념의 잔재이며, 컴파일러도 EntryPoint outgoing을
산출에 쓰지 않는다("다음 단계" v1 정책에 명시). 사용자 피드백: "user invocable이면
전부 시작 가능해져서 별도의 시작점이 필요하지 않음."

**에이전트 FSM의 EntryPoint/ExitPoint는 절대 건드리지 않는다** — 에이전트는 별도
컨텍스트의 단일 진입이 실재한다. 이 WP는 **프로젝트 그래프(캔버스 탭 0)의 투영과
검증**에만 적용된다.

## 확정 설계 (모델 불변, 투영·검증만 변경)

- `_make_project_graph()`는 계속 합성 `EntryPoint(name="start")`를 `initial_state`로
  갖는다 — `StateMachine.initial_state` required 유지, 직렬화 포맷 불변, 구버전
  파일(EntryPoint + 시작 전이 포함) 로드 왕복 호환.
- 변경점: ① 프로젝트 캔버스가 EntryPoint와 그에 닿는 전이를 **그리지 않는다**,
  ② 프로젝트 그래프 검증에서 `unreachable_state`를 **스킵**한다.
- `scene.py`의 EntryPoint 삭제-방어 코드는 **그대로 둔다** — 에이전트 캔버스
  (AgentFsmScene)와 공용 경로라 제거하면 위험하고, 프로젝트 캔버스에서는 VM이
  없어져 자연히 죽은 경로가 된다(무해).

## Part A — view: 프로젝트 캔버스 비노출

`daedalus/view/app.py`의 `_load_project_graph`(~229행부터 — EntryPoint 마커 +
placement + 전이를 VM으로 복원하는 함수):

1. `graph.states` 순회에서 `EntryPoint` 인스턴스를 **스킵** — VM/노드 아이템을 만들지
   않는다 (현재 `entries`/`others` 분리 코드를 정리).
2. 전이 복원에서 source 또는 target이 EntryPoint인 전이를 스킵 (구버전 파일의
   시작 전이 — 모델에는 남고 화면에만 안 나온다). 이때 경고/에러를 내지 않는다.
3. `_save_graph_layout`: EntryPoint 좌표를 저장하지 않는다 (VM이 없으니 자연
   충족될 것 — 확인만). 로드 시 graph_layout에 EntryPoint 키가 있어도 무시.
4. `app.py:356` 부근 "빈 그래프" 판정(`len(...states) > 1  # EntryPoint 제외`)은
   의미 불변이므로 유지.
5. `FsmScene`의 VM→모델 동기화(sync)가 "모델에는 있으나 VM이 없는 상태"를
   허용하는지 확인하고, EntryPoint 부재로 예외/경고가 나면 스킵 처리를 추가한다.

주의: `agent_editor._load_agent_fsm`의 EntryPoint 자동 추가/배치 로직(131~193행)은
에이전트 전용이므로 **절대 수정 금지**.

## Part B — validation: 프로젝트 그래프 도달성 스킵

`daedalus/model/validation.py`:

1. 머신 수준 검증 진입점에 `skip_rules: frozenset[str] = frozenset()` 파라미터를
   추가한다 (기본값이 빈 집합이라 기존 호출 전부 하위 호환). 해당 규칙 이름의
   검사를 생략한다. 재귀(sub_machine/Region)에는 **전파하지 않는다** — 프로젝트
   그래프 자체에만 적용.
2. `validate_project`의 프로젝트 그래프 검증 호출에 `skip_rules={"unreachable_state"}`
   를 전달한다. 근거: CC 의미론상 최상위 배치는 전부 독립 시작점이라 "도달 불가"가
   성립하지 않는다.
3. 스킬/에이전트 FSM(및 그 하위 재귀)에서는 `unreachable_state` 규칙이 기존대로
   동작해야 한다.

## Part C — 테스트

신규/갱신 (`tests/view/`·`tests/model/` 적절한 위치):

1. 프로젝트 로드 후 캔버스 VM 목록에 EntryPoint가 없다 (데모 프로젝트 + 직렬화
   왕복 프로젝트 양쪽).
2. 구버전 형태 파일(EntryPoint + EntryPoint→스킬 전이 포함 직렬화 dict) 로드 시
   예외/경고 없이 성공하고, 그 전이는 캔버스에 렌더되지 않으며, 저장 왕복 후에도
   모델에 EntryPoint가 보존된다.
3. `_save_graph_layout` 결과에 EntryPoint의 state.id 키가 없다.
4. 고아 배치(전이 0개 placement)가 있는 프로젝트 그래프 → `unreachable_state`
   경고가 나오지 않는다.
5. 에이전트 FSM의 도달 불가 상태 → 여전히 `unreachable_state` 경고가 나온다
   (스킵 미전파 확인).
6. `skip_rules` 기본값 경로: 인수 없이 호출한 머신 검증 결과가 기존과 동일하다
   (기존 검증 테스트 전체가 이를 보증 — 깨지는 게 없어야 한다).

기존 테스트 중 프로젝트 캔버스의 EntryPoint 마커 존재를 단언하는 것들
(`tests/view/canvas/test_project_graph_sync.py` 등 — grep으로 전수 확인)을 새
의미론에 맞게 갱신한다.

`python -m pytest tests/ -q` 전체 통과(현재 920 + 신규, 회귀 0)가 완료 조건.

## 비목표

- `StateMachine.initial_state` Optional화, EntryPoint 모델/직렬화 삭제·변경
- 에이전트 FSM의 EntryPoint/ExitPoint 관련 일체 (agent_editor, AgentFsmScene,
  node_item의 entry_point 스타일 — 전부 불변)
- scene.py의 EntryPoint 삭제-방어 코드 제거 (에이전트 캔버스 공용 — 존치)
- 컴파일러 변경 (EntryPoint outgoing은 이미 무시됨)
- `transfer_on_not_empty` 등 다른 검증 규칙 변경

## 작업 관례

- 브랜치 `wp-ep` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- CLAUDE.md의 "PluginProject.graph = 워크플로 백킹 머신" 단락과 Validator 규칙 표의
  `unreachable_state` 행을 새 의미론으로 갱신.
