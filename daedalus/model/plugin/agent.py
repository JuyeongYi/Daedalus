from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from daedalus.model.fsm.section import EventDef

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
    graph_layout: dict[str, list[float]] = field(default_factory=dict)
    # WP-ER — 전이 엣지의 경유점(waypoint) 좌표. 키는 Transition.id, 값은 [x, y] 목록
    # (소스→타깃 순서). PluginProject.edge_layout과 동일 규약.
    edge_layout: dict[str, list[list[float]]] = field(default_factory=dict)
    # WP-AF — 출력 포트. 내부 FSM 퇴역 후 에이전트의 결과 분기는 스킬과 동일하게
    # transfer_on이 담는다. v1 파일의 ExitPoint 출력 포트는 로드 시 transfer_on으로
    # 마이그레이션된다(serialize._migrate_v1) — 여기가 단일 진실이다.
    transfer_on: list[EventDef] = field(default_factory=list)
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    @property
    def kind(self) -> str:
        return "agent"

    @property
    def output_events(self) -> list[str]:
        """출력 포트 이름 목록 (StateNodeItem 호환) — transfer_on이 단일 진실."""
        return [e.name for e in self.transfer_on]

    @property
    def output_event_defs(self) -> list[EventDef]:
        """노드 포트 렌더링용 EventDef 목록 — output_events와 같은 소스."""
        return list(self.transfer_on)
