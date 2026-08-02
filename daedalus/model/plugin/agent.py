from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

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
      config, execution_policy, body, skills (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    body: str = ""
    skills: list[ProceduralSkill | TransferSkill | ReferenceSkill] = field(default_factory=list)
    reference_placements: list = field(default_factory=list)  # list[ReferencePlacement]
    caller_contracts: list[Section] = field(default_factory=list)
    graph_layout: dict[str, list[float]] = field(default_factory=dict)
    # WP-IC — 입력 포트 정의. 빈 리스트 = 기본 포트 1개(암묵, 이름 없음).
    entry_paths: list[EventDef] = field(default_factory=list)
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

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
