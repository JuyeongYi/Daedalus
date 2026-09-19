# daedalus/compiler/emit/sections.py
"""공용 단락 생성 — 가드/트리거 서술, FSM 절차 서술, 요구 환경(MCP), 블랙보드,
tool_shelf 참조 단락.

스킬(skill.py)·에이전트(agent.py) 조립이 함께 쓰는 단락들이다.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import (
    _graph_placements,
    delegate_to_phrase,
    external_skill_name,
)
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
from daedalus.model.fsm.walk import iter_states
from daedalus.model.plugin.placement import is_reference_placed
from daedalus.model.plugin.roles import BodySource, Bucket
from daedalus.model.plugin.skill import Skill, StepSkill


# ─────────────────────────── 가드/트리거 서술 ───────────────────────────


def _describe_evaluation(ev: EvaluationStrategy) -> str:
    """EvaluationStrategy를 사람이 읽는 한 줄 조건으로."""
    if isinstance(ev, LLMEvaluation):
        return f"LLM judgment ({ev.prompt})" if ev.prompt else "LLM judgment"
    if isinstance(ev, ToolEvaluation):
        cond = f" (success when: {ev.success_condition})" if ev.success_condition else ""
        tool = ev.tool or "tool"
        return f"result of running `{tool}`{cond}"
    if isinstance(ev, MCPEvaluation):
        return f"result of MCP `{ev.server}.{ev.tool}`"
    if isinstance(ev, ExpressionEvaluation):
        return f"expression `{ev.expression}`" if ev.expression else "expression"
    if isinstance(ev, CompositeEvaluation):
        op = " AND " if ev.operator == "and" else " OR "
        inner = op.join(_describe_evaluation(c) for c in ev.children)
        return f"({inner})" if inner else "compound condition"
    return "condition"


def _describe_guard(guard: Guard | None) -> str:
    if guard is None:
        return ""
    return _describe_evaluation(guard.evaluation)


def _describe_trigger(trigger: object) -> str:
    if trigger is None:
        return ""
    name = getattr(trigger, "name", "")
    if isinstance(trigger, CompletionEvent):
        return f"completion event `{name}`"
    return f"event `{name}`" if name else ""


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
        parts.append("reads " + ", ".join(f"`{r}`" for r in reads))
    if writes:
        parts.append("writes " + ", ".join(f"`{w}`" for w in writes))
    return " (" + " / ".join(parts) + ")"


def _transition_condition(t) -> str:
    """전이 조건 문구(트리거 + 가드)를 조합."""
    parts: list[str] = []
    trig = _describe_trigger(t.trigger)
    if trig:
        parts.append(trig)
    g = _describe_guard(t.guard)
    if g:
        parts.append(f"guard: {g}")
    return ", ".join(parts)


# ─────────────────────────── FSM 절차 서술 ───────────────────────────


def _state_label(state: State) -> str:
    """상태 노드를 가리키는 표지 — 이름 + 종류 표식."""
    return state.name


def _describe_node_action(state: SimpleState) -> str:
    """SimpleState의 skill_ref에 따른 작업 지시 문구.

    "이 노드로 가는 것이 위임인가"는 대상이 선언한다(`DELEGATION_TARGET`, Q9) —
    종류를 열거하지 않는다.
    """
    ref = state.skill_ref
    if ref is None:
        return ""
    if getattr(ref, "DELEGATION_TARGET", False):
        # 단서 없이 한 줄만 내던 종전 산출을 보존한다(`note=False`).
        return delegate_to_phrase(ref, note=False)
    # 스킬 참조
    name = getattr(ref, "name", "")
    return f"use skill `{name}`"


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


def _describe_fsm(sm: StateMachine, skill: StepSkill) -> list[str]:
    """StepSkill(절차형·fork 2종) FSM을 사람이 읽는 절차 단락 블록 목록으로 변환.

    형식: 번호 매긴 상태 진행 목록 + 각 상태의 작업·출구 전이 조건.
    결정적: _ordered_states로 고정된 순서.

    방어 가드: states 비어 있음 / initial_state=None인 불완전 FSM은 절차 단락을
    생략하고 출력 이벤트만 서술한다 (compile_project 경유 시 게이트가 먼저
    거부하지만, compile_skill 직접 호출 경로를 보호).
    """
    blocks: list[str] = []
    if sm.states and sm.initial_state is not None:
        blocks.append("## Procedure")
        blocks.extend(_fsm_procedure_blocks(sm))

    # transfer_on 출구 이벤트 의미
    if skill.transfer_on:
        ev_lines = [
            "## Output Events",
            "End this skill with exactly one of the following outcome events:",
        ]
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
        f"Work through the steps below in order, starting at `{sm.initial_state.name}`."
    )
    blocks.append(intro)

    lines: list[str] = []
    for idx, state in enumerate(states, start=1):
        marks: list[str] = []
        if state is initial:
            marks.append("start")
        if id(state) in final_ids:
            marks.append("end")
        mark_str = f" ({', '.join(marks)})" if marks else ""

        head = f"{idx}. **{_state_label(state)}**{mark_str}"
        if isinstance(state, SimpleState):
            action = _describe_node_action(state)
            if action:
                head += f": {action}."
            else:
                head += "."
        elif isinstance(state, CompositeState):
            head += f": delegate to agent `{state.name}` (runs in its own context)."
        elif isinstance(state, ParallelState):
            regs = ", ".join(r.name for r in state.regions)
            join_note = _describe_join(state)
            head += f": run {regs} in parallel ({join_note})."
        elif isinstance(state, ChoiceState):
            head += ": evaluate the conditions and branch immediately — do not stop here."
        elif isinstance(state, TerminateState):
            head += ": stop the workflow here."
        elif isinstance(state, (EntryPoint, ExitPoint)):
            head += f" — pseudo state ({state.kind})."
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
                xfer = f" (first invoke transition skill `{t.skill_ref.name}`)"
            lines.append(
                f"    - → **{t.target.name}**{cond_str}{xfer}"
            )

    blocks.append("\n".join(lines))
    return blocks


def _describe_join(state: ParallelState) -> str:
    """ParallelState.join 전략을 사람이 읽는 문구로."""
    from daedalus.model.fsm.join import JoinStrategy
    if state.join is JoinStrategy.ANY:
        return "continue as soon as any region finishes"
    if state.join is JoinStrategy.N_OF:
        n = state.join_count if state.join_count is not None else "?"
        return f"continue once {n} regions finish"
    return "continue after every region finishes"


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
    """스킬 config.allowed_tools의 mcp__ 접두에서 서버 이름을 추출해 "## Requirements"
    단락을 만든다. 서버가 없으면 빈 목록(단락 생략).
    """
    servers = _mcp_servers_from_tools(getattr(skill.config, "allowed_tools", None))
    if not servers:
        return []
    names = ", ".join(f"`{s}`" for s in servers)
    return [
        "## Requirements",
        f"This skill requires these MCP servers to be connected: {names}",
    ]


def referenced_mcp_servers(project) -> list[str]:
    """프로젝트가 참조하는 MCP 서버 이름 합집합 (이름순 정렬 — 결정적).

    에이전트: ``config.mcp_servers`` 선언 ∪ ``config.tools`` 추출.
    스킬: ``config.allowed_tools`` 추출.
    "요구 환경" 단락과 같은 합집합 규칙 — 본문·프론트매터·설치 배선이 서로 다른
    목록을 말하지 않는다.
    """
    servers: set[str] = set()
    for skill in getattr(project, "skills", []) or []:
        config = skill.config
        servers.update(_mcp_servers_from_tools(getattr(config, "allowed_tools", None)))
    for agent in getattr(project, "agents", []) or []:
        config = agent.config
        servers.update(getattr(config, "mcp_servers", None) or [])
        servers.update(_mcp_servers_from_tools(getattr(config, "tools", None)))
    return sorted(s for s in servers if s)


# ─────────────────────────── 블랙보드 사용 지침 단락 ───────────────────────────


def _collect_state_access(sm: StateMachine) -> tuple[set[str], set[str]]:
    """머신(재귀 — sub_machine/Region 포함)의 모든 상태 reads/writes 합집합."""
    reads: set[str] = set()
    writes: set[str] = set()
    for state in iter_states(sm):
        reads.update(getattr(state, "reads", None) or [])
        writes.update(getattr(state, "writes", None) or [])
    return reads, writes


def _component_access_union(component, project) -> tuple[set[str], set[str]]:
    """component(스킬/에이전트) 자체 FSM(재귀) + 프로젝트 그래프 placement의
    reads/writes 선언 합집합 (WP-BB Part D-2)."""
    reads: set[str] = set()
    writes: set[str] = set()
    for sm in component.state_machines():
        sm_reads, sm_writes = _collect_state_access(sm)
        reads.update(sm_reads)
        writes.update(sm_writes)
    for placement in _graph_placements(component, project):
        reads.update(getattr(placement, "reads", None) or [])
        writes.update(getattr(placement, "writes", None) or [])
    return reads, writes


def linked_background_skills(component, project) -> list[tuple[str, str]]:
    """이 컴포넌트의 배치 노드에 링크된 **참조 용도 랩핑 스킬** →
    [(CC 명령 이름 `플러그인:스킬`, 랩퍼 description)] (WP-WR).

    소비자가 둘이다 — 스킬 산출은 consult 지시 단락
    (`_background_references_section`), 에이전트 산출은 `skills` 프론트매터
    주입(`_agent_skills_list` — 외부 플러그인 스킬은 서브에이전트에서만 쓴다,
    사용자 확정 2026-09-12). 판정을 한 곳에 둬야 둘이 같은 목록을 말한다.
    비활성 랩퍼·source 형식 불일치는 빠진다. 명령 이름순 정렬 — 결정적.
    ReferenceSkill(자체 산출이 있는 진짜 참조 문서)은 대상이 아니다.
    """
    if project is None:
        return []
    node_names = {
        s.name for s in getattr(project.graph, "states", [])
        if getattr(s, "skill_ref", None) is component
    }
    if not node_names:
        return []
    # **참조 노드로 쓰이는, 본문 정본이 외부인, 켜져 있는 스킬** — 세 능력
    # 선언이 종전의 `kind == "wrapped_skill" and usage == "reference" and
    # not disabled` 사다리를 그대로 대신한다(WP-2c). 자체 산출이 있는
    # `ReferenceSkill`은 `BODY_SOURCE`가 OWNED라 자연 제외된다.
    wrapped_refs = {
        s.name: s for s in project.skills
        if s.BODY_SOURCE is BodySource.EXTERNAL
        and is_reference_placed(s)
        and s.is_active()
    }
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rp in getattr(project, "reference_placements", []) or []:
        skill = wrapped_refs.get(rp.skill_name)
        if skill is None or skill.name in seen:
            continue
        if not node_names & set(getattr(rp, "connected_states", []) or []):
            continue
        ext = external_skill_name(skill.external_source or "")
        if not ext:
            continue  # external_source_missing 소관 — 빈 지시를 내지 않는다
        seen.add(skill.name)
        entries.append((ext, skill.description))
    entries.sort(key=lambda e: e[0])
    return entries


def _background_references_section(component, project) -> list[str]:
    """링크된 참조 용도 랩핑 스킬 → consult 지시 단락 (WP-WR — 스킬 산출 전용).

    참조 용도는 산출 파일이 없으므로 링크된 노드의 산출에 이 지시가 유일한
    흔적이다. 에이전트는 이 단락 대신 `skills` 프론트매터로 주입받는다.
    """
    entries = linked_background_skills(component, project)
    if not entries:
        return []
    lines = [
        "## Background Skills",
        (
            "External skills linked to this step as background — invoke them "
            "when their subject comes up (they are provided by plugins this "
            "plugin depends on; no local copy exists):"
        ),
    ]
    for name, description in entries:
        suffix = f" — {description}" if description else ""
        lines.append(f"- `/{name}`{suffix}")
    return ["\n".join(lines)]


def _blackboard_section(project, component) -> list[str]:
    """이 컴포넌트의 블랙보드 접근 선언 → '## Shared State (Blackboard)' 블록.

    **총론·CLI 사용법·규칙은 여기 없다** — 스킬마다 글자 하나 다르지 않게
    반복되던 문장이라 `guides/<플러그인>/blackboard.md`로 뺐다(WP-FK2 C3).
    여기 남는 것은 이 컴포넌트에만 해당하는 사실, 즉 "무엇을 읽고 쓰는가"와
    그에 해당하는 상태 파일 목록뿐이다.

    그래서 접근 선언(자체 FSM 재귀 + 그래프 placement) 합집합이 비면 **단락
    자체를 생략한다** — 가이드가 이미 전부 말하고 있어 덧붙일 고유 정보가 없다.

    `component`는 **필수 위치 인자**다. 기본값 None을 남겨 두면 "컴포넌트를
    빠뜨린 호출 = 단락이 통째로 사라짐"이 아무 말 없이 성립한다(원칙 5) —
    이 단락의 내용이 전부 컴포넌트에서 나오게 된 뒤로는 의미 없는 호출이다.
    """
    bb = getattr(project, "blackboard", None)
    classes = getattr(bb, "class_definitions", None) or []
    if not classes:
        return []

    reads, writes = _component_access_union(component, project)
    union = reads | writes
    if not union:
        return []

    # 플러그인 이름이 곧 네임스페이스다 (WP-NS) — 한 작업 폴더에 여러 ddls
    # 플러그인이 깔려도 스키마와 상태가 서로를 덮지 않게 이름으로 가른다.
    plugin = getattr(project, "name", "") or "plugin"
    state_dir = f"state/{plugin}"

    relevant_names = {ref.split(".", 1)[0] for ref in union}
    lines = [
        f"- `{cls.name}` → `{state_dir}/{cls.name}.json`"
        + (f" — {cls.description}" if cls.description else "")
        for cls in classes if cls.name in relevant_names
    ]

    # "이 컴포넌트를 무엇이라 부르는가" — 에이전트 두 종류 모두 "agent"다.
    # 컴파일러 산출의 영어 명사 — 버킷이 가른다(에이전트 두 종류 모두 "agent").
    subject = "agent" if component.BUCKET is Bucket.AGENTS else "skill"
    intro_lines: list[str] = []
    if reads:
        intro_lines.append(
            f"This {subject} reads: " + ", ".join(f"`{r}`" for r in sorted(reads))
        )
    if writes:
        intro_lines.append(
            f"This {subject} writes: " + ", ".join(f"`{w}`" for w in sorted(writes))
        )

    return [
        "## Shared State (Blackboard)",
        "\n".join(intro_lines),
        "\n".join(lines),
    ]


# ─────────────────────────── tool_shelf 참조 단락 ───────────────────────────


def _tool_shelf_section(project) -> list[str]:
    """tool_shelf를 참조 문서 단락으로 (Tier 2 실행 코드 생성 아님)."""
    shelf = getattr(project, "tool_shelf", None) or []
    if not shelf:
        return []
    blocks = ["## Reference: Tool Shelf"]
    intro = "Tool definitions this plugin refers to (execution wrappers are separate):"
    blocks.append(intro)
    lines: list[str] = []
    for tool in shelf:
        desc = f" — {tool.description}" if getattr(tool, "description", "") else ""
        lines.append(f"- **{tool.name}** ({tool.kind}){desc}")
        body = tool.body
        note = getattr(tool, "allowed_arguments_note", "")
        server = getattr(tool, "server", "")
        tool_name = getattr(tool, "tool_name", "")
        if server or tool_name:
            lines.append(f"  - MCP: server `{server}`, tool `{tool_name}`")
        if note:
            lines.append(f"  - Argument notes: {note}")
        if body.strip():
            lines.append(f"  - Body:\n\n```\n{body.strip()}\n```")
    blocks.append("\n".join(lines))
    return blocks


# ─────────────────────────── 출구 목록 ───────────────────────────


def _exits_section(events) -> list[str]:
    """출구 목록 → "## Exits" 단락. 에이전트와 랩핑 스킬 실행 에이전트
    (emit/wrapped.py)가 공유한다 — 호출자가 분기하는 규약이 같아야 한다."""
    if not events:
        return []
    lines = [
        "## Exits",
        "End with exactly one of the exits below. State which exit you took on "
        "the first line of your final report — the caller branches on that name:",
    ]
    for ev in events:
        desc = (getattr(ev, "description", "") or "").strip()
        lines.append(f"- `{ev.name}`" + (f" — {desc}" if desc else ""))
    return ["\n".join(lines)]
