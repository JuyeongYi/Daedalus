# WP-RF: 대규모 리팩토링 계획

> 상태: **계획만 수립 — 실행 보류** (사용자 지시 2026-08-17).
> 후속 목표인 블랙보드 CLI(C+A — uv 동봉 `daedalus-bb` + 컴파일 지시 합류)의 선행 작업.
> 범위 3축은 사용자 확정: ① legacy 잔재 일소 ② core/GUI 분리 ③ 거대 파일 분해.

## 순서 원칙

**일소 → 경계 → 분해.** 지울 코드를 분해·이동하는 낭비를 막으려면 삭제가 먼저다
(RF-1이 이후 모든 단계의 표면적을 줄인다). 경계(RF-2)가 정해져야 분해(RF-3)의
목적지가 정해진다.

## 현황 실측 (2026-08-17)

| 파일 | 라인 |
|---|---|
| compiler/emit.py | 1,936 |
| mcp/tools.py | 1,923 |
| view/widgets/markdown_editor.py | 1,919 |
| model/validation.py | 1,751 |
| view/app.py | 1,574 |
| model/serialize.py | 1,381 |
| view/canvas/scene.py | 1,039 |

legacy 표면(파일 수, grep -ril): delegation 15 / ExitPoint 10 / entry_paths 8 /
target_port 5 / caller_contracts 4 / 로컬 스킬(agent.skills) ~8.

테스트 기준선: 1,694 passed / 1 skipped (f1f206b).

---

## RF-1: legacy 잔재 일소

퇴역 개념 4건(WP-CT 계약 카드, WP-AF 내부 FSM, WP-IP 입력 포트, delegation 격하)이
"구버전 파일 왕복 보존"을 이유로 모델 필드·직렬화·폴백 경로를 남겨 두었다. 이
잔재가 serialize.py(1,381줄)·validation.py·emit.py 비대의 큰 몫이다.

### 핵심 결정 (착수 전 사용자 확인)

1. **직렬화 포맷 v2 승격** — `"format": 2` + 로드 시 v1→v2 단방향 일괄
   마이그레이션(현재 흩어진 개별 마이그레이션들을 한 함수로 공식화), 모델의
   호환용 필드(`entry_paths`/`target_port`/`caller_contracts`/`exit_points`
   폴백)는 **삭제**. v1 왕복 보존은 포기한다(열면 v2로 저장됨).
   *권장: 채택.* 실사용자가 제작자 본인뿐인 도그푸딩 단계 — 왕복 보존의 수혜자가
   없다. 구버전 픽스처 파일을 tests에 보관해 마이그레이션을 고정한다.
2. **delegation 완전 삭제** — 모델(delegation.py)·에디터(delegation_editor.py)·
   레지스트리 탭·컴파일 4절·검증 규칙 4종(dangling_teammate_ref/
   unregistered_delegation/empty_delegation/forget_completion_mismatch)·직렬화.
   v1 파일에 위임이 있으면 로드 경고 후 드롭. *권장: 삭제* (신규 생성 UI는 이미
   없고, 권장 경로는 "스킬 본문에 위임 지시 서술"로 확정된 지 오래다).
3. **에이전트 로컬 스킬 퇴역 완결** — 생성 경로는 이미 없다(WP-AF). 남은 읽기
   경로(agent.skills 컴파일·`--` 결합·MCP `agent=` 인자·skill-files 매칭)를
   제거하고, v1 파일의 로컬 스킬은 로드 시 **전역 스킬로 승격**(이름 충돌 시
   `<agent>--<name>`으로 개명 + 경고). *권장: 승격 마이그레이션* — 드롭은 본문
   유실이다.

### WP 분할

- **RF-1a delegation 삭제** (결정 2) — 15개 파일. 컴파일 스펙 4절/1-b절 산출
  로직·테스트 동반 삭제. CLAUDE.md의 위임 항목 제거.
- **RF-1b 퇴역 필드 삭제 + 직렬화 v2** (결정 1) — entry_paths/target_port/
  caller_contracts/ExitPoint 폴백(output_events는 transfer_on 단일 진실로)/
  Section의 계약 카드 용도 서술 정리. `deserialize_project`에 v1→v2
  마이그레이션 집약. FieldType.NUMBER·TOOL_MATCH_EVENTS 별칭·policy.py
  JoinStrategy re-export 등 소형 별칭도 이 WP에서 일괄 정리.
- **RF-1c 로컬 스킬 승격 마이그레이션** (결정 3) — emit._agent_skills_list·
  `_local_skill_dir_name`·MCP `_find_component(agent=)`·field_matrix의
  `local_*` kind 제거.
- **체크포인트:** RF-1 완료 후 실프로젝트 `project/daedalus_cc_plugin` 로드 →
  검증 0/0 → 저장(v2) → 재로드 수동 확인.

---

## RF-2: core/GUI 경계 공식화

현황: `model/`·`compiler/`는 이미 Qt 무관(임포트 순수성 테스트 존재).
실질 결합 지점은 ① `mcp/tools.py`가 view(MainWindow·VM·body_documents)에 깊이
결합 ② `mcp/invoker.py`가 Qt 의존(의도된 설계) ③ view→compiler 방향 임포트
(SKILL_FILES_DIRNAME 등 — 방향 자체는 정상).

### 두 안

- **A안 — 물리 재배치**: `daedalus/core/{model,compiler}` + `daedalus/gui/`(현
  view) + `daedalus/cli/`(신설 자리). 전면 임포트 치환(소스+테스트 수백 지점).
  구조가 이름으로 드러나지만 이득 대부분이 미학이고 이력 추적 비용이 크다.
- **B안 — 경계 강제 + CLI 자리만 신설 (권장)**: 물리 이동 없음. 대신
  1. 임포트 계약 테스트 확장 — `model/`·`compiler/`·`mcp/endpoint.py`·(신설)
     `cli/`는 PySide6·view·mcp 서버 계열 임포트 금지를 테스트로 고정
     (기존 test_purity.py 확장).
  2. `daedalus/cli/` 신설 + pyproject `[project.scripts]`에 `daedalus-bb`
     자리 예약(빈 구현 아님 — RF 이후 블랙보드 CLI가 여기로 들어온다.
     RF-2에서는 스켈레톤 없이 계약 테스트에 경로만 등록).
  3. `mcp/tools.py`의 view 결합을 "GUI 어댑터"로 명시 — RF-3b에서 분해할 때
     조회/편집 로직과 Qt 마샬링을 나누는 근거가 된다.
  단일 패키지·단일 배포 유지(사용자 전제: `uv tool install`로 앱과 CLI가 함께
  설치 — PySide6 의존 경량화는 목표가 아니다).

*권장: B안.* A안은 사용자가 물리 분리를 명시적으로 원할 때만.

---

## RF-3: 거대 파일 분해

원칙: **분해 커밋은 이동만, 동작 불변** — 기존 임포트 경로를 재-export로
유지해 전체 테스트가 무수정 통과하는 것이 1차 게이트. 임포트 정리는 별도
후속 커밋. 컴파일 산출 문자열 바이트 동일(결정성) 게이트 병행. 파일당 1 WP.

| WP | 대상 | 분해안 |
|---|---|---|
| RF-3a | emit.py 1,936 | `compiler/emit/` 패키지 — frontmatter / skill(다음 단계·재개·진입 맥락) / agent(출구·호출 계약·skills 합류) / sections(블랙보드·요구 환경) / hooks. `emit.py`는 재-export 파사드 |
| RF-3b | mcp/tools.py 1,923 | 도메인별 믹스인 — query / session / canvas(구조) / ports / blackboard / hooks / body / project_props. `DaedalusTools`는 합성 클래스. TOOL_NAMES는 service.py에 유지 |
| RF-3c | markdown_editor.py 1,919 | `widgets/markdown/` 패키지 — highlighter / editor(드롭·단축키) / toolbar / search_bar / toc / slash_menu / providers(루트 provider들) |
| RF-3d | validation.py 1,751 | severity(WARNING_RULES·ValidationError) / machine_rules / project_rules — `validation.py`는 재-export 파사드(외부 참조 다수) |
| RF-3e | app.py 1,574 | MainWindow 골격 + session_io(저장/열기/최근/패키지) + compile_actions + mcp_actions + docks 배선 — Mixin이 아니라 협력 객체로 추출 |
| 보류 | serialize.py 1,381 | RF-1 삭제로 자연 축소 예상 — RF-1 후 재실측해 필요 시만 |
| 보류 | scene.py 1,039 | 드래그/전이 로직 응집도가 높아 분해 이득 낮음 |

---

## 실행 규약 (확립된 파이프라인 준수)

- WP별 브랜치 → 구현자 서브에이전트 → 스펙 리뷰(보고서 불신·코드 직접 검증) →
  품질 리뷰 → master `--no-ff` 머지. 사소한 지적은 오케스트레이터 직접 수정.
- 리뷰어에게 뮤테이션·오탐 스모크를 시킬 때는 **워크트리 격리**(2026-08-03 사고 규약).
- 구현자 프롬프트 필수 문구: "계획 문서만 쓰고 멈추지 말고 끝까지 직접 구현",
  `python -m pytest tests/ -q`, Pyright 스테일 경고 무시, 커밋 한국어.
- push는 사용자 지시 시에만.
- 매 WP 게이트: 전체 스위트 통과 + (RF-3) 산출 바이트 동일 + CLAUDE.md 동기화.

## 순서와 의존성

```
RF-1a(delegation) → RF-1b(퇴역 필드+v2) → RF-1c(로컬 스킬) → [체크포인트]
   → RF-2(경계) → RF-3a‥3e (상호 독립 — 병렬 가능, 단 3b는 RF-2의 어댑터 방침 이후)
```

## 착수 전 사용자 확인 대기 항목

1. RF-1 결정 3건 (직렬화 v2 / delegation 삭제 / 로컬 스킬 승격) — 각 권장안 포함.
2. RF-2 A안 vs B안 (권장 B).
3. 착수 시점 — 현재 도그푸딩 사이클(daedalus_cc_plugin 정리 → Ctrl+B 설치)과의 선후.
