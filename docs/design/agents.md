# 에이전트 — 네 종류, 본문 + 출력 포트 (WP-AF / WP-FK2 / WP-9 / WP-EX)

> CLAUDE.md에서 이관한 설계 기록(2026-09-12, 원문 그대로). 코드와 어긋나면 코드가
> 정본이다 — 발견 즉시 이 문서를 고친다. 색인은 루트 `CLAUDE.md`의 "설계 문서" 절.

## 에이전트 두 종류 (WP-FK2, 사용자 확정 2026-09-17)

> 2026-09-19에 외부 플러그인 에이전트 2종(`ExternalAgent`·`ExternalForkAgent`)이 붙어 종류는 넷이다 — 이 절의 두 종류 비교는 **우리가 파일을 내는** 에이전트 둘에 대한 것이고, 외부 2종은 아래 "## 외부 플러그인 에이전트" 절에 따로 있다.

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
  퇴역한 `fork_agent_placed`는 배치를 봤다), 아무 fork 스킬도 부르지 않는 fork 실행 기반은 경고
  `unused_fork_agent`(`IS_FORK_BASE` 선언이 대상을 정하므로 `ExternalForkAgent`도 함께 받는다).
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
  전부 + 그 에이전트 placement에 링크된 ReferenceSkill
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
  **워크플로 에이전트**·외부 플러그인 에이전트를 받는다(판정의 단일 진실은 `PortTools._require_call_port_owner`).
  `get_project`의 에이전트 행과 `get_component`가 `kind`를 싣고, fork 에이전트에는
  `used_by_fork_skills`가 함께 실린다(원칙 2 — GUI의 새 조회에 대응하는 읽기).
- **컴파일:** 종류별 본문 조립은 `compiler.md` 7-b번. "## Internal Workflow"는 legacy FSM에 실질
  상태(SimpleState 등)가 있을 때만, "## Exits"는 transfer_on 기반(`_agent_outputs_section` — 완료 보고
  첫 줄에 출구 명시 지시 + description 병기)이며 **둘 다 워크플로 에이전트 전용**이다.

## 외부 플러그인 에이전트 — 역할 2종 (WP-9 / WP-EX)

> 다른 플러그인이 소유한 서브에이전트를 쓰는 길은 둘이고, **등록 시점에 역할이
> 고정된다**(사용자 확정 2026-09-19): 내 워크플로의 **그래프 노드**로 쓰거나
> (`ExternalAgent`), fork 스킬의 **실행 기반**으로 쓰거나(`ExternalForkAgent`).
> 둘 다 `config.source = "플러그인[@마켓]:이름"`이고 산출 파일이 없다.

| | `ExternalAgent` (kind `external_agent`) | `ExternalForkAgent` (kind `external_fork_agent`) |
|---|---|---|
| 뜻 | 그 서브에이전트를 **그래프 노드**로 지목 | 그 서브에이전트를 **fork 스킬의 실행 기반**으로 지목 |
| 부르는 것 | 호출자의 `call_agents` 포트에서 나가는 전이 | `config.agent`로 지목한 fork 스킬 |
| fsm | **없다** — 그 에이전트의 절차는 남의 파일이다 | **없다** |
| transfer_on / call_agents / 배치 | 있다 (단일 배치 상태 노드) | **없다** — 결과 갈래는 부르는 fork 스킬의 보고 양식이 정한다 |
| config | `ExternalAgentConfig` | `ExternalForkAgentConfig` — 둘 다 **`source` 하나뿐**이고 공통 추상 `ExternalSourceConfig`를 상속한다 |
| 산출 | **없다.** `OUTPUT_LOCATION=NONE` — emitter도 미리보기도 없다 | **없다** (같다) |
| 편집기 | AgentEditor(포트·호출자 패널) + 중앙은 본문 편집기 대신 원본 패널 | AgentEditor(🍴 사용하는 fork 스킬 패널) + 같은 원본 패널 |
| 탭 접두 | 🔌 | 🔌🧩 |

**역할 고정 (사용자 확정 2026-09-19).** 같은 `source`를 두 역할로, 또는 같은 역할로 두 번
등록할 수 없다 — `external_source_role_conflict` **에러**이고 두 컴포넌트 모두를 짚는다
(어느 하나만 지목하면 "이쪽이 옳다"는 거짓말이 된다). 역할 전환 액션도 없다: 지우고 다시
만든다. 판정은 종류를 묻지 않고 `external_source` **원문 정확 일치**만 본다
(`alpha@mkt:x` ≠ `alpha:x` — 설치 대상이 다를 수 있다). 빈/깨진 source는 제외한다
(그쪽은 `external_source_missing` 소관이고, 편집 중인 빈 칸 둘을 충돌로 보고하면
만들자마자 에러가 뜬다).

**두 종류의 공통 구현은 `ExternalSourceMixin` 한 곳이다**(`external_source` ·
`external_plugin_refs()` · 생성 시드의 `config`). 상속 순서까지가 계약이다 —
`plugin-model.md`의 클래스 계층 절 참조.

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
노출하지 않는다 — **`set_component_hooks`도 거절한다**(2026-09-19). 훅 참조는 산출 파일의
프론트매터로만 나가므로 이 종류에는 실릴 자리가 없고, 받아 두면 저장·직렬화만 되고 컴파일에는
닿지 않는 조용한 no-op이 된다. 판정은 매트릭스의 `hooks` 행 유무에서 파생한다
(`field_matrix.component_supports_hooks`) — GUI 폼과 MCP가 같은 답을 말한다.

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
| `undeclared_external_plugin` | 경고 | `external_plugin_refs()` — `external_plugins` 미선언. **이제 이 한 갈래뿐이다**: 종전에 fork 스킬의 같은 사실을 에러로 짚던 `fork_agent_undeclared_plugin`은 WP-EX에서 퇴역했다(외부 에이전트도 컴포넌트로 등록되므로 같은 참조 경로를 탄다 — 등급 비대칭이 사라졌다) |
| `external_source_role_conflict` | 에러 | `external_source` 원문이 같은 컴포넌트가 2개 이상 — 역할 고정 |
| `transfer_on_not_empty` | 에러 | `REQUIRES_OUTPUT_PORTS=True` (`ExternalAgent`만 — fork 기반은 포트가 없다) |
| `agent_chain_too_deep` | 에러 | `DELEGATION_TARGET=True` — callee로 체인 깊이에 **합류한다** |
| `agent_calls_higher_model` | – | **건너뛴다** (아래) |

`_check_agent_calls_higher_model`은 `OUTPUT_LOCATION is NONE`인 callee를 건너뛴다
(WP-9에서 추가한 한 줄). 그 에이전트의 모델은 남의 플러그인 파일이 정하고 우리
`config.model`은 어디로도 나가지 않는다 — 비교하면 우리가 적어 본 값으로 남의
에이전트를 판정하는 셈이라 실체 없는 에러가 된다. 깊이 규칙에서는 빼지 않는다:
그 노드를 거치는 체인은 **실제로** 한 계층 깊어진다.

**fork 실행 기반으로 쓸 때의 이름 해소.** fork 스킬의 `agent:`에 나가는 값은
`compiler/emit/common.agent_invocation_name`이 정한다 — 지목된 프로젝트 에이전트가
`external_source`를 가지면 **source 원문 그대로**(타깃 무관)이고, 그 밖의 프로젝트
에이전트만 타깃별 이름(`<플러그인>:<이름>` / `<이름>`)이 된다. 원문이 비었거나 깨졌으면
`general-purpose`로 떨어뜨리지 않고 **`agent:` 줄 자체를 생략한다** — 떨어뜨리면 산출이
조용히 다른 에이전트를 지목하고 컴파일은 `external_source_missing` 경고만 낸 채 성공한다
(그래프 노드 쪽 `delegation_target_name`과 같은 규약).

**fork 후보에서 문자열은 퇴역했다.** 종전에는 사용 선언한 플러그인의 에이전트를
`플러그인:이름` 문자열 후보로 fork 스킬에 직접 흘려 넣었다(`wrap_catalog.used_plugin_agents`).
같은 외부 에이전트가 어디서는 컴포넌트이고 어디서는 이름뿐인 문자열이라 역할도 검증도 두
갈래였다 — 이제 후보는 내장과 **등록된 `IS_FORK_BASE` 컴포넌트**뿐이고, 원문을 적으면
거절하며 등록하는 법을 말한다. 구버전 파일은 `serialize.migrate.migrate_external_fork_agents`가
원문마다 `ExternalForkAgent` 하나를 만들어 흡수한다(원칙 7 — 같은 원문을 여러 스킬이
가리키면 컴포넌트는 하나다).

**MCP.** `create_agent(name, kind=…)`의 어휘는 레지스트리 **파생**이라 두 종류 모두
자동으로 받는다(F10 패리티). `source`는 생성 인자로 함께 줄 수 있고
(`create_agent(kind="external_fork_agent", source="플러그인:이름")` — 등록과 정본 지목이
1 undo), 나중에 `set_component_field(name, "source", …)`로도 바꾼다(매트릭스의 비-FIXED
행이라 setter가 자동으로 허용한다). `source`를 가질 수 없는 종류에 주면 **거절**하고 어느
종류가 그 인자를 받는지 말한다(`create_skill(fork_agent=)` 선례).

## 외부 플러그인 스킬 — 사용 경로는 하나 (WP-B, 2026-09-19)

**사용자 확정 (2026-09-19).** 외부 플러그인 **스킬**을 쓰는 길은 하나뿐이다 —
**프로젝트 fork 에이전트의 `skills:` 프론트매터**에 `플러그인:스킬`을 적는
것. 참조 노드로 끌어오거나, 워크플로 단계로 감싸거나, 선언형으로 흉내 내는
경로는 없다(랩핑 스킬 퇴역과 같은 결정 — WP-10). 근거는 실측이다:
`plugin-model.md`의 실측 표 "fork 에이전트 `skills:`의 외부 플러그인 스킬"
행(CC 2.1.278, 2026-09-19) — fork 에이전트에 `skills: [플러그인:스킬]`을
적으면 그 본문이 서브에이전트 첫 user 메시지에 **Read 호출 없이 전문으로**
실린다. 외부 플러그인 **에이전트**(WP-9 `ExternalAgent`)와는 참조 표현이
다르다 — 에이전트는 그래프 노드(`source`), 스킬은 문자열 목록 항목이다.

**판정의 실체는 하나, `model/plugin/config.is_external_skill_ref(name)`** —
콜론이 있으면 외부 참조다. 프로젝트 컴포넌트 이름은
`^[a-z0-9][a-z0-9-]*$`라 콜론을 가질 수 없어 오검출이 없다. `AgentConfigBase`
(`AgentConfig`·`ForkAgentConfig` 공유)의 두 갈래 계약:

- `name_refs(Bucket.SKILLS)`는 **프로젝트 스킬 참조만** 돌려준다(외부 참조
  제외) — 안 그러면 `dangling_string_reference`가 "그 이름의 스킬이
  프로젝트에 없다"고 오탐하고, `rename_ref`가 무관한 문자열을 건드릴 뻔한다.
- `external_skill_refs()`는 외부 참조 **원문**(`플러그인:스킬`) 목록이고,
  `external_plugin_refs()`는 그 플러그인 부분을 **적힌 그대로** 돌려준다(`@마켓`을
  떼지 않는다 — 떼면 검증이 그 표기를 볼 수 없다). `PluginComponent.
  external_plugin_refs()`의 **기본 구현이 config에 위임**하므로 `AgentDefinition`·
  `ForkAgent`는 아무것도 오버라이드하지 않는다(새 에이전트 종류도 자동 합류).
  `ExternalAgent`만 자기 `source`를 읽는 오버라이드를 갖는다.

**매칭 정책은 하나다 — `config.plugin_ids_match` (2026-09-19 리뷰로 단일화).**
정확 일치, 또는 **한쪽만 bare**일 때 bare 이름 일치. 양쪽 다 마켓을 달고
다르면(`alpha@mkt1` vs `alpha@mkt2`) 불일치다. 완화가 필요한 이유는 카탈로그
자신이 마켓 표기를 비대칭으로 내기 때문이다 — 선언(`external_plugins`)은
`플러그인@마켓`인데 `CataloguedAgent.agent_type`과 `CataloguedSkill.skill_ref`는
CC가 찾는 이름 그대로 bare `플러그인:이름`이다. 표준 경로(카탈로그 체크 →
`agent_type`을 `source`로 / `skill_ref`를 `skills`에)를 따르기만 한 프로젝트에
경고가 뜨면 안 된다(원칙 5). 종전 "`ExternalAgent.source`는 정확 일치"
정책은 그 비대칭을 오탐하는 버그였고(`test_bare_source_matches_marketplace_
declaration`이 고정), 참조의 **출처**로 정책을 가르던 중간안(WP-B 초안)은 같은
사실을 두 정책으로 말한 셈이라 걷었다(원칙 1). `_check_external_plugins`
(`naming.py`)는 `comp.external_plugin_refs()` 한 목록을 이 술어로 대조한다.

**`@마켓`이 붙은 스킬 참조는 경고다 — `external_skill_ref_marketplace`.** CC는
fork 에이전트 `skills:`의 외부 스킬을 마켓 표기 없는 이름으로 찾는다(실측).
`beta@mkt:lint`는 선언 `beta@mkt`와 맞아 배선 경고는 없지만 산출이 원문
그대로 나가 런타임에 조용히 해소되지 않으므로, `_check_external_skill_refs`가
정규형(`normalize_external_skill_ref` → `beta:lint`)을 제시하며 짚는다.
GUI 후보(`used_plugin_skill_refs`)와 MCP `skill_ref`는 항상 정규형을 내므로
손으로 친 참조만 여기 걸린다.

**산출은 그대로다.** `_agent_skills_list`(compiler/emit/agent_sections.py)는
`config.skills` 항목을 그대로 프론트매터에 낸다 — 외부 참조도 로컬 이름도
구분 없이 원문 그대로(변경 없음 — `tests/compiler/test_external_plugins.py`의
산출 테스트가 두 빌드 타깃에서 고정한다).

**GUI·MCP 패리티.** 에이전트 편집기 SKILLS TagInput은 프로젝트 스킬 이름 +
사용 선언한 플러그인의 스킬(`플러그인:스킬`, `wrap_catalog.
used_plugin_skill_refs(project)`)을 자동완성 후보로 준다(`app.set_project`가
`tag_input.set_skill_candidate_provider` 등록). MCP `set_component_field(name,
"skills", [...])`는 미선언 플러그인 참조를 **거절하지 않고** 응답에
`warning`을 싣는다(형식은 유효하고 사용자가 곧 선언할 수도 있다 — 원칙 5는
"조용한 실패 금지"이지 "선제적 거절"이 아니다). `list_external_plugins`의
스킬 행에 `skill_ref`(넣을 이름)와 `used_by`(그 참조를 가진 프로젝트 에이전트
이름 목록 — 참조는 정규형으로 대조)가 실린다 — 쓸 수 있는 값은 읽을 수도 있어야 한다(원칙 2).

## 외부 플러그인 카탈로그 (D2 — WP-WR에서 이관, WP-10)

> 종전 `wrapped-skills.md`의 카탈로그 절이다. 랩핑 스킬이 퇴역해도 카탈로그·사용
> 선언·실물 캐시는 그대로 살아 있다 — 이제 그 소비자가 `ExternalAgent`다.

- **발견의 단일 진실은 `model/plugin/wrap_catalog.py`**다(파일시스템을 아는 모듈 —
  hook_store 지위. 검증기·컴파일러는 임포트 금지, 필요하면 호출자 주입).
  **마켓플레이스 폴더** 등록은 전역 `~/.daedalus/external_marketplaces.json`
  (`marketplaces_file` — 테스트는 conftest `_isolate_external_marketplaces`가 격리),
  발견은 폴더 밑 깊이 4까지 `.claude-plugin/plugin.json` 탐색 +
  `skills/*/SKILL.md`(스킬 이름의 단일 진실은 **디렉토리명**) + 동봉 `.mcp.json`/
  `plugin.json`의 `mcpServers` 키(`CataloguedPlugin.mcp_servers`) + 동봉 에이전트
  `agents/**/*.md`(`CataloguedPlugin.agents` — 이름은 프론트매터 `name` 또는 파일명
  이고 하위 폴더는 콜론으로 잇는다. `agent_type`=`플러그인:이름`은 CC가 정확 일치로
  찾는 이름이라 사람이 조립하지 않고 이 값을 쓴다. 사용 선언분만 거르는 단일 진실은
  `used_plugin_agents`). 마켓 이름 해소: 등록 시 명시 > 폴더
  `.claude-plugin/marketplace.json`의 name > bare.
- **"이 프로젝트가 이미 쓰는 source"의 단일 진실은 `project_external_sources`**다 —
  창의 ✔와 MCP `list_external_plugins`의 `already_used`가 같은 함수를 부른다
  (원칙 1·2). 종류도 버킷도 묻지 않고 `external_source`만 보므로 외부 정본을 갖는
  새 종류는 선언 한 줄로 합류한다.
- **원본 파일 해소는 버킷이 규약을 고른다** — `resolve_source_file(component)`가
  스킬이면 `skills/<이름>/SKILL.md`, 에이전트면 `agents/<이름>.md`를 찾는다.
  편집기의 "원본 열기" 버튼이 쓴다.
- **GUI 창**은 도구 메뉴 "외부 플러그인 카탈로그..."(`view/editors/
  wrap_catalog_dialog`) — 폴더→플러그인→스킬·에이전트 트리, **플러그인 체크 = 이
  프로젝트에서 사용 선언**(`external_plugins`에 SetAttrCmd — undo·저장 왕복),
  ✔ = 이미 이 프로젝트가 쓰는 source. 체크 토글의 트리 재구성은
  `singleShot(0, self, refresh)`로 미룬다(itemChanged를 쏜 아이템을 같은 호출에서
  `clear()`로 파괴하면 간헐 access violation — 실측. 수신 컨텍스트 덕에 닫힌
  다이얼로그에 발화하지 않는다). **이 창의 동작은 등록·선언뿐이다**(사용자 확정 —
  배선은 빌드 소관이라 생성 버튼 없음).
- **실물의 출처는 세 곳, 기준은 "설치했는가"가 아니라 "실물을 읽었는가"**
  (사용자 확정 2026-09-07): 마켓플레이스는 `marketplace.json`에 플러그인을 **선언**만
  하고 실물은 따로 온다(실측: 공식 마켓 291개 선언 / 저장소 동봉 40개).
  `CataloguedPlugin.files_from`이 출처를 말한다 — `"marketplace"`(저장소 동봉) /
  `"installed"`(**CC가 설치** — `~/.claude/plugins/cache/<마켓>/<이름>/<버전>/`,
  `cc_installed_dirs()`가 `installed_plugins.json`에서 읽는다) / `"cache"`(우리가
  클론) / `""`(못 읽음). `has_files` property가 그 판정이고, 어디서 왔든 스킬은
  `_scan_skills` 하나가 읽는다.
  - **마켓 저장소만 훑던 것이 버그였다**(사용자 보고) — CC는 마켓 저장소가 아니라
    별도 캐시에 푸므로, 사용자가 **실제로 설치한** 플러그인이 "미설치"로 나왔다.
  - 못 읽으면 `skills=[]`·`agents=[]`이라 종류를 지목할 수는 없지만 **사용 선언은
    지금도 된다**: plugin_id만 있으면 빌드가 dependencies/enabledPlugins를 내고
    설치는 CC가 한다. 매니페스트 없는 실물도 정상이다(스킬 없이 LSP·훅만 주는
    플러그인 — 실측 pyright-lsp).
  - 표면: 카탈로그 창은 아이콘으로 가르고(🧩 읽음 / ⬇ 받아야 함) 못 읽은 것은
    "⋯ 스킬 미확인 (N)" **접힌 그룹**으로 묶는다. MCP는
    `list_external_plugins(include_unfetched=False)`가 읽은 것만 + `unfetched_count`
    로 나머지를 알리고 각 항목에 `files_from`을 싣는다.
  - **창의 펼침 상태는 재구성을 견딘다** — 체크마다 트리를 다시 그려 폴더가 접히던
    것을 고쳤다(사용자 보고). 체크 토글은 트리를 건드리지 않고 상태 문구의 개수만
    갱신하며(`_update_status_counts` — 모델 재스캔이 아니라 **화면을 센다**), 펼침은
    plugin_id·폴더 경로 키 집합으로 복원한다.
- **미설치 플러그인 실물 캐시**(사용자 확정 2026-09-07): `model/plugin/
  plugin_cache.py`가 선언 `source`로 저장소를 **얕게 클론**해 캐시에 두고, 스킬
  스캔은 `wrap_catalog._scan_skills`를 **그대로 재사용**한다. 그래서 이름뿐 아니라
  **설명(SKILL.md 프론트매터)까지** 나오고, 같은 스킬을 어디서 읽었느냐에 따라
  목록이 달라질 여지가 없다.
  - **`git clone --branch`가 아니라 init + `fetch --depth 1`**이다 — 선언에는 커밋
    SHA가 흔한데 `--branch`는 태그·브랜치만 받는다. `sha`가 있으면 `ref`보다
    우선한다(태그는 옮겨 달릴 수 있고 SHA는 불변이라 캐시 키로 안전).
  - **언제 인터넷에 나가는가 — 사용자가 그 플러그인을 지목했을 때만이다.**
    카탈로그를 열거나 새로고침하는 것만으로는 절대 받지 않는다(291개 일괄 클론은
    디스크도 시간도 감당할 수 없다). 캐시 폴더 이름에 ref가 들어가므로 같은 버전은
    다시 받지 않고 버전이 바뀌면 새 폴더로 받는다.
  - 실패하면 받다 만 폴더를 **지운다** — 남기면 다음 호출이 그것을 "이미 받은 것"
    으로 보고 빈 디렉토리를 스캔한다. git 부재는 stack trace 대신 안내 문구.
  - 클론할 주소가 없는 source(마켓 폴더 안 상대 경로 등)는 `None`을 돌려주고
    "설치 후 확인"으로 안내한다. git URL이면 **GitHub이 아니어도 된다**.
  - **받아 온 결과는 창이 아니라 카탈로그가 들고 있다**: `discover_plugins`가 매
    스캔마다 `cached_path`(**절대 받지 않는 조회 전용**)로 캐시를 확인하므로, 받은
    실물은 설치본과 완전히 같은 경로로 실린다.
  - 표면: 카탈로그 창 "스킬 목록 받아오기" 버튼(이 창에서 인터넷에 나가는 유일한
    지점 — 클론 중 대기 커서) / MCP `fetch_plugin_skills(plugin_id, refresh=False)` —
    실물이 이미 있으면 그 자리에서 읽어 받지 않는다. 테스트는 `_shallow_clone`을
    몽키패치해 **호출 횟수까지** 센다(언제 받느냐가 이 기능의 계약이다).
- **외부 플러그인의 MCP 서버 활용**: 사용 선언된 플러그인의 `mcp_servers`가
  ① 에이전트 MCP_SERVERS TagInput 자동완성 후보(`tag_input.
  set_mcp_server_candidate_provider` — app.set_project가 `used_plugin_mcp_servers
  (project) ∪ mcp_server_defs` 등록. **tools 후보에는 넣지 않는다** — 개별 도구 목록
  미지원, 사용자 확정) ② LOCAL 컴파일 주입 `compile_project(provided_server_names=)`
  (compile_inputs 합류 — 플러그인 활성화가 서버를 가져오므로
  `missing_mcp_server_def` 대상에서 제외)로 쓰인다.
- **MCP 짝**(패리티): `list_external_plugins`(plugin_id·used·mcp_servers·skills·
  agents·already_used)/`fetch_plugin_skills`/`list_marketplace_folders`/
  `add_marketplace_folder`/`remove_marketplace_folder`(홈 설정 파일 — undo 비대상)/
  `set_external_plugins`(선언 통째 교체 — undo 가능). `get_project` meta에
  `external_plugins`.

## 랩핑 스킬 퇴역 (WP-10, 2026-09-19)

`WrappedSkill`(외부 플러그인의 **스킬**을 워크플로 단계로 감싸는 종류)은 사라졌다.
그 일은 두 갈래로 나뉜다 — 워크플로 단계로 쓰던 것은 `ExternalAgent`(외부
서브에이전트를 노드로), 참고 자료로 쓰던 것은 `ReferenceSkill`(자체 본문을 가진
참조 문서)이다. 외부 **스킬**은 이제 감싸지 않는다: 플러그인을 사용 선언하면 CC가
그 스킬들을 네이티브로 로드하므로 우리가 대신 인보크할 이유가 없다.

**저장 파일은 이관하지 않는다 — 후방 호환을 버린다 (사용자 확정 2026-09-19).**
`wrapped_skill`이 남은 format 2 파일은 로드 시 레지스트리가 미지 종류로 **거부**한다
(`ValueError`, 조용한 강등 없음 — 원칙 5). 퇴역 당일 단방향 흡수 마이그레이션
(`migrate_wrapped_retirement`)을 함께 냈으나 같은 날 사용자 결정으로 걷었다: 이 종류를
저장한 파일은 사용자 작업 사본에 없고, 새 종류(`ExternalAgent`·`ReferenceSkill`)로 다시
그리는 편이 옛 용도 값을 추측해 옮기는 것보다 정직하다. 동결 dogfood 사본
(`tests/data/golden/dogfood.daedalus.json`)은 이관된 저장 형태로 다시 동결했다.
