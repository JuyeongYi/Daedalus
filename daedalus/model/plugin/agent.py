from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy

if TYPE_CHECKING:
    from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill, TransferSkill


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, execution_policy, sections, skills (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    sections: list[Section] = field(
        default_factory=lambda: [Section(title="instruction")]
    )
    skills: list[ProceduralSkill | TransferSkill | ReferenceSkill] = field(default_factory=list)
    reference_placements: list = field(default_factory=list)  # list[ReferencePlacement]

    @property
    def kind(self) -> str:
        return "agent"

    @property
    def exit_points(self) -> list[ExitPoint]:
        """FSM states에서 ExitPoint 목록을 반환."""
        return [s for s in self.fsm.states if isinstance(s, ExitPoint)]

    @property
    def output_events(self) -> list[str]:
        """ExitPoint 이름 목록 (StateNodeItem 호환)."""
        return [ep.name for ep in self.exit_points]

    @property
    def output_event_defs(self) -> list[EventDef]:
        """노드 포트 렌더링용 — ExitPoint에서 EventDef 변환."""
        return [EventDef(name=ep.name, color=ep.color) for ep in self.exit_points]
