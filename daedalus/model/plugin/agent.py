from __future__ import annotations

from dataclasses import dataclass, field

from daedalus.model.plugin.base import PluginComponent, WorkflowComponent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.policy import ExecutionPolicy


@dataclass
class AgentDefinition(PluginComponent, WorkflowComponent):
    """에이전트 = PluginComponent + FSM.

    필드 순서 (dataclass MRO):
      fsm (required, WorkflowComponent)
      name, description (required, PluginComponent)
      config, execution_policy (default)
    """
    config: AgentConfig = field(default_factory=AgentConfig)
    execution_policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)

    @property
    def kind(self) -> str:
        return "agent"
