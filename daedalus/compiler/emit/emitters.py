# daedalus/compiler/emit/emitters.py
"""kind별 `ComponentEmitter` — **각 종류가 자기 산출을 안다** (WP-6).

지시문의 *"각각의 구성요소가 알아서 자기 할 일을 하도록"*의 컴파일러 쪽 실체다.
종전에는 `compile_skill`/`compile_agent` 두 함수가 종류를 열거하는 if 사다리로
프론트매터·절 순서·산출 파일 개수를 한꺼번에 결정했다. 이제는

- **무엇을 내는가**(파일 0..N개·경로 종류·계획 kind) → `outputs()`
- **프론트매터가 어떻게 생겼는가** → `frontmatter_block()`
- **어떤 절을 어떤 순서로 내는가** → `section_plan.SECTION_PLANS`의 선언
- **텍스트 조립** → `section_plan.assemble_blocks` + 가이드 포인터 후처리

를 종류마다 한 객체가 말한다. 새 종류는 emitter 한 줄 + 절 표 한 행이고,
빠뜨리면 `EMITTERS` 패리티 테스트가 **시끄럽게** 실패한다(원칙 5).

**경로를 조립하지 않는다.** `EmittedFile`은 "어느 자리(`OutputLocation`)에 어떤
이름으로"까지만 말하고, `<cc>/skills/<n>/SKILL.md` 같은 CC 플러그인 레이아웃
조립은 `compiler/units/paths.py`가 한다 — `emit`은 `units`보다 **아래**이고
(`units.context`가 `emit`을 임포트한다) 반대 방향 간선은 패키지 순환이 된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from daedalus.compiler import plan_kinds
from daedalus.compiler.emit.blackboard_tools import bb_tools_for
from daedalus.compiler.emit.common import _join_blocks
from daedalus.compiler.emit.fork import fork_frontmatter_lines
from daedalus.compiler.emit.frontmatter import (
    _frontmatter_block,
    _frontmatter_lines_skill,
    _yaml_block_lines,
)
from daedalus.compiler.emit.agent_sections import (
    _frontmatter_lines_agent,
    _local_settings_frontmatter_lines,
)
from daedalus.compiler.emit.guides import _insert_guide_pointer
from daedalus.compiler.emit.hooks import component_hook_groups
from daedalus.compiler.emit.section_plan import (
    GuidePointerRule,
    OutcomeStyle,
    SectionId,
    assemble_blocks,
    plan_for_kind,
)
from daedalus.compiler.token_report import TokenKind
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.roles import OutputLocation
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
)


@dataclass(frozen=True)
class EmittedFile:
    """이 컴포넌트가 내는 산출 파일 1건의 **선언**.

    경로 조립(CC 플러그인 레이아웃)은 호출자가 한다 — 여기는 "어느 자리에 어떤
    이름으로, 어떤 계획 kind로"까지다.
    """

    location: OutputLocation
    name: str
    label: str
    plan_kind: str


class ComponentEmitter(ABC):
    """한 종류의 산출 텍스트와 산출 파일 선언."""

    #: 컴포넌트 KIND(`ProceduralSkill.KIND` …) — `EMITTERS`의 키.
    kind: ClassVar[str]
    #: 주 산출의 계획 kind(`plan_kinds.SKILL` | `plan_kinds.AGENT`).
    plan_kind: ClassVar[str]
    #: 사람이 읽는 표지 — 게이트 에러 문구가 쓴다.
    label_fmt: ClassVar[str]
    #: 타깃 중립 토큰 `${ROOT}`를 빌드 타깃 변수로 확장하는가 (WP-RT).
    expands_root: ClassVar[bool] = True
    #: 토큰 계기판에서 세는 방식 (A5-lite) — 컴포넌트 산출은 컨텍스트에 실린다.
    token_kind: ClassVar[TokenKind] = TokenKind.CONTEXT

    @property
    def sections(self) -> tuple[SectionId, ...]:
        return plan_for_kind(self.kind).sections

    @property
    def outcome_style(self) -> OutcomeStyle:
        return plan_for_kind(self.kind).outcome_style

    @property
    def guide_pointer(self) -> GuidePointerRule:
        return plan_for_kind(self.kind).guide_pointer

    @property
    def tracks_progress(self) -> bool:
        """진행 사슬에 끼는 종류인가 — OUTCOME 절이 자기 배치를 보는가."""
        return plan_for_kind(self.kind).tracks_progress

    def outputs(self, component) -> list[EmittedFile]:
        """이 컴포넌트가 내는 산출 파일 0..N개.

        기본은 `emits_output()`이면 선언된 자리에 1개다. 산출이 없는 종류
        (`OUTPUT_LOCATION is NONE`·비활성·참조 용도)는 빈 목록이므로 **이름
        게이트도 받지 않는다**.
        """
        if not component.emits_output():
            return []
        return [EmittedFile(
            location=type(component).OUTPUT_LOCATION,
            name=component.name,
            label=self.label_fmt.format(name=component.name),
            plan_kind=self.plan_kind,
        )]

    @abstractmethod
    def frontmatter_block(self, component, project, resolved_hooks) -> str:
        """`---`로 감싼 프론트매터 블록."""

    def render(self, component, project=None, resolved_hooks=None) -> str:
        """산출 텍스트 1건 (LF, BOM 없음, 결정적)."""
        blocks = assemble_blocks(component, project, resolved_hooks, self)
        _insert_guide_pointer(blocks, component, project)
        return _join_blocks(blocks)


class SkillEmitter(ComponentEmitter, ABC):
    """스킬 산출 — `skills/<이름>/SKILL.md` 1개 + 스킬 프론트매터 표."""

    plan_kind = plan_kinds.SKILL
    label_fmt = "스킬 '{name}'"
    def frontmatter_block(self, component, project, resolved_hooks) -> str:
        # 블랙보드 권한 유도(WP-BM) — 스킬의 `allowed-tools`는 권한 **부여**라
        # 합류가 곧 "이 스킬은 블랙보드를 만질 수 있다"이다. fork 스킬은 빈
        # 목록을 받는다(도구를 부여하는 것은 그 fork 에이전트의 파일이다).
        lines = _frontmatter_lines_skill(component, bb_tools_for(component, project))
        lines = self.adjust_frontmatter(lines, component, project)
        # 스킬 훅 — 스킬이 활성인 동안만 걸린다(2026-09-13 실측: 플러그인 스킬도
        # 동작). settings.json과 같은 3단 구조라 한 줄 키-값이 아니라 블록으로 낸다.
        hook_groups = component_hook_groups(component, project, resolved_hooks)
        if hook_groups:
            lines.append("hooks:")
            lines.extend(_yaml_block_lines(hook_groups, 2))
        return _frontmatter_block(lines)

    def adjust_frontmatter(self, lines: list[str], component, project) -> list[str]:
        """매트릭스가 만든 줄에 종류 전용 보정을 건다. 기본은 보정 없음."""
        return lines


class ProceduralEmitter(SkillEmitter):
    kind = ProceduralSkill.KIND


class ForkSkillEmitter(SkillEmitter, ABC):
    """fork 스킬 2종 공통 — `agent:` 이름 해소만 다르다."""

    def adjust_frontmatter(self, lines, component, project) -> list[str]:
        return fork_frontmatter_lines(lines, component, project)


class SyncForkEmitter(ForkSkillEmitter):
    kind = SyncForkSkill.KIND


class AsyncForkEmitter(ForkSkillEmitter):
    kind = AsyncForkSkill.KIND


class DeclarativeEmitter(SkillEmitter):
    kind = DeclarativeSkill.KIND


class TransferEmitter(SkillEmitter):
    kind = TransferSkill.KIND


class ReferenceEmitter(SkillEmitter):
    kind = ReferenceSkill.KIND


class AgentEmitter(ComponentEmitter, ABC):
    """에이전트 산출 — `agents/<이름>.md` 1개 + 에이전트 프론트매터 표."""

    plan_kind = plan_kinds.AGENT
    label_fmt = "에이전트 '{name}'"

    def frontmatter_block(self, component, project, resolved_hooks) -> str:
        bb_tools = bb_tools_for(component, project)
        lines = _frontmatter_lines_agent(component, project, bb_tools)
        # LOCAL 빌드에서만 hooks/mcpServers가 프론트매터로 나간다 (WP-LA)
        lines.extend(_local_settings_frontmatter_lines(
            component, project, resolved_hooks, bb_tools,
        ))
        return _frontmatter_block(lines)


class WorkflowAgentEmitter(AgentEmitter):
    kind = AgentDefinition.KIND


class ForkAgentEmitter(AgentEmitter):
    kind = ForkAgent.KIND


#: 종류 → emitter. **산출 파일을 내는 종류마다 정확히 하나**이고,
#: `OUTPUT_LOCATION is NONE`인 종류는 여기 없다(패리티 테스트가 양방향 고정).
EMITTERS: dict[str, ComponentEmitter] = {
    e.kind: e for e in (
        ProceduralEmitter(),
        SyncForkEmitter(),
        AsyncForkEmitter(),
        DeclarativeEmitter(),
        TransferEmitter(),
        ReferenceEmitter(),
        WorkflowAgentEmitter(),
        ForkAgentEmitter(),
    )
}


def emitter_for(component) -> ComponentEmitter:
    """컴포넌트 → emitter. 없으면 시끄럽게 실패한다 (원칙 5).

    `OUTPUT_LOCATION is NONE`인 종류에는 emitter가 없으므로 여기서 걸린다 —
    호출자는 그 앞에서 `emits_output()`으로 거른다(`ComponentUnit.plan`).
    """
    kind = getattr(type(component), "KIND", None)
    emitter = EMITTERS.get(kind) if kind is not None else None
    if emitter is None:
        raise ValueError(
            f"산출 emitter가 없는 컴포넌트 종류입니다: {kind!r} — "
            f"등록: {', '.join(sorted(EMITTERS))}"
        )
    return emitter


def compile_skill(skill, *, project=None, resolved_hooks=None) -> str:
    """단일 스킬 → SKILL.md 텍스트 — **emitter 파사드**(종전 진입점).

    project가 주어지면 그래프 유도 단락(다음 단계·진입 맥락·블랙보드 …)까지
    포함된 실제와 같은 산출이 된다.
    """
    return emitter_for(skill).render(skill, project, resolved_hooks)


def compile_agent(agent, project=None, resolved_hooks=None) -> str:
    """에이전트 → agent .md 텍스트 — **emitter 파사드**(종전 진입점).

    그래프 유도 단락은 절 표가 가른다: fork 에이전트의 튜플에는 호출 계약·내부
    워크플로·출구가 없다(fsm도 포트도 배치도 없어 부르면 AttributeError다).
    """
    return emitter_for(agent).render(agent, project, resolved_hooks)
