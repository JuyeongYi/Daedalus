# daedalus/compiler/emit/skill.py
"""SKILL.md 조립 — 다음 단계(project.graph)·작업 재개(WP-RS)·진입 맥락(WP-IC)
단락 + `compile_skill` 공개 API.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import (
    _body_block,
    _graph_placements,
    _graph_placements_any,
    _join_blocks,
)
from daedalus.compiler.emit.frontmatter import (
    _frontmatter_block,
    _frontmatter_lines_skill,
)
from daedalus.compiler.emit.sections import (
    _blackboard_section,
    _describe_fsm,
    _mcp_requirement_section_skill,
    _tool_shelf_section,
    _transition_condition,
)
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    Skill,
    TransferSkill,
)


# ─────────────────────────── 프로젝트 그래프: 다음 단계 ───────────────────────────


def _next_step_condition(t) -> str:
    """프로젝트 그래프 전이의 조건 문구. 무가드 전이는 '무조건'."""
    cond = _transition_condition(t)
    return cond if cond else "always"


def _transfer_prefix(transition) -> str:
    """전이에 붙은 TransferSkill을 **수행하라는 지시**로 (A11).

    도착 스킬의 "진입 맥락"은 "전이 스킬 X의 지침을 수행한 상태다"라고 가정하는데,
    출발 스킬의 "다음 단계"에는 그것을 수행하라는 지시가 없었다 — 아무도
    전이 스킬을 실행하지 않는 구조였다. 지시를 만드는 쪽은 **출발 스킬**이다
    (도착 쪽은 이미 수행된 것을 전제로 읽는다).

    transfer가 없으면 빈 문자열이라 기존 문구가 그대로 나온다.
    """
    ref = getattr(transition, "skill_ref", None)
    if ref is None:
        return ""
    name = getattr(ref, "name", "")
    desc = (getattr(ref, "description", "") or "").strip()
    shown = f"`{name}` (`{desc}`)" if desc else f"`{name}`"
    return f"follow transition skill {shown}, then "


def _next_step_invoke_line(transition, sm: StateMachine) -> str | None:
    """전이 타깃 placement에 대한 한 줄 지시문.

    - 스킬 placement: "[조건] → `<skill>` 스킬을 인보크하라"
    - 에이전트 placement: "[조건] → 에이전트 `X`에게 위임하라" + 그 에이전트
      placement의 outgoing을 한 단계 인라인("위임 완료 후: …")
    전이에 TransferSkill이 붙어 있으면 앞에 그 지침을 수행하라는 지시가 붙는다
    (A11) — 위임 인라인의 후속 전이도 각자의 transfer를 갖는다.
    EntryPoint 등 skill_ref 없는 타깃은 None(스킵).
    """
    target_state = transition.target
    ref = getattr(target_state, "skill_ref", None)
    if ref is None:
        return None
    name = getattr(ref, "name", "")
    prefix = _transfer_prefix(transition)
    if isinstance(ref, AgentDefinition):
        line = f"{prefix}delegate to agent `{name}`"
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
                    f"after the agent returns: [{cond}] → "
                    f"{_transfer_prefix(t)}{_invoke_phrase(tgt_ref, tgt_name)}"
                )
        if inline_parts:
            line += " (" + "; ".join(inline_parts) + ")"
        return line
    return f"{prefix}{_invoke_phrase(ref, name)}"


def _invoke_phrase(ref, name: str) -> str:
    """skill_ref 종류별 인보크 지시 문구."""
    return f"invoke skill `{name}`"


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
    events_by_name = {
        e.name: e for e in getattr(component, "transfer_on", None) or []
    }
    lines: list[str] = []
    for placement in placements:
        for t in graph.transitions:
            if t.source is not placement:
                continue
            invoke = _next_step_invoke_line(t, graph)
            if invoke is None:
                continue
            cond = _next_step_condition(t)
            line = f"- [{cond}] → {invoke}"
            # WP-IP — 도착 노드의 입력 포트 선언이 퇴역했으므로, 이 갈래가
            # 무엇을 뜻하는지(출력 포트 description)는 호출하는 쪽 산출에 싣는다.
            trig_name = getattr(getattr(t, "trigger", None), "name", "")
            ev = events_by_name.get(trig_name)
            if ev is not None and (ev.description or "").strip():
                line += f" — {ev.description.strip()}"
            lines.append(line)
    if not lines:
        return []
    return [
        "## Next Steps",
        "When this skill is done, continue the workflow by the matching branch:",
        "\n".join(lines),
    ]


# ─────────────────────────── 작업 재개 (WP-RS) ───────────────────────────

# state/__progress__.json 규약 — 플러그인 FSM(프로젝트 그래프)의 진행 위치를 담는
# 단일 파일. 스킬 내부 FSM 상태는 기록하지 않는다(사용자 확정 설계).

_PROGRESS_UPDATE_NOTE = (
    "Before handing off, update `state/__progress__.json`: add this skill to "
    "`completed`, set `current` to the next target, set `prev` to this skill's "
    "own name, and write **which branch (output event name) you took plus a "
    "one-line handoff** into `note`. Set `updated` to the current time (ISO 8601). "
    "The receiving skill works out which path it came in on from (`prev`, the "
    "branch in `note`) — omit the branch and it cannot tell apart two different "
    "outcomes from the same source. When delegating to an agent, update twice: set "
    "`current` to the agent name just before delegating, then to the follow-up "
    "skill once the agent returns (keep `prev` as the delegating skill both times)."
)

_TRANSFER_PROGRESS_NOTE = (
    "You are a step on the transition itself, not a position in the workflow: "
    "leave `current` in `state/__progress__.json` as the caller set it, and record "
    "what happened during this transition in `note`."
)


def _resume_preamble_section(project, skill_name: str) -> list[str]:
    """WP-RS Part A-1: 재개 프리앰블 — 프론트매터 직후, 본문 앞에 배출된다.

    프로젝트 그래프에 배치된 전역 ProceduralSkill에만 배출된다(게이트는 호출부).
    WP-IC: JSON 예시에 `prev`(직전 출처 스킬 이름) 필드를 포함한다.
    """
    plugin_name = getattr(project, "name", "")
    body = "\n".join([
        "Read `state/__progress__.json` before you start.",
        (
            f"- If `current` is this skill (`{skill_name}`), resume from where it "
            "stopped, using `note` for context."
        ),
        (
            "- If `current` is a different skill, the workflow is somewhere else — "
            "stop and confirm with the user before continuing."
        ),
        (
            "- If the file does not exist, create it as "
            f'`{{"plugin": "{plugin_name}", "current": "{skill_name}", "completed": [], '
            '"note": "", "prev": "", "updated": "<current time, ISO 8601>"}`'
            " and continue."
        ),
    ])
    return ["## Resuming Work", body]


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
        line = f"- entered after agent `{name}` returned{cond_str}"
        delegators = sorted({
            getattr(getattr(tr.source, "skill_ref", None), "name", "")
            for tr in getattr(project.graph, "transitions", [])
            if tr.target is t.source
        } - {""})
        if delegators:
            names = ", ".join(f"`{d}`" for d in delegators)
            line += f" (`prev` holds the delegating skill here — {names})"
    else:
        line = f"- entered from `{name}`{cond_str}"
    # 출처가 그 출력 포트에 적어 둔 설명 — "무엇을 넘기는가"는 호출자가 말한다
    # (WP-IP: 인터페이스 선언은 값을 만드는 쪽에만 — 호출 계약(WP-CT)과 같은 원칙).
    trig_name = getattr(getattr(t, "trigger", None), "name", "")
    if trig_name and ref is not None:
        for ev in getattr(ref, "transfer_on", None) or []:
            if ev.name == trig_name and (ev.description or "").strip():
                line += f" — {ev.description.strip()}"
                break
    if t.skill_ref is not None:
        desc = f" (`{t.skill_ref.description}`)" if t.skill_ref.description else ""
        line += (
            f": transition skill `{t.skill_ref.name}`{desc} has already been "
            f"followed"
        )
    return line


def _entry_context_section(component, project) -> list[str]:
    """"## 진입 맥락" 단락 — 작업 재개 프리앰블 뒤·본문 앞.

    **그래프에서만 유도한다(WP-IP).** 도착 노드는 입력 포트를 선언하지
    않는다 — (출처, 트리거)가 이미 경로를 특정하고, 무엇을 넘기는지는 출처가
    자기 출력 포트 description에 적는다(계약 카드 퇴역과 같은 원칙: 인터페이스
    선언은 값을 만드는 쪽에만 둔다). 경로별로 다르게 행동해야 하면 그 지시는
    도착 스킬 본문에 쓴다.

    배치된 전역 ProceduralSkill/DeclarativeSkill에서 incoming 전이가 1개 이상일
    때만 배출(게이트는 호출부). incoming이 없으면 빈 리스트(단락 생략, 하위 호환).
    """
    incoming = _entry_incoming_transitions(component, project)
    if not incoming:
        return []
    blocks: list[str] = [
        "## Entry Context",
        (
            "Read `prev` (the previous skill) and `note` (the branch taken) from "
            "`state/__progress__.json`, then follow the matching source entry "
            "below. When one source has several entries, the branch name recorded "
            "in `note` picks the right one. After returning from an agent "
            "delegation, `prev` holds the delegating skill, not the agent."
        ),
    ]
    ordered = sorted(incoming, key=_entry_source_ref_name)
    blocks.append("\n".join(_entry_item_line(t, project) for t in ordered))
    return blocks


def _progress_terminal_section() -> list[str]:
    """WP-RS Part A-3: 터미널 배치(outgoing 0개) — "다음 단계" 대신 배출된다."""
    return [
        "## Finishing Up",
        (
            "This skill is the last step of the workflow. When it is done, update "
            "`state/__progress__.json`: add this skill to `completed`, set "
            "`current` to `\"done\"`, put a result summary in `note`, and set "
            "`updated` to the current time (ISO 8601)."
        ),
    ]


# ─────────────────────────── 공개: compile_skill ───────────────────────────


def _skill_kind_key(skill: Skill) -> str:
    """Skill 인스턴스 → SKILL_FIELD_MATRIX 키."""
    if isinstance(skill, ProceduralSkill):
        return "procedural"
    if isinstance(skill, TransferSkill):
        return "transfer"
    if isinstance(skill, DeclarativeSkill):
        return "declarative"
    if isinstance(skill, ReferenceSkill):
        return "reference"
    raise TypeError(f"알 수 없는 스킬 타입: {type(skill).__name__}")


def compile_skill(
    skill: Skill,
    *,
    project=None,
) -> str:
    """단일 스킬 → SKILL.md 텍스트 (LF, BOM 없음, 결정적).

    project가 주어지면 tool_shelf 참조 단락을 덧붙인다(ProceduralSkill에 한함).
    """
    kind_key = _skill_kind_key(skill)
    fm_lines = _frontmatter_lines_skill(skill, kind_key)

    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 작업 재개 프리앰블(WP-RS) — 프론트매터 직후, 본문 앞. 프로젝트 그래프에
    # 배치된 Procedural/Declarative 스킬에 배출(미배치는 없음).
    # Declarative 포함 이유: 배치되면 "다음 단계"를 받는데 갱신 규칙이 빠지면
    # 그 노드에서 진행 사슬이 끊긴다 (리뷰 지적 ①).
    progress_placements: list = []
    if (
        project is not None
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

    # TransferSkill: 전이 도중 중단 대비 note (본문 끝).
    # 진행 파일을 만드는 배치 스킬이 하나도 없는 프로젝트에서는 고아 지시가
    # 되므로 placement 존재를 게이트로 건다 (리뷰 지적 ②).
    if (
        isinstance(skill, TransferSkill)
        and project is not None
        and _graph_placements_any(project)
    ):
        blocks.append("## Progress Record")
        blocks.append(_TRANSFER_PROGRESS_NOTE)

    # ProceduralSkill — FSM 절차 + tool_shelf
    if isinstance(skill, ProceduralSkill):
        blocks.extend(_describe_fsm(skill.fsm, skill))
        if project is not None:
            blocks.extend(_tool_shelf_section(project))
            blocks.extend(_blackboard_section(project, skill))

    # 요구 환경(MCP 서버 자동 언급) — allowed_tools의 mcp__ 접두에서 추출.
    # project 유무와 무관(스킬 자체 config만 참조), "다음 단계" 단락 앞.
    blocks.extend(_mcp_requirement_section_skill(skill))

    # 프로젝트 그래프 기반 "다음 단계" (버그 2).
    # WP-RS: 배치 스킬이면 다음 단계 단락 끝에 진행 상태 갱신 규칙을 합류시키고,
    # outgoing이 없는 터미널 배치면 "다음 단계" 대신 "작업 완료"를 배출한다.
    # 터미널 판정은 "다음 단계 문구 생성 실패"가 아니라 **placement의 실제
    # outgoing 전이 부재**다 — 타깃이 빈 상태(skill_ref=None)뿐이라 문구가 안
    # 나와도 중간 스킬은 터미널이 아니다 (리뷰 차단 지적).
    if project is not None:
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
