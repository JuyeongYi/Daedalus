from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from uuid import uuid4

from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import (
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
