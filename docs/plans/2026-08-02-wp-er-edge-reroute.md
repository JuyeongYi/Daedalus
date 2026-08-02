# WP-ER — 연결선 리루트 (엣지 웨이포인트)

## 배경

사용자 요청: "이전 노드로 돌아갈 때 연결선 정리가 힘들다 — 리루트 기능이 있었으면
함." 루프 전이(예: DTest 샘플의 suggest-fixes → test-runner → review-code rework
재진입)가 노드들을 가로질러 그려져 캔버스가 어지럽다. 엣지에 **경유점(waypoint)**을
추가·드래그해 경로를 손으로 정리할 수 있게 한다.

## Part A — 저장 모델 (graph_layout 관례 미러링)

1. `PluginProject.edge_layout: dict[str, list[list[float]]]`와
   `AgentDefinition.edge_layout`(동일 타입) 추가 — **키는 Transition.id**(안정
   식별자, graph_layout의 state.id 규약과 동일), 값은 경유점 좌표 `[x, y]` 목록
   (소스→타깃 순서).
2. serialize: 왕복 + 구버전 키 부재 → 빈 dict(경고 없음).
3. 저장 직전 기록·로드 시 복원 — `app._save_graph_layout`/`_load_project_graph`와
   `agent_editor`의 대응 지점에 미러링(참조 배치 복원과 같은 위치). 웨이포인트는
   뷰 관심사이므로 fsm 모델(Transition)에는 넣지 않는다 — graph_layout 전례.

## Part B — 렌더: 경유점 경유 경로

`view/canvas/edge_item.py` (`TransitionEdgeItem` — 프로젝트/에이전트 캔버스 공용):

1. VM(TransitionViewModel)에 `waypoints: list[tuple[float, float]]` 추가(기본 빈
   리스트). 엣지 경로를 소스 포트 → 경유점들 → 타깃 포트 순으로 그린다 — 경유점
   구간은 부드러운 곡선(기존 곡선 스타일 유지, 각 경유점을 통과)으로. 경유점이
   없으면 기존 렌더와 동일(하위 호환 — 기존 렌더 테스트 불변이 판정 기준).
2. 화살촉·라벨 위치는 마지막 구간 기준으로 기존 로직 유지.

## Part C — 상호작용

1. **경유점 추가**: 엣지 **더블클릭** — 클릭 지점에 경유점 삽입(경로상 가장 가까운
   구간의 순서 위치에). 컨텍스트 메뉴에도 "경유점 추가" 항목(같은 동작).
2. **드래그**: 엣지 선택 시 경유점 핸들(작은 원, 포트 색 계열)을 표시하고 드래그로
   이동. 비선택 시 핸들 숨김(캔버스 잡음 방지).
3. **제거**: 핸들 우클릭 → "경유점 제거", 또는 핸들 선택 후 Delete. 컨텍스트
   메뉴에 "경유점 모두 제거"(직선 복원)도 추가.
4. **undo**: 추가/이동/제거를 기존 커맨드 관례에 맞춘다 — 노드 이동이 커맨드화되어
   있으면 동일하게, 아니면 기존 관례(직접 변경 + notify) 그대로. 구현 전 노드
   드래그 이동의 실제 처리 방식을 확인해 **일관되게** 하라.
5. 프로젝트 캔버스(FsmScene)와 에이전트 캔버스(AgentFsmScene) 모두 동작.

## Part D — 테스트

1. serialize: edge_layout 왕복(프로젝트/에이전트) + 구버전 부재 기본값.
2. 렌더: 경유점 있는 엣지의 경로가 경유점을 통과(path 상 최근접 거리 ≈ 0),
   경유점 없으면 기존 경로와 동일(기존 테스트 불변).
3. 상호작용: 더블클릭 추가(경로 순서 위치), 핸들 드래그 → VM·모델 반영,
   제거/모두 제거, 저장→로드 왕복 후 경유점 보존.
4. `python -m pytest tests/ -q` 전체 통과 (현재 1144 기준, 회귀 0).

## 비목표

- 자동 라우팅(장애물 회피, 직교 라우팅) — 수동 경유점만 (v1)
- RefEdgeItem(참조 연결선) 경유점 — 전이 엣지만
- 경유점 스냅/그리드

## 작업 관례

- 브랜치 `wp-er` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- CLAUDE.md 갱신: edge_layout(모델·직렬화), 캔버스 리루트 상호작용 반영.
