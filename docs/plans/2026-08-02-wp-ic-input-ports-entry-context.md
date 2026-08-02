# WP-IC — 입력 포트 + 진입 맥락 배출

## 배경·확정 설계

- 출력 쪽은 `transfer_on`(출력 포트)이 있지만 입력 쪽은 뷰 전용 렌더뿐, 모델 개념이
  없다. 도착 스킬은 자기가 어디서·어떤 경로로 진입했는지 모른다.
- **입력 상태**(어떤 상태로부터 전이) ≠ **입력 포트**(이 상태에 이 경로로 접근).
  둘 다 컴파일 섹션으로 배출하고, 진행 저장에 `prev`를 추가한다 (사용자 확정).
- 한 입력 포트에 여러 연결이 오면 **연결선이 그 포트 한 점에 수렴**해야 한다.

## Part A — model

1. `entry_paths: list[EventDef] = field(default_factory=list)` 추가 —
   `ProceduralSkill`/`DeclarativeSkill`/`AgentDefinition`. 빈 리스트 = 기본 포트
   1개(암묵, 이름 없음) — 기존 파일·기존 렌더와 호환.
2. `Transition.target_port: str = ""` — 빈 값 = 기본 포트. entry_paths의 EventDef
   이름을 문자열로 참조(rename 고아는 Validator가 검출).
3. serialize: 둘 다 왕복, 구버전 키 부재 → 기본값(경고 없음).

## Part B — canvas: 포트 렌더 + 수렴

1. placement 노드의 입력 포트 수 = `max(1, len(skill_ref.entry_paths))`.
   포트 라벨은 출력 포트 라벨과 대칭(포트 오른쪽·본체 안, EventDef.color 사용).
2. 엣지의 도착 끝점을 `target_port` 인덱스의 포트 y 좌표에 앵커 — **같은 포트의
   여러 연결은 자연히 한 점에 수렴**한다. target_port가 빈 값이거나 이름이
   entry_paths에 없으면 기본(첫) 포트.
3. 전이 생성 시 드롭 지점에서 **가장 가까운 입력 포트에 스냅**해 `target_port`
   기록(포트 1개면 빈 값 유지 — 하위 호환).
4. entry_paths 편집 UI: 스킬 에디터의 transfer_on(출력 이벤트) 편집과 대칭 위치·
   패턴으로 "입력 경로" 편집(이름/색/설명). 구현 전 transfer_on 편집 실경로 확인.

## Part C — compiler: 진입 맥락 + prev + 호출 계약

1. **"## 진입 맥락" 단락** — 배치된 전역 스킬(Procedural/Declarative)에서 incoming
   전이가 1개 이상이면, "## 작업 재개" 프리앰블 뒤·본문 앞에 배출:
   - 도입: "`state/__progress__.json`의 `prev`를 확인하고 아래에서 해당 출처
     항목을 따르라."
   - **포트별 그룹**: `### 경로: <port name>` + EventDef.description
     (기본 포트 그룹은 `### 기본 경로` — entry_paths가 없거나 target_port 빈 전이).
     incoming이 있는 포트만 배출.
   - 그룹 안 **출처별 항목**: "- `<출처>`에서 [<조건>]로 진입: <설명>" — 조건은
     `_transition_condition` 재사용. 엣지에 TransferSkill이 있으면 "전이 스킬
     `X`(`<description>`)의 지침을 수행한 상태다" 합류. 출처가 에이전트 placement면
     "에이전트 `X`의 위임 완료 후" 문구.
   - 정렬: 포트는 entry_paths 선언 순서(기본 경로 마지막), 출처는 이름순 — 결정적.
2. **progress 규약에 `prev`**: `_PROGRESS_UPDATE_NOTE`에 "`prev`에 자신(이 스킬
   이름)을" 추가, 재개 프리앰블 JSON 예시에 `"prev": ""` 포함. (RS 규약 확장 —
   CLAUDE.md 12번 항목 갱신.)
3. **caller_contracts 배출** (기존 누락 해소): `compile_agent`가 caller_contracts가
   비어 있지 않으면 본문 뒤에 "## 호출 계약" 단락 — 각 Section을
   `### <title>` + content로 나열(선언 순서 유지).
4. 하위 호환: incoming 0개 배치·미배치·로컬은 변화 없음. incoming 있는 기존
   프로젝트는 진입 맥락 단락이 **새로 생기는 의도된 산출 변화**다(테스트 갱신 시
   검증 의도 유지).

## Part D — validation

- `dangling_target_port` — `Transition.target_port`가 비어 있지 않은데 타깃
  placement의 skill_ref `entry_paths` 이름 집합에 없으면 경고 (trigger_unknown_event의
  입력판, WARNING_RULES 등재). 타깃이 skill_ref 없는 상태면 스킵.

## Part E — 테스트

1. model/serialize: entry_paths·target_port 왕복 + 구버전 부재 기본값.
2. canvas: 포트 2개 스킬 placement의 입력 포트 렌더 수·라벨, 같은 target_port
   전이 2개의 도착 y 좌표 동일(수렴), 스냅 기록, 빈 값 하위 호환.
3. compiler: 진입 맥락 단락(포트 그룹/출처 항목/전이 스킬 합류/에이전트 출처
   문구/prev 도입부), 위치(작업 재개 뒤·본문 앞), incoming 0개 생략, 정렬 결정성.
4. compiler: prev 갱신 규칙 문구, 프리앰블 JSON에 prev.
5. compiler: caller_contracts 배출/빈 리스트 생략.
6. validation: dangling_target_port 검출/빈 값 스킵.
7. 전체 통과 (회귀 0 — 진입 맥락 신설로 갱신되는 기존 테스트는 검증 의도 유지).

## 비목표

- 스킬 내부 FSM 상태의 입력 포트 (플러그인 워크플로 수준만)
- 포트별 데이터 계약(스키마) — EventDef.description 산문으로 충분 (v1)
- UI에서 입력 포트/입력 상태 구분 노출 (사용자: "UI에서 드러날 필요는 없다" —
  포트 렌더와 수렴만, 별도 구분 표시 없음)

## 작업 관례

- 브랜치 `wp-ic` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
- CLAUDE.md 갱신: entry_paths/target_port(모델·직렬화), 캔버스 포트 수렴, 진입
  맥락·prev·호출 계약 배출(컴파일 정책), dangling_target_port(규칙 표), WP-RS
  규약(12번 항목)에 prev 반영.
