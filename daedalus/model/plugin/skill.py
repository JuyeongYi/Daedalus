from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.placement import placement_role_of
from daedalus.model.plugin.roles import (
    BodySource,
    Bucket,
    OutputLocation,
    PlacementRole,
)
from daedalus.model.plugin.config import (
    WrappedSkillConfig,
    AsyncForkSkillConfig,
    DeclarativeSkillConfig,
    ForkSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    StepSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
)


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스.

    본문의 단일 진실 공급원은 ``body`` 필드(마크다운 문자열)다 (WP-SB).
    새 컴포넌트의 기본값은 빈 문자열 — 구조 없는 자유 텍스트로 편집한다.

    스킬 7종의 공통 능력 선언: `project.skills`에 담기고(`BUCKET`)
    `skills/<이름>/SKILL.md`를 낸다(`OUTPUT_LOCATION`).
    """

    BUCKET: ClassVar[Bucket] = Bucket.SKILLS
    OUTPUT_LOCATION: ClassVar[OutputLocation] = OutputLocation.SKILL_DIR

    when_to_use: str = ""
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)


@dataclass
class WrappedSkill(Skill, WorkflowComponent):
    """랩핑 스킬 (WP-WR) — 다른 플러그인 스킬을 워크플로 단계로 감싼다.

    본문의 정본은 config.source가 가리키는 외부 스킬이다(런타임 참조 — 컴파일
    산출은 "그 스킬을 따르라" 지시 + 우리 그래프 유도 단락). body 필드는
    구조상 남지만 **항상 빈 값**이어야 한다 — 편집 UI가 잠그고 컴파일이
    무시한다. 배치 규칙은 procedural과 동일(단일 배치 — no_duplicate_skill_ref).
    같은 source를 여러 랩퍼가 감싸는 것은 정상이다(재사용은 랩퍼 복수로).

    **능력 표면의 유일한 오버라이드 덩어리**다 — 용도(`usage`)·켜짐(`enabled`)
    두 인스턴스 스위치를 가진 종류가 이것뿐이라서다. WP-10에서 이 클래스가
    퇴역하면 인스턴스 훅 오버라이드는 전 컴포넌트에서 0이 된다.
    """

    KIND: ClassVar[str] = "wrapped_skill"
    CONFIG_CLS: ClassVar[type[WrappedSkillConfig]] = WrappedSkillConfig
    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.STATE
    BODY_SOURCE: ClassVar[BodySource] = BodySource.EXTERNAL
    RUNS_IN_SUBAGENT: ClassVar[bool] = True

    config: WrappedSkillConfig = field(default_factory=WrappedSkillConfig)
    body: str = ""
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )
    call_agents: list[EventDef] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.KIND

    # -- 인스턴스 훅 --
    def effective_placement(self) -> PlacementRole:
        """용도가 reference로 고정된 랩퍼는 참조 노드다(사용자 확정 2026-09-07).

        미정("")은 state로 친다 — 최초 배치가 용도를 고정한다.
        """
        if self.config.usage == WrappedSkillConfig.USAGE_REFERENCE:
            return PlacementRole.REFERENCE
        return PlacementRole.STATE

    def is_active(self) -> bool:
        return bool(self.config.enabled)

    def emits_output(self) -> bool:
        """참조 용도는 파일을 내지 않는다 — 링크된 노드의 산출에 consult 지시로만 합류."""
        return (
            super().emits_output()
            and self.effective_placement() is not PlacementRole.REFERENCE
        )

    def can_delete(self) -> tuple[bool, str | None]:
        return (False, "랩핑 스킬이기 때문입니다")

    # -- 형상 조회 --
    def state_machines(self) -> list[StateMachine]:
        return [self.fsm]

    def output_ports(self) -> list[EventDef]:
        return list(self.transfer_on)

    def call_ports(self) -> list[EventDef]:
        return list(self.call_agents)

    # -- 참조 --
    def external_plugin_refs(self) -> list[str]:
        """꺼 둔 랩퍼는 참조로 치지 않는다 — 배선도 필요 없고 쓰는 것도 아니다.

        형식이 깨진 source는 source 형식 검사 규칙의 소관이라 여기서 중복으로
        짚지 않는다(오늘 `naming._check_external_plugins`와 같은 제외 규칙).

        원문은 `external_source`로 읽는다 — 손상된 저장 파일의 non-str `source`
        를 견디는 자리가 두 벌이면 한쪽만 터진다(원칙 1).
        """
        if not self.is_active():
            return []
        plugin_id, _, skill_name = (self.external_source or "").partition(":")
        plugin_id = plugin_id.strip()
        if not plugin_id or not skill_name.strip():
            return []
        return [plugin_id]

    @property
    def external_source(self) -> str | None:
        """랩핑 스킬은 **항상** 외부 정본을 선언한다 — 값이 비었거나 손상돼도
        `None`(= 이 종류엔 외부 정본이 없다)이 아니라 빈 문자열로 답한다.

        `None`을 돌려주면 `_check_external_sources`가 "외부 정본이 없는 종류"로
        보고 건너뛰어 `external_source_missing` 경고가 조용히 사라진다(원칙 5).
        역직렬화는 `source`를 날것으로 싣는다(`deser_plugin._deser_config` —
        `d.get("source", "")`라 저장 파일의 명시적 `null`이 그대로 들어온다).
        """
        source = self.config.source
        return source if isinstance(source, str) else ""

    def delegated_agent_name(self) -> str | None:
        """랩퍼 본문은 **자기 이름의 러너 서브에이전트**가 실행한다(WP-WR)."""
        return self.name


def is_reference_usage(component: object) -> bool:
    """참조처럼 배치되는 컴포넌트인가 — ReferenceSkill, 또는 용도가
    reference로 고정된 WrappedSkill (WP-WR, 사용자 확정 2026-09-07).

    캔버스 드롭·링크·에디터 패널·emit·검증이 전부 이 판정을 쓴다 — 표면마다
    다른 판정을 들고 있으면 참조 노드로 놓이는데 산출은 파일을 만드는 식의
    어긋남이 생긴다.

    **한 줄 파사드다**(WP-2b): 실체는 `component.effective_placement()`이고
    여기서는 그 값에 이름을 붙일 뿐이다. 새 참조 종류는 `PLACEMENT` 선언만으로
    이 판정에 합류한다 — 호출자 무수정.
    """
    return placement_role_of(component) is PlacementRole.REFERENCE


def has_external_body(component: object) -> bool:
    """본문의 **정본이 외부**에 있는가 — 본문 편집 잠금의 단일 판정.

    랩핑 스킬의 본문은 산출에 절대 도달하지 않는다: 정본은 `config.source`가
    가리키는 외부 플러그인의 SKILL.md이고, 컴파일은 그것을 인보크하라는 지시만
    만든다(WP-WR, 사용자 확정 2026-09-07). 그래서 편집기는 본문 패널을 아예
    만들지 않고(`view/editors/component_editor`), MCP 본문 쓰기 도구는
    거절한다(`mcp/tools/body`) — 두 표면이 **같은 판정**을 써야 "GUI는 막는데
    MCP는 조용히 성공"이 생기지 않는다(원칙 1·2).

    **한 줄 파사드다**(WP-2c D4): 실체는 종류가 아니라 `BODY_SOURCE` 선언이다.
    본문 정본이 외부인 종류가 랩핑 스킬 하나가 아니게 되면(외부 플러그인
    서브에이전트 등) 여기를 고치지 않고 선언을 고른다 — 종류로 물으면 새
    종류의 본문이 **편집 가능한 채로 조용히 열린다**(원칙 5).

    컴포넌트가 아닌 값(빈 노드의 `skill_ref` 등)이 섞여 들어오므로 선언 조회는
    `getattr` 폴백으로 관용한다 — 종전 `isinstance`와 같은 계약이다.
    """
    return getattr(component, "BODY_SOURCE", None) is BodySource.EXTERNAL


@dataclass
class StepSkill(Skill, WorkflowComponent, ABC):
    """워크플로 **단계** 스킬 공통 = Skill + FSM + 포트 (추상).

    절차형과 fork 2종의 부모다. 예전에는 `ForkSkill ⊂ ProceduralSkill` 상속이
    "워크플로 단계인가"를 지탱했는데, fork가 두 종류로 갈라지면서 그 판정의
    이름을 여기로 옮겼다 — `isinstance(x, StepSkill)`가 "단계(fork 포함)"이고
    `isinstance(x, ProceduralSkill)`는 "절차형만"이다.

    `kind`를 정의하지 않으므로 추상이다(인스턴스화 금지).

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      when_to_use (Skill), config, body, transfer_on, call_agents (default)

    `config`를 여기서 선언하는 이유: 구체 클래스에만 두면 순서가
    `…, when_to_use, body, transfer_on, call_agents, config`로 바뀐다(실측
    2026-09-17). 기본 팩토리는 추상 클래스지만 세 구체 클래스가 전부
    override하므로 한 번도 호출되지 않는다.
    """

    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.STATE
    CONVERT_FAMILY: ClassVar[str | None] = "step"
    REQUIRES_OUTPUT_PORTS: ClassVar[bool] = True

    config: StepSkillConfig = field(default_factory=StepSkillConfig)  # type: ignore[type-abstract]
    body: str = ""
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )
    call_agents: list[EventDef] = field(default_factory=list)

    def state_machines(self) -> list[StateMachine]:
        return [self.fsm]

    def output_ports(self) -> list[EventDef]:
        return list(self.transfer_on)

    def call_ports(self) -> list[EventDef]:
        return list(self.call_agents)

    def known_outgoing_events(self) -> frozenset[str]:
        """출력 포트 + 호출 포트 — 캔버스가 Agent Call 포트에서도 전이를 만든다."""
        return frozenset(
            [e.name for e in self.output_ports()]
            + [e.name for e in self.call_ports()]
        )


@dataclass
class ProceduralSkill(StepSkill):
    """절차형 = 메인 대화에서 그대로 도는 단계."""

    KIND: ClassVar[str] = "procedural_skill"
    CONFIG_CLS: ClassVar[type[ProceduralSkillConfig]] = ProceduralSkillConfig

    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class ForkSkill(StepSkill, ABC):
    """fork 스킬 공통 — 본문이 `config.agent` 서브에이전트의 작업 지시가 된다.

    배치·포트·전이·본문은 절차형과 같고 실행 장소만 서브에이전트다. 동기/비동기
    두 종류로 갈린다(사용자 확정 2026-09-17) — 이 클래스는 **추상**이고,
    "fork인가" 판정은 그대로 `isinstance(x, ForkSkill)`다.
    """

    RUNS_IN_SUBAGENT: ClassVar[bool] = True

    config: ForkSkillConfig = field(default_factory=ForkSkillConfig)  # type: ignore[type-abstract,assignment]

    def delegated_agent_name(self) -> str | None:
        return self.config.agent

    @classmethod
    def creation_defaults(cls, *, name: str, agent: str | None) -> dict[str, Any]:
        """새 fork 스킬은 실행 기반을 **등록 전에** 채운다.

        undo/redo에 `agent`가 빈 중간 상태를 만들지 않기 위해서다
        (`view/actions/creation.make_component`의 종전 주석).
        """
        return {"config": cls.CONFIG_CLS(agent=agent or "general-purpose")}


@dataclass
class SyncForkSkill(ForkSkill):
    """동기 fork — `background: false`. 부른 쪽이 보고를 기다려 갈래를 고른다."""

    KIND: ClassVar[str] = "sync_fork_skill"
    CONFIG_CLS: ClassVar[type[SyncForkSkillConfig]] = SyncForkSkillConfig

    config: SyncForkSkillConfig = field(default_factory=SyncForkSkillConfig)  # type: ignore[assignment]

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class AsyncForkSkill(ForkSkill):
    """비동기 fork — `background: true`. 보고는 작업 알림으로 뒤늦게 온다."""

    KIND: ClassVar[str] = "async_fork_skill"
    CONFIG_CLS: ClassVar[type[AsyncForkSkillConfig]] = AsyncForkSkillConfig
    REPORTS_OUT_OF_BAND: ClassVar[bool] = True

    config: AsyncForkSkillConfig = field(default_factory=AsyncForkSkillConfig)  # type: ignore[assignment]

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only. FSM 없음, transfer_on 없음.

    캔버스에 놓이지 않는다(`PLACEMENT`는 기저 기본값 NONE) — 모델이 알아서
    집어 쓰는 지식 스킬이다.
    """

    KIND: ClassVar[str] = "declarative_skill"
    CONFIG_CLS: ClassVar[type[DeclarativeSkillConfig]] = DeclarativeSkillConfig

    body: str = ""
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class TransferSkill(Skill, WorkflowComponent):
    """엣지 전용 스킬 — 입출력 1개 고정, transfer_on 없음."""

    KIND: ClassVar[str] = "transfer_skill"
    CONFIG_CLS: ClassVar[type[TransferSkillConfig]] = TransferSkillConfig
    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.EDGE

    config: TransferSkillConfig = field(default_factory=TransferSkillConfig)
    body: str = ""

    @property
    def kind(self) -> str:
        return self.KIND

    def state_machines(self) -> list[StateMachine]:
        return [self.fsm]


@dataclass
class ReferenceSkill(Skill):
    """참조 스킬 — FSM 없음, 재사용 가능한 참고용 노드.

    전역 정의이며 에이전트 로컬에서도 사용 가능.
    상하 방향 연결로 워크플로우 노드에 부착됨.
    """

    KIND: ClassVar[str] = "reference_skill"
    CONFIG_CLS: ClassVar[type[ReferenceSkillConfig]] = ReferenceSkillConfig
    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.REFERENCE

    body: str = ""
    config: ReferenceSkillConfig = field(default_factory=ReferenceSkillConfig)

    @property
    def kind(self) -> str:
        return self.KIND
