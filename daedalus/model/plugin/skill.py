from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import DeclarativeSkillConfig, ProceduralSkillConfig


@dataclass
class Skill(PluginComponent, ABC):
    """스킬 베이스."""


@dataclass
class ProceduralSkill(Skill, WorkflowComponent):
    """절차형 = Skill + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, sections, transfer_on (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    sections: list[Section] = field(default_factory=list)
    transfer_on: list[EventDef] = field(
        default_factory=lambda: [EventDef("done")]
    )

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
    sections: list[Section] = field(default_factory=list)
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"
