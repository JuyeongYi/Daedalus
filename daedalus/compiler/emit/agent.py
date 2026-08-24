# daedalus/compiler/emit/agent.py
"""에이전트 .md 조립 — 프론트매터(skills 합류·LOCAL hooks/mcpServers)·호출
계약(그래프 유도)·내부 워크플로(legacy)·출구(transfer_on) + `compile_agent`.
"""
from __future__ import annotations

from typing import Any

from daedalus.compiler.emit.common import (
    _MISSING,
    _body_block,
    _build_target,
    _config_default,
    _enum_value,
    _is_local_build,
    _join_blocks,
)
from daedalus.compiler.emit.frontmatter import (
    _compose_description,
    _format_kv,
    _frontmatter_block,
    _yaml_block_lines,
    _yaml_scalar,
)
from daedalus.compiler.emit.sections import (
    _blackboard_section,
    _describe_access,
    _describe_guard,
    _describe_node_action,
    _mcp_servers_from_tools,
    _ordered_states,
    _tool_shelf_section,
    _transition_condition,
)
from daedalus.model.fsm.pseudo import ChoiceState, ExitPoint
from daedalus.model.fsm.state import CompositeState, SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import (
    AgentField,
    FieldEmit,
    FieldVisibility,
    ModelType,
)
from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX, FieldRule
from daedalus.model.plugin.hook import HookDef, HookEvent


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
        if afield is AgentField.SKILLS:
            merged = _agent_skills_list(agent, project)
            if merged:
                lines.append(_format_kv(key, merged))
            continue

        emitted = _emit_agent_field(afield, rule, config, key)
        if emitted is not None:
            lines.append(emitted)
    return lines


def _agent_skills_list(agent: AgentDefinition, project) -> list[str]:
    """에이전트 `skills` 프론트매터 — 자동 합류 + 수동 선언 (WP-AS).

    서브에이전트는 별도 컨텍스트라 스킬을 상속받지 않는다 — 목록에 없는 지식은
    없는 지식이다. 그래서 자동으로 합류시킨다:
      1. 전역 DeclarativeSkill 전부 — 배경 지식은 어느 컨텍스트에나 필요하다.
      2. 이 에이전트 placement에 링크된 ReferenceSkill — 캔버스에서 "이 에이전트가
         이 문서를 참조한다"고 선언한 것이 여기서 실현된다.
    그 뒤에 `config.skills`(수동 선언)가 순서대로 붙는다(중복 제거 — 자동 목록에
    이미 있으면 다시 넣지 않는다). project가 없으면 수동 선언만(하위 호환).
    """
    from daedalus.model.plugin.skill import DeclarativeSkill, ReferenceSkill

    auto: list[str] = []
    if project is not None:
        for skill in getattr(project, "skills", []) or []:
            if isinstance(skill, DeclarativeSkill):
                auto.append(skill.name)
        # placement 노드 이름 집합 — 참조 링크(connected_states)는 노드 이름을 가리킨다
        node_names = {
            s.name
            for s in getattr(getattr(project, "graph", None), "states", []) or []
            if getattr(s, "skill_ref", None) is agent
        }
        if node_names:
            ref_names = {
                s.name for s in project.skills if isinstance(s, ReferenceSkill)
            }
            for rp in getattr(project, "reference_placements", []) or []:
                if rp.skill_name in ref_names and node_names & set(rp.connected_states):
                    if rp.skill_name not in auto:
                        auto.append(rp.skill_name)
    for name in getattr(agent.config, "skills", None) or []:
        if name not in auto:
            auto.append(name)
    return auto


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


def _agent_mcp_server_names(agent: AgentDefinition) -> list[str]:
    """에이전트가 필요로 하는 MCP 서버 이름 (선언 + tools의 mcp__ 접두 추출).

    `_settings_note_agent`와 같은 합집합 규칙을 쓴다 — 본문 언급과 프론트매터
    배출이 서로 다른 목록을 말하면 안 된다.
    """
    config = agent.config
    declared = set(getattr(config, "mcp_servers", None) or ())
    from_tools = set(_mcp_servers_from_tools(getattr(config, "tools", None)))
    return sorted(declared | from_tools)


def _agent_hook_groups(
    agent: AgentDefinition, project, resolved_hooks: dict[str, HookDef] | None = None
) -> dict[str, Any]:
    """에이전트가 참조하는 훅을 CC hooks 스키마(이벤트 → 그룹 목록)로.

    구조는 `compile_hooks_json`이 만드는 것과 같다 — 서브에이전트 프론트매터의
    `hooks`가 settings.json의 `hooks`와 동일한 형식을 쓰기 때문이다.
    라이브러리에 없는 이름은 조용히 빠진다(`dangling_hook_ref`가 잡는다).
    """
    referenced = list(getattr(agent.config, "hooks", None) or {})
    if not referenced or project is None:
        return {}
    wanted = set(referenced)
    # A1 — 전역 훅 2단 스코프. resolved_hooks 생략 시 프로젝트 라이브러리만(하위 호환).
    from daedalus.compiler.emit.hooks import hook_library

    library = hook_library(project, resolved_hooks)

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


def _local_settings_frontmatter_lines(
    agent: AgentDefinition, project, resolved_hooks: dict[str, HookDef] | None = None
) -> list[str]:
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
    hook_groups = _agent_hook_groups(agent, project, resolved_hooks)
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


def _call_contract_section(agent: AgentDefinition, project) -> list[str]:
    """"## 호출 계약" — 그래프에서 유도한다 (WP-CT, 수동 계약 카드 퇴역).

    호출 정보를 양쪽에 적게 하던 중복(호출자의 call_agents 포트 + 에이전트의
    수동 계약 카드)을 해소했다 — **호출자가 무엇을 넘기는지는 호출자가 자기
    포트 description에 적는다**(사용자 확정 설계). 에이전트 .md의 호출 계약은
    프로젝트 그래프의 incoming 호출 전이에서 자동 유도되므로, 에이전트 쪽에서
    입력할 것이 없다. 넘겨받는 데이터 자체는 블랙보드 reads 선언이 말한다
    (블랙보드 단락이 그 클래스로 좁혀진다).

    수동 계약 카드는 v2에서 삭제됐다(v1 파일의 카드는 로드 시 드롭) — 같은
    사실의 소스가 둘이면 반드시 어긋난다.
    """
    if project is None:
        return []
    graph = getattr(project, "graph", None)
    if graph is None:
        return []

    entries: list[tuple[str, str, str, str]] = []  # (caller, port, desc, guard)
    for trans in getattr(graph, "transitions", []) or []:
        tgt_ref = getattr(trans.target, "skill_ref", None)
        if tgt_ref is not agent:
            continue
        src_ref = getattr(trans.source, "skill_ref", None)
        caller = getattr(src_ref, "name", None)
        if not caller:
            continue
        port = getattr(getattr(trans, "trigger", None), "name", "") or ""
        desc = ""
        for ev in getattr(src_ref, "call_agents", None) or []:
            if ev.name == port:
                desc = (ev.description or "").strip()
                break
        guard = _describe_guard(getattr(trans, "guard", None))
        entries.append((caller, port, desc, guard))

    if not entries:
        return []
    entries.sort(key=lambda e: (e[0], e[1]))
    blocks: list[str] = [
        "## 호출 계약",
        (
            "이 에이전트는 다음 경로로 호출된다. 넘겨받는 데이터는 공유 상태"
            "(블랙보드) 단락의 읽기 선언을 따른다."
        ),
    ]
    for caller, port, desc, guard in entries:
        line = f"- `{caller}`의 `{port}` 포트에서 호출" if port else f"- `{caller}`에서 호출"
        if guard:
            line += f" [가드: {guard}]"
        if desc:
            line += f" — {desc}"
        blocks.append(line)
    return blocks


def compile_agent(
    agent: AgentDefinition, project=None,
    resolved_hooks: dict[str, HookDef] | None = None,
) -> str:
    """에이전트 → agent .md 텍스트 (LF, BOM 없음, 결정적)."""
    fm_lines = _frontmatter_lines_agent(agent, project)
    # LOCAL 빌드에서만 hooks/mcpServers가 프론트매터로 나간다 (WP-LA)
    fm_lines.extend(_local_settings_frontmatter_lines(agent, project, resolved_hooks))
    blocks: list[str] = [_frontmatter_block(fm_lines)]

    # 본문(body)
    body_block = _body_block(agent.body)
    if body_block is not None:
        blocks.append(body_block)

    # 호출 계약(WP-CT) — 그래프에서 유도. 수동 계약 카드는 퇴역했다.
    blocks.extend(_call_contract_section(agent, project))

    # 호출 파라미터(INVOCATION)
    blocks.extend(_invocation_section_agent(agent))
    # 요구 환경(SETTINGS 언급) — LOCAL 빌드는 프론트매터가 대신하므로 생략된다
    blocks.extend(_settings_note_agent(agent, project))

    # 내부 워크플로 — legacy FSM에 실질 상태가 있을 때만 (WP-AF)
    blocks.extend(_describe_agent_fsm(agent))

    # 출구 — 출력 포트(transfer_on). 호출자 그래프가 이 이름으로 분기한다.
    blocks.extend(_agent_outputs_section(agent))

    if project is not None:
        blocks.extend(_tool_shelf_section(project))
        blocks.extend(_blackboard_section(project, agent))

    return _join_blocks(blocks)


def _describe_agent_fsm(agent: AgentDefinition) -> list[str]:
    """에이전트 내부 FSM 절차 단락 — **legacy 전용** (WP-AF).

    내부 FSM은 퇴역했다 — 절차는 본문 산문이 담고, 결과 분기는 transfer_on
    (출력 포트)이 담는다. 다만 구버전 프로젝트의 내부 FSM에는 실제 설계가
    들어 있으므로, **실질 상태(SimpleState 등)가 하나라도 있으면** 종전처럼
    서술한다. entry/exit 표지뿐인 FSM(신규 기본형)은 서술할 내용이 없으므로
    생략한다 — "1. entry (시작) 2. done (출구)" 같은 무의미한 목록을 막는다.

    출구("## 출구") 단락은 여기가 아니라 `_agent_outputs_section`(transfer_on
    기반)이 담당한다.

    방어 가드: states 비어 있음 / initial_state=None인 불완전 FSM은 생략
    (게이트가 먼저 거부하지만 compile_agent 직접 호출 경로 보호).
    """
    from daedalus.model.fsm.pseudo import EntryPoint as _Entry

    sm = agent.fsm
    if not sm.states or sm.initial_state is None:
        return []
    if not any(
        not isinstance(s, (_Entry, ExitPoint)) for s in sm.states
    ):
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

    return blocks


def _agent_outputs_section(agent: AgentDefinition) -> list[str]:
    """"## 출구" — 출력 포트(transfer_on) 기반 (WP-AF).

    호출자 그래프가 이 이름들로 분기하므로, 에이전트는 종료 시 자신이 어느
    출구로 끝났는지 명시해야 한다. description이 있으면 판정 기준으로 병기.
    """
    events = agent.output_event_defs
    if not events:
        return []
    lines = [
        "## 출구",
        "이 에이전트는 다음 출구 중 하나로 종료한다. 완료 보고의 첫 줄에 어느 "
        "출구인지 명시하라 — 호출자가 이 이름으로 다음 단계를 가른다:",
    ]
    for ev in events:
        desc = (getattr(ev, "description", "") or "").strip()
        lines.append(f"- `{ev.name}`" + (f" — {desc}" if desc else ""))
    return ["\n".join(lines)]
