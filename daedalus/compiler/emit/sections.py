# daedalus/compiler/emit/sections.py
"""공용 단락 생성 — 가드/트리거 서술, FSM 절차 서술, 요구 환경(MCP), 블랙보드,
tool_shelf 참조 단락.

스킬(skill.py)·에이전트(agent.py) 조립이 함께 쓰는 단락들이다.
"""
from __future__ import annotations

from daedalus.compiler.emit.common import _graph_placements
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
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill, Skill
from daedalus.model.plugin.variables import ROOT_TOKEN


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
    """SimpleState의 skill_ref에 따른 작업 지시 문구."""
    ref = state.skill_ref
    if ref is None:
        return ""
    if isinstance(ref, AgentDefinition):
        return f"delegate to agent `{ref.name}`"
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
                xfer = f" (first follow transition skill `{t.skill_ref.name}`)"
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
    config = getattr(skill, "config", None)
    servers = _mcp_servers_from_tools(getattr(config, "allowed_tools", None))
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
        config = getattr(skill, "config", None)
        servers.update(_mcp_servers_from_tools(getattr(config, "allowed_tools", None)))
    for agent in getattr(project, "agents", []) or []:
        config = getattr(agent, "config", None)
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
    fsm = getattr(component, "fsm", None)
    if fsm is not None:
        reads, writes = _collect_state_access(fsm)
    for placement in _graph_placements(component, project):
        reads.update(getattr(placement, "reads", None) or [])
        writes.update(getattr(placement, "writes", None) or [])
    return reads, writes


def _blackboard_section(project, component=None) -> list[str]:
    """프로젝트 최상위 블랙보드 class_definitions → '## Shared State (Blackboard)' 블록.

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

    # 플러그인 이름이 곧 네임스페이스다 (WP-NS) — 한 작업 폴더에 여러 ddls
    # 플러그인이 깔려도 스키마와 상태가 서로를 덮지 않게 이름으로 가른다.
    # 스키마 경로는 타깃 중립 토큰으로 넘긴다(WP-RT). ${ROOT}는 컴파일 시
    # MARKETPLACE→${CLAUDE_PLUGIN_ROOT} / LOCAL→${CLAUDE_PROJECT_DIR}로 확장되고,
    # schemas/<플러그인>.json은 양쪽 타깃 모두 그 루트 밑에 산출되므로 토큰
    # 하나로 둘 다 맞는다.
    plugin = getattr(project, "name", "") or "plugin"
    state_dir = f"state/{plugin}"
    schemas_ref = ROOT_TOKEN + f"/schemas/{plugin}.json"
    intro = (
        "State shared across contexts in this workflow lives as JSON files in the\n"
        f"`{state_dir}/` directory of the working folder. Each file follows the\n"
        f"schema defined in the plugin's `schemas/{plugin}.json`."
    )
    cli_lines = (
        "Run `command -v daedalus-bb` to check whether the CLI is available (this\n"
        "assumes a POSIX shell; if you cannot tell, assume it is missing and edit\n"
        "the files directly per the rules below). If it is available, do not edit\n"
        "the state files by hand — read and write them through the CLI, which\n"
        "validates against the schema before writing:\n"
        f"- `daedalus-bb --schemas {schemas_ref} read <Class>`\n"
        f"- `daedalus-bb --schemas {schemas_ref} write <Class> --set <field>=<value>`\n"
        "  (use `--append` / `--remove` for collection fields)\n"
        f"- `daedalus-bb --schemas {schemas_ref} validate`\n"
        "`--schemas` is required, and it also decides where state goes: the CLI\n"
        "derives the state directory from the schema filename, so it writes under\n"
        f"`{state_dir}/`.\n"
        "`daedalus-bb` ships with Daedalus — do not install any package to obtain it."
    )

    rule_lines = (
        "Rules:\n"
        "- Always read a state file before changing it (read, modify, write).\n"
        "- If the file does not exist, create it from the schema.\n"
        "- Always fill every field the schema marks as required."
    )

    if union:
        relevant_names = {ref.split(".", 1)[0] for ref in union}
        relevant_classes = [c for c in classes if c.name in relevant_names]
        lines: list[str] = []
        for cls in relevant_classes:
            desc = f" — {cls.description}" if cls.description else ""
            lines.append(f"- `{cls.name}` → `{state_dir}/{cls.name}.json`{desc}")

        subject = "agent" if isinstance(component, AgentDefinition) else "skill"
        intro_lines: list[str] = []
        if reads:
            intro_lines.append(
                f"This {subject} reads: " + ", ".join(f"`{r}`" for r in sorted(reads))
            )
        if writes:
            intro_lines.append(
                f"This {subject} writes: " + ", ".join(f"`{w}`" for w in sorted(writes))
            )

        # 총론(디렉토리·스키마 설명)은 선언 유무와 무관하게 유지 — 선언은
        # "덧붙이는" 정보이지 총론을 대체하지 않는다 (리뷰 지적 1).
        return [
            "## Shared State (Blackboard)",
            intro,
            "\n".join(intro_lines),
            "\n".join(lines),
            cli_lines,
            rule_lines,
        ]

    lines = []
    for cls in classes:
        desc = f" — {cls.description}" if cls.description else ""
        lines.append(f"- `{cls.name}` → `{state_dir}/{cls.name}.json`{desc}")

    return [
        "## Shared State (Blackboard)",
        intro,
        "\n".join(lines),
        cli_lines,
        rule_lines,
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
        body = getattr(tool, "body", "")
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
