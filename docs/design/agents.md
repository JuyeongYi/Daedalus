# 에이전트 — 본문 + 출력 포트 (WP-AF)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 에이전트 — 본문 + 출력 포트 (WP-AF, 내부 FSM 퇴역)

- **왜 퇴역했나:** Daedalus FSM은 런타임 엔진이 없다 — 내부 FSM은 컴파일되면 에이전트 .md 안의
  번호 목록 텍스트가 될 뿐이고, 같은 지시는 본문 산문이 동일한 효력을 낸다. 형식화 비용(그래프
  탭·별도 CommandStack·로컬 스킬 기계장치)에 걸맞은 대가가 없었다(사용자 확정. 도그푸딩에서
  손실·버그 대부분이 이 표면에서 났고, 실사용 세션은 에이전트를 내부 FSM 없이 본문만으로 만들었다).
- **살아남은 조각 = 출력 포트.** 프로젝트 그래프가 에이전트의 결과로 분기한다(과거 ExitPoint 이름이
  전이 trigger). `AgentDefinition.transfer_on: list[EventDef]`로 이관 — 스킬과 동일 필드·동일 편집
  패널(_TransferOnPanel)·동일 캔버스 포트 렌더. `output_events`/`output_event_defs`는 transfer_on을
  **단일 진실**로 읽는다 (legacy ExitPoint 폴백은 RF-1b에서 삭제 — v1 파일은 로드 시 마이그레이션).
- **마이그레이션:** v1 파일(transfer_on 키 부재)은 `serialize._migrate_v1`이 내부 FSM ExitPoint의
  이름·색을 승계한다(단방향, 경고 없음). fsm 필드 자체는 WorkflowComponent 계약상 남는다 — 신규
  에이전트는 EntryPoint 하나짜리 빈 기계(`app._make_agent_fsm`) + 기본 출력 포트 `done`.
- **로컬 스킬 퇴역 완결 (WP-RF-1c):** `AgentDefinition.skills` 필드째 삭제. 에이전트에게 줄
  지식은 전역 스킬로 — 컴파일이 skills 프론트매터에 자동 합류시킨다(WP-AS: 전역 DeclarativeSkill
  전부 + 그 에이전트 placement에 링크된 ReferenceSkill + 링크된 참조 용도 랩핑 스킬(`플러그인:스킬`, WP-WR)
  + config.skills 수동 선언 순, 중복 제거.
  `emit._agent_skills_list`). v1 파일의 로컬 스킬은 로드 시 **전역 스킬로 승격**된다
  (`_promote_local_skills` — `_migrate_v1` 1-b 단계가 호출. 이름 충돌 시 `<agent>--<name>`으로
  개명하고 그마저 충돌하면 `-2` 접미로 유일화, 개명 시 소유 에이전트 config.skills 참조도 치환,
  승격마다 경고 1건, id 보존이라 에이전트 FSM 전이의 transfer skill_ref도 그대로 해소. 블랙보드
  parent 재배선·본문 마이그레이션은 전역 스킬과 완전히 같은 경로). **RF-1b 시점 코드가 저장한
  format 2 파일에도 인라인 로컬 스킬이 남아 있을 수 있어**, `deserialize_project`는 format 2에서도
  에이전트 dict에 `skills` 키가 있으면 같은 승격을 태운다(경고 없는 드롭 방지).
- **호출 계약 = 그래프 유도 (WP-CT):** 수동 계약 카드(caller_contracts 편집·자동 생성)는 퇴역 —
  호출 정보를 양쪽(호출자 포트 + 에이전트 카드)에 적게 하던 중복이었다. **호출자가 무엇을 넘기는지는
  호출자의 call_agents 포트 description에 적는다.** 에이전트 .md의 "## 호출 계약"은
  `emit._call_contract_section(agent, project)`이 프로젝트 그래프의 incoming 호출 전이에서 유도한다
  (호출자·포트·description·가드, 호출자 이름순). caller_contracts 필드는 RF-1b에서 삭제 —
  v1 파일의 카드는 로드 시 조용히 드롭된다(`_migrate_v1`).
- **에이전트도 에이전트를 부른다 (2026-09-12):** CC가 서브에이전트의 중첩 스폰을 허용한다
  (주 대화 기준 3계층, 실측 확인 — CC 2.1.268). 그래서 `AgentDefinition.call_agents:
  list[EventDef]`가 스킬과 **같은 필드·같은 의미론**으로 존재한다(직렬화 왕복, 키 부재인
  구버전 파일은 빈 목록). 캔버스 규칙은 그대로다 — 에이전트 노드로 가는 전이는 호출 포트에서만
  나간다. 호출은 **동기**이고 부른 쪽이 결과를 받아 자기 출구를 고른다. 대가는 그 구간의 중간
  결과가 메인 컨텍스트에 남지 않는 것이다(진행 기록·재개가 약해진다 — `no_agent_to_agent`
  경고). 하드 제약 둘은 에러다: `agent_chain_too_deep`(깊이 3), `agent_calls_higher_model`
  (자기보다 상위 모델 호출 금지 — 사용자 확정).
- **fork 에이전트 (2026-09-13, 종류 분리 WP-FK2):** fork 스킬의 실행 기반은 **`ForkAgent`**(kind
  `fork_agent`)라는 별도 종류다 — 캔버스에 배치되지 않고 fsm·포트가 없다. 그 에이전트 본문이 시스템
  프롬프트, fork 스킬 본문이 작업 지시다(실측). `.md`의 "## Invocation Contract"에 "Execution base of
  fork skill X"가 유도된다. `skills` 프리로드·`maxTurns`는 적용되고 `isolation`은 적용되지 않으므로
  `ForkAgentConfig`에 그 필드가 아예 없다(실측 재확인 2026-09-18, CC 2.1.274 — 경고
  `fork_agent_isolation_ignored`는 그래서 퇴역했다). 워크플로 에이전트(`AgentDefinition`)를 fork
  스킬의 `agent`로 지목하면 에러 `fork_agent_wrong_kind`, 아무 fork 스킬도 부르지 않는 `ForkAgent`는
  경고 `unused_fork_agent`다. 상세는 `plugin-model.md` "fork 스킬".
- **에이전트 편집기:** AgentEditor = ComponentEditor + 출력 포트 패널 + **에이전트 호출 포트
  패널**(스킬 에디터와 같은 `_TransferOnPanel` 위젯) — 스킬 편집기와
  같은 레벨(그래프/컨텐츠 탭 구조 제거, 별도 그래프 VM 없음 — undo는 프로젝트 스택).
- **MCP:** 도구의 `agent` 스코프 파라미터는 WP-RF-1c에서 시그니처째 제거됐다(스키마 노출 기준 —
  캔버스 편집의 대상은 프로젝트 그래프 하나뿐이다). `set_transfer_on(에이전트 이름)`으로 출력
  포트 편집. `create_agent`는 기본 포트 done으로 시작. 호출 포트 도구
  (`add_agent_call`/`set_agent_calls`/`remove_agent_call`)는 절차형 스킬·state 용도 랩핑
  스킬·**에이전트**를 받는다(판정의 단일 진실은 `PortTools._require_call_port_owner`).
- **컴파일:** "## 내부 워크플로"는 legacy FSM에 실질 상태(SimpleState 등)가 있을 때만 배출.
  "## 출구"는 transfer_on 기반(`_agent_outputs_section` — 완료 보고 첫 줄에 출구 명시 지시 + description 병기).
