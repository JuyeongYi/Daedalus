# WP-DG — Delegation 단계적 격하 (deprecated)

## 배경

사용자 실측: 스킬 본문에 "다이나믹 워크플로우를 사용하라" 수준의 지시를 서술하면
CC가 알아서 Workflow/Agent 도구를 호출한다. 위임 노드(TeamSpawn/DynamicWorkflow/
AgoraDispatch)의 컴파일 산출도 결국 같은 프롬프트 문구라, 전용 모델 3종 + 에디터 +
컴파일러 스펙 4절 + 검증 3규칙의 유지비가 가치를 넘어섰다. CC에서 팀 기능은
다이나믹 워크플로우로 흡수되는 추세이기도 하다.

**정책: 완전 삭제가 아니라 격하.** 신규 생성 UI만 제거하고, 기존 프로젝트의 위임은
로드·표시·편집·배치·삭제·직렬화·컴파일·검증 전부 유지한다. 완전 삭제는 실전
플러그인을 몇 개 더 돌린 뒤 별도 WP로 결정한다.

## 현재 생성 진입점 (실측 — 이 두 곳이 전부)

1. **RegistryPanel** (`daedalus/view/panels/registry_panel.py`): `"delegation"`
   `_RegistrySection`의 "+" → `new_component_requested("delegation")` →
   `app.py _on_new_component`의 delegation 분기 → `_on_new_delegation()`
   (종류 선택 QInputDialog → 이름 → `project.delegations.append`).
2. **AgentEditor** (`daedalus/view/editors/agent_editor.py`): 그래프 사이드바
   `_deleg_section`의 "+" → `_on_add_delegation()` (같은 흐름, ~267행).

## Part A — view: 신규 생성 경로 제거

1. `_RegistrySection`에 add 버튼을 숨기는 옵션을 추가한다 (기존 `no_place` 옵션과
   같은 방식의 생성자 플래그, 예: `no_add: bool = False`). "+" 버튼 위젯을 만들지
   않거나 숨긴다.
2. **RegistryPanel**: delegation 섹션에 `no_add=True` 적용 + 섹션 타이틀을
   `"🛰 DELEGATION (deprecated)"`로 변경. `_rebuild`에서 위임 항목이 0개면 섹션을
   `setVisible(False)`, 1개 이상이면 `setVisible(True)` (기존 항목 보유 프로젝트는
   계속 보임).
3. **AgentEditor**: `_deleg_section`에도 동일하게 add 버튼 제거 + 빈 목록 시 숨김
   (해당 섹션 구성 코드를 찾아 같은 플래그 적용).
4. 죽은 코드 제거: `app.py`의 delegation 분기(`_on_new_component` 내)와
   `_on_new_delegation` 메서드, `agent_editor.py`의 `_on_add_delegation`과 그
   시그널 연결부를 삭제한다. **더블클릭 편집(`_open_delegation`)·삭제·캔버스
   배치(드래그) 경로는 절대 건드리지 않는다.**
5. **DelegationEditor** (`delegation_editor.py`) 다이얼로그 상단에 안내 라벨 1줄:
   `"⚠ 위임 노드는 deprecated — 스킬 본문에 위임 지시를 직접 서술하는 방식을 권장합니다."`
   (스타일은 기존 다이얼로그 관례를 따름, 편집 기능은 그대로.)

## Part B — 문서 (CLAUDE.md)

- `delegation.py` 항목에 "(deprecated — 신규 생성 UI 제거, 기존 프로젝트 호환용
  존치. 권장 경로: 스킬 본문에 위임 지시 서술)" 표기.
- 컴파일 정책 5번(위임 노드)과 검증 규칙 표의 위임 관련 행은 그대로 두되, 위임
  단락 어딘가에 "격하(deprecated) 상태" 한 마디를 덧붙인다.

## Part C — 테스트

1. 빈 프로젝트(`PluginProject(name="p")`) → RegistryPanel의 delegation 섹션이
   비표시(`isVisible()` False 또는 add 버튼 부재 — 구현 방식에 맞는 단언).
2. 위임 보유 프로젝트 → 섹션 표시 + 항목 렌더 + `component_double_clicked`/
   `component_delete_requested` 시그널 경로가 기존대로 동작.
3. delegation 섹션(및 AgentEditor `_deleg_section`)에 add 버튼이 없다/숨겨져 있다.
4. 기존 위임 관련 테스트(직렬화 왕복·컴파일 스펙 4절·검증 3규칙·배치) 전부
   무수정 통과 — 격하가 기능 회귀를 만들지 않았음의 증명.

`python -m pytest tests/ -q` 전체 통과(현재 929 + 신규, 회귀 0)가 완료 조건.

## 비목표

- 모델 3종(delegation.py)/직렬화/컴파일러 스펙 4절/검증 규칙(empty_delegation,
  forget_completion_mismatch, dangling_teammate_ref, unregistered_delegation) 삭제
  — 전부 존치
- 기존 위임의 편집·배치·삭제 기능 변경
- 스킬 본문 "위임 스니펫" 슬래시 메뉴 항목 추가 (후속 후보 — 이 WP 범위 밖)

## 작업 관례

- 브랜치 `wp-dg` (이미 생성돼 있으면 체크아웃만). master 직접 작업 금지.
- 테스트는 반드시 `python -m pytest tests/ -q` (pytest 직접 실행 불가).
- Pyright 진단은 스테일이 잦다 — 런타임 테스트로 판정.
- 커밋은 Part 단위 이상, 메시지는 한국어. push 금지.
- Qt 바인딩은 PySide6. QTest 타이핑 입력은 ASCII만.
