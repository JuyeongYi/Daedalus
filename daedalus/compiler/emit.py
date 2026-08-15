# daedalus/compiler/emit.py
"""model → 마크다운 텍스트 생성 (순수 — 파일시스템·Qt 무관).

여기서는 문자열만 만든다. 파일 쓰기·게이트는 project_compiler.py가 담당한다.
출력은 결정적이다 (같은 모델 → 같은 문자열, LF 줄바꿈).

확정 정책 (WP-compiler-v0):
  1. 프론트매터: 해당 kind 매트릭스에서 emit==FRONTMATTER인 필드만. 키는
     frontmatter_key. FIXED는 fixed_value 강제. model==INHERIT는 키 생략.
     OPTIONAL 필드 값이 선언 기본값과 같으면 생략. enum은 .value.
  2. when_to_use: description과 합류 — "<description> Use when <when_to_use>".
  3. 본문: body(단일 마크다운 문자열)을 그대로 배출(공백뿐이면 블록 생략, WP-SB).
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
from daedalus.model.plugin.hook import (
    HOOK_SCRIPT_DIR,
    HOOK_SCRIPT_REF_PREFIX,
    HookDef,
    HookEvent,
)
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


def _yaml_block_lines(value: Any, indent: int = 0) -> list[str]:
    """중첩 dict/list를 블록 스타일 YAML 줄 목록으로 (WP-LA).

    flow-style(`_yaml_list`)로는 표현할 수 없는 프론트매터 값 — 에이전트의
    ``hooks``(이벤트 → 그룹 → 훅 3단 중첩) 전용이다. 다루는 값은 dict/list/
    스칼라뿐이고, 스칼라 표기는 `_yaml_scalar`를 그대로 쓴다(단일 진실).
    """
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, val in value.items():
            if isinstance(val, (dict, list)) and val:
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_block_lines(val, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(_enum_value(val))}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                sub = _yaml_block_lines(item, indent + 2)
                # 첫 줄만 "- "로 끌어올리고 나머지는 그 들여쓰기를 유지한다
                lines.append(f"{pad}- {sub[0].lstrip()}")
                lines.extend(sub[1:])
            else:
                lines.append(f"{pad}- {_yaml_scalar(_enum_value(item))}")
    else:
        lines.append(f"{pad}{_yaml_scalar(_enum_value(value))}")
    return lines


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


# ─────────────────────────── 본문(body) ───────────────────────────


def _body_block(body: str) -> str | None:
    """component.body를 본문 블록 하나로. 공백뿐이면 None(블록 생략).

    앞뒤 개행만 정리한다(내부 서식은 사용자 마크다운 그대로 보존).
    """
    stripped = (body or "").strip("\n")
    if not stripped.strip():
        return None
    return stripped


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


def _describe_access(state: State) -> str:
    """WP-BB Part D-1: 상태의 reads/writes 접근 선언을 절차 서술 접미사로.

    형식: " (읽기: `A.x`, `B` / 쓰기: `A.y`)". 각각 이름순 정렬(결정적).
    선언이 없으면 빈 문자열(문구 생략 — 하위 호환 불변).
    """
    reads = sorted(getattr(state, "reads", None) or [])
    writes = sorted(getattr(state, "writes", None) or [])
    if not reads and not writes:
        return ""
    parts: list[str] = []
    if reads:
        parts.append("읽기: " + ", ".join(f"`{r}`" for r in reads))
    if writes:
        parts.append("쓰기: " + ", ".join(f"`{w}`" for w in writes))
    return " (" + " / ".join(parts) + ")"


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
        head += _describe_access(state)
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


# ─────────────────────────── 프로젝트 그래프: 다음 단계 ───────────────────────────


def _next_step_condition(t) -> str:
    """프로젝트 그래프 전이의 조건 문구. 무가드 전이는 '무조건'."""
    cond = _transition_condition(t)
    return cond if cond else "무조건"


def _next_step_invoke_line(target_state, sm: StateMachine) -> str | None:
    """전이 타깃 placement에 대한 한 줄 지시문.

    - 스킬 placement: "[조건] → `<skill>` 스킬을 인보크하라"
    - 에이전트 placement: "[조건] → 에이전트 `X`에게 위임하라" + 그 에이전트
      placement의 outgoing을 한 단계 인라인("위임 완료 후: …")
    EntryPoint 등 skill_ref 없는 타깃은 None(스킵).
    """
    ref = getattr(target_state, "skill_ref", None)
    if ref is None:
        return None
    name = getattr(ref, "name", "")
    if isinstance(ref, AgentDefinition):
        line = f"에이전트 `{name}`에게 위임하라"
        # 에이전트 placement의 outgoing을 한 단계 인라인 (별도 컨텍스트라 호출자
        # 쪽에 후속 지시를 둔다 — 에이전트 .md는 호출자 지침을 담을 수 없음).
        inline_parts: list[str] = []
        for t in sm.transitions:
            if t.source is target_state:
                tgt_ref = getattr(t.target, "skill_ref", None)
                if tgt_ref is None or isinstance(tgt_ref, AgentDefinition):
                    continue
                tgt_name = getattr(tgt_ref, "name", "")
                cond = _next_step_condition(t)
                inline_parts.append(
                    f"위임 완료 후: [{cond}] → {_invoke_phrase(tgt_ref, tgt_name)}"
                )
        if inline_parts:
            line += " (" + "; ".join(inline_parts) + ")"
        return line
    return _invoke_phrase(ref, name)


def _invoke_phrase(ref, name: str) -> str:
    """skill_ref 종류별 인보크 지시 문구 — 위임 노드를 '스킬'로 오라벨하지 않는다."""
    if isinstance(ref, DelegationDef):
        return f"`{name}` 위임 노드를 수행하라"
    return f"`{name}` 스킬을 인보크하라"


def _graph_placements(component, project) -> list:
    """component가 project.graph에 SimpleState로 배치된 노드 목록(identity 비교).

    "다음 단계" 단락(버그 2)과 WP-RS 작업 재개 단락이 공유하는 placement 판정
    로직의 단일 진실.
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    return [
        s for s in graph.states
        if getattr(s, "skill_ref", None) is component
    ]


def _next_steps_section(component, project) -> list[str]:
    """project.graph에서 component placement의 outgoing 전이를 모아 "## 다음 단계"
    단락 블록을 생성한다 (버그 2). outgoing이 없으면 빈 목록(단락 생략).

    component는 전역 스킬 객체. 그래프에서 skill_ref가 identity로 일치하는
    SimpleState placement를 찾고, 그 placement에서 나가는 전이를 서술한다.
    """
    placements = _graph_placements(component, project)
    if not placements:
        return []
    graph = project.graph
    lines: list[str] = []
    for placement in placements:
        for t in graph.transitions:
            if t.source is not placement:
                continue
            invoke = _next_step_invoke_line(t.target, graph)
            if invoke is None:
                continue
            cond = _next_step_condition(t)
            lines.append(f"- [{cond}] → {invoke}")
    if not lines:
        return []
    return [
        "## 다음 단계",
        "이 스킬 완료 후 다음 조건에 따라 워크플로를 이어가라:",
        "\n".join(lines),
    ]


# ─────────────────────────── 작업 재개 (WP-RS) ───────────────────────────

# state/__progress__.json 규약 — 플러그인 FSM(프로젝트 그래프)의 진행 위치를 담는
# 단일 파일. 스킬 내부 FSM 상태는 기록하지 않는다(사용자 확정 설계).

_PROGRESS_UPDATE_NOTE = (
    "전이 시 `state/__progress__.json`을 갱신하라 — 이 스킬을 `completed`에 추가하고 "
    "`current`를 다음 대상으로, `prev`에 자신(이 스킬 이름)을, `note`에 인계 한 줄을, "
    "`updated`에 현재 시각(ISO8601)을 남겨라. 에이전트에게 위임하는 전이는 두 번 갱신한다: "
    "위임 직전 `current`를 에이전트 이름으로, 위임 완료 후 후속 스킬 이름으로(이때도 `prev`는 "
    "위임한 스킬 이름으로 남긴다)."
)

_TRANSFER_PROGRESS_NOTE = (
    "이 전이 스킬 실행 중에는 `state/__progress__.json`의 `note`에 전이 맥락을 기록하라."
)


def _resume_preamble_section(project, skill_name: str) -> list[str]:
    """WP-RS Part A-1: 재개 프리앰블 — 프론트매터 직후, 본문 앞에 배출된다.

    프로젝트 그래프에 배치된 전역 ProceduralSkill에만 배출된다(게이트는 호출부).
    WP-IC: JSON 예시에 `prev`(직전 출처 스킬 이름) 필드를 포함한다.
    """
    plugin_name = getattr(project, "name", "")
    body = "\n".join([
        "시작 전에 `state/__progress__.json`을 확인하라.",
        (
            f"- `current`가 이 스킬(`{skill_name}`)이면: `note`를 참고해 중단 지점부터 "
            "이어서 진행하라."
        ),
        "- `current`가 다른 스킬이면: 워크플로 위치가 그쪽이다 — 진행을 멈추고 사용자에게 확인하라.",
        (
            "- 파일이 없으면: "
            f'`{{"plugin": "{plugin_name}", "current": "{skill_name}", "completed": [], '
            '"note": "", "prev": "", "updated": "<현재 시각 ISO8601>"}`'
            "로 생성하고 진행하라."
        ),
    ])
    return ["## 작업 재개", body]


# ─────────────────────────── 진입 맥락 (WP-IC) ───────────────────────────


def _entry_incoming_transitions(component, project) -> list:
    """component의 project.graph placement로 들어오는 전이 목록.

    출처(source)의 skill_ref가 없는 상태(EntryPoint 등 의사 상태·빈 상태)에서
    오는 전이는 "출처"로 서술할 대상이 없으므로 제외한다.
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    placements = _graph_placements(component, project)
    if not placements:
        return []
    placement_ids = {id(p) for p in placements}
    return [
        t for t in graph.transitions
        if id(t.target) in placement_ids
        and getattr(t.source, "skill_ref", None) is not None
    ]


def _entry_context_groups(component, project) -> list[tuple[str | None, str, list]]:
    """(포트 이름 또는 None(기본 경로), EventDef.description, 전이 목록) 튜플 리스트.

    정렬: 포트는 entry_paths 선언 순서(기본 경로 마지막). 그룹 내 전이는 호출부가
    출처 이름순으로 정렬한다. incoming이 있는 포트만 배출.
    """
    incoming = _entry_incoming_transitions(component, project)
    if not incoming:
        return []
    entry_paths = getattr(component, "entry_paths", None) or []
    name_set = {e.name for e in entry_paths}
    groups: dict[str, list] = {}
    for t in incoming:
        # target_port가 entry_paths에 없는 이름(dangling)이면 기본 경로로 수렴
        # (캔버스 렌더의 "이름 불일치 → 기본 포트" 규칙과 동일한 관용).
        key = t.target_port if t.target_port in name_set else ""
        groups.setdefault(key, []).append(t)

    ordered: list[tuple[str | None, str, list]] = []
    for edef in entry_paths:
        if edef.name in groups:
            ordered.append((edef.name, edef.description, groups[edef.name]))
    if "" in groups:
        ordered.append((None, "", groups[""]))
    return ordered


def _entry_source_ref_name(t) -> str:
    """정렬용 — 전이 출처의 표시 이름(skill_ref.name)."""
    ref = getattr(t.source, "skill_ref", None)
    return getattr(ref, "name", "") or t.source.name


def _entry_item_line(t, project) -> str:
    """진입 맥락 그룹 안 출처별 항목 한 줄.

    "- `<출처>`에서 [<조건>]로 진입" + (TransferSkill이 있으면 지침 수행 문구 합류).
    출처가 에이전트 placement면 "에이전트 `X`의 위임 완료 후" 문구로 대체하고,
    위임을 시작한 스킬 이름을 병기한다 — 규약상 `prev`에는 에이전트가 아니라
    위임 스킬 이름이 남으므로, 병기 없이는 prev로 이 항목을 특정할 수 없다
    (리뷰 지적 f).
    """
    ref = getattr(t.source, "skill_ref", None)
    name = getattr(ref, "name", "") or t.source.name
    cond = _transition_condition(t)
    cond_str = f" [{cond}]" if cond else ""
    if isinstance(ref, AgentDefinition):
        line = f"- 에이전트 `{name}`의 위임 완료 후{cond_str}로 진입"
        delegators = sorted({
            getattr(getattr(tr.source, "skill_ref", None), "name", "")
            for tr in getattr(project.graph, "transitions", [])
            if tr.target is t.source
        } - {""})
        if delegators:
            names = ", ".join(f"`{d}`" for d in delegators)
            line += f" (이때 `prev`는 위임을 시작한 스킬 — {names})"
    else:
        line = f"- `{name}`에서{cond_str}로 진입"
    if t.skill_ref is not None:
        desc = f"(`{t.skill_ref.description}`)" if t.skill_ref.description else ""
        line += f": 전이 스킬 `{t.skill_ref.name}`{desc}의 지침을 수행한 상태다"
    return line


def _entry_context_section(component, project) -> list[str]:
    """WP-IC Part C-1: "## 진입 맥락" 단락 — 작업 재개 프리앰블 뒤·본문 앞.

    배치된 전역 ProceduralSkill/DeclarativeSkill에서 incoming 전이가 1개 이상일
    때만 배출(게이트는 호출부). incoming이 없으면 빈 리스트(단락 생략, 하위 호환).
    """
    groups = _entry_context_groups(component, project)
    if not groups:
        return []
    blocks: list[str] = [
        "## 진입 맥락",
        (
            "`state/__progress__.json`의 `prev`를 확인하고 아래에서 해당 출처 항목을 따르라. "
            "에이전트 위임에서 복귀한 경우 `prev`에는 에이전트가 아니라 위임을 시작한 "
            "스킬 이름이 남아 있다."
        ),
    ]
    for name, desc, transitions in groups:
        heading = f"### 경로: {name}" if name is not None else "### 기본 경로"
        blocks.append(heading)
        if desc:
            blocks.append(desc)
        ordered = sorted(transitions, key=_entry_source_ref_name)
        blocks.append("\n".join(_entry_item_line(t, project) for t in ordered))
    return blocks


def _progress_terminal_section() -> list[str]:
    """WP-RS Part A-3: 터미널 배치(outgoing 0개) — "다음 단계" 대신 배출된다."""
    return [
        "## 작업 완료",
        (
            "이 스킬이 워크플로의 마지막 단계다. 완료 시 `state/__progress__.json`에서 "
            "이 스킬을 `completed`에 추가하고 `current`를 `\"done\"`으로 바꾼 뒤, "
            "`note`에 결과 요약을, `updated`에 현재 시각(ISO8601)을 남겨라."
        ),
    ]


# ─────────────────────────── 요구 환경: MCP 서버 자동 언급 (WP-TM Part C) ───────────────────────────


def _mcp_servers_from_tools(tools) -> list[str]:
    """allowed_tools/tools 문자열 목록에서 ``mcp__<server>__`` 접두의 서버 이름을
    추출한다 (이름순 정렬 — 결정적 출력).
    """
    servers: set[str] = set()
    for tool_str in tools or ():
        if not isinstance(tool_str, str) or not tool_str.startswith("mcp__"):
            continue
        rest = tool_str[len("mcp__"):]
        server = rest.split("__", 1)[0]
        if server:
            servers.add(server)
    return sorted(servers)


def _mcp_requirement_section_skill(skill: Skill) -> list[str]:
    """스킬 config.allowed_tools의 mcp__ 접두에서 서버 이름을 추출해 "## 요구 환경"
    단락을 만든다. 서버가 없으면 빈 목록(단락 생략).
    """
    config = getattr(skill, "config", None)
    servers = _mcp_servers_from_tools(getattr(config, "allowed_tools", None))
    if not servers:
        return []
    names = ", ".join(f"`{s}`" for s in servers)
    return [
        "## 요구 환경",
        f"이 스킬은 다음 MCP 서버가 연결되어 있어야 한다: {names}",
    ]


def referenced_mcp_servers(project) -> list[str]:
    """프로젝트가 참조하는 MCP 서버 이름 합집합 (이름순 정렬 — 결정적).

    에이전트: ``config.mcp_servers`` 선언 ∪ ``config.tools`` 추출.
    스킬(로컬 스킬 포함): ``config.allowed_tools`` 추출.
    "요구 환경" 단락과 같은 합집합 규칙 — 본문·프론트매터·설치 배선이 서로 다른
    목록을 말하지 않는다.
    """
    servers: set[str] = set()
    for skill in getattr(project, "skills", []) or []:
        config = getattr(skill, "config", None)
        servers.update(_mcp_servers_from_tools(getattr(config, "allowed_tools", None)))
    for agent in getattr(project, "agents", []) or []:
        config = getattr(agent, "config", None)
        servers.update(getattr(config, "mcp_servers", None) or [])
        servers.update(_mcp_servers_from_tools(getattr(config, "tools", None)))
        for local in getattr(agent, "skills", []) or []:
            local_cfg = getattr(local, "config", None)
            servers.update(
                _mcp_servers_from_tools(getattr(local_cfg, "allowed_tools", None))
            )
    return sorted(s for s in servers if s)


# ─────────────────────────── 블랙보드 사용 지침 단락 ───────────────────────────


def _collect_state_access(sm: StateMachine) -> tuple[set[str], set[str]]:
    """머신(재귀 — sub_machine/Region 포함)의 모든 상태 reads/writes 합집합."""
    reads: set[str] = set()
    writes: set[str] = set()
    for state in sm.states:
        reads.update(getattr(state, "reads", None) or [])
        writes.update(getattr(state, "writes", None) or [])
        if isinstance(state, CompositeState):
            r, w = _collect_state_access(state.sub_machine)
            reads.update(r)
            writes.update(w)
        elif isinstance(state, ParallelState):
            for region in state.regions:
                r, w = _collect_state_access(region.sub_machine)
                reads.update(r)
                writes.update(w)
    return reads, writes


def _component_access_union(component, project) -> tuple[set[str], set[str]]:
    """component(스킬/에이전트) 자체 FSM(재귀) + 프로젝트 그래프 placement의
    reads/writes 선언 합집합 (WP-BB Part D-2)."""
    reads: set[str] = set()
    writes: set[str] = set()
    fsm = getattr(component, "fsm", None)
    if fsm is not None:
        reads, writes = _collect_state_access(fsm)
    for placement in _graph_placements(component, project):
        reads.update(getattr(placement, "reads", None) or [])
        writes.update(getattr(placement, "writes", None) or [])
    return reads, writes


def _blackboard_section(project, component=None) -> list[str]:
    """프로젝트 최상위 블랙보드 class_definitions → '## 공유 상태 (블랙보드)' 블록.

    정의가 없으면 빈 리스트 (단락 생략).

    component가 주어지고 그 접근 선언(자체 FSM 재귀 + 그래프 placement) 합집합이
    비어 있지 않으면, "이 스킬/에이전트가 읽는 것/쓰는 것"을 명시하고 파일
    목록을 관련 클래스만으로 좁힌다. component가 없거나 합집합이 비면 기존
    동작(전 클래스 일반 안내) 그대로 — 하위 호환, 기존 산출 문자열 불변.
    """
    bb = getattr(project, "blackboard", None)
    classes = getattr(bb, "class_definitions", None) or []
    if not classes:
        return []

    reads: set[str] = set()
    writes: set[str] = set()
    if component is not None:
        reads, writes = _component_access_union(component, project)
    union = reads | writes

    rule_lines = (
        "규칙:\n"
        "- 파일을 수정하기 전에 반드시 현재 내용을 읽어라 (읽기-수정-쓰기).\n"
        "- 파일이 없으면 스키마에 맞는 초기 객체로 생성하라.\n"
        "- 스키마의 required 필드는 항상 채워라."
    )

    if union:
        relevant_names = {ref.split(".", 1)[0] for ref in union}
        relevant_classes = [c for c in classes if c.name in relevant_names]
        lines: list[str] = []
        for cls in relevant_classes:
            desc = f" — {cls.description}" if cls.description else ""
            lines.append(f"- `{cls.name}` → `state/{cls.name}.json`{desc}")

        # 주어+조사 — "스킬이"(받침 있음)/"에이전트가"(받침 없음).
        subject = "에이전트가" if isinstance(component, AgentDefinition) else "스킬이"
        intro_lines: list[str] = []
        if reads:
            intro_lines.append(f"이 {subject} 읽는 것: " + ", ".join(f"`{r}`" for r in sorted(reads)))
        if writes:
            intro_lines.append(f"이 {subject} 쓰는 것: " + ", ".join(f"`{w}`" for w in sorted(writes)))

        # 총론(디렉토리·스키마 설명)은 선언 유무와 무관하게 유지 — 선언은
        # "덧붙이는" 정보이지 총론을 대체하지 않는다 (리뷰 지적 1).
        return [
            "## 공유 상태 (블랙보드)",
            (
                "이 워크플로의 컨텍스트 간 공유 상태는 작업 폴더의 `state/` 디렉토리에 JSON 파일로\n"
                "유지한다. 각 파일의 구조는 플러그인의 `schemas/schemas.json`에 정의된 스키마를 따른다."
            ),
            "\n".join(intro_lines),
            "\n".join(lines),
            rule_lines,
        ]

    lines = []
    for cls in classes:
        desc = f" — {cls.description}" if cls.description else ""
        lines.append(f"- `{cls.name}` → `state/{cls.name}.json`{desc}")

    return [
        "## 공유 상태 (블랙보드)",
        (
            "이 워크플로의 컨텍스트 간 공유 상태는 작업 폴더의 `state/` 디렉토리에 JSON 파일로\n"
            "유지한다. 각 파일의 구조는 플러그인의 `schemas/schemas.json`에 정의된 스키마를 따른다."
        ),
        "\n".join(lines),
        rule_lines,
    ]


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

    # 작업 재개 프리앰블(WP-RS) — 프론트매터 직후, 본문 앞. 프로젝트 그래프에
    # 배치된 전역 Procedural/Declarative 스킬에 배출(미배치·로컬은 없음).
    # Declarative 포함 이유: 배치되면 "다음 단계"를 받는데 갱신 규칙이 빠지면
    # 그 노드에서 진행 사슬이 끊긴다 (리뷰 지적 ①).
    progress_placements: list = []
    if (
        project is not None
        and not local
        and isinstance(skill, (ProceduralSkill, DeclarativeSkill))
    ):
        progress_placements = _graph_placements(skill, project)
    if progress_placements:
        blocks.extend(_resume_preamble_section(project, skill.name))
        # 진입 맥락(WP-IC) — 작업 재개 프리앰블 뒤·본문 앞. incoming 전이가
        # 없으면 _entry_context_section이 빈 리스트를 반환(단락 생략).
        blocks.extend(_entry_context_section(skill, project))

    # 본문(body)
    body_block = _body_block(getattr(skill, "body", ""))
    if body_block is not None:
        blocks.append(body_block)

    # TransferSkill: 전이 도중 중단 대비 note (본문 끝, 로컬 스킬은 제외).
    # 진행 파일을 만드는 배치 스킬이 하나도 없는 프로젝트에서는 고아 지시가
    # 되므로 placement 존재를 게이트로 건다 (리뷰 지적 ②).
    if (
        isinstance(skill, TransferSkill)
        and not local
        and project is not None
        and _graph_placements_any(project)
    ):
        blocks.append("## 진행 기록")
        blocks.append(_TRANSFER_PROGRESS_NOTE)

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
        if project is not None and not local:
            blocks.extend(_blackboard_section(project, skill))

    # 요구 환경(MCP 서버 자동 언급) — allowed_tools의 mcp__ 접두에서 추출.
    # project 유무와 무관(스킬 자체 config만 참조), "다음 단계" 단락 앞.
    blocks.extend(_mcp_requirement_section_skill(skill))

    # 프로젝트 그래프 기반 "다음 단계" (버그 2) — 전역 스킬에 한함.
    # 로컬 스킬(에이전트 소유)은 프로젝트 그래프 placement 대상이 아니다.
    # WP-RS: 배치 스킬이면 다음 단계 단락 끝에 진행 상태 갱신 규칙을 합류시키고,
    # outgoing이 없는 터미널 배치면 "다음 단계" 대신 "작업 완료"를 배출한다.
    # 터미널 판정은 "다음 단계 문구 생성 실패"가 아니라 **placement의 실제
    # outgoing 전이 부재**다 — 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안
    # 나와도 중간 스킬은 터미널이 아니다 (리뷰 차단 지적).
    if project is not None and not local:
        next_blocks = _next_steps_section(skill, project)
        has_outgoing = any(
            t.source is p
            for p in progress_placements
            for t in getattr(project.graph, "transitions", [])
        )
        if next_blocks:
            if progress_placements:
                next_blocks = list(next_blocks)
                next_blocks[-1] = next_blocks[-1] + "\n\n" + _PROGRESS_UPDATE_NOTE
            blocks.extend(next_blocks)
        elif progress_placements and not has_outgoing:
            blocks.extend(_progress_terminal_section())

    return _join_blocks(blocks)


# ─────────────────────────── 공개: compile_agent ───────────────────────────


def _frontmatter_lines_agent(agent: AgentDefinition, project=None) -> list[str]:
    """에이전트 프론트매터 줄 목록 (emit==FRONTMATTER 만).

    마켓플레이스 빌드에서는 CC가 무시하는 필드(`permissionMode` 등)를 아예 내지
    않는다 — 값이 파일에 남아 있으면 걸린 줄 알지만 실제로는 아무 일도 일어나지
    않기 때문이다(WP-EL). 판정의 단일 진실은 `agent_field_supported`.
    """
    from daedalus.model.plugin.field_matrix import agent_field_supported

    build_target = _build_target(project)
    config = agent.config
    lines: list[str] = []
    for afield in AgentField:
        rule = AGENT_FIELD_MATRIX[afield]
        if rule.emit is not FieldEmit.FRONTMATTER:
            continue
        if not agent_field_supported(afield, build_target):
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
    """INVOCATION emit 필드를 호출 파라미터 안내 단락으로.

    WP-FF 이후 이 emit을 쓰는 에이전트 필드는 없다 — max_turns/background/
    isolation이 프론트매터로 올라갔기 때문이다(본문 안내문은 부르는 쪽이 읽고
    따라야 적용되지만, 프론트매터는 CC 런타임이 직접 강제한다).

    함수는 남겨 둔다: 호출 시점에만 의미가 있는 필드가 나중에 생기면 여기가
    자리다. 지금은 항상 빈 목록이라 단락이 배출되지 않는다.
    """
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


def _build_target(project):
    """프로젝트 빌드 타깃. project 미지정이면 MARKETPLACE 취급(하위 호환)."""
    from daedalus.model.plugin.enums import BuildTarget

    if project is None:
        return BuildTarget.MARKETPLACE
    return getattr(project, "build_target", None) or BuildTarget.MARKETPLACE


def _is_local_build(project) -> bool:
    """프로젝트 빌드 타깃이 LOCAL인가. project 미지정이면 MARKETPLACE 취급(하위 호환)."""
    from daedalus.model.plugin.enums import BuildTarget

    return _build_target(project) is BuildTarget.LOCAL


def _agent_mcp_server_names(agent: AgentDefinition) -> list[str]:
    """에이전트가 필요로 하는 MCP 서버 이름 (선언 + tools의 mcp__ 접두 추출).

    `_settings_note_agent`와 같은 합집합 규칙을 쓴다 — 본문 언급과 프론트매터
    배출이 서로 다른 목록을 말하면 안 된다.
    """
    config = agent.config
    declared = set(getattr(config, "mcp_servers", None) or ())
    from_tools = set(_mcp_servers_from_tools(getattr(config, "tools", None)))
    return sorted(declared | from_tools)


def _agent_hook_groups(agent: AgentDefinition, project) -> dict[str, Any]:
    """에이전트가 참조하는 훅을 CC hooks 스키마(이벤트 → 그룹 목록)로.

    구조는 `compile_hooks_json`이 만드는 것과 같다 — 서브에이전트 프론트매터의
    `hooks`가 settings.json의 `hooks`와 동일한 형식을 쓰기 때문이다.
    라이브러리에 없는 이름은 조용히 빠진다(`dangling_hook_ref`가 잡는다).
    """
    referenced = list(getattr(agent.config, "hooks", None) or {})
    if not referenced or project is None:
        return {}
    wanted = set(referenced)
    library = getattr(project, "hook_library", None) or []

    buckets: dict[HookEvent, list[HookDef]] = {}
    for hook in library:  # 라이브러리 선언 순서 = 결정적
        if hook.name in wanted:
            buckets.setdefault(hook.event, []).append(hook)

    out: dict[str, Any] = {}
    for event in HookEvent:  # 선언 순서 = 결정적 이벤트 키 순서
        groups = [h.to_json() for h in (buckets.get(event) or []) if h.handlers]
        if groups:
            out[event.value] = groups
    return out


def _local_settings_frontmatter_lines(agent: AgentDefinition, project) -> list[str]:
    """LOCAL 빌드에서만 나가는 에이전트 프론트매터 줄 — hooks / mcpServers (WP-LA).

    CC는 **플러그인 서브에이전트의 `hooks`/`mcpServers`/`permissionMode`를 보안상
    무시한다**. `.claude/agents/`에 반입되는 LOCAL 빌드에서만 실제로 동작하므로,
    이 두 필드는 여기서만 배출한다(`permissionMode`는 매트릭스가 이미 프론트매터로
    내보내고 있어 별도 처리하지 않는다 — 마켓플레이스 빌드에서 무시된다는 사실은
    `unsupported_agent_field_in_marketplace_build` 경고가 알린다).
    """
    if not _is_local_build(project):
        return []

    lines: list[str] = []
    hook_groups = _agent_hook_groups(agent, project)
    if hook_groups:
        lines.append(f"{AgentField.HOOKS.frontmatter_key}:")
        lines.extend(_yaml_block_lines(hook_groups, 2))
    servers = _agent_mcp_server_names(agent)
    if servers:
        # 이름 참조 형태(리스트) — 이미 세션에 설정된 서버를 가리킨다.
        # 인라인 정의는 모델에 서버 설정 자체가 없으므로 지원 범위 밖이다.
        lines.append(f"{AgentField.MCP_SERVERS.frontmatter_key}:")
        lines.extend(_yaml_block_lines(servers, 2))
    return lines


def _settings_note_agent(agent: AgentDefinition, project=None) -> list[str]:
    """SETTINGS emit 필드(hooks/mcp_servers)를 요구 환경 언급 단락으로 (v0 산출 제외).

    WP-TM Part C: config.tools의 mcp__ 접두에서 추출한 서버 이름도 명시적
    mcp_servers 선언과 합쳐(중복 제거, 이름순) 같은 단락에 담는다 — 별도
    "## 요구 환경" 단락을 또 만들지 않는다.

    WP-LA: LOCAL 빌드에서는 이 둘이 프론트매터로 **실제 배출**되므로(설정을
    직접 들고 가므로) 이 언급 단락을 내지 않는다 — 같은 사실을 두 번 말하는
    데다, "설정 파일을 생성하지 않음"이라는 문구가 거짓이 된다.
    """
    if _is_local_build(project):
        return []

    config = agent.config
    needs: list[str] = []
    hooks = getattr(config, "hooks", None)
    if hooks:
        names = ", ".join(str(n) for n in hooks)
        needs.append(f"lifecycle hooks: {names} (hooks/hooks.json 생성됨)")
    mcp_all = _agent_mcp_server_names(agent)
    if mcp_all:
        names = ", ".join(mcp_all)
        needs.append(f"MCP 서버 연결: {names} (`.mcp.json`)")
    if not needs:
        return []
    blocks = [
        "## 요구 환경",
        "이 에이전트는 다음 외부 설정을 전제한다 (v0 컴파일러는 설정 파일을 생성하지 않음):",
        "\n".join(f"- {n}" for n in needs),
    ]
    return blocks


def _caller_contracts_section(agent: AgentDefinition) -> list[str]:
    """WP-IC Part C-3: caller_contracts(잠금 계약 카드)를 "## 호출 계약" 단락으로.

    각 Section을 `### <title>` + content로 선언 순서대로 나열. 비어 있으면
    빈 리스트(단락 생략) — 기존 누락 해소(caller_contracts는 지금까지 컴파일
    산출에 반영되지 않았다).
    """
    contracts = getattr(agent, "caller_contracts", None) or []
    if not contracts:
        return []
    blocks: list[str] = ["## 호출 계약"]
    for sec in contracts:
        blocks.append(f"### {sec.title}")
        content = (sec.content or "").strip()
        if content:
            blocks.append(content)
    return blocks


def compile_agent(agent: AgentDefinition, project=None) -> str:
    """에이전트 → agent .md 텍스트 (LF, BOM 없음, 결정적)."""
    fm_lines = _frontmatter_lines_agent(agent, project)
    # LOCAL 빌드에서만 hooks/mcpServers가 프론트매터로 나간다 (WP-LA)
    fm_lines.extend(_local_settings_frontmatter_lines(agent, project))
    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 본문(body)
    body_block = _body_block(agent.body)
    if body_block is not None:
        blocks.append(body_block)

    # 호출 계약(WP-IC) — 본문 뒤, 기존 누락 해소.
    blocks.extend(_caller_contracts_section(agent))

    # 호출 파라미터(INVOCATION)
    blocks.extend(_invocation_section_agent(agent))
    # 요구 환경(SETTINGS 언급) — LOCAL 빌드는 프론트매터가 대신하므로 생략된다
    blocks.extend(_settings_note_agent(agent, project))

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
        blocks.extend(_blackboard_section(project, agent))

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
        head += _describe_access(state)
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


# WP-RS Part B: SessionStart에 합성 배출되는 진행 상태 주입 훅.
# hook_library를 오염시키지 않는다 — hooks.json 합류는 컴파일 시점에만 합성된다.
# WP-HS: 다른 훅과 같은 규칙으로 스크립트 파일이 되고, hooks.json에는 경로만 남는다.
_PROGRESS_SESSION_START_COMMAND = 'cat state/__progress__.json 2>/dev/null || true'
_PROGRESS_SCRIPT_NAME = "__progress__.sh"
_PROGRESS_SCRIPT_REF = f"{HOOK_SCRIPT_REF_PREFIX}{_PROGRESS_SCRIPT_NAME}"


def _progress_hook_entry() -> dict[str, Any]:
    return {"type": "command", "command": _PROGRESS_SCRIPT_REF}


def compile_hook_scripts(project) -> list[tuple[str, str]]:
    """훅 스크립트 파일 — [(``hooks/scripts/`` 기준 상대경로, 내용), …] (WP-HS).

    커맨드는 아무리 짧아도 파일로 나간다 — hooks.json에는 루트 기반 경로만
    남는다. 참조된 훅만 대상이며(hooks.json에 실리는 것과 같은 집합), 진행 상태
    합성 훅도 같은 규칙으로 파일이 된다.

    반환 순서는 결정적이다(라이브러리 선언 순서 → 훅 내 핸들러 순서).
    같은 파일명이 둘 나오면 나중 것이 앞의 것을 덮으므로 **먼저 선언된 훅이
    이긴다** — 이름 충돌은 `duplicate_hook_script`가 컴파일 게이트에서 잡는다.
    """
    library = getattr(project, "hook_library", None) or []
    referenced = set(_collect_referenced_hook_names(project))

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for hook in library:
        if hook.name not in referenced:
            continue
        for filename, body in hook.script_files():
            if filename in seen:
                continue
            seen.add(filename)
            out.append((filename, _script_text(body)))

    if _should_emit_progress_hook(project) and _PROGRESS_SCRIPT_NAME not in seen:
        out.append((_PROGRESS_SCRIPT_NAME, _script_text(_PROGRESS_SESSION_START_COMMAND)))
    return out


def _script_text(body: str) -> str:
    """스크립트 본문을 파일 텍스트로 — LF 고정, 끝 개행 1개."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _should_emit_progress_hook(project) -> bool:
    return bool(getattr(project, "emit_progress_hook", True)) and bool(
        _graph_placements_any(project)
    )


def compile_hooks_json(project) -> str | None:
    """프로젝트가 참조하는 HookDef를 모아 CC settings hooks.json 텍스트로.

    스키마:
        {"hooks": {"<EventName>": [{"matcher": "...", "hooks": [{"type": "command",
          "command": "...", "timeout": ...}]}]}}
    - matcher는 도구 이벤트(Pre/PostToolUse)에서만 출력. 그 외 이벤트는 matcher 생략.
    - 같은 이벤트의 복수 훅은 hook_library 선언 순서로 정렬(결정적).
    - 이벤트 키 순서는 HookEvent 선언 순서(결정적).

    WP-RS Part B: `project.emit_progress_hook`(기본 True)이고 프로젝트 그래프에
    placement가 1개 이상이면 SessionStart 이벤트에 진행 상태 주입 커맨드를
    합성해 합류시킨다(hook_library에는 기록하지 않음 — 순수 컴파일 시점 합성).
    사용자 정의 SessionStart 훅이 있으면 그 뒤에 공존한다.

    참조된 라이브러리 훅도 없고 합성 진행 훅도 없으면 None(파일 생성 안 함).

    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    library = getattr(project, "hook_library", None) or []
    by_name = {h.name: h for h in library}
    referenced = _collect_referenced_hook_names(project)
    resolved = [by_name[n] for n in referenced if n in by_name]

    emit_progress = _should_emit_progress_hook(project)

    if not resolved and not emit_progress:
        return None

    # 이벤트 → HookDef 목록 (라이브러리 선언 순서 유지, 결정적).
    resolved_names = {h.name for h in resolved}
    event_buckets: dict[HookEvent, list[HookDef]] = {}
    for hook in library:
        if hook.name in resolved_names:
            event_buckets.setdefault(hook.event, []).append(hook)

    hooks_obj: dict[str, Any] = {}
    for event in HookEvent:  # 선언 순서 = 결정적 이벤트 키 순서
        bucket = event_buckets.get(event) or []
        # 핸들러가 하나도 없는 훅은 배출하지 않는다 — CC 스키마에서 hooks는
        # 필수이고, 빈 배열은 아무 일도 하지 않으면서 파일만 늘린다.
        groups: list[dict[str, Any]] = [h.to_json() for h in bucket if h.handlers]
        if event is HookEvent.SESSION_START and emit_progress:
            # 사용자 정의 SessionStart 훅 뒤에 합성 훅을 이어붙인다(공존).
            groups.append({"hooks": [_progress_hook_entry()]})
        if groups:
            hooks_obj[event.value] = groups

    text = json.dumps({"hooks": hooks_obj}, ensure_ascii=False, indent=2)
    # 스크립트 참조의 ${ROOT}를 빌드 타깃에 맞는 CC 변수로 확장한다 (WP-HS/WP-RT).
    text = expand_root_token(text, project)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _graph_placements_any(project) -> bool:
    """프로젝트 그래프에 EntryPoint 외 노드(placement)가 하나라도 있으면 True.

    판정의 단일 진실은 Validator._graph_has_placements — 복붙 드리프트 방지를
    위해 위임한다 (리뷰 지적 ⑦).
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return False
    from daedalus.model.validation import Validator
    return Validator._graph_has_placements(graph)


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


# ─────────────────────────── plugin.json (매니페스트) ───────────────────────────


def compile_plugin_manifest(project) -> str:
    """프로젝트 → .claude-plugin/plugin.json 텍스트 (LF, 결정적, 항상 생성).

    키 순서 고정: name → description(빈 문자열이면 키 생략) → version.
    LF·UTF-8 보장 텍스트(끝 개행 1개). json.loads 왕복 가능.
    """
    manifest: dict[str, Any] = {"name": getattr(project, "name", "")}
    description = getattr(project, "description", "") or ""
    if description:
        manifest["description"] = description
    manifest["version"] = getattr(project, "version", "0.1.0")

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


# ─────────────────────────── 로컬 빌드 (WP-TG) ───────────────────────────

# LOCAL 빌드에서 files/ 참조만 치환한다 — files/ 외 용도의 ${CLAUDE_PLUGIN_ROOT}는
# 그대로 두고 검증 규칙(plugin_root_in_local_build)이 경고한다.
_LOCAL_FILE_REF_FROM = "${CLAUDE_PLUGIN_ROOT}/files/"
_LOCAL_FILE_REF_TO = "${CLAUDE_PROJECT_DIR}/files/"


def expand_root_token(text: str, project=None) -> str:
    """산출 텍스트의 ``${ROOT}``를 빌드 타깃에 맞는 CC 변수로 확장한다 (WP-RT).

    본문 정본은 타깃 중립 토큰 하나만 쓰고, 어느 CC 변수가 되는지는 여기서
    정해진다 — 마켓플레이스는 ``${CLAUDE_PLUGIN_ROOT}``, 프로젝트 설치는
    ``${CLAUDE_PROJECT_DIR}``. 매핑의 단일 진실은 model/plugin/variables.py.
    """
    from daedalus.model.plugin.variables import expand_root

    return expand_root(text, _build_target(project))


def substitute_local_file_refs(text: str) -> str:
    """LOCAL 빌드 산출 텍스트에서 ``${CLAUDE_PLUGIN_ROOT}/files/`` →
    ``${CLAUDE_PROJECT_DIR}/files/``로 치환한다.

    본문 저장 정본은 마켓플레이스 형태 하나이며(WP-FR 재작업 없음), 이 치환은
    LOCAL 빌드 산출 시점에만 적용된다 — MARKETPLACE 산출 문자열은 불변.
    """
    return text.replace(_LOCAL_FILE_REF_FROM, _LOCAL_FILE_REF_TO)


# ─────────────────────────── 블록 결합 ───────────────────────────


def _join_blocks(blocks: list[str]) -> str:
    """블록 목록을 빈 줄 하나로 구분해 결합하고 끝에 개행 1개. LF 고정."""
    text = "\n\n".join(b for b in blocks if b is not None and b != "")
    # CRLF 잔존 방지
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text
