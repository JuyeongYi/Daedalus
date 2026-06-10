# CC 기능 위임 노드 3종 설계

> 2026-06-11 브레인스토밍 결과. AGENT_TEAM spawn / Dynamic Workflow / AgentAgora 송신 노드를
> Daedalus FSM 캔버스의 1급 모델 타입으로 추가한다.

## 배경과 결정 요약

Daedalus의 산출물(SKILL.md / agent .md)을 실행하는 Claude Code 인스턴스는
서브에이전트(Agent) 외에도 팀(TeamCreate), 동적 워크플로우(Workflow 도구),
AgentAgora MCP(인스턴스 간 dispatch/broadcast)로 일을 위임할 수 있다.
서브에이전트는 CompositeState로 이미 모델링되어 있으나 나머지 셋은 표현 수단이 없다.

브레인스토밍에서 확정된 결정:

| 질문 | 결정 |
|------|------|
| 산출물에서의 형태 | **1급 모델 타입 + 전용 규칙** (단순 본문 텍스트 아님) |
| 배치 위치 | **프로젝트 FSM 캔버스 + 에이전트 그래프 둘 다** |
| 완료 의미론 | **노드별 wait_mode 설정** (동기 대기 / fire-and-forget) |
| 참조 수준 | **혼합** — 프로젝트 내부 대상(AgentDefinition)은 객체 참조, 외부 대상(Agora instance_id, msgtype)은 자유 입력 |
| 모델 표현 | **접근법 C: 플러그인 컴포넌트 + 기존 `skill_ref` 배치 메커니즘 재사용** |
| 구현 순서 | **① 모델+검증만 먼저** (직렬화 WP-F 선행 조건), UI는 감사 로드맵 1차 WP들 이후 |

접근법 C의 근거: 캔버스 노드가 되는 경로는 `SimpleState(skill_ref=컴포넌트)`로 이미
단일화되어 있다(스킬·에이전트 동일). 새 노드를 plugin 레이어 컴포넌트로 정의하면
레지스트리 등록 → 드롭 → 배치 → 더블클릭 편집의 기존 메커니즘과 WP-A의 fsm 동기화를
전부 재사용하고, `model/fsm/`의 "Claude 무관" 원칙도 유지된다.

## 1. 컴포넌트 모델 — `daedalus/model/plugin/delegation.py` 신설

```python
class WaitMode(Enum):
    WAIT = "wait"                  # 위임 결과를 받은 뒤 전이
    FIRE_AND_FORGET = "forget"     # 위임 직후 즉시 진행


class DispatchMode(Enum):
    DISPATCH = "dispatch"          # 단일 대상 (target 지정, 빈 값이면 schema-routed)
    BROADCAST = "broadcast"        # 자기 제외 전원 fan-out


@dataclass
class TeammateSpec:
    agent_ref: AgentDefinition     # 프로젝트 내 에이전트 객체 참조
    count: int = 1                 # 같은 정의로 spawn할 인원
    role_note: str = ""            # 팀 내 역할 보충 설명


@dataclass
class PhaseSpec:
    title: str
    detail: str = ""
    agent_ref: AgentDefinition | None = None  # 이 단계를 맡길 서브에이전트 (선택)


@dataclass
class DelegationDef(PluginComponent, ABC):
    """CC 실행 단위에 일을 위임하는 노드의 공통 베이스."""
    wait_mode: WaitMode = WaitMode.WAIT

    @property
    @abstractmethod
    def kind(self) -> str: ...     # ABC 인스턴스화 방지 (프로젝트 관례)


@dataclass
class TeamSpawnDef(DelegationDef):
    """AGENT_TEAM spawn — TeamCreate + 팀원 Agent spawn. kind = "team_spawn"."""
    teammates: list[TeammateSpec] = field(default_factory=list)


@dataclass
class DynamicWorkflowDef(DelegationDef):
    """Dynamic Workflow — Workflow 도구로 멀티에이전트 오케스트레이션 작성·실행.
    kind = "dynamic_workflow"."""
    objective: str = ""                                  # 워크플로가 달성할 목표
    phases: list[PhaseSpec] = field(default_factory=list)


@dataclass
class AgoraDispatchDef(DelegationDef):
    """AgentAgora 송신/위임 — agora.dispatch / agora.broadcast.
    kind = "agora_dispatch"."""
    mode: DispatchMode = DispatchMode.DISPATCH
    target: str = ""               # 대상 instance_id. 자유 입력 (런타임 외부 존재).
    msgtype: str = ""              # payload msgtype. 자유 입력.
    payload_note: str = ""         # 페이로드 구성 지침 (컴파일 시 본문에 포함)
```

구현 주의 (CLAUDE.md 관례):
- 모든 ABC에 `@property @abstractmethod kind` — dataclass+ABC 인스턴스화 함정 방지.
- `PluginComponent`의 required 필드(name, description)와 다중 상속 필드 순서 확인 —
  자식의 신규 필드는 전부 default를 가지므로 안전.
- dataclass는 unhashable — 컬렉션 멤버십은 list 사용.

기존 모델과의 관계:
- `policy.py: ExecutionPolicy/JoinStrategy`(병렬 서브에이전트 정책)와 TeamSpawnDef는
  별개 개념이다 — ExecutionPolicy는 단일 에이전트 정의의 병렬 실행량, TeamSpawn은
  이름 있는 협업 팀 구성. 컴파일 시 `TeammateSpec.count`가 spawn 반복으로 해석된다.
  이중 모델링을 피하기 위해 TeamSpawnDef에 join 전략을 두지 않는다 — 대기 방식은
  wait_mode 하나로 충분 (감사 2-6의 단일화 원칙).
- AgentAgora의 comm-matrix·봇·스키마 본문은 모델링하지 않는다 (YAGNI) —
  Daedalus가 설계하는 것은 "이 시점에 누구에게 무엇을 보낸다"는 행동양식뿐이다.

## 2. 배치·씬·편집기 (후속 WP — 모델 확정 후)

- 레지스트리(프로젝트 RegistryPanel + AgentEditor 사이드바)에 🛰 DELEGATION 섹션 추가.
  3종 정의의 생성("새 …" 버튼)과 나열.
- 배치: `skill_lookup`이 위임 정의도 반환하도록 확장 → 기존 `drop_skill` 경로에서
  `SimpleState(name=정의.name, skill_ref=정의)` 생성. WP-A의 `_target_fsm` 동기화 자동 적용.
- `StateNodeItem`: kind별 색상/뱃지 분기만 추가 (구조 무변경).
- 더블클릭 → kind별 폼 편집기:
  - TeamSpawn: 팀원 목록(에이전트 콤보 + count 스핀 + role_note), wait_mode 콤보
  - DynamicWorkflow: objective 텍스트, phases 목록(title/detail/agent 콤보)
  - AgoraDispatch: mode 콤보, target/msgtype 라인에딧, payload_note 텍스트
- 복수 배치 허용: 같은 정의를 여러 위치에 일반 상태 노드로 배치할 수 있다.
  ReferenceSkill의 참조 노드 메커니즘(ReferencePlacement)을 쓰지 않고, `drop_skill`의
  "이미 배치됨" 중복 가드를 DelegationDef에는 적용하지 않는 방식으로 구현한다.

## 3. 검증 규칙 (Validator 확장 — 모델 WP에 포함)

| 규칙 | 수준 | 내용 |
|------|------|------|
| `dangling_teammate_ref` | 에러 | TeammateSpec/PhaseSpec의 `agent_ref`가 프로젝트 agents에 실존하는지 |
| `empty_delegation` | 경고 | teammates 0명 / objective 빈 값 / msgtype 빈 값 |
| `forget_completion_mismatch` | 경고 | `FIRE_AND_FORGET` 노드에서 나가는 전이가 복수 CompletionEvent로 결과 분기를 시도 — 결과가 없으므로 단일 "done" 진행만 유효 |

기존 규칙과 동일하게 머신 재귀 검증에 합류한다. (배치 노드의 skill_ref가
DelegationDef인 경우를 규칙들이 인지해야 함.)

## 4. 컴파일 의미론 (컴파일러 WP에서 구현 — 본 스펙으로 고정)

각 노드는 해당 위치의 본문에 도구 호출 지침 단락으로 컴파일된다:

- **TeamSpawnDef** → "TeamCreate로 팀을 만들고 다음 팀원을 spawn하라: {teammates —
  에이전트 이름·count·role_note}." + wait면 "전원 완료를 기다려 결과를 종합한 뒤
  다음 단계로", forget이면 "백그라운드로 두고 즉시 진행".
- **DynamicWorkflowDef** → "Workflow 도구로 다음 구성의 워크플로우를 작성·실행하라:
  목표 {objective}, 단계 {phases}. 단계에 agent_ref가 있으면 해당 에이전트 타입으로
  agentType을 지정하라."
- **AgoraDispatchDef** → "agora.{dispatch|broadcast}를 호출하라 — target {target},
  payload는 msgtype '{msgtype}'로 {payload_note}." + wait면 "agora.flush로 답신을
  대기한 뒤 전이", forget이면 즉시 진행.
- **공통 전제 조건**: 산출물 본문 상단에 요구 환경을 명시한다 — 팀/워크플로 도구
  가용성, AgoraDispatch 사용 시 `.mcp.json`의 agora 연결(`X-Agora-Instance-Id` 헤더).

## 5. 구현 단계

| 단계 | 범위 | 시점 |
|------|------|------|
| ① 모델 + 검증 | delegation.py + Validator 규칙 + 테스트 (순수 Python) | **지금 — WP-F(직렬화)보다 먼저 확정 필요** |
| ② 레지스트리·배치·씬 | DELEGATION 섹션, drop 경로, NodeItem 분기 | 감사 1차 WP들 이후 |
| ③ kind별 편집기 폼 | 더블클릭 편집기 3종 | ② 이후 |
| ④ 컴파일 규칙 | 본 스펙 4절 구현 | 컴파일러 WP에 합류 |

## 제외 (YAGNI)

- comm-matrix / 봇 / Agora 스키마 본문 모델링
- 배치 인스턴스별 wait_mode 오버라이드 (필요해지면 그때 SimpleState 확장)
- TeamSpawn의 join 전략 필드 (wait_mode로 충분, ExecutionPolicy와 이중화 방지)
- 팀 내 통신 토폴로지 설계 (CC 팀 런타임이 처리)
