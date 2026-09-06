from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from uuid import uuid4

from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import (
    WrappedSkillConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스.

    본문의 단일 진실 공급원은 ``body`` 필드(마크다운 문자열)다 (WP-SB).
    새 컴포넌트의 기본값은 빈 문자열 — 구조 없는 자유 텍스트로 편집한다.
    """
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
    """
    config: WrappedSkillConfig = field(default_factory=WrappedSkillConfig)
    body: str = ""
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )
    call_agents: list[EventDef] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "wrapped_skill"

    @property
    def output_events(self) -> list[str]:
        return [e.name for e in self.transfer_on]


def is_reference_usage(component: object) -> bool:
    """참조처럼 배치되는 컴포넌트인가 — ReferenceSkill, 또는 용도가
    reference로 고정된 WrappedSkill (WP-WR, 사용자 확정 2026-09-07).

    캔버스 드롭·링크·에디터 패널·emit·검증이 전부 이 판정을 쓴다 — 표면마다
    다른 판정을 들고 있으면 참조 노드로 놓이는데 산출은 파일을 만드는 식의
    어긋남이 생긴다.
    """
    if isinstance(component, ReferenceSkill):
        return True
    return (
        isinstance(component, WrappedSkill)
        and getattr(component.config, "usage", "") == "reference"
    )


def is_disabled_wrapped(component: object) -> bool:
    """비활성으로 꺼 둔 랩핑 스킬인가 (WP-WR, 사용자 확정 2026-09-07).

    랩핑 스킬은 **삭제할 수 없고** `config.enabled`로 끈다 — 그래서 "쓰지
    않는다"를 표현하는 유일한 방법이 이 상태이고, 산출·배선·검증이 전부 이
    판정을 공유해야 한다(표면마다 다르면 꺼 뒀는데 산출에는 남는 식이 된다).
    랩핑 스킬이 아닌 컴포넌트는 항상 False — 그쪽엔 이 스위치가 없다.
    """
    return (
        isinstance(component, WrappedSkill)
        and not getattr(component.config, "enabled", True)
    )


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, body, transfer_on, call_agents (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    body: str = ""
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )
    call_agents: list[EventDef] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "procedural_skill"

    @property
    def output_events(self) -> list[str]:
        """transfer_on에서 파생된 읽기 전용 프로퍼티 (StateNodeItem 호환)."""
        return [e.name for e in self.transfer_on]


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only. FSM 없음, transfer_on 없음."""
    body: str = ""
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"


@dataclass
class TransferSkill(Skill, WorkflowComponent):
    """엣지 전용 스킬 — 입출력 1개 고정, transfer_on 없음."""
    config: TransferSkillConfig = field(default_factory=TransferSkillConfig)
    body: str = ""

    @property
    def kind(self) -> str:
        return "transfer_skill"

    @property
    def output_events(self) -> list[str]:
        return []


@dataclass
class ReferenceSkill(Skill):
    """참조 스킬 — FSM 없음, 재사용 가능한 참고용 노드.

    전역 정의이며 에이전트 로컬에서도 사용 가능.
    상하 방향 연결로 워크플로우 노드에 부착됨.
    """
    body: str = ""
    config: ReferenceSkillConfig = field(default_factory=ReferenceSkillConfig)

    @property
    def kind(self) -> str:
        return "reference_skill"
