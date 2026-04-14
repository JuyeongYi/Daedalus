from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import Skill


@dataclass
class ReferencePlacement:
    """캔버스 위의 참조 노드 하나. 여러 상태가 공유 가능."""

    skill_name: str
    x: float = 0.0
    y: float = 0.0
    connected_states: list[str] = field(default_factory=list)


@dataclass
class PluginProject:
    name: str
    skills: list[Skill] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    reference_placements: list[ReferencePlacement] = field(default_factory=list)
