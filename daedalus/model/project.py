from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import Skill


@dataclass
class PluginProject:
    name: str
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
