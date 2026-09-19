# 에이전트 — 세 종류, 본문 + 출력 포트 (WP-AF / WP-FK2 / WP-9)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 에이전트 두 종류 (WP-FK2, 사용자 확정 2026-09-17)

> 2026-09-19에 세 번째 종류 `ExternalAgent`가 붙었다 — 이 절의 두 종류 비교는 **우리가 파일을 내는** 에이전트 둘에 대한 것이고, 외부 플러그인 에이전트는 맨 아래 "## 외부 플러그인 에이전트" 절에 따로 있다.

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

## 외부 플러그인 에이전트 (`ExternalAgent`, WP-9)

> 다른 플러그인이 소유한 서브에이전트를 **내 워크플로의 노드로** 쓴다.
> `config.source = "플러그인[@마켓]:이름"`, 산출 파일 없음, 그래프 노드(포트 있음), 내부 FSM 없음.

| | `ExternalAgent` (kind `external_agent`) |
|---|---|
| 뜻 | 설치된 다른 플러그인의 서브에이전트를 그래프 노드로 지목 |
| 부르는 것 | 호출자의 `call_agents` 포트에서 나가는 전이 (워크플로 에이전트와 같다) |
| fsm | **없다** — 그 에이전트의 절차는 남의 파일이다 |
| transfer_on / call_agents / 배치 | 있다 (단일 배치 상태 노드) |
| config | `ExternalAgentConfig` — **`source` 하나뿐**이고 `ComponentConfig` 직속이다 |
| 산출 | **없다.** `OUTPUT_LOCATION=NONE` — emitter도 미리보기도 없다 |
| 편집기 | AgentEditor(포트·호출자 패널) + 중앙은 본문 편집기 대신 원본 패널 |
| 탭 접두 | 🔌 |

**왜 `Agent` 직속인가.** 종전 `compile_agent`의 `isinstance(agent, AgentDefinition)`
하나가 "그래프 노드인가 = 내부 FSM이 있는가 = 파일을 내는가"를 한꺼번에 답했다.
이 종류는 **노드이면서 내부 FSM도 산출 파일도 없다** — boolean 하나로는 표현할 수
없는 조합이고, 그것을 `PLACEMENT`/`HAS_INTERNAL_FSM`/`OUTPUT_LOCATION` 세 선언으로
쪼갠 것이 능력 표면(`plugin-model.md`)의 값이다. 덕분에 계획·가이드 포인터·훅
스크립트·미리보기·포트 패널이 **한 줄도 고쳐지지 않고** 옳게 답한다.

**왜 config가 `ComponentConfig` 직속인가.** tools·skills·permission_mode·color·
max_turns는 전부 그 플러그인이 소유한 파일의 값이다. 우리 쪽에 칸을 만들면 사용자가
채워 넣고도 아무 일이 일어나지 않는다 — 산출 파일이 없으니 배출될 자리 자체가 없다
(원칙 5). 기저의 `model`/`effort`/`hooks`는 상속되지만 매트릭스 행이 없어 편집기·MCP가
노출하지 않는다.

**갈래는 부르는 쪽이 판정한다.** 외부 에이전트는 우리 워크플로도 블랙보드도 진행
기록 규약도 모르므로 "어느 출력 포트로 끝났는지"를 스스로 말할 수 없다. 그래서
`transfer_on`은 *그 에이전트가 선언하는 출구*가 아니라 **호출자가 보고를 읽고 고르는
갈래**다. 호출자 산출("## Next Steps" / 에이전트의 "## Delegation")은 그 사실을 함께
싣는다 — `compiler/emit/common.EXTERNAL_DELEGATION_NOTE`:
*"external plugin agent — it knows neither this workflow nor the blackboard: put
everything it needs in the prompt, record the result yourself, and pick the branch
below from its report"*.

**부르는 이름은 `source` 원문이다.** 우리 산출에는 그 이름의 파일이 없고 CC는 설치된
플러그인에서 **정확 일치**로 찾는다. 판정의 실체는
`compiler/emit/common.delegation_target_name(component)` 하나이고, "다음 단계"·"진입
맥락"·FSM 절차 서술·에이전트 "## Delegation"이 전부 그것을 부른다. 본문을 누가
실행하는가를 묻는 `agent_invocation_name`(fork 스킬의 `config.agent`)과는 **다른
질문**이라 한 함수로 묶지 않는다 — 묶으면 위임 대상이 없는 종류가
`general-purpose`로 답한다.

**source가 깨졌으면 이름을 지어내지 않는다** (WP-9 리뷰 반영). `source`가 비었거나
`플러그인:이름` 형식이 아니면 `delegation_target_name`이 **`None`**이고, 산출은 이름
대신 고칠 자리를 말한다 — 지시 자리는 `delegate_to_phrase`의 *"cannot delegate — the
external plugin agent on node `X` has no usable `source` …"*, 서술 자리(진입 맥락)는
`delegation_source_label`의 *"the external plugin agent on node `X`"*다. 종전에는
`source or name`이라 노드 이름(`critic`)이나 플러그인 id(`review-pack`)가 위임 지시에
그대로 실렸고, 둘 다 CC가 못 찾는 이름이라 **없는 에이전트를 지목한 산출**이 나갔다 —
`external_source_missing`은 경고라 컴파일이 성공하기 때문이다(원칙 5).

**이름 게이트를 받지 않는다.** 산출 파일이 없으므로 CC 파일명 규약
(`^[a-z0-9][a-z0-9-]*$`)을 따를 이유가 없다 — 그 이름은 남의 플러그인이 지은 것이라
우리가 고칠 수 없고, 게이트를 걸면 남의 작명 때문에 컴파일이 통째로 막힌다
(`ComponentUnit.plan`의 `emits_output()` 게이트가 emitter 조회보다 앞에 있는 부수 효과,
`tests/compiler/test_gate.py`가 고정).

**검증(종류를 묻는 규칙은 하나도 없다).**

| 규칙 | 등급 | 합류 경로 |
|---|---|---|
| `external_source_missing` | 경고 | `external_source`가 `None`이 아닌 컴포넌트 전부 — 빈 값·형식 불일치 |
| `undeclared_external_plugin` | 경고 | `external_plugin_refs()` — `external_plugins` 미선언. fork 스킬의 같은 사실이 **에러**(`fork_agent_undeclared_plugin`)인 비대칭은 `docs/backlog.md`에 결정으로 기록돼 있다(등급의 단일 진실이 규칙 **이름**의 집합이라 종류별 등급은 규칙을 쪼개야 한다) |
| `transfer_on_not_empty` | 에러 | `REQUIRES_OUTPUT_PORTS=True` |
| `agent_chain_too_deep` | 에러 | `DELEGATION_TARGET=True` — callee로 체인 깊이에 **합류한다** |
| `agent_calls_higher_model` | – | **건너뛴다** (아래) |

`_check_agent_calls_higher_model`은 `OUTPUT_LOCATION is NONE`인 callee를 건너뛴다
(WP-9에서 추가한 한 줄). 그 에이전트의 모델은 남의 플러그인 파일이 정하고 우리
`config.model`은 어디로도 나가지 않는다 — 비교하면 우리가 적어 본 값으로 남의
에이전트를 판정하는 셈이라 실체 없는 에러가 된다. 깊이 규칙에서는 빼지 않는다:
그 노드를 거치는 체인은 **실제로** 한 계층 깊어진다.

**MCP.** `create_agent(name, kind="external_agent")`가 어휘에서 **파생**되므로 도구를
고치지 않아도 받는다(F10 패리티). source는
`set_component_field(name, "source", "플러그인:이름")`으로 채운다 — 매트릭스의
비-FIXED 행이라 setter가 자동으로 허용한다.
