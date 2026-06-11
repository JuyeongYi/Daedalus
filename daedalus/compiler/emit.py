# daedalus/compiler/emit.py
"""model → 마크다운 텍스트 생성 (순수 — 파일시스템·PyQt 무관).

여기서는 문자열만 만든다. 파일 쓰기·게이트는 project_compiler.py가 담당한다.
출력은 결정적이다 (같은 모델 → 같은 문자열, LF 줄바꿈).

확정 정책 (WP-compiler-v0):
  1. 프론트매터: 해당 kind 매트릭스에서 emit==FRONTMATTER인 필드만. 키는
     frontmatter_key. FIXED는 fixed_value 강제. model==INHERIT는 키 생략.
     OPTIONAL 필드 값이 선언 기본값과 같으면 생략. enum은 .value.
  2. when_to_use: description과 합류 — "<description> Use when <when_to_use>".
  3. 본문: sections 트리 → 헤딩 깊이(H1=루트).
  4. ProceduralSkill FSM → 사람이 읽는 절차 단락.
  5. 위임 노드: 스펙 4절 + 1-b절(guided) 문구.
  6. tool_shelf: 참조 문서 단락.
"""
from __future__ import annotations

import json
from dataclasses import MISSING as _DC_MISSING
from dataclasses import fields as dc_fields
from enum import Enum
from typing import Any

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    SimpleState,
    State,
)
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    EvaluationStrategy,
    ExpressionEvaluation,
    LLMEvaluation,
    MCPEvaluation,
    ToolEvaluation,
)
from daedalus.model.fsm.section import Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DelegationDef,
    DispatchMode,
    DynamicWorkflowDef,
    TeamSpawnDef,
    WaitMode,
)
from daedalus.model.plugin.enums import (
    AgentField,
    FieldEmit,
    FieldVisibility,
    ModelType,
    SkillField,
)
from daedalus.model.plugin.field_matrix import (
    AGENT_FIELD_MATRIX,
    SKILL_FIELD_MATRIX,
    FieldRule,
)
from daedalus.model.plugin.hook import HookDef, HookEvent, TOOL_MATCH_EVENTS
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    Skill,
    TransferSkill,
)


# ─────────────────────────── 공통 헬퍼 ───────────────────────────


def _enum_value(v: Any) -> Any:
    """enum이면 .value, 아니면 그대로."""
    return v.value if isinstance(v, Enum) else v


# YAML이 boolean/null로 오파싱할 수 있는 예약 스칼라 (YAML 1.1 포함 보수적 집합).
# 문자열 값이 이와 (대소문자 무시) 일치하면 따옴표로 보호한다.
_YAML_RESERVED: frozenset[str] = frozenset({
    "true", "false", "null", "~", "yes", "no", "on", "off", "",
})


def _yaml_scalar(v: Any) -> str:
    """프론트매터 스칼라 값을 YAML 표기로. bool은 true/false, 나머지는 문자열."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # YAML 예약 스칼라(true/null/yes/…)는 따옴표로 보호 — boolean/null 오파싱 방지.
    if s.lower() in _YAML_RESERVED:
        return '"' + s + '"'
    # 콜론/특수문자 포함 시 따옴표 — 보수적으로 콜론+공백, 선두 특수문자만 감싼다.
    if (": " in s) or s.startswith(("#", "-", "[", "{", "*", "&", "!", "|", ">", "@")):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _yaml_list(values: list[Any]) -> str:
    """flow-style YAML 리스트: [a, b, c]."""
    items = ", ".join(_yaml_scalar(_enum_value(v)) for v in values)
    return f"[{items}]"


def _config_default(config: ComponentConfig | None, attr: str) -> Any:
    """config 클래스의 선언 기본값(단일 진실)을 반환. 없으면 sentinel."""
    if config is None:
        return _MISSING
    for f in dc_fields(type(config)):
        if f.name == attr:
            if f.default is not _DC_MISSING:
                return f.default
            if f.default_factory is not _DC_MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
    return _MISSING


class _Missing:
    pass


_MISSING = _Missing()


# ─────────────────────────── 프론트매터 ───────────────────────────


def _frontmatter_lines_skill(
    skill: Skill, kind_key: str,
) -> list[str]:
    """스킬 프론트매터 키-값 줄 목록 (--- 구분선 제외).

    name/description은 항상 출력(REQUIRED). when_to_use는 description에 합류하므로
    여기서는 직출하지 않는다. 나머지는 매트릭스 emit==FRONTMATTER + visibility 규칙.
    """
    matrix = SKILL_FIELD_MATRIX[kind_key]
    config = getattr(skill, "config", None)
    lines: list[str] = []

    for sfield in SkillField:
        rule = matrix[sfield]
        if rule.emit is not FieldEmit.FRONTMATTER:
            continue
        key = sfield.frontmatter_key
        if key is None:  # WHEN_TO_USE — 본문/description 합류
            continue

        if sfield is SkillField.NAME:
            lines.append(f"{key}: {_yaml_scalar(skill.name)}")
            continue
        if sfield is SkillField.DESCRIPTION:
            lines.append(f"{key}: {_yaml_scalar(_compose_description(skill))}")
            continue

        emitted = _emit_skill_field(sfield, rule, skill, config, key)
        if emitted is not None:
            lines.append(emitted)
    return lines


def _emit_skill_field(
    sfield: SkillField,
    rule: FieldRule,
    skill: Skill,
    config: ComponentConfig | None,
    key: str,
) -> str | None:
    """단일 스킬 프론트매터 필드를 YAML 줄로. 생략 시 None."""
    attr = sfield.value  # SkillField.value == config 속성명

    # FIXED — config 무시, fixed_value 강제
    if rule.visibility is FieldVisibility.FIXED:
        return _format_kv(key, rule.fixed_value)

    # config에서 실제 값 읽기
    value = getattr(config, attr, _MISSING) if config is not None else _MISSING
    if value is _MISSING or value is None:
        return None

    # model == INHERIT 이면 키 생략
    if sfield is SkillField.MODEL and value is ModelType.INHERIT:
        return None

    # 빈 컬렉션은 생략
    if isinstance(value, (list, dict)) and not value:
        return None

    # hooks(dict[str, Any]) — 프론트매터에는 참조 이름 목록만 표기(flow-list).
    # 본문 풀이 단락은 두지 않는다 (이름 참조 규약). 라이브러리 실존은 게이트가 검증.
    if sfield is SkillField.HOOKS and isinstance(value, dict):
        return _format_kv(key, list(value.keys()))

    # REQUIRED 외에는 선언 기본값과 같으면 생략(잡음 제거)
    if rule.visibility is not FieldVisibility.REQUIRED:
        default = _config_default(config, attr)
        if default is not _MISSING and value == default:
            return None

    return _format_kv(key, value)


def _format_kv(key: str, value: Any) -> str:
    """키-값 한 줄. 리스트는 flow-list, enum/스칼라는 스칼라."""
    if isinstance(value, list):
        return f"{key}: {_yaml_list(value)}"
    return f"{key}: {_yaml_scalar(_enum_value(value))}"


def _compose_description(component: Skill | AgentDefinition) -> str:
    """description + when_to_use 합류.

    정책 2: description이 있으면 "<description> Use when <when_to_use>".
    description이 비어 있으면 when_to_use만(있을 때). 둘 다 비면 빈 문자열.
    when_to_use는 Skill에만 있으므로 getattr 가드.
    """
    desc = (component.description or "").strip()
    when = (getattr(component, "when_to_use", "") or "").strip()
    if desc and when:
        sep = " " if desc.endswith((".", "!", "?")) else ". "
        return f"{desc}{sep}Use when {when}"
    if desc:
        return desc
    if when:
        return f"Use when {when}"
    return ""


def _frontmatter_block(lines: list[str]) -> str:
    """--- 로 감싼 프론트매터 블록 문자열."""
    body = "\n".join(lines)
    return f"---\n{body}\n---"


# ─────────────────────────── 본문(sections) ───────────────────────────


def _render_sections(sections: list[Section], depth: int = 1) -> list[str]:
    """sections 트리를 마크다운 블록 목록으로. depth=1 → H1(#)."""
    blocks: list[str] = []
    for sec in sections:
        hashes = "#" * min(depth, 6)
        blocks.append(f"{hashes} {sec.title}".rstrip())
        content = (sec.content or "").strip("\n")
        if content.strip():
            blocks.append(content)
        if sec.children:
            blocks.extend(_render_sections(sec.children, depth + 1))
    return blocks


# ─────────────────────────── 가드/트리거 서술 ───────────────────────────


def _describe_evaluation(ev: EvaluationStrategy) -> str:
    """EvaluationStrategy를 사람이 읽는 한 줄 조건으로."""
    if isinstance(ev, LLMEvaluation):
        return f"LLM 판단({ev.prompt})" if ev.prompt else "LLM 판단"
    if isinstance(ev, ToolEvaluation):
        cond = f" (성공 조건: {ev.success_condition})" if ev.success_condition else ""
        tool = ev.tool or "도구"
        return f"도구 '{tool}' 실행 결과{cond}"
    if isinstance(ev, MCPEvaluation):
        return f"MCP '{ev.server}.{ev.tool}' 결과"
    if isinstance(ev, ExpressionEvaluation):
        return f"표현식 `{ev.expression}`" if ev.expression else "표현식"
    if isinstance(ev, CompositeEvaluation):
        op = " AND " if ev.operator == "and" else " OR "
        inner = op.join(_describe_evaluation(c) for c in ev.children)
        return f"({inner})" if inner else "복합 조건"
    return "조건"


def _describe_guard(guard: Guard | None) -> str:
    if guard is None:
        return ""
    return _describe_evaluation(guard.evaluation)


def _describe_trigger(trigger: object) -> str:
    if trigger is None:
        return ""
    name = getattr(trigger, "name", "")
    if isinstance(trigger, CompletionEvent):
        return f"완료 이벤트 '{name}'"
    return f"이벤트 '{name}'" if name else ""


def _transition_condition(t) -> str:
    """전이 조건 문구(트리거 + 가드)를 조합."""
    parts: list[str] = []
    trig = _describe_trigger(t.trigger)
    if trig:
        parts.append(trig)
    g = _describe_guard(t.guard)
    if g:
        parts.append(f"가드: {g}")
    return ", ".join(parts)


# ─────────────────────────── FSM 절차 서술 ───────────────────────────


def _state_label(state: State) -> str:
    """상태 노드를 가리키는 표지 — 이름 + 종류 표식."""
    return state.name


def _describe_node_action(state: SimpleState) -> str:
    """SimpleState의 skill_ref에 따른 작업 지시 문구."""
    ref = state.skill_ref
    if ref is None:
        return ""
    if isinstance(ref, DelegationDef):
        return _describe_delegation_inline(ref)
    if isinstance(ref, AgentDefinition):
        return f"에이전트 '{ref.name}'에 위임한다"
    # 스킬 참조
    name = getattr(ref, "name", "")
    return f"skill '{name}'을(를) 사용한다"


def _describe_delegation_inline(ref: DelegationDef) -> str:
    """절차 흐름 안에서 위임 노드를 한 줄로 요약(상세 단락은 별도)."""
    if isinstance(ref, TeamSpawnDef):
        return f"위임: 팀 '{ref.name}' 구성·spawn (아래 위임 지침 참조)"
    if isinstance(ref, DynamicWorkflowDef):
        return f"위임: 동적 워크플로 '{ref.name}' 실행 (아래 위임 지침 참조)"
    if isinstance(ref, AgoraDispatchDef):
        return f"위임: Agora 송신 '{ref.name}' (아래 위임 지침 참조)"
    return f"위임: '{ref.name}'"


def _ordered_states(sm: StateMachine) -> list[State]:
    """initial_state부터 전이를 따라 BFS 순서로 상태를 정렬(결정적).

    도달 불가 상태는 states 선언 순서로 뒤에 덧붙인다.
    """
    order: list[State] = []
    seen: set[int] = set()

    def visit(s: State) -> None:
        if id(s) in seen:
            return
        seen.add(id(s))
        order.append(s)
        # 이 상태에서 나가는 전이를 선언 순서로
        for t in sm.transitions:
            if t.source is s and id(t.target) not in seen:
                visit(t.target)

    if sm.initial_state is not None:
        visit(sm.initial_state)
    for s in sm.states:
        if id(s) not in seen:
            visit(s)
    return order


def _describe_fsm(sm: StateMachine, skill: ProceduralSkill) -> list[str]:
    """ProceduralSkill FSM을 사람이 읽는 절차 단락 블록 목록으로 변환.

    형식: 번호 매긴 상태 진행 목록 + 각 상태의 작업·출구 전이 조건.
    결정적: _ordered_states로 고정된 순서.

    방어 가드: states 비어 있음 / initial_state=None인 불완전 FSM은 절차 단락을
    생략하고 출력 이벤트만 서술한다 (compile_project 경유 시 게이트가 먼저
    거부하지만, compile_skill 직접 호출 경로를 보호).
    """
    blocks: list[str] = []
    if sm.states and sm.initial_state is not None:
        blocks.append("## 워크플로 절차")
        blocks.extend(_fsm_procedure_blocks(sm))

    # transfer_on 출구 이벤트 의미
    if skill.transfer_on:
        ev_lines = ["## 출력 이벤트", "이 스킬은 다음 결과 이벤트로 종료한다:"]
        for ev in skill.transfer_on:
            desc = f" — {ev.description}" if ev.description else ""
            ev_lines.append(f"- `{ev.name}`{desc}")
        blocks.append("\n".join(ev_lines))

    return blocks


def _fsm_procedure_blocks(sm: StateMachine) -> list[str]:
    """유효한 FSM의 절차 단락 본체 (intro + 번호 목록)."""
    blocks: list[str] = []
    states = _ordered_states(sm)
    initial = sm.initial_state
    final_ids = {id(s) for s in sm.final_states}

    intro = (
        f"이 스킬은 '{sm.initial_state.name}' 상태에서 시작하는 상태 기계로 동작한다. "
        "각 단계를 순서대로 수행하라."
    )
    blocks.append(intro)

    lines: list[str] = []
    for idx, state in enumerate(states, start=1):
        marks: list[str] = []
        if state is initial:
            marks.append("시작")
        if id(state) in final_ids:
            marks.append("종료")
        mark_str = f" ({', '.join(marks)})" if marks else ""

        head = f"{idx}. **{_state_label(state)}**{mark_str}"
        if isinstance(state, SimpleState):
            action = _describe_node_action(state)
            if action:
                head += f": {action}."
            else:
                head += "."
        elif isinstance(state, CompositeState):
            head += f": 에이전트 '{state.name}'에 위임한다 (별도 컨텍스트 상태 기계)."
        elif isinstance(state, ParallelState):
            regs = ", ".join(r.name for r in state.regions)
            join_note = _describe_join(state)
            head += f": 병렬 실행 — 리전 {regs}을(를) 동시에 진행한다 ({join_note})."
        elif isinstance(state, ChoiceState):
            head += ": 즉시 조건을 평가해 분기한다 (머무르지 않음)."
        elif isinstance(state, TerminateState):
            head += ": 상태 기계를 강제 종료한다."
        elif isinstance(state, (EntryPoint, ExitPoint)):
            head += f" — 의사 상태({state.kind})."
        else:
            head += "."
        lines.append(head)

        # 나가는 전이 — 출구 조건
        outgoing = [t for t in sm.transitions if t.source is state]
        is_choice = isinstance(state, ChoiceState)
        for t in outgoing:
            cond = _transition_condition(t)
            # ChoiceState 무가드 전이 = else 분기 (관례)
            if is_choice and t.guard is None:
                cond_str = " [else]" if not cond else f" [else, {cond}]"
            else:
                cond_str = f" [{cond}]" if cond else ""
            xfer = ""
            if t.skill_ref is not None:
                xfer = f" (전이 시 skill '{t.skill_ref.name}' 실행)"
            lines.append(
                f"    - → **{t.target.name}**{cond_str}{xfer}"
            )

    blocks.append("\n".join(lines))
    return blocks


def _describe_join(state: ParallelState) -> str:
    """ParallelState.join 전략을 사람이 읽는 문구로."""
    from daedalus.model.fsm.join import JoinStrategy
    if state.join is JoinStrategy.ANY:
        return "리전 중 하나라도 완료하면 다음으로 진행"
    if state.join is JoinStrategy.N_OF:
        n = state.join_count if state.join_count is not None else "?"
        return f"리전 {n}개가 완료하면 다음으로 진행"
    return "모든 리전 완료 후 종합"


# ─────────────────────────── 위임 단락 ───────────────────────────

_WAIT_NOTE = {
    WaitMode.WAIT: "전원/전체 완료를 기다려 결과를 종합한 뒤 다음 단계로 진행하라.",
    WaitMode.FIRE_AND_FORGET: "백그라운드에 두고 결과를 기다리지 말고 즉시 다음 단계로 진행하라.",
}


def _delegation_section(ref: DelegationDef) -> list[str]:
    """단일 위임 노드를 본문 지침 단락 블록으로 컴파일 (스펙 4절 + 1-b절)."""
    is_guided = ref.composition is CompositionMode.GUIDED
    blocks: list[str] = [f"### 위임: {ref.name}"]
    if ref.description:
        blocks.append(ref.description.strip())

    if isinstance(ref, TeamSpawnDef):
        blocks.append(_team_spawn_body(ref, is_guided))
    elif isinstance(ref, DynamicWorkflowDef):
        blocks.append(_dynamic_workflow_body(ref, is_guided))
    elif isinstance(ref, AgoraDispatchDef):
        blocks.append(_agora_dispatch_body(ref, is_guided))

    blocks.append(_WAIT_NOTE[ref.wait_mode])
    if is_guided and ref.guidance.strip():
        blocks.append(f"보충 지침: {ref.guidance.strip()}")
    return blocks


def _team_spawn_body(ref: TeamSpawnDef, is_guided: bool) -> str:
    if is_guided:
        lines = [
            "이 노드가 속한 문서 본문(위 섹션 계층)을 근거로 필요한 역할과 인원을 "
            "스스로 판단해 팀을 구성하고, TeamCreate로 팀을 만든 뒤 팀원을 spawn하라."
        ]
        if ref.teammates:
            lines.append("다음 구성을 출발점(힌트)으로 삼되, 본문이 요구하면 조정하라:")
            lines.extend(_teammate_hint_lines(ref))
        return "\n".join(lines)
    # EXPLICIT
    lines = ["TeamCreate로 팀을 만들고 다음 팀원을 spawn하라:"]
    lines.extend(_teammate_hint_lines(ref))
    return "\n".join(lines)


def _teammate_hint_lines(ref: TeamSpawnDef) -> list[str]:
    out: list[str] = []
    for tm in ref.teammates:
        note = f" — {tm.role_note}" if tm.role_note else ""
        out.append(f"- 에이전트 '{tm.agent_ref.name}' × {tm.count}{note}")
    return out


def _dynamic_workflow_body(ref: DynamicWorkflowDef, is_guided: bool) -> str:
    if is_guided:
        lines = [
            "본문이 기술하는 작업을 달성하는 워크플로우를 스스로 설계해 Workflow "
            "도구로 작성·실행하라."
        ]
        if ref.objective:
            lines.append(f"목표 힌트: {ref.objective}")
        if ref.phases:
            lines.append("다음 단계를 힌트로 삼되 본문에 맞춰 조정하라:")
            lines.extend(_phase_hint_lines(ref))
        return "\n".join(lines)
    # EXPLICIT
    lines = [
        "Workflow 도구로 다음 구성의 워크플로우를 작성·실행하라:",
        f"- 목표: {ref.objective}" if ref.objective else "- 목표: (미지정)",
    ]
    if ref.phases:
        lines.append("- 단계:")
        lines.extend(f"  {ln}" for ln in _phase_hint_lines(ref))
    lines.append(
        "단계에 에이전트가 지정되어 있으면 해당 에이전트 타입으로 agentType을 지정하라."
    )
    return "\n".join(lines)


def _phase_hint_lines(ref: DynamicWorkflowDef) -> list[str]:
    out: list[str] = []
    for ph in ref.phases:
        agent = f" [에이전트 '{ph.agent_ref.name}']" if ph.agent_ref is not None else ""
        detail = f" — {ph.detail}" if ph.detail else ""
        out.append(f"- {ph.title}{agent}{detail}")
    return out


def _agora_dispatch_body(ref: AgoraDispatchDef, is_guided: bool) -> str:
    verb = "agora.broadcast" if ref.mode is DispatchMode.BROADCAST else "agora.dispatch"
    if ref.mode is DispatchMode.BROADCAST:
        target_clause = "자신을 제외한 전원에게"
    else:
        target_clause = f"target '{ref.target}'에게" if ref.target else "스키마 라우팅 대상에게"
    lines = [
        f"`{verb}`를 호출해 {target_clause} payload를 msgtype '{ref.msgtype}'로 보내라."
    ]
    if is_guided:
        lines.append("payload 내용은 본문 맥락에서 구성하라 (msgtype/target은 위 명시 값 고정).")
    elif ref.payload_note:
        lines.append(f"payload 구성: {ref.payload_note}")
    if ref.wait_mode is WaitMode.WAIT:
        lines.append("agora.flush로 답신을 대기한 뒤 전이하라.")
    return "\n".join(lines)


def _collect_delegations(sm: StateMachine) -> list[DelegationDef]:
    """머신(재귀)에서 배치된 DelegationDef를 선언 순서·중복 제거로 수집."""
    found: list[DelegationDef] = []
    seen: set[int] = set()

    def scan(machine: StateMachine) -> None:
        for state in machine.states:
            if isinstance(state, SimpleState):
                ref = state.skill_ref
                if isinstance(ref, DelegationDef) and id(ref) not in seen:
                    seen.add(id(ref))
                    found.append(ref)
            elif isinstance(state, CompositeState):
                scan(state.sub_machine)
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    scan(region.sub_machine)

    scan(sm)
    return found


_DELEGATION_PREAMBLE = (
    "이 절차는 CC 실행 단위에 일을 위임하는 노드를 포함한다. 다음 환경을 전제한다: "
    "팀(TeamCreate)/워크플로(Workflow) 도구 가용성, AgoraDispatch 사용 시 "
    "`.mcp.json`의 agora 연결(`X-Agora-Instance-Id` 헤더)."
)


# ─────────────────────────── tool_shelf 참조 단락 ───────────────────────────


def _tool_shelf_section(project) -> list[str]:
    """tool_shelf를 참조 문서 단락으로 (Tier 2 실행 코드 생성 아님)."""
    shelf = getattr(project, "tool_shelf", None) or []
    if not shelf:
        return []
    blocks = ["## 참조: 도구 선반"]
    intro = "이 플러그인이 참조하는 도구 정의 (실행 래퍼는 별도):"
    blocks.append(intro)
    lines: list[str] = []
    for tool in shelf:
        desc = f" — {tool.description}" if getattr(tool, "description", "") else ""
        lines.append(f"- **{tool.name}** ({tool.kind}){desc}")
        body = getattr(tool, "body", "")
        note = getattr(tool, "allowed_arguments_note", "")
        server = getattr(tool, "server", "")
        tool_name = getattr(tool, "tool_name", "")
        if server or tool_name:
            lines.append(f"  - MCP: 서버 '{server}', 도구 '{tool_name}'")
        if note:
            lines.append(f"  - 인자 메모: {note}")
        if body.strip():
            lines.append(f"  - 본문:\n\n```\n{body.strip()}\n```")
    blocks.append("\n".join(lines))
    return blocks


# ─────────────────────────── 공개: compile_skill ───────────────────────────


def _skill_kind_key(skill: Skill, *, local: bool = False) -> str:
    """Skill 인스턴스 → SKILL_FIELD_MATRIX 키.

    local=True(에이전트 소유)이면 local_procedural / local_transfer.
    """
    if isinstance(skill, ProceduralSkill):
        return "local_procedural" if local else "procedural"
    if isinstance(skill, TransferSkill):
        return "local_transfer" if local else "transfer"
    if isinstance(skill, DeclarativeSkill):
        return "declarative"
    if isinstance(skill, ReferenceSkill):
        return "reference"
    raise TypeError(f"알 수 없는 스킬 타입: {type(skill).__name__}")


def compile_skill(
    skill: Skill,
    *,
    local: bool = False,
    project=None,
) -> str:
    """단일 스킬 → SKILL.md 텍스트 (LF, BOM 없음, 결정적).

    local=True이면 에이전트 로컬 스킬 매트릭스를 쓴다(local_procedural/local_transfer).
    project가 주어지면 tool_shelf 참조 단락을 덧붙인다(ProceduralSkill에 한함).
    """
    kind_key = _skill_kind_key(skill, local=local)
    fm_lines = _frontmatter_lines_skill(skill, kind_key)

    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 본문(sections)
    sections = getattr(skill, "sections", [])
    blocks.extend(_render_sections(sections, depth=1))

    # ProceduralSkill — FSM 절차 + 위임 + tool_shelf
    if isinstance(skill, ProceduralSkill):
        delegations = _collect_delegations(skill.fsm)
        if delegations:
            blocks.append("## 위임 전제 조건")
            blocks.append(_DELEGATION_PREAMBLE)
        blocks.extend(_describe_fsm(skill.fsm, skill))
        if delegations:
            blocks.append("## 위임 지침")
            for ref in delegations:
                blocks.extend(_delegation_section(ref))
        if project is not None:
            blocks.extend(_tool_shelf_section(project))

    return _join_blocks(blocks)


# ─────────────────────────── 공개: compile_agent ───────────────────────────


def _frontmatter_lines_agent(agent: AgentDefinition) -> list[str]:
    """에이전트 프론트매터 줄 목록 (emit==FRONTMATTER 만)."""
    config = agent.config
    lines: list[str] = []
    for afield in AgentField:
        rule = AGENT_FIELD_MATRIX[afield]
        if rule.emit is not FieldEmit.FRONTMATTER:
            continue
        key = afield.frontmatter_key

        if afield is AgentField.NAME:
            lines.append(f"{key}: {_yaml_scalar(agent.name)}")
            continue
        if afield is AgentField.DESCRIPTION:
            lines.append(f"{key}: {_yaml_scalar(_compose_description(agent))}")
            continue

        emitted = _emit_agent_field(afield, rule, config, key)
        if emitted is not None:
            lines.append(emitted)
    return lines


def _emit_agent_field(
    afield: AgentField,
    rule: FieldRule,
    config,
    key: str,
) -> str | None:
    """단일 에이전트 프론트매터 필드 → YAML 줄. 생략 시 None."""
    attr = afield.value
    if rule.visibility is FieldVisibility.FIXED:
        return _format_kv(key, rule.fixed_value)

    value = getattr(config, attr, _MISSING)
    if value is _MISSING or value is None:
        return None
    if afield is AgentField.MODEL and value is ModelType.INHERIT:
        return None
    if isinstance(value, (list, dict)) and not value:
        return None
    if rule.visibility is not FieldVisibility.REQUIRED:
        default = _config_default(config, attr)
        if default is not _MISSING and value == default:
            return None
    return _format_kv(key, value)


def _invocation_section_agent(agent: AgentDefinition) -> list[str]:
    """INVOCATION emit 필드(max_turns/background/isolation)를 호출 파라미터 안내 단락으로."""
    config = agent.config
    rows: list[str] = []
    for afield in AgentField:
        rule = AGENT_FIELD_MATRIX[afield]
        if rule.emit is not FieldEmit.INVOCATION:
            continue
        attr = afield.value
        value = getattr(config, attr, _MISSING)
        if value is _MISSING or value is None:
            continue
        # 기본값과 같으면 생략
        default = _config_default(config, attr)
        if default is not _MISSING and value == default:
            continue
        rows.append(f"- `{afield.frontmatter_key}`: {_enum_value(value)}")
    if not rows:
        return []
    blocks = [
        "## 호출 파라미터",
        "이 에이전트는 Agent/Task 도구로 호출될 때 다음 파라미터를 권장한다:",
        "\n".join(rows),
    ]
    return blocks


def _settings_note_agent(agent: AgentDefinition) -> list[str]:
    """SETTINGS emit 필드(hooks/mcp_servers)를 요구 환경 언급 단락으로 (v0 산출 제외)."""
    config = agent.config
    needs: list[str] = []
    hooks = getattr(config, "hooks", None)
    if hooks:
        names = ", ".join(str(n) for n in hooks)
        needs.append(f"lifecycle hooks: {names} (hooks/hooks.json 생성됨)")
    mcp = getattr(config, "mcp_servers", None)
    if mcp:
        names = ", ".join(str(n) for n in mcp)
        needs.append(f"MCP 서버 연결: {names} (`.mcp.json`)")
    if not needs:
        return []
    blocks = [
        "## 요구 환경",
        "이 에이전트는 다음 외부 설정을 전제한다 (v0 컴파일러는 설정 파일을 생성하지 않음):",
        "\n".join(f"- {n}" for n in needs),
    ]
    return blocks


def compile_agent(agent: AgentDefinition, project=None) -> str:
    """에이전트 → agent .md 텍스트 (LF, BOM 없음, 결정적)."""
    fm_lines = _frontmatter_lines_agent(agent)
    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 본문(sections)
    blocks.extend(_render_sections(agent.sections, depth=1))

    # 호출 파라미터(INVOCATION)
    blocks.extend(_invocation_section_agent(agent))
    # 요구 환경(SETTINGS 언급)
    blocks.extend(_settings_note_agent(agent))

    # 에이전트 FSM 절차 (ExitPoint 출구 의미 포함)
    blocks.extend(_describe_agent_fsm(agent))

    # 위임 지침 (에이전트 그래프 내부)
    delegations = _collect_delegations(agent.fsm)
    if delegations:
        blocks.append("## 위임 전제 조건")
        blocks.append(_DELEGATION_PREAMBLE)
        blocks.append("## 위임 지침")
        for ref in delegations:
            blocks.extend(_delegation_section(ref))

    if project is not None:
        blocks.extend(_tool_shelf_section(project))

    return _join_blocks(blocks)


def _describe_agent_fsm(agent: AgentDefinition) -> list[str]:
    """에이전트 FSM을 절차 단락으로 — 상태 진행 + ExitPoint 출구 의미.

    방어 가드: states 비어 있음 / initial_state=None인 불완전 FSM은 생략
    (게이트가 먼저 거부하지만 compile_agent 직접 호출 경로 보호).
    """
    sm = agent.fsm
    if not sm.states or sm.initial_state is None:
        return []
    blocks: list[str] = ["## 내부 워크플로"]
    blocks.append(
        f"이 에이전트는 '{sm.initial_state.name}'에서 시작하는 상태 기계로 동작한다."
    )
    states = _ordered_states(sm)
    final_ids = {id(s) for s in sm.final_states}
    lines: list[str] = []
    for idx, state in enumerate(states, start=1):
        marks: list[str] = []
        if state is sm.initial_state:
            marks.append("시작")
        if id(state) in final_ids:
            marks.append("종료")
        if isinstance(state, ExitPoint):
            marks.append("출구")
        mark_str = f" ({', '.join(marks)})" if marks else ""
        head = f"{idx}. **{state.name}**{mark_str}"
        if isinstance(state, SimpleState):
            action = _describe_node_action(state)
            head += f": {action}." if action else "."
        elif isinstance(state, CompositeState):
            head += f": 에이전트 '{state.name}'에 위임한다."
        else:
            head += "."
        lines.append(head)
        is_choice = isinstance(state, ChoiceState)
        for t in sm.transitions:
            if t.source is state:
                cond = _transition_condition(t)
                if is_choice and t.guard is None:
                    cond_str = " [else]" if not cond else f" [else, {cond}]"
                else:
                    cond_str = f" [{cond}]" if cond else ""
                lines.append(f"    - → **{t.target.name}**{cond_str}")
    blocks.append("\n".join(lines))

    # ExitPoint 출구 의미
    exits = [s for s in sm.states if isinstance(s, ExitPoint)]
    if exits:
        ex_lines = ["## 출구", "이 에이전트는 다음 출구로 종료할 수 있다:"]
        for ep in exits:
            ex_lines.append(f"- `{ep.name}`")
        blocks.append("\n".join(ex_lines))
    return blocks


# ─────────────────────────── hooks.json (SETTINGS) ───────────────────────────


def _collect_referenced_hook_names(project) -> list[str]:
    """프로젝트 전체 config.hooks 키(훅 이름 참조)를 첫 등장 순서·중복 제거로 수집.

    스킬·에이전트·에이전트 로컬 스킬의 config.hooks를 모두 훑는다. 출력은
    결정적(선언 순회 순서)이며, hook_library에 없는 이름은 여기서 거르지 않는다
    (dangling은 검증/게이트 경고로 별도 처리 — emit은 라이브러리 교집합만 출력).
    """
    names: list[str] = []
    seen: set[str] = set()

    def _add_from(cfg) -> None:
        hooks = getattr(cfg, "hooks", None)
        if isinstance(hooks, dict):
            for name in hooks:
                if name not in seen:
                    seen.add(name)
                    names.append(name)

    for skill in getattr(project, "skills", []):
        _add_from(getattr(skill, "config", None))
    for agent in getattr(project, "agents", []):
        _add_from(getattr(agent, "config", None))
        for local in getattr(agent, "skills", []):
            _add_from(getattr(local, "config", None))
    return names


def _hook_command_entry(hook: HookDef) -> dict[str, Any]:
    """단일 훅 → CC hooks.json의 command 엔트리. timeout은 있을 때만 출력."""
    entry: dict[str, Any] = {"type": "command", "command": hook.command}
    if hook.timeout is not None:
        entry["timeout"] = hook.timeout
    return entry


def compile_hooks_json(project) -> str | None:
    """프로젝트가 참조하는 HookDef를 모아 CC settings hooks.json 텍스트로.

    스키마:
        {"hooks": {"<EventName>": [{"matcher": "...", "hooks": [{"type": "command",
          "command": "...", "timeout": ...}]}]}}
    - matcher는 도구 이벤트(Pre/PostToolUse)에서만 출력. 그 외 이벤트는 matcher 생략.
    - 같은 이벤트의 복수 훅은 hook_library 선언 순서로 정렬(결정적).
    - 이벤트 키 순서는 HookEvent 선언 순서(결정적).
    참조가 없거나 라이브러리에 매칭되는 훅이 없으면 None(파일 생성 안 함).

    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    library = getattr(project, "hook_library", None) or []
    by_name = {h.name: h for h in library}
    referenced = _collect_referenced_hook_names(project)
    resolved = [by_name[n] for n in referenced if n in by_name]
    if not resolved:
        return None

    # 이벤트 → HookDef 목록 (라이브러리 선언 순서 유지, 결정적).
    resolved_names = {h.name for h in resolved}
    event_buckets: dict[HookEvent, list[HookDef]] = {}
    for hook in library:
        if hook.name in resolved_names:
            event_buckets.setdefault(hook.event, []).append(hook)

    hooks_obj: dict[str, Any] = {}
    for event in HookEvent:  # 선언 순서 = 결정적 이벤트 키 순서
        bucket = event_buckets.get(event)
        if not bucket:
            continue
        groups: list[dict[str, Any]] = []
        for hook in bucket:
            group: dict[str, Any] = {}
            if event in TOOL_MATCH_EVENTS and hook.matcher:
                group["matcher"] = hook.matcher
            group["hooks"] = [_hook_command_entry(hook)]
            groups.append(group)
        hooks_obj[event.value] = groups

    text = json.dumps({"hooks": hooks_obj}, ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


# ─────────────────────────── schemas.json (블랙보드) ───────────────────────────


def _field_to_json_schema(fld) -> dict[str, Any]:
    """DynamicField → JSON Schema 속성. CollectionType으로 array 래핑."""
    from daedalus.model.fsm.blackboard import (
        CollectionType,
        FIELD_TYPE_TO_JSON_SCHEMA,
    )
    scalar = dict(FIELD_TYPE_TO_JSON_SCHEMA.get(fld.field_type, {}))
    if fld.collection is CollectionType.LIST:
        return {"type": "array", "items": scalar}
    if fld.collection is CollectionType.SET:
        return {"type": "array", "items": scalar, "uniqueItems": True}
    return scalar


def _class_to_json_schema(cls) -> dict[str, Any]:
    """DynamicClass → JSON Schema object. required는 필드 required 플래그 기준."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for fld in cls.fields:
        prop = _field_to_json_schema(fld)
        if fld.default is not None:
            prop = {**prop, "default": fld.default}
        properties[fld.name] = prop
        if fld.required:
            required.append(fld.name)
    schema: dict[str, Any] = {"type": "object"}
    if cls.description:
        schema["description"] = cls.description
    schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


def compile_schemas_json(project) -> str | None:
    """프로젝트 최상위 블랙보드의 class_definitions → schemas.json 텍스트.

    각 DynamicClass를 JSON Schema object로 변환해
    ``{"<클래스명>": <schema>}`` 형태로 묶는다 (선언 순서 = 결정적 키 순서).
    class_definitions가 비어 있으면 None (파일 생성 안 함).

    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    bb = getattr(project, "blackboard", None)
    classes = getattr(bb, "class_definitions", None) or []
    if not classes:
        return None
    schemas_obj: dict[str, Any] = {}
    for cls in classes:
        schemas_obj[cls.name] = _class_to_json_schema(cls)
    text = json.dumps(schemas_obj, ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


# ─────────────────────────── 블록 결합 ───────────────────────────


def _join_blocks(blocks: list[str]) -> str:
    """블록 목록을 빈 줄 하나로 구분해 결합하고 끝에 개행 1개. LF 고정."""
    text = "\n\n".join(b for b in blocks if b is not None and b != "")
    # CRLF 잔존 방지
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text
