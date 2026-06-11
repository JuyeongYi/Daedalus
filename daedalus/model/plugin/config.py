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
    # hooks: 키 = PluginProject.hook_library의 HookDef.name 참조,
    #        값 = 오버라이드 dict (빈 dict면 HookDef 정의 그대로 사용).
    # 이름 참조 규약은 tool_shelf 선례와 동일하며, 빈 dict 본문 보존 write-back
    # (skill_editor의 {name: existing.get(name, {})})과 자연 호환된다.
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
    mcp_servers: list[str] | None = None  # MCP 서버 이름 참조 목록 — 서버 정의 자체는 .mcp.json 등 외부 소유, 모델은 이름만 참조
    memory: MemoryScope | None = None
    background: bool = False
    isolation: AgentIsolation = AgentIsolation.NONE
    color: AgentColor | None = None

    @property
    def kind(self) -> str:
        return "agent"


@dataclass
class TransferSkillConfig(SkillConfig):
    """전이 엣지 전용 스킬 설정. user_invocable은 항상 False (UI 노출 불필요)."""
    disable_model_invocation: bool = False
    user_invocable: bool = False   # fixed — transfer skills are never user-invocable
    context: SkillContext = SkillContext.INLINE
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return "transfer"


@dataclass
class ReferenceSkillConfig(SkillConfig):
    """참조 스킬 설정. 워크플로우에 참여하지 않는 참고용 노드."""
    user_invocable: bool = False

    @property
    def kind(self) -> str:
        return "reference"


