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
# 진입 의미론 두 필드는 **tri-state**다 (A8): None = 미지정(프론트매터 키 생략 →
# CC 기본값에 위임) / True·False = 명시 지정. 순수 bool이면 "기본값을 쓴다"와
# "기본값과 같은 값을 못 박았다"가 구분되지 않아, 캔버스 프리셋의 "일반 상태로"
# (두 필드 미지정)를 표현할 수 없다. 컴파일은 기존 규칙 그대로 동작한다 —
# "OPTIONAL 값이 선언 기본값과 같으면 생략"에서 선언 기본값이 None이 되므로
# None은 생략되고 명시 True/False는 발행된다(`user-invocable: true`가 나가는 것은
# 사용자가 진입점으로 못 박았다는 뜻이라 정상이다).
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None
    context: SkillContext = SkillContext.INLINE
    agent: str | None = None
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return "procedural"


@dataclass
class WrappedSkillConfig(SkillConfig):
    """스킬 랩핑 (WP-WR) — 다른 플러그인 스킬의 절차 재사용.

    ``source``가 핵심이다: ``<플러그인>:<스킬>`` 문자열 참조로, 본문의 정본은
    그 스킬이고 랩퍼는 워크플로 위치·배선·프론트매터만 소유한다(사용자 확정 —
    본문 수정 불가). 진입 의미론 tri-state는 ProceduralSkillConfig와 동일.

    ``usage``(사용자 확정 2026-09-07): ""(미정) / "state" / "reference".
    최초 배치 시 사용자가 고르면 **고정**된다 — 한 랩핑 스킬이 워크플로
    단계와 참조 두 용도로 동시에 쓰이는 것을 막는다. state는 단일 배치 +
    SKILL.md 산출(현행), reference는 참조 노드 복수 배치 + **산출 파일 없음**
    (링크된 노드의 산출에 consult 지시만 합류). 배치 경로가 고정하는 파생
    상태라 프론트매터로 나가지 않고 매트릭스에도 없다(set_component_field
    거부). 구버전 파일(키 부재)은 "state"로 로드된다 — 그때는 state만 있었다.

    ``enabled``(사용자 확정 2026-09-07 — "삭제가 불가능하게 해라. 삭제 대신
    비활성화"): 랩핑 스킬은 **지울 수 없고** 이 스위치로 끈다. 소스·프론트매터·
    배선을 다시 입력하는 비용이 큰 데다, 지우면 이 프로젝트가 그 외부 스킬을
    한때 썼다는 사실 자체가 사라진다. `False`면 산출에서 빠지고(state 용도는
    SKILL.md 미산출, reference 용도는 consult 지시 미합류) 외부 플러그인 배선
    판정에서도 참조로 치지 않는다 — 꺼둔 것은 쓰지 않는 것이다. 구버전
    파일(키 부재)은 True.
    """
    source: str = ""
    usage: str = ""
    enabled: bool = True
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None

    @property
    def kind(self) -> str:
        return "wrapped"


@dataclass
class DeclarativeSkillConfig(SkillConfig):
    # tri-state — ProceduralSkillConfig의 같은 필드 주석 참조 (A8).
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None

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


