# 에이전트 — 두 종류, 본문 + 출력 포트 (WP-AF / WP-FK2)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 에이전트 두 종류 (WP-FK2, 사용자 확정 2026-09-17)

`Agent(PluginComponent, ABC)`가 추상 부모이고 구체 종류는 둘이다 — 계층·config 표는 `plugin-model.md`.

| | `AgentDefinition` (kind `agent`) | `ForkAgent` (kind `fork_agent`) |
|---|---|---|
| 뜻 | **워크플로 에이전트** — 그래프에 배치되는 노드 | fork 스킬의 **실행 기반** |
| 부르는 것 | 호출자의 `call_agents` 포트에서 나가는 전이 | `config.agent`로 지목한 fork 스킬 |
| fsm / transfer_on / call_agents / 배치 | 있다 | **없다** |
| config | `AgentConfig`(+ background, isolation, color) | `ForkAgentConfig`(+ color) |
| 산출 | `agents/<이름>.md` | `agents/<이름>.md` (**같다**) |
| 편집기 우측 패널 | 출력 포트 · 에이전트 호출 포트 · 호출자 목록 | 🍴 **사용하는 fork 스킬**(읽기 전용) |
| 탭 접두 | 🤖 | 🧩 |

- **두 판정의 축이 다르다.** "에이전트 컴포넌트 전반"(`project.agents` 버킷·`compile_agent`·매트릭스·편집기·
  미리보기·토큰 리포트 라벨)은 `Agent`를 보고, "그래프에 배치된 노드가 에이전트인가"(위임 문구·호출 계약·
  캔버스/MCP 연결 규칙)는 `AgentDefinition`을 본다 — ForkAgent는 배치 불가라 후자에서 자연 제외된다.
  전자를 좁게 두면 ForkAgent가 `project.skills`로 새어 저장이 `when_to_use`에서 죽고 미리보기가
  `compile_skill`로 떨어진다.
- **역참조 조회의 실체는 하나다** — `model/plugin/placement.fork_skills_using(agent, project)`.
  편집기 패널·삭제 확인 다이얼로그·MCP `delete_component`의 `still_referenced_by`·MCP `get_component`의
  `used_by_fork_skills`·컴파일러의 "## Invocation Contract"가 전부 이것을 부른다(원칙 1·2).
  컴파일러는 뷰를 임포트할 수 없으므로(import 계약) 실체가 모델에 있어야 한다 —
  `compiler/emit/fork.fork_skills_using`은 이 함수를 재-export하는 얇은 껍데기다.
- **검증:** 워크플로 에이전트를 fork 스킬의 `agent`로 지목하면 에러 `fork_agent_wrong_kind`(배치 여부 무관 —
  퇴역한 `fork_agent_placed`는 배치를 봤다), 아무 fork 스킬도 부르지 않는 ForkAgent는 경고 `unused_fork_agent`.
  `fork_agent_isolation_ignored`는 필드 자체가 없어져 퇴역했다.

## 에이전트 — 본문 + 출력 포트 (WP-AF, 내부 FSM 퇴역)

- **왜 퇴역했나:** Daedalus FSM은 런타임 엔진이 없다 — 내부 FSM은 컴파일되면 에이전트 .md 안의
  번호 목록 텍스트가 될 뿐이고, 같은 지시는 본문 산문이 동일한 효력을 낸다. 형식화 비용(그래프
  탭·별도 CommandStack·로컬 스킬 기계장치)에 걸맞은 대가가 없었다(사용자 확정. 도그푸딩에서
  손실·버그 대부분이 이 표면에서 났고, 실사용 세션은 에이전트를 내부 FSM 없이 본문만으로 만들었다).
- **살아남은 조각 = 출력 포트.** 프로젝트 그래프가 에이전트의 결과로 분기한다(과거 ExitPoint 이름이
  전이 trigger). `AgentDefinition.transfer_on: list[EventDef]`로 이관 — 스킬과 동일 필드·동일 편집
  패널(_TransferOnPanel)·동일 캔버스 포트 렌더. 포트 조회 표면은 능력 메서드 `output_ports()`
  **하나**다 — 옛 `output_events`/`output_event_defs` 파사드는 캔버스가 `output_ports()`를 직접
  부르게 되면서 소비자가 0이 되어 WP-2d에서 삭제했다 (legacy ExitPoint 폴백은 RF-1b에서 삭제 —
  v1 파일은 로드 시 마이그레이션).
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
- **fork 에이전트 (2026-09-13, 종류 분리 WP-FK2):** 그 에이전트 본문이 시스템 프롬프트, fork 스킬 본문이
  작업 지시다(실측). `.md`의 "## Invocation Contract"에 "Execution base of fork skill `X` — that skill's
  instructions arrive as your task; this file sets your role and limits."가 유도된다(`_fork_base_contract_section`).
  `skills` 프리로드·`maxTurns`는 적용되고 `isolation`은 적용되지 않으므로 `ForkAgentConfig`에 그 필드가
  아예 없다(실측 재확인 2026-09-18, CC 2.1.274 — 상세 기록은 `plugin-model.md` 실측 표).
- **에이전트 편집기:** AgentEditor = ComponentEditor + **종류별 우측 패널**. 워크플로 에이전트는 출력 포트
  패널 + 에이전트 호출 포트 패널(스킬 에디터와 같은 `_TransferOnPanel` 위젯) + 호출자 목록을, fork
  에이전트는 "🍴 사용하는 fork 스킬" 읽기 전용 목록을 받는다(비어 있으면 "산출은 되지만 아무도 부르지
  않습니다 — fork 스킬의 [agent] 필드에서 고르세요" 안내. 탭을 다시 보일 때 `showEvent`가 새로
  읽으므로 다른 탭에서 `agent`를 바꿔도 반영된다). 스킬 편집기와 같은 레벨(그래프/컨텐츠 탭 구조 제거,
  별도 그래프 VM 없음 — undo는 프로젝트 스택). 프론트매터 폼은 `matrix_for(agent)`가 고른 종류별 표로
  그린다(fork 에이전트에는 background·isolation 행이 없다).
- **MCP:** 도구의 `agent` 스코프 파라미터는 WP-RF-1c에서 시그니처째 제거됐다(스키마 노출 기준 —
  캔버스 편집의 대상은 프로젝트 그래프 하나뿐이다). `create_agent(name, kind="agent"|"fork_agent")`가
  종류를 받고(기본 `"agent"`), fork 에이전트에 x/y를 주면 배치 불가라 거절한다. `set_transfer_on`은
  fork 에이전트를 **명시 거부**한다("fork 에이전트는 fork 스킬의 실행 기반이라 갈래가 없습니다" —
  `SetAttrCmd`의 `getattr(..., None)` 폴백 때문에, 거부하지 않으면 없는 필드가 인스턴스 속성으로 생기고
  성공 응답이 돌아간 뒤 저장 한 번에 사라진다). 워크플로 에이전트는 기본 포트 done으로 시작한다.
  호출 포트 도구(`add_agent_call`/`set_agent_calls`/`remove_agent_call`)는 절차형·fork 스킬·state 용도
  랩핑 스킬·**워크플로 에이전트**를 받는다(판정의 단일 진실은 `PortTools._require_call_port_owner`).
  `get_project`의 에이전트 행과 `get_component`가 `kind`를 싣고, fork 에이전트에는
  `used_by_fork_skills`가 함께 실린다(원칙 2 — GUI의 새 조회에 대응하는 읽기).
- **컴파일:** 종류별 본문 조립은 `compiler.md` 7-b번. "## Internal Workflow"는 legacy FSM에 실질
  상태(SimpleState 등)가 있을 때만, "## Exits"는 transfer_on 기반(`_agent_outputs_section` — 완료 보고
  첫 줄에 출구 명시 지시 + description 병기)이며 **둘 다 워크플로 에이전트 전용**이다.
