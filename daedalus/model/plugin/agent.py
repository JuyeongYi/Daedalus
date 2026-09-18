from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef

from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.roles import Bucket, OutputLocation, PlacementRole
from daedalus.model.plugin.config import (
    AgentConfig,
    AgentConfigBase,
    ForkAgentConfig,
)


@dataclass
class Agent(PluginComponent, ABC):
    """에이전트 베이스 (추상) — 두 종류의 공통은 `config`와 안정 id뿐이다.

    "에이전트 컴포넌트 전반"을 묻는 판정(어느 리스트에 담는가 / 어느 컴파일러로
    보내는가 / 어느 매트릭스·에디터를 쓰는가)은 전부 이 클래스를 본다. "그래프에
    배치된 노드가 에이전트인가"(위임·호출 계약·연결 규칙)는 `AgentDefinition`을
    그대로 본다 — ForkAgent는 배치될 수 없어 자연 제외된다.

    `body`는 **여기서 선언하지 않는다** — 넣으면 `fields(AgentDefinition)`에서
    body가 `config` 바로 뒤로 올라가 종전 필드 순서가 깨진다(실측 2026-09-17).
    두 구체 클래스가 각자 선언한다.

    에이전트 2종의 공통 능력 선언: `project.agents`에 담기고(`BUCKET`)
    `agents/<이름>.md`를 내며(`OUTPUT_LOCATION`), 본문이 서브에이전트
    컨텍스트에서 돌고(`RUNS_IN_SUBAGENT`) 이쪽으로 가는 전이는 위임이다
    (`DELEGATION_TARGET`).
    """

    BUCKET: ClassVar[Bucket] = Bucket.AGENTS
    OUTPUT_LOCATION: ClassVar[OutputLocation] = OutputLocation.AGENT_FILE
    DELEGATION_TARGET: ClassVar[bool] = True
    RUNS_IN_SUBAGENT: ClassVar[bool] = True

    config: AgentConfigBase = field(default_factory=AgentConfigBase)  # type: ignore[type-abstract]
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)


@dataclass
class AgentDefinition(Agent, WorkflowComponent):
    """워크플로 에이전트 = Agent + FSM. 캔버스 노드로 배치되는 종류다.

    로컬 스킬(skills 필드)은 퇴역했다(WP-RF-1c) — v1 파일의 로컬 스킬은 로드 시
    전역 스킬로 승격된다(serialize._migrate_v1). 에이전트에게 줄 지식은 전역
    스킬로 만들면 컴파일이 skills 프론트매터에 자동 합류시킨다(WP-AS).

    **에이전트는 그래프에 놓이는 노드이지 그래프를 소유하지 않는다** — 배치·경유점
    좌표(`graph_layout`/`edge_layout`)와 참조 노드 배치(`reference_placements`),
    그리고 병렬 실행 정책(`execution_policy`)은 퇴역했다(2026-09-19). 넷 다 어떤
    편집 표면도 쓰지 않고 직렬화 왕복만 하던 호환 잔재였고, 실체는 `PluginProject`의
    동명 필드다. 구버전 파일의 키는 `serialize.migrate._migrate_v1`이 단방향으로
    떨군다(원칙 7).

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config (Agent), body (default)
    """

    KIND: ClassVar[str] = "agent"
    CONFIG_CLS: ClassVar[type[AgentConfig]] = AgentConfig
    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.STATE
    REQUIRES_OUTPUT_PORTS: ClassVar[bool] = True
    HAS_INTERNAL_FSM: ClassVar[bool] = True

    config: AgentConfig = field(default_factory=AgentConfig)  # type: ignore[assignment]
    body: str = ""
    # WP-AF — 출력 포트. 내부 FSM 퇴역 후 에이전트의 결과 분기는 스킬과 동일하게
    # transfer_on이 담는다. v1 파일의 ExitPoint 출력 포트는 로드 시 transfer_on으로
    # 마이그레이션된다(serialize._migrate_v1) — 여기가 단일 진실이다.
    transfer_on: list[EventDef] = field(default_factory=list)
    # 에이전트 호출 포트 — 스킬과 **같은 필드·같은 의미론**이다(2026-09-12).
    # CC가 서브에이전트의 중첩 스폰을 허용하면서(주 대화 기준 3계층) 에이전트도
    # 다른 에이전트를 부를 수 있게 됐다. 이 포트에서 나가는 전이만 에이전트
    # 노드로 갈 수 있다(캔버스 규칙과 동일). 깊이·모델 티어 제약은 프로젝트
    # 검증(agent_chain_too_deep / agent_calls_higher_model)이 짚는다.
    call_agents: list[EventDef] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.KIND

    @property
    def output_events(self) -> list[str]:
        """출력 포트 이름 목록 (StateNodeItem 호환) — `output_ports()`의 파사드."""
        return [e.name for e in self.output_ports()]

    @property
    def output_event_defs(self) -> list[EventDef]:
        """노드 포트 렌더링용 EventDef 목록 — `output_ports()`의 파사드."""
        return self.output_ports()

    def state_machines(self) -> list[StateMachine]:
        return [self.fsm]

    def output_ports(self) -> list[EventDef]:
        return list(self.transfer_on)

    def call_ports(self) -> list[EventDef]:
        return list(self.call_agents)

    def known_outgoing_events(self) -> frozenset[str]:
        """출력 포트만 — 호출 포트는 **오늘 포함되지 않는다**(backlog D9).

        스킬(`StepSkill.known_outgoing_events`)은 호출 포트도 합법 집합에
        넣는데 에이전트는 넣지 않는 비대칭이다. 넓히면 `trigger_unknown_event`
        경고가 사라지는 동작 변경이라 여기서 바로잡지 않는다.
        """
        return frozenset(e.name for e in self.output_ports())

    @classmethod
    def creation_defaults(cls, *, name: str, agent: str | None) -> dict[str, Any]:
        """새 에이전트는 출력 포트 `done` 하나로 태어난다.

        dataclass 기본값은 **빈 목록**이다(저장 파일에 키가 없으면 포트를
        발명하지 않는다). 그런데 새로 만든 에이전트가 포트 0개면 배치 즉시
        `transfer_on_not_empty` 에러가 뜬다 — 그래서 "파일에서 읽을 때"와
        "새로 만들 때"의 값이 다르고, 후자가 이 표다.
        """
        return {"transfer_on": [EventDef(name="done")]}


@dataclass
class ForkAgent(Agent):
    """fork 에이전트 — fork 스킬의 실행 기반 (사용자 확정 2026-09-17).

    FSM도 포트도 없고 캔버스에 배치되지 않는다: 부르는 것은 그래프가 아니라
    fork 스킬이고, 결과 분기는 그 스킬의 보고 양식(`EXIT: … / NEXT: …`)이
    정한다. 산출은 워크플로 에이전트와 같은 `agents/<name>.md`다.
    """

    KIND: ClassVar[str] = "fork_agent"
    CONFIG_CLS: ClassVar[type[ForkAgentConfig]] = ForkAgentConfig
    IS_FORK_BASE: ClassVar[bool] = True

    config: ForkAgentConfig = field(default_factory=ForkAgentConfig)  # type: ignore[assignment]
    body: str = ""

    @property
    def kind(self) -> str:
        return self.KIND
