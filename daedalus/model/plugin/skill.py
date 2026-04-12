from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

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
      config, output_events (default)
    """
    config: ProceduralSkillConfig = field(default_factory=ProceduralSkillConfig)
    output_events: list[str] = field(default_factory=lambda: ["done"])

    @property
    def kind(self) -> str:
        return "procedural_skill"


@dataclass
class DeclarativeSkill(Skill):
    """선언형 = Skill only. FSM 없음."""
    content: str = ""
    config: DeclarativeSkillConfig = field(default_factory=DeclarativeSkillConfig)

    @property
    def kind(self) -> str:
        return "declarative_skill"
