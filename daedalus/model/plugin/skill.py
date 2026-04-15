from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import (
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""
    when_to_use: str = ""


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, sections, transfer_on, call_agents (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    sections: list[Section] = field(
        default_factory=lambda: [Section("Instructions")]
    )
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
    content: str = ""
    sections: list[Section] = field(
        default_factory=lambda: [Section("Instructions")]
    )
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"


@dataclass
class TransferSkill(Skill, WorkflowComponent):
    """엣지 전용 스킬 — 입출력 1개 고정, transfer_on 없음."""
    config: TransferSkillConfig = field(default_factory=TransferSkillConfig)
    sections: list[Section] = field(
        default_factory=lambda: [Section("Instructions")]
    )

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
    content: str = ""
    sections: list[Section] = field(
        default_factory=lambda: [Section("Content")]
    )
    config: ReferenceSkillConfig = field(default_factory=ReferenceSkillConfig)

    @property
    def kind(self) -> str:
        return "reference_skill"
