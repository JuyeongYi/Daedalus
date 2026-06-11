from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import DelegationDef
from daedalus.model.plugin.skill import Skill
from daedalus.model.plugin.tool import Tool


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
    delegations: list[DelegationDef] = field(default_factory=list)
    # 도구 선반 — BuiltinTool/MCPTool/UserDefinedTool의 단일 진실 (결정 Z: shelf).
    # FSM 전략의 ToolEvaluation/ToolExecution.tool은 여기 Tool.name을 이름으로 참조한다.
    tool_shelf: list[Tool] = field(default_factory=list)
