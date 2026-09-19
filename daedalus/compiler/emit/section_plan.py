# daedalus/compiler/emit/section_plan.py
"""절 적용 표 — **어느 종류가 어떤 절을, 어떤 순서로 내는가** (WP-6).

종전에는 이 지식이 `compile_skill`/`compile_agent` 본문의 if 사다리였다. 절
하나를 더하려면 두 함수를 읽고 "이 조건이 어느 종류를 뜻하는지"를 매번 역산해야
했고, 종류가 늘면 사다리도 늘었다. 이제는 종류마다 **순서 있는 절 튜플** 하나가
선언이고, 절마다 provider 함수 하나가 실체다.

**절 이름은 컴파일러 어휘다**(모델에 두지 않는다 — REFACTOR_SPEC §0-b). 편집기·
MCP·검증 중 어느 계층도 "이 종류가 BLACKBOARD 절을 갖는가"를 묻지 않는다. 산출
구조를 모델에 올리면 "모델이 컴파일러 배치 규칙을 흉내 낸다"는 새 위반이 된다.

**전역 절 순서 하나로는 두 산출을 만들 수 없다.** 스킬은 REQUIREMENTS가
BLACKBOARD 뒤에 오고 에이전트는 SETTINGS_NOTE가 BLACKBOARD 앞에 온다 — 그래서
순서는 전역이 아니라 **종류별 튜플**이 갖는다.

**provider는 게이트를 한 줄도 옮기지 않는다.** 각 provider는 오늘의 조건식을
그대로 감싸고, 낼 것이 없으면 빈 목록을 돌려준다(= 절 생략). 절 튜플에 없는
종류는 provider가 아예 돌지 않는다 — 종전 조립 분기의 배치 클래스 튜플(C10)이
튜플 자체로 대체됐다.

**임포트 방향.** 이 모듈은 단락 빌더를 **아래에서** 임포트하고(`skill_sections`·
`agent_sections`·`sections`·`wrapped`·`fork`), `emitters.py`를 임포트하지
않는다(provider의 emitter 인자는 타입 주석도 달지 않는다 — `TYPE_CHECKING`
블록의 임포트도 간선으로 세기 때문이다). 조립 결과에 가이드
포인터를 끼우는 후처리도 여기서 하지 않는다 — 그 판정이 다시 종류 선언을 읽어야
해서 순환이 되기 때문이다(`emitters.ComponentEmitter.render`가 맡는다,
`tests/compiler/test_emit_import_acyclic.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from daedalus.compiler.emit.agent_sections import (
    _agent_delegation_section,
    _agent_outputs_section,
    _call_contract_section,
    _describe_agent_fsm,
    _fork_base_contract_section,
    _settings_note_agent,
)
from daedalus.compiler.emit.common import (
    _body_block,
    _graph_placements,
    _graph_placements_any,
)
from daedalus.compiler.emit.fork import fork_report_section
from daedalus.compiler.emit.sections import (
    _background_references_section,
    _blackboard_section,
    _describe_fsm,
    _mcp_requirement_section_skill,
    _tool_shelf_section,
)
from daedalus.compiler.emit.skill_sections import (
    _async_fork_handoff_note,
    _async_fork_targets,
    _entry_context_section,
    _next_steps_section,
    _progress_cli,
    _progress_terminal_section,
    _progress_update_note,
    _resume_preamble_section,
    _transfer_progress_note,
)
from daedalus.compiler.emit.wrapped import (
    _wrapped_procedure_section,
    _wrapped_requirements_section,
)
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)


class SectionId(StrEnum):
    """산출 텍스트의 절 하나 — 이름은 **영어 산출 구조**의 이름이다."""

    RESUME = "resume"                        # "## Resuming Work" (WP-RS)
    ENTRY_CONTEXT = "entry_context"          # "## Entry Context" (WP-IC)
    BODY = "body"                            # 사용자 본문
    TRANSFER_PROGRESS = "transfer_progress"  # 전이 스킬의 "## Progress Record"
    DELEGATED_PROCEDURE = "delegated_procedure"  # 랩핑 스킬 "## Procedure" (WP-10 삭제)
    FSM_PROCEDURE = "fsm_procedure"          # 스킬 내부 FSM 절차
    TOOL_SHELF = "tool_shelf"                # 참조 문서 선반
    BLACKBOARD = "blackboard"                # "## Shared State (Blackboard)"
    BACKGROUND_SKILLS = "background_skills"  # 링크된 참조 용도 랩핑 스킬 consult
    REQUIREMENTS_MCP = "requirements_mcp"    # "## Requirements" (MCP 서버)
    REQUIREMENTS_WRAPPED = "requirements_wrapped"  # 〃 + 소스 플러그인 (WP-10 삭제)
    OUTCOME = "outcome"                      # 다음 단계 | fork 보고 | 작업 완료
    CALL_CONTRACT = "call_contract"          # 워크플로 에이전트 "## Invocation Contract"
    FORK_BASE_CONTRACT = "fork_base_contract"  # fork 에이전트 〃
    DELEGATION = "delegation"                # 에이전트 "## Delegation"
    SETTINGS_NOTE = "settings_note"          # 에이전트 요구 환경 언급
    INTERNAL_WORKFLOW = "internal_workflow"  # legacy 내부 FSM (WP-AF)
    EXITS = "exits"                          # "## Exits" (transfer_on)


class OutcomeStyle(StrEnum):
    """OUTCOME 절이 무엇으로 나가는가 — 종전 `is_fork`/`REPORTS_OUT_OF_BAND` 조합."""

    NEXT_STEPS = "next_steps"          # 메인 대화가 다음 단계를 부른다
    FORK_REPORT_SYNC = "fork_sync"     # 동기 fork — 보고가 지시가 된다
    FORK_REPORT_ASYNC = "fork_async"   # 비동기 fork — 보고가 늦게 닿는다


class GuidePointerRule(StrEnum):
    """공통 안내 파일 포인터를 받는 규칙 — 판정은 `pointer_rules.py`가 한다."""

    NONE = "none"                          # 포인터 없음
    MAIN_IF_PLACED = "main_placed"         # 배치돼 있으면 "main"
    MAIN_IF_ANY_PLACEMENT = "main_any"     # 그래프에 배치 노드가 있으면 "main"
    FORK_IF_PLACED = "fork_placed"         # 배치돼 있으면 "fork"


@dataclass(frozen=True)
class SectionPlan:
    """한 종류의 산출 선언 — 절 순서 + OUTCOME 양식 + 가이드 포인터 규칙."""

    sections: tuple[SectionId, ...]
    outcome_style: OutcomeStyle = OutcomeStyle.NEXT_STEPS
    guide_pointer: GuidePointerRule = GuidePointerRule.NONE
    #: **진행 사슬에 끼는 종류인가** — 종전 조립 분기의
    #: `PLACEMENT not in (EDGE, REFERENCE)` 게이트(C10)를 선언으로 옮긴 것이다.
    #: 거짓이면 OUTCOME은 자기 그래프 배치를 **보지 않는다**(= 빈 배치 목록):
    #: 진행 기록 갱신 지시도, 터미널 "작업 완료"도 내지 않는다. 엣지 스킬(전이)과
    #: 참조 노드 스킬은 자기 placement를 소유하지 않기 때문이다 — 전이 스킬이
    #: `current`를 소유하지 않는다는 규약(`compiler.md` 정책 6-a-④)과 같은 사실
    #: 이고, 게이트를 잃으면 손으로 만든 `.ddpj`(전이·참조 스킬이 상태 노드의
    #: `skill_ref`로 박힌 형상 — 역직렬화는 placement 검사를 하지 않는다)에서
    #: 같은 파일이 '## Progress Record'와 정반대의 `--current` 지시를 함께 낸다.
    tracks_progress: bool = True


# ─────────────────────────── 종류별 절 튜플 ───────────────────────────
#
# 순서는 종전 `compile_skill`/`compile_agent`의 **실제 배출 순서를 축자 전사**한
# 것이다(골든 스냅샷이 증명한다). 키는 컴포넌트 KIND 선언 — 문자열 리터럴을 쓰지
# 않는다(`tests/test_kind_literals.py`).

_STEP_SKILL_SECTIONS: tuple[SectionId, ...] = (
    SectionId.ENTRY_CONTEXT,
    SectionId.BODY,
    SectionId.FSM_PROCEDURE,
    SectionId.TOOL_SHELF,
    SectionId.BLACKBOARD,
    SectionId.BACKGROUND_SKILLS,
    SectionId.REQUIREMENTS_MCP,
    SectionId.OUTCOME,
)

SECTION_PLANS: dict[str, SectionPlan] = {
    ProceduralSkill.KIND: SectionPlan(
        sections=(SectionId.RESUME, *_STEP_SKILL_SECTIONS),
        guide_pointer=GuidePointerRule.MAIN_IF_PLACED,
    ),
    # fork 스킬에는 재개 프리앰블이 없다 — fork 서브에이전트는 사용자에게 확인하거나
    # 진행 기록을 쓸 수 없고, 재개 판단은 부르는 메인 몫이다.
    SyncForkSkill.KIND: SectionPlan(
        sections=_STEP_SKILL_SECTIONS,
        outcome_style=OutcomeStyle.FORK_REPORT_SYNC,
        guide_pointer=GuidePointerRule.FORK_IF_PLACED,
    ),
    AsyncForkSkill.KIND: SectionPlan(
        sections=_STEP_SKILL_SECTIONS,
        outcome_style=OutcomeStyle.FORK_REPORT_ASYNC,
        guide_pointer=GuidePointerRule.FORK_IF_PLACED,
    ),
    DeclarativeSkill.KIND: SectionPlan(
        sections=(
            SectionId.RESUME,
            SectionId.ENTRY_CONTEXT,
            SectionId.BODY,
            SectionId.BACKGROUND_SKILLS,
            SectionId.REQUIREMENTS_MCP,
            SectionId.OUTCOME,
        ),
        guide_pointer=GuidePointerRule.MAIN_IF_PLACED,
    ),
    TransferSkill.KIND: SectionPlan(
        sections=(
            SectionId.BODY,
            SectionId.TRANSFER_PROGRESS,
            SectionId.BACKGROUND_SKILLS,
            SectionId.REQUIREMENTS_MCP,
            SectionId.OUTCOME,
        ),
        guide_pointer=GuidePointerRule.MAIN_IF_ANY_PLACEMENT,
        # 전이 스킬은 배치가 아니라 엣지 위의 단계라 `current`를 소유하지 않는다.
        tracks_progress=False,
    ),
    ReferenceSkill.KIND: SectionPlan(
        sections=(
            SectionId.BODY,
            SectionId.BACKGROUND_SKILLS,
            SectionId.REQUIREMENTS_MCP,
            SectionId.OUTCOME,
        ),
        # 참조 스킬은 여러 노드에 링크되는 자료라 자기 placement가 없다.
        tracks_progress=False,
    ),
    WrappedSkill.KIND: SectionPlan(
        sections=(
            SectionId.RESUME,
            SectionId.ENTRY_CONTEXT,
            SectionId.BODY,
            SectionId.DELEGATED_PROCEDURE,
            SectionId.BLACKBOARD,
            SectionId.BACKGROUND_SKILLS,
            SectionId.REQUIREMENTS_WRAPPED,
            SectionId.OUTCOME,
        ),
        guide_pointer=GuidePointerRule.MAIN_IF_PLACED,
    ),
    AgentDefinition.KIND: SectionPlan(
        sections=(
            SectionId.BODY,
            SectionId.CALL_CONTRACT,
            SectionId.DELEGATION,
            SectionId.SETTINGS_NOTE,
            SectionId.INTERNAL_WORKFLOW,
            SectionId.EXITS,
            SectionId.TOOL_SHELF,
            SectionId.BLACKBOARD,
        ),
        guide_pointer=GuidePointerRule.MAIN_IF_PLACED,
    ),
    ForkAgent.KIND: SectionPlan(
        sections=(
            SectionId.BODY,
            SectionId.FORK_BASE_CONTRACT,
            SectionId.SETTINGS_NOTE,
            SectionId.TOOL_SHELF,
            SectionId.BLACKBOARD,
        ),
    ),
}


def plan_for_kind(kind: str | None) -> SectionPlan:
    """컴포넌트 종류의 절 선언 — 없으면 시끄럽게 실패한다 (원칙 5)."""
    plan = SECTION_PLANS.get(kind) if kind is not None else None
    if plan is None:
        raise ValueError(
            f"절 적용 표에 없는 컴포넌트 종류입니다: {kind!r} — "
            f"등록: {', '.join(sorted(SECTION_PLANS))}"
        )
    return plan


# ─────────────────────────── provider ───────────────────────────
#
# 시그니처는 `(component, project, emitter) -> list[str]`다. `project`는 오늘의
# 조립 함수들이 받던 것 그대로이고(`None`이면 그래프 유도 단락이 통째로 빠진다),
# `emitter`는 OUTCOME이 양식을 고를 때만 쓴다. **`CompileContext`를 받지
# 않는다** — 그 타입은 `compiler/units/`에 있고 `units.context`가 `emit`을
# 임포트하므로, emit이 반대로 units를 들이면 패키지 순환이 된다.

#: `emitter`의 타입(`emitters.ComponentEmitter`)은 **이름으로도 임포트하지
#: 않는다** — `TYPE_CHECKING` 블록의 임포트도 모듈 간 간선으로 세므로
#: (`tests/compiler/test_emit_import_acyclic.py`) 그것만으로 순환이 된다.
#: 방향은 `section_plan → emitters` 한 쪽뿐이다.
Provider = Callable[[Any, Any, Any], list[str]]


def _provide_resume(component, project, emitter) -> list[str]:
    if project is None or not _graph_placements(component, project):
        return []
    return _resume_preamble_section(project, component.name)


def _provide_entry_context(component, project, emitter) -> list[str]:
    if project is None or not _graph_placements(component, project):
        return []
    return _entry_context_section(component, project)


def _provide_body(component, project, emitter) -> list[str]:
    block = _body_block(component.body)
    return [] if block is None else [block]


def _provide_transfer_progress(component, project, emitter) -> list[str]:
    if project is None or not _graph_placements_any(project):
        return []
    return ["## Progress Record", _transfer_progress_note(project)]


def _provide_delegated_procedure(component, project, emitter) -> list[str]:
    return _wrapped_procedure_section(component)


def _provide_fsm_procedure(component, project, emitter) -> list[str]:
    # "어떤 FSM을 갖는가"는 컴포넌트가 답한다(`state_machines()`, Q2).
    return [b for sm in component.state_machines() for b in _describe_fsm(sm, component)]


def _provide_tool_shelf(component, project, emitter) -> list[str]:
    return [] if project is None else _tool_shelf_section(project)


def _provide_blackboard(component, project, emitter) -> list[str]:
    return [] if project is None else _blackboard_section(project, component)


def _provide_background_skills(component, project, emitter) -> list[str]:
    return [] if project is None else _background_references_section(component, project)


def _provide_requirements_mcp(component, project, emitter) -> list[str]:
    return _mcp_requirement_section_skill(component)


def _provide_requirements_wrapped(component, project, emitter) -> list[str]:
    return _wrapped_requirements_section(component)


def _provide_call_contract(component, project, emitter) -> list[str]:
    return _call_contract_section(component, project)


def _provide_fork_base_contract(component, project, emitter) -> list[str]:
    return _fork_base_contract_section(component, project)


def _provide_delegation(component, project, emitter) -> list[str]:
    return _agent_delegation_section(component, project)


def _provide_settings_note(component, project, emitter) -> list[str]:
    return _settings_note_agent(component, project)


def _provide_internal_workflow(component, project, emitter) -> list[str]:
    return _describe_agent_fsm(component)


def _provide_exits(component, project, emitter) -> list[str]:
    return _agent_outputs_section(component)


def _provide_outcome(component, project, emitter) -> list[str]:
    """다음 단계(버그 2) · fork 보고(WP-FK2) · 작업 완료(WP-RS Part A-3).

    셋은 **같은 갈래 목록**에서 나오고 서로 배타적이라 provider 하나다 —
    나누면 placement·outgoing 계산이 세 벌이 되고 한쪽만 고치는 날이 온다.
    """
    if project is None:
        return []
    # 진행 사슬에 끼지 않는 종류(전이·참조)는 자기 배치를 **보지 않는다** —
    # 선언은 절 표의 `tracks_progress`다(종전 배치 클래스 튜플 게이트, C10).
    placements = (
        _graph_placements(component, project) if emitter.tracks_progress else []
    )
    next_blocks = _next_steps_section(component, project)
    has_outgoing = any(
        t.source is p
        for p in placements
        for t in getattr(project.graph, "transitions", [])
    )
    is_fork = emitter.outcome_style is not OutcomeStyle.NEXT_STEPS
    if is_fork and placements:
        # 갈래 목록은 Next Steps와 같은 것을 쓰되, 실행 지시가 아니라 보고 양식이다.
        return list(fork_report_section(
            _progress_cli(project),
            next_blocks[-1] if next_blocks else "",
            terminal=not has_outgoing,
            background=emitter.outcome_style is OutcomeStyle.FORK_REPORT_ASYNC,
            skill_name=component.name,
        ))
    if next_blocks:
        if placements:
            next_blocks = list(next_blocks)
            note = _progress_update_note(project)
            # 비동기 fork로 넘기는 갈래가 있으면 `current` 소유 규약을 덧붙인다
            # (오케스트레이터 확정 2026-09-18 — fork 쪽 선행 조건과 짝을 이룬다).
            bg_targets = _async_fork_targets(component, project)
            if bg_targets:
                note += "\n" + _async_fork_handoff_note(
                    _progress_cli(project), bg_targets,
                )
            next_blocks[-1] = next_blocks[-1] + "\n\n" + note
        return list(next_blocks)
    if placements and not has_outgoing:
        return _progress_terminal_section(project)
    return []


#: 절 → 그 절을 만드는 함수. 절 튜플에 있는데 여기 없으면 조립이 **시끄럽게**
#: 멈춘다 — 조용히 건너뛰면 산출에서 단락 하나가 아무 말 없이 사라진다(원칙 5).
SECTION_PROVIDERS: dict[SectionId, Provider] = {
    SectionId.RESUME: _provide_resume,
    SectionId.ENTRY_CONTEXT: _provide_entry_context,
    SectionId.BODY: _provide_body,
    SectionId.TRANSFER_PROGRESS: _provide_transfer_progress,
    SectionId.DELEGATED_PROCEDURE: _provide_delegated_procedure,
    SectionId.FSM_PROCEDURE: _provide_fsm_procedure,
    SectionId.TOOL_SHELF: _provide_tool_shelf,
    SectionId.BLACKBOARD: _provide_blackboard,
    SectionId.BACKGROUND_SKILLS: _provide_background_skills,
    SectionId.REQUIREMENTS_MCP: _provide_requirements_mcp,
    SectionId.REQUIREMENTS_WRAPPED: _provide_requirements_wrapped,
    SectionId.OUTCOME: _provide_outcome,
    SectionId.CALL_CONTRACT: _provide_call_contract,
    SectionId.FORK_BASE_CONTRACT: _provide_fork_base_contract,
    SectionId.DELEGATION: _provide_delegation,
    SectionId.SETTINGS_NOTE: _provide_settings_note,
    SectionId.INTERNAL_WORKFLOW: _provide_internal_workflow,
    SectionId.EXITS: _provide_exits,
}


def provider_for(section: SectionId) -> Provider:
    """절 provider — 없으면 ValueError + 등록 목록 (원칙 5)."""
    provider = SECTION_PROVIDERS.get(section)
    if provider is None:
        raise ValueError(
            f"절 '{section}'의 provider가 없습니다 — "
            f"등록: {', '.join(sorted(SECTION_PROVIDERS))}"
        )
    return provider


def assemble_blocks(component, project, resolved_hooks, emitter) -> list[str]:
    """프론트매터 블록 + 절 튜플 순서대로의 블록 목록.

    `resolved_hooks`는 프론트매터 훅 블록에만 쓰인다(전역 훅 A1 — 원칙 4의
    주입 인자). 절 provider는 아무도 읽지 않으므로 provider 시그니처에는 없다.

    가이드 포인터 삽입은 여기서 하지 않는다(`ComponentEmitter.render`) —
    §4-b 임포트 방향.
    """
    blocks: list[str] = [
        emitter.frontmatter_block(component, project, resolved_hooks)
    ]
    for section in emitter.sections:
        blocks.extend(provider_for(section)(component, project, emitter))
    return blocks
