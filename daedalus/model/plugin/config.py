from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillShell,
)


@dataclass
class ComponentConfig(ABC):
    """플러그인 컴포넌트 공통 설정."""
    model: ModelType | str = ModelType.INHERIT
    effort: EffortLevel | None = None
    hooks: dict[str, Any] | None = None

    @property
    @abstractmethod
    def kind(self) -> str:
        """설정 종류 식별자."""


@dataclass
class SkillConfig(ComponentConfig, ABC):
    """스킬 공통 프론트매터."""
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    paths: list[str] | None = None


@dataclass
class ProceduralSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True
    context: SkillContext = SkillContext.INLINE
    agent: str | None = None
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return "procedural"


@dataclass
class DeclarativeSkillConfig(SkillConfig):
    disable_model_invocation: bool = False
    user_invocable: bool = True

    @property
    def kind(self) -> str:
        return "declarative"


@dataclass
class AgentConfig(ComponentConfig):
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] | None = None
    memory: MemoryScope | None = None
    background: bool = False
    isolation: AgentIsolation = AgentIsolation.NONE
    color: AgentColor | None = None
    initial_prompt: str | None = None

    @property
    def kind(self) -> str:
        return "agent"
