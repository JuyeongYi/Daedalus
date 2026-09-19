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
from daedalus.compiler.emit.fork import fork_frontmatter_lines, fork_report_section
from daedalus.compiler.emit.frontmatter import (
    _frontmatter_block,
    _frontmatter_lines_skill,
)
from daedalus.compiler.emit.guides import _insert_guide_pointer
from daedalus.compiler.emit.sections import (
    _background_references_section,
    _blackboard_section,
    _describe_fsm,
    _mcp_requirement_section_skill,
    _tool_shelf_section,
    _transition_condition,
)
from daedalus.compiler.emit.wrapped import (  # noqa: F401 — parse_wrapped_source 재노출(기존 임포트 경로)
    _wrapped_procedure_section,
    _wrapped_requirements_section,
    parse_wrapped_source,
)
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.placement import is_edge_placeable
from daedalus.model.plugin.roles import BodySource, Bucket, PlacementRole
from daedalus.model.plugin.variables import ROOT_TOKEN
from daedalus.model.plugin.skill import Skill


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
    return f"invoke transition skill {shown} and follow it, then "


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
    # "이 노드로 가는 것이 위임인가"는 대상이 선언한다(`DELEGATION_TARGET`, Q9).
    if ref.DELEGATION_TARGET:
        line = f"{prefix}delegate to agent `{name}`"
        # 에이전트 placement의 outgoing을 한 단계 인라인 (별도 컨텍스트라 호출자
        # 쪽에 후속 지시를 둔다 — 에이전트 .md는 호출자 지침을 담을 수 없음).
        inline_parts: list[str] = []
        for t in sm.transitions:
            if t.source is target_state:
                tgt_ref = getattr(t.target, "skill_ref", None)
                if tgt_ref is None or tgt_ref.DELEGATION_TARGET:
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


#: 비동기 fork 갈래에 붙는 접미 (WP-FK2 C1).
#:
#: `background: true` 스킬은 **보통** 서브에이전트가 따로 돌고 보고가 나중에 작업
#: 알림으로 온다. 다만 항상 그렇지는 않다 — 비대화 `claude -p`/Agent SDK,
#: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, 재진입 호출, 스케줄 작업 발화에서는
#: 강제로 인라인 실행된다(공식 문서 2026-09-17 확인). 그래서 "기다리지 말라"가
#: 아니라 "막고 기다리지 말고, 보고가 어떤 경로로 오든 받는 대로 처리하라"고
#: 말한다 — 단정하면 인라인으로 돌아온 경우 오지 않을 알림을 기다린다.
_ASYNC_FORK_BRANCH_SUFFIX = (
    " (background fork — do not block on it; act on its report as soon as you "
    "have it, whether it comes back inline in this turn or later as a task "
    "notification)"
)


def _invoke_phrase(ref, name: str) -> str:
    """skill_ref 인보크 지시 문구 — 보고가 뒤늦게 오는 종류만 접미가 붙는다.

    술어는 `REPORTS_OUT_OF_BAND` 선언이다(Q20) — "비동기 fork인가"가 아니라
    "결과가 작업 알림으로 뒤늦게 오는가"가 이 문장이 묻는 것이다.
    """
    phrase = f"invoke skill `{name}`"
    if ref.REPORTS_OUT_OF_BAND:
        phrase += _ASYNC_FORK_BRANCH_SUFFIX
    return phrase


def _next_steps_section(component, project) -> list[str]:
    """project.graph에서 component placement의 outgoing 전이를 모아 "## Next Steps"
    단락 블록을 생성한다 (버그 2). outgoing이 없으면 빈 목록(단락 생략).

    component는 전역 스킬 객체. 그래프에서 skill_ref가 identity로 일치하는
    SimpleState placement를 찾고, 그 placement에서 나가는 전이를 서술한다.
    """
    placements = _graph_placements(component, project)
    if not placements:
        return []
    graph = project.graph
    events_by_name = {e.name: e for e in component.output_ports()}
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

def _progress_cli(project) -> str:
    """진행 파일을 다루는 CLI 접두 — `daedalus-bb --schemas <스키마> progress`.

    갱신을 CLI에 맡기는 이유(WP-NS/D13): 진행 파일은 최상위 키가 플러그인 이름인
    **공유 파일**이라, 손편집을 시키면 "남의 키는 건드리지 말라"는 병합을 모델이
    매번 정확히 해내야 한다. 한 번만 놓쳐도 파일을 통째 덮어써 다른 플러그인의
    진행 기록이 사라진다. CLI는 그 병합을 코드로 보장한다.
    """
    plugin = getattr(project, "name", "") or "plugin"
    return f"daedalus-bb --schemas {ROOT_TOKEN}/schemas/{plugin}.json progress"


def _progress_update_note(project) -> str:
    """"## Next Steps" 끝의 진행 기록 잔여 — 명령 1줄 + 위임 갈래의 단서 1줄.

    양식 설명·`note`에 갈래를 적는 이유·수동 폴백은 워크플로 가이드가 말한다
    (WP-FK2 C3). 다만 **에이전트 위임 갈래의 2회 갱신**은 여기 남긴다 — 갈래 줄
    바로 아래의 단일 템플릿이 그대로 실행될 공산이 커서, 규칙을 통째로 가이드로
    보내면 위임 갈래에서 조용히 한 번만 갱신된다.
    """
    cli = _progress_cli(project)
    return (
        "Before handing off, record progress:\n"
        f"- `{cli} set --completed <this skill> --current <next target> "
        '--prev <this skill> --note "<branch you took> — <one-line handoff>"`\n'
        "If the branch delegates to an agent, run this twice — see the workflow guide."
    )


def _async_fork_targets(component, project) -> list[str]:
    """component placement의 outgoing 전이가 가리키는 비동기 fork 스킬 이름 (이름순).

    호출자 산출에만 쓴다 — 넘길 때 `current`를 누가 갖는지 말해야 하기 때문이다.
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    placements = _graph_placements(component, project)
    if not placements:
        return []
    placement_ids = {id(p) for p in placements}
    names = {
        getattr(ref, "name", "")
        for t in getattr(graph, "transitions", None) or []
        if id(t.source) in placement_ids
        for ref in (getattr(t.target, "skill_ref", None),)
        if ref is not None and ref.REPORTS_OUT_OF_BAND
    }
    return sorted(names - {""})


def _async_fork_handoff_note(cli: str, names: list[str]) -> str:
    """비동기 fork로 넘기는 갈래의 진행 기록 규약 — 오케스트레이터 확정 (2026-09-18), 1단계.

    진행 파일은 플러그인당 항목이 하나뿐이라 "지금 도는 비동기 단계"를 적을 자리가
    없다. 그래서 넘기는 순간 `current`를 그 fork에게 주고 `note`로 기다리는 중임을
    밝힌다 — 그래야 ① 중간에 끊겨도 재개 판단이 가능하고 ② 보고가 돌아왔을 때
    fork의 선행 조건(`current`가 아직 자기인가)이 판정할 대상이 생긴다.
    """
    shown = ", ".join(f"`{n}`" for n in names)
    return (
        f"Handing off to a background fork ({shown}) is still a handoff. For that "
        f"branch use this instead of the command above: `{cli} set --completed "
        "<this skill> --current <that fork> --prev <this skill> --note "
        '"awaiting background fork"`, then do not block on it — that fork\'s '
        "report says what to record next."
    )


def _transfer_progress_note(project) -> str:
    """전이 스킬의 "## Progress Record" 잔여 — 명령 1줄.

    "`current`를 소유하지 않는다"는 규약은 워크플로 가이드 2절이 말한다.
    """
    cli = _progress_cli(project)
    return f'- `{cli} set --note "<what happened>"`'


def _resume_preamble_section(project, skill_name: str) -> list[str]:
    """WP-RS Part A-1: 재개 프리앰블 — 프론트매터 직후, 본문 앞에 배출된다.

    재개 규칙의 일반형은 워크플로 가이드 3절이 말한다(WP-FK2 C3). 여기에는 이
    스킬의 **이름이 들어가는 줄**만 남는다. exit 3의 조건절은 잔여에 남긴다 —
    조건을 떼고 명령만 남기면 가이드의 일반형("항목이 없으면 지금 불린 스킬이
    시작점이다")과 워크플로 중간 스킬의 `--current <나>` 기록이 충돌한다.
    """
    cli = _progress_cli(project)
    body = (
        f"Run `{cli} read` first; this skill is `{skill_name}`. Follow the resume "
        f"rules in the workflow guide. If it exits 3 (no entry for this plugin "
        f"yet), this invocation is the start: `{cli} set --current {skill_name}`."
    )
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

    출처가 **비동기 fork**면 "background fork `X` reported"로 말한다(WP-FK2) —
    그 fork는 스스로 다음 단계를 부르지 않았고, 이 스킬은 fork의 보고를 받은
    메인이 시작시킨 것이다. 동기 fork는 문구가 다르지 않다(호출 흐름이 같다).
    """
    ref = getattr(t.source, "skill_ref", None)
    name = getattr(ref, "name", "") or t.source.name
    cond = _transition_condition(t)
    cond_str = f" [{cond}]" if cond else ""
    if ref is not None and ref.DELEGATION_TARGET:
        line = f"- entered after agent `{name}` returned{cond_str}"
        delegators = sorted({
            getattr(getattr(tr.source, "skill_ref", None), "name", "")
            for tr in getattr(project.graph, "transitions", [])
            if tr.target is t.source
        } - {""})
        if delegators:
            names = ", ".join(f"`{d}`" for d in delegators)
            line += f" (`prev` holds the delegating skill here — {names})"
    elif ref is not None and ref.REPORTS_OUT_OF_BAND:
        line = f"- entered when background fork `{name}` reported{cond_str}"
    else:
        line = f"- entered from `{name}`{cond_str}"
    # 출처가 그 출력 포트에 적어 둔 설명 — "무엇을 넘기는가"는 호출자가 말한다
    # (WP-IP: 인터페이스 선언은 값을 만드는 쪽에만 — 호출 계약(WP-CT)과 같은 원칙).
    trig_name = getattr(getattr(t, "trigger", None), "name", "")
    if trig_name and ref is not None:
        for ev in ref.output_ports():
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
    """"## Entry Context" 단락 — 작업 재개 프리앰블 뒤·본문 앞.

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
        # 읽는 법(어디서 읽는가·여러 갈래를 어떻게 가르는가·에이전트 위임 뒤의
        # prev)은 워크플로 가이드 4절이 말한다 — 여기는 지목 한 문장만.
        "Check `prev` and the branch in `note`, then follow the matching entry below.",
    ]
    ordered = sorted(incoming, key=_entry_source_ref_name)
    blocks.append("\n".join(_entry_item_line(t, project) for t in ordered))
    return blocks


def _progress_terminal_section(project) -> list[str]:
    """WP-RS Part A-3: 터미널 배치(outgoing 0개) — "다음 단계" 대신 배출된다.

    잔여는 명령 1줄이다(수동 폴백은 워크플로 가이드 2절).
    """
    cli = _progress_cli(project)
    return [
        "## Finishing Up",
        (
            "This skill is the last step of the workflow:\n"
            f'- `{cli} set --completed <this skill> --current done '
            '--note "<result summary>"`'
        ),
    ]


# ─────────────────────────── 공개: compile_skill ───────────────────────────


def _skill_kind_key(skill: Skill) -> str:
    """Skill 인스턴스 → SKILL_FIELD_MATRIX 키 — **`config.kind`가 단일 진실**이다.

    isinstance 사슬로 문자열을 다시 만들면 클래스와 config가 어긋난 날 두 사실이
    나온다. 표에 없는 kind면 `matrix_for`가 이유를 말하는 ValueError를 낸다.
    """
    from daedalus.model.plugin.field_matrix import matrix_for

    matrix_for(skill)  # 표가 없으면 여기서 이유를 말하고 멈춘다
    return str(skill.config.kind)


def compile_skill(
    skill: Skill,
    *,
    project=None,
    resolved_hooks=None,
) -> str:
    """단일 스킬 → SKILL.md 텍스트 (LF, BOM 없음, 결정적).

    project가 주어지면 tool_shelf 참조 단락을 덧붙인다(ProceduralSkill에 한함).
    """
    kind_key = _skill_kind_key(skill)
    fm_lines = _frontmatter_lines_skill(skill, kind_key)
    # fork 스킬 = **본문이 우리 것이면서 서브에이전트에서 도는 스킬**. 종류를
    # 열거하지 않는다 — 랩핑 스킬도 서브에이전트에서 돌지만 본문의 정본이
    # 외부라(`BODY_SOURCE`) fork 산출 규약(보고가 지시가 된다)을 받지 않는다.
    is_fork = (
        skill.BUCKET is Bucket.SKILLS
        and skill.RUNS_IN_SUBAGENT
        and skill.BODY_SOURCE is BodySource.OWNED
    )
    if is_fork:
        fm_lines = fork_frontmatter_lines(fm_lines, skill, project)
    # 스킬 훅 — 스킬이 활성인 동안만 걸린다(2026-09-13 실측: 플러그인 스킬도 동작).
    # settings.json과 같은 3단 구조라 한 줄 키-값이 아니라 블록으로 낸다.
    from daedalus.compiler.emit.frontmatter import _yaml_block_lines
    from daedalus.compiler.emit.hooks import component_hook_groups

    hook_groups = component_hook_groups(skill, project, resolved_hooks)
    if hook_groups:
        fm_lines.append("hooks:")
        fm_lines.extend(_yaml_block_lines(hook_groups, 2))

    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 작업 재개 프리앰블(WP-RS) — 프론트매터 직후, 본문 앞. 프로젝트 그래프에
    # 배치된 Procedural/Declarative 스킬에 배출(미배치는 없음).
    # Declarative 포함 이유: 배치되면 "다음 단계"를 받는데 갱신 규칙이 빠지면
    # 그 노드에서 진행 사슬이 끊긴다 (리뷰 지적 ①).
    progress_placements: list = []
    # 진행 사슬에 끼는 것은 **그래프 노드로 놓이는 종류**다(C10 — 종전의 배치
    # 클래스 튜플). 엣지 스킬(전이)·참조 노드 스킬은 자기 placement가 없어
    # 재개 프리앰블·진입 맥락의 대상이 아니다.
    if project is not None and type(skill).PLACEMENT not in (
        PlacementRole.EDGE,
        PlacementRole.REFERENCE,
    ):
        progress_placements = _graph_placements(skill, project)
    if progress_placements:
        # fork 서브에이전트는 사용자에게 확인하거나 진행 기록을 쓸 수 없다 —
        # 재개 판단은 부르는 메인 몫이다.
        if not is_fork:
            blocks.extend(_resume_preamble_section(project, skill.name))
        # 진입 맥락(WP-IC) — 작업 재개 프리앰블 뒤·본문 앞. incoming 전이가
        # 없으면 _entry_context_section이 빈 리스트를 반환(단락 생략).
        blocks.extend(_entry_context_section(skill, project))

    # 본문(body)
    body_block = _body_block(skill.body)
    if body_block is not None:
        blocks.append(body_block)

    # TransferSkill: 전이 도중 중단 대비 note (본문 끝).
    # 진행 파일을 만드는 배치 스킬이 하나도 없는 프로젝트에서는 고아 지시가
    # 되므로 placement 존재를 게이트로 건다 (리뷰 지적 ②).
    if (
        is_edge_placeable(skill)
        and project is not None
        and _graph_placements_any(project)
    ):
        blocks.append("## Progress Record")
        blocks.append(_transfer_progress_note(project))

    # WrappedSkill (WP-WR) — 절차는 실행 서브에이전트 위임 지시(emit/wrapped.py —
    # 외부 스킬은 메인 컨텍스트에서 직접 인보크하지 않는다). FSM 절차·tool_shelf는
    # 없다(본문의 정본이 소스라 여기서 만들 절차가 없다). 블랙보드 단락은
    # placement reads/writes 기반이라 유지.
    if skill.BODY_SOURCE is BodySource.EXTERNAL:
        blocks.extend(_wrapped_procedure_section(skill))
        if project is not None:
            blocks.extend(_blackboard_section(project, skill))

    # 단계 스킬(절차형·fork 2종) = 상태 노드로 놓이면서 본문이 우리 것인 스킬 —
    # FSM 절차 + tool_shelf. 랩핑 스킬은 본문 정본이 외부라 만들 절차가 없고,
    # 전이/참조/선언형은 상태 노드가 아니다.
    if (
        type(skill).PLACEMENT is PlacementRole.STATE
        and skill.BODY_SOURCE is BodySource.OWNED
    ):
        blocks.extend(_describe_fsm(skill.fsm, skill))
        if project is not None:
            blocks.extend(_tool_shelf_section(project))
            blocks.extend(_blackboard_section(project, skill))

    # 배치 노드에 링크된 참조 용도 랩핑 스킬 → consult 지시 (WP-WR).
    # 참조 용도는 산출 파일이 없어 이 단락이 유일한 흔적이다.
    if project is not None:
        blocks.extend(_background_references_section(skill, project))

    # 요구 환경(MCP 서버 자동 언급) — allowed_tools의 mcp__ 접두에서 추출.
    # project 유무와 무관(스킬 자체 config만 참조), "다음 단계" 단락 앞.
    # WrappedSkill은 소스 플러그인 의존까지 합쳐 전용 단락으로(헤딩 중복 방지).
    if skill.BODY_SOURCE is BodySource.EXTERNAL:
        blocks.extend(_wrapped_requirements_section(skill))
    else:
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
        if is_fork and progress_placements:
            # 갈래 목록은 Next Steps와 같은 것을 쓰되, 실행 지시가 아니라 보고 양식이다.
            blocks.extend(fork_report_section(
                _progress_cli(project),
                next_blocks[-1] if next_blocks else "",
                terminal=not has_outgoing,
                background=skill.REPORTS_OUT_OF_BAND,
                skill_name=skill.name,
            ))
        elif next_blocks:
            if progress_placements:
                next_blocks = list(next_blocks)
                note = _progress_update_note(project)
                # 비동기 fork로 넘기는 갈래가 있으면 `current` 소유 규약을 덧붙인다
                # (오케스트레이터 확정 2026-09-18 — fork 쪽 선행 조건과 짝을 이룬다).
                bg_targets = _async_fork_targets(skill, project)
                if bg_targets:
                    note += "\n" + _async_fork_handoff_note(
                        _progress_cli(project), bg_targets,
                    )
                next_blocks[-1] = next_blocks[-1] + "\n\n" + note
            blocks.extend(next_blocks)
        elif progress_placements and not has_outgoing:
            blocks.extend(_progress_terminal_section(project))

    _insert_guide_pointer(blocks, skill, project)
    return _join_blocks(blocks)
