# daedalus/compiler/emit/agent_sections.py
"""에이전트 산출의 **에이전트 전용 단락 빌더** (WP-6 — `agent.py`에서 이동만).

프론트매터 줄(skills 합류·LOCAL hooks/mcpServers)·호출 계약(종류별)·위임·
요구 환경·내부 워크플로(legacy)·출구를 만드는 함수들이 여기 있다. 조립 순서는
`section_plan.py`, 최종 텍스트 산출은 `emitters.py`가 담당하고, 종전 진입점
`compile_agent`은 `agent.py`가 파사드로 지킨다.

호출 계약은 에이전트 종류마다 다른 단락이다(WP-FK2 C2): 워크플로 에이전트
(`AgentDefinition`)는 프로젝트 그래프의 도착 전이에서 유도하고
(`_call_contract_section`), fork 에이전트(`ForkAgent`)는 자기를 실행 기반으로 쓰는
fork 스킬 목록만 낸다(`_fork_base_contract_section`). 그래프 유도 단락은 절 표에서
워크플로 에이전트에만 걸린다 — fork 에이전트에는 fsm도 포트도 배치도 없어
무조건 부르면 AttributeError로 죽는다.

**왜 갈랐는가(임포트 방향).** `skill_sections.py`와 같은 이유다 —
`compile_agent`이 emitter 파사드가 되면 `agent.py`가 `emitters.py` 위로
올라가는데, 절 provider 표는 이 빌더들을 아래에서 임포트해야 한다.
"""
from __future__ import annotations


from functools import singledispatch
from typing import Any

from daedalus.compiler.emit.common import (
    _MISSING,
    _build_target,
    _config_default,
    _is_local_build,
    delegate_to_phrase,
    delegation_target_name,
)
from daedalus.compiler.emit.frontmatter import (
    _compose_description,
    _format_kv,
    _yaml_block_lines,
    _yaml_scalar,
)
from daedalus.compiler.emit.sections import (  # noqa: F401 — _exits_section 재-export
    _exits_section,
    _describe_access,
    _describe_guard,
    _describe_node_action,
    _mcp_servers_from_tools,
    _ordered_states,
    _transition_condition,
    _unguarded_is_else,
)
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import CompositeState, SimpleState, State
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.roles import PlacementRole
from daedalus.model.plugin.enums import (
    AgentField,
    FieldEmit,
    FieldVisibility,
    ModelType,
)
from daedalus.model.plugin.field_matrix import FieldRule, matrix_for
from daedalus.model.plugin.hook import HookDef



def _frontmatter_lines_agent(agent: AgentDefinition, project=None) -> list[str]:
    """에이전트 프론트매터 줄 목록 (emit==FRONTMATTER 만).

    마켓플레이스 빌드에서는 CC가 무시하는 필드(`permissionMode` 등)를 아예 내지
    않는다 — 값이 파일에 남아 있으면 걸린 줄 알지만 실제로는 아무 일도 일어나지
    않기 때문이다(WP-EL). 판정의 단일 진실은 `agent_field_supported`.
    """
    from daedalus.model.plugin.field_matrix import agent_field_supported

    build_target = _build_target(project)
    config = agent.config
    # 스킬 쪽과 같은 규약: **매트릭스 부재 = 비적용**. fork 에이전트 표에는
    # background·isolation 행이 없다(맨 첨자면 KeyError로 컴파일이 죽는다).
    matrix = matrix_for(agent)
    lines: list[str] = []
    for afield in AgentField:
        rule = matrix.get(afield)
        if rule is None:
            continue
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
    auto: list[str] = []
    if project is not None:
        # 1. 배경 지식 스킬 = **어디에도 놓이지 않는 종류**(선언형). 캔버스에
        #    놓이는 종류는 그래프가 언제 쓸지 말하지만, 놓이지 않는 스킬은
        #    모델이 알아서 집어 쓰는 지식이라 서브에이전트에 통째로 실어 준다.
        for skill in getattr(project, "skills", []) or []:
            if type(skill).PLACEMENT is PlacementRole.NONE:
                auto.append(skill.name)
        # placement 노드 이름 집합 — 참조 링크(connected_states)는 노드 이름을 가리킨다
        node_names = {
            s.name
            for s in getattr(getattr(project, "graph", None), "states", []) or []
            if getattr(s, "skill_ref", None) is agent
        }
        if node_names:
            # 2. 참조 노드로 **선언된** 스킬(참조 스킬).
            ref_names = {
                s.name for s in project.skills
                if type(s).PLACEMENT is PlacementRole.REFERENCE
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

    **`HookDef.enabled`를 보지 않는 것이 의도다**(사용자 확정 2026-09-07):
    그 스위치는 "플러그인 전역 훅으로 켤지"이고, 여기는 그 에이전트 안에서만
    도는 별개 경로다 — 전역으로는 끄고 특정 에이전트에서만 쓰는 것이 정상적인
    사용이다. 그러므로 `emitted_hooks`로 바꾸지 마라(스크립트 파일 쪽은
    `hooks_needing_scripts`가 이 경로까지 포함해 함께 낸다).
    """
    # 실체는 스킬 프론트매터와 공용이다(2026-09-13) — 같은 모양을 두 벌 만들지 않는다.
    from daedalus.compiler.emit.hooks import component_hook_groups

    return component_hook_groups(agent, project, resolved_hooks)


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
    "## Requirements" 단락을 또 만들지 않는다.

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
        needs.append(f"lifecycle hooks: {names} (emitted to hooks/hooks.json)")
    mcp_all = _agent_mcp_server_names(agent)
    if mcp_all:
        names = ", ".join(mcp_all)
        needs.append(f"MCP servers connected: {names} (`.mcp.json`)")
    if not needs:
        return []
    blocks = [
        "## Requirements",
        "This agent assumes the following is already set up outside the plugin:",
        "\n".join(f"- {n}" for n in needs),
    ]
    return blocks


def _fork_base_contract_section(agent, project) -> list[str]:
    """fork 에이전트의 "## Invocation Contract" — fork 스킬 실행 기반 줄만.

    fork 에이전트는 캔버스에 놓이지 않으므로 도착 전이가 없다(그래프 유도 항목이
    구조적으로 0건이다). 그 대신 **누가 자기를 실행 기반으로 쓰는지**를 말한다 —
    fork 스킬 본문이 작업 지시로 오고 이 파일은 시스템 프롬프트가 된다(실측
    2026-09-13). 캔버스에 선이 없으니 여기서 말하지 않으면 이 에이전트를 고치는
    사람이 그 쓰임을 모른다.

    어떤 fork 스킬도 가리키지 않으면 단락 생략 — 그 상태는 검증 경고
    `unused_fork_agent`가 따로 짚는다(산출은 침묵한다).
    """
    if project is None:
        return []
    from daedalus.compiler.emit.fork import fork_skills_using

    lines = [
        f"- Execution base of fork skill `{name}` — that skill's instructions "
        f"arrive as your task; this file sets your role and limits."
        for name in fork_skills_using(agent, project)
    ]
    if not lines:
        return []
    # 목록은 한 블록으로 낸다 — 블록을 나누면 `_join_blocks`가 항목 사이에 빈
    # 줄을 넣어 다른 단락("## Exits"·"## Next Steps")과 생김새가 어긋난다.
    return ["\n".join([
        "## Invocation Contract",
        (
            "This agent is invoked through the paths below. If this file has a "
            "Shared State (Blackboard) section, what it declares as reads is "
            "what you receive; otherwise the task text is all you get."
        ),
        *lines,
    ])]


def _call_contract_section(agent: AgentDefinition, project) -> list[str]:
    """"## Invocation Contract" — 그래프에서 유도한다 (WP-CT, 수동 계약 카드 퇴역).

    호출 정보를 양쪽에 적게 하던 중복(호출자의 call_agents 포트 + 에이전트의
    수동 계약 카드)을 해소했다 — **호출자가 무엇을 넘기는지는 호출자가 자기
    포트 description에 적는다**(사용자 확정 설계). 에이전트 .md의 호출 계약은
    프로젝트 그래프의 incoming 호출 전이에서 자동 유도되므로, 에이전트 쪽에서
    입력할 것이 없다. 넘겨받는 데이터 자체는 블랙보드 reads 선언이 말한다
    (블랙보드 단락이 그 클래스로 좁혀진다).

    수동 계약 카드는 v2에서 삭제됐다(v1 파일의 카드는 로드 시 드롭) — 같은
    사실의 소스가 둘이면 반드시 어긋난다.

    **워크플로 에이전트 전용이다.** fork 실행 기반 줄은 여기서 나오지 않는다 —
    워크플로 에이전트는 fork 에이전트가 될 수 없고(`fork_agent_wrong_kind`),
    fork 에이전트 쪽은 `_fork_base_contract_section`이 담당한다(WP-FK2 C2).
    """
    if project is None:
        return []
    graph = getattr(project, "graph", None)

    # (caller, port, desc, guard, transfer, transfer_desc) — transfer는 호출
    # 전이에 붙은 TransferSkill(A11). 호출자가 위임 **전에** 그 지침을 수행하므로,
    # 에이전트는 그 산출물을 전제로 일을 시작한다.
    #
    # **이 단락이 에이전트에게 유일한 채널이다**(A11-2, 사용자 실증): "## Entry
    # Context"는 배치된 Procedural/Declarative 스킬 전용이라(WP-IC) 에이전트
    # 도착에는 아예 없다. 스킬 도착은 진입 맥락이 transfer를 말해 주지만
    # 에이전트는 여기서 말하지 않으면 자기가 받는 입력의 전처리 상태를 영영
    # 알 수 없다 — 호출자에게서 바로 받은 것처럼 서술된다.
    entries: list[tuple[str, str, str, str, str, str]] = []
    for trans in getattr(graph, "transitions", None) or []:
        tgt_ref = getattr(trans.target, "skill_ref", None)
        if tgt_ref is not agent:
            continue
        src_ref = getattr(trans.source, "skill_ref", None)
        caller = getattr(src_ref, "name", None)
        if not caller:
            continue
        port = getattr(getattr(trans, "trigger", None), "name", "") or ""
        desc = ""
        for ev in src_ref.call_ports():
            if ev.name == port:
                desc = (ev.description or "").strip()
                break
        guard = _describe_guard(getattr(trans, "guard", None))
        transfer_ref = getattr(trans, "skill_ref", None)
        transfer = getattr(transfer_ref, "name", "") or ""
        transfer_desc = (getattr(transfer_ref, "description", "") or "").strip()
        entries.append((caller, port, desc, guard, transfer, transfer_desc))

    if not entries:
        return []
    entries.sort(key=lambda e: (e[0], e[1]))
    # 항목은 한 블록으로 모은다 — 블록마다 나누면 `_join_blocks`가 빈 줄을 넣어
    # 다른 목록 단락("## Exits"·"## Delegation")과 생김새가 어긋난다.
    lines: list[str] = [
        "## Invocation Contract",
        (
            "This agent is invoked through the paths below. If this file has a "
            "Shared State (Blackboard) section, what it declares as reads is "
            "what you receive; otherwise the task text is all you get."
        ),
    ]
    for caller, port, desc, guard, transfer, transfer_desc in entries:
        line = (
            f"- from `{caller}` via port `{port}`" if port else f"- from `{caller}`"
        )
        if guard:
            line += f" [guard: {guard}]"
        if desc:
            line += f" — {desc}"
        if transfer:
            shown = f"`{transfer}` ({transfer_desc})" if transfer_desc else f"`{transfer}`"
            # 포트 description이 문장부호 없이 끝나면 두 문장이 붙어 버린다 —
            # `_compose_description`과 같은 관례로 마침표를 보충한다.
            if line and line[-1] not in ".!?":
                line += "."
            # 이름만으로는 무엇이 전처리됐는지 알 수 없다 — 설명과 "그 산출물을
            # 전제로 작업하라"까지 함께 말한다.
            line += (
                f" The caller follows transition skill {shown} before delegating — "
                f"work from what that step produced."
            )
        lines.append(line)
    return ["\n".join(lines)]


def _agent_delegation_section(agent: AgentDefinition, project=None) -> list[str]:
    """"## Delegation" — 이 에이전트가 호출 포트로 부르는 다른 에이전트 (2026-09-12).

    스킬의 "## Next Steps"에 해당하는 것을 에이전트 쪽에 두는 단락이다. 호출은
    **동기**다 — 부른 에이전트의 보고를 받아 이 에이전트가 자기 출구를 고른다.
    중간 결과는 메인 컨텍스트에 올라가지 않으므로 진행 기록은 건드리지 않는다
    (그건 메인 스레드에서 도는 스킬 소유다).

    포트 이름순 정렬 — 결정적. 호출 전이가 없으면 단락 생략.
    """
    if project is None:
        return []
    graph = getattr(project, "graph", None)
    if graph is None:
        return []
    port_desc = {e.name: (e.description or "").strip() for e in agent.call_agents}
    # (port, 정렬키, desc, guard, 위임 지시 문구)
    entries: list[tuple[str, str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for trans in getattr(graph, "transitions", []) or []:
        if getattr(trans.source, "skill_ref", None) is not agent:
            continue
        callee = getattr(trans.target, "skill_ref", None)
        # 위임 대상 선언이 답한다(Q9) — 종류를 열거하지 않는다.
        if callee is None or not callee.DELEGATION_TARGET:
            continue
        port = getattr(getattr(trans, "trigger", None), "name", "") or ""
        if (port, callee.name) in seen:
            continue
        seen.add((port, callee.name))
        entries.append((
            port,
            # 정렬은 부르는 이름으로 — 이름이 없는(깨진 source) 대상만 노드
            # 이름으로 자리를 잡는다. 지시 문구가 정렬을 바꾸면 안 된다.
            delegation_target_name(callee) or callee.name,
            port_desc.get(port, ""),
            _describe_guard(getattr(trans, "guard", None)),
            # 부르는 이름·외부 에이전트 단서는 **대상이 정한다**(WP-9).
            delegate_to_phrase(callee),
        ))
    if not entries:
        return []
    entries.sort(key=lambda e: (e[0], e[1]))
    lines = [
        "## Delegation",
        (
            "Parts of this task are delegated to the agents below. Spawn one with "
            "the Agent tool, pass it the context it needs, and wait for its report — "
            "you own what it produced and you choose this agent's exit from it. The "
            "caller of this agent never sees those reports, so summarize what "
            "matters in your own final report."
        ),
    ]
    for port, _sort_name, desc, guard, phrase in entries:
        line = f"- `{port}` → {phrase}" if port else f"- {phrase}"
        if guard:
            line += f" [guard: {guard}]"
        if desc:
            line += f" — {desc}"
        lines.append(line)
    return ["\n".join(lines)]



@singledispatch
def _describe_legacy_step(state: State) -> str:
    """legacy 에이전트 내부 FSM의 상태 한 줄 **꼬리 문구** (WP-11).

    스킬 산출의 `sections._describe_step`과 **일부러 다르다** — 여기에는
    Parallel/Choice/Terminate 분기가 없고 CompositeState 문구에
    "(runs in its own context)"가 붙지 않는다. 합치면 구버전 프로젝트의
    에이전트 산출 바이트가 바뀐다(REFACTOR_SPEC §0-a — 합치지 않는다).
    """
    return "."


@_describe_legacy_step.register(SimpleState)
def _(state: SimpleState) -> str:
    action = _describe_node_action(state)
    return f": {action}." if action else "."


@_describe_legacy_step.register(CompositeState)
def _(state: CompositeState) -> str:
    return f": delegate to agent `{state.name}`."


@singledispatch
def _legacy_extra_marks(state: State) -> list[str]:
    """start/end 표지 뒤에 덧붙는 종류별 표지. 폴백은 없음."""
    return []


@_legacy_extra_marks.register(ExitPoint)
def _(state: ExitPoint) -> list[str]:
    return ["exit"]


@singledispatch
def _is_substantive_state(state: State) -> bool:
    """실질 상태인가 — 표지(entry/exit)만 든 FSM은 서술할 내용이 없다.

    폴백 True가 옳다: 새 상태 종류는 기본적으로 "서술할 것이 있는" 쪽이다.
    """
    return True


@_is_substantive_state.register(EntryPoint)
@_is_substantive_state.register(ExitPoint)
def _(state: State) -> bool:
    return False


def _describe_agent_fsm(agent: AgentDefinition) -> list[str]:
    """에이전트 내부 FSM 절차 단락 — **legacy 전용** (WP-AF).

    내부 FSM은 퇴역했다 — 절차는 본문 산문이 담고, 결과 분기는 transfer_on
    (출력 포트)이 담는다. 다만 구버전 프로젝트의 내부 FSM에는 실제 설계가
    들어 있으므로, **실질 상태(SimpleState 등)가 하나라도 있으면** 종전처럼
    서술한다. entry/exit 표지뿐인 FSM(신규 기본형)은 서술할 내용이 없으므로
    생략한다 — "1. entry (시작) 2. done (출구)" 같은 무의미한 목록을 막는다.

    출구("## Exits") 단락은 여기가 아니라 `_agent_outputs_section`(transfer_on
    기반)이 담당한다.

    방어 가드: states 비어 있음 / initial_state=None인 불완전 FSM은 생략
    (게이트가 먼저 거부하지만 compile_agent 직접 호출 경로 보호).
    """
    sm = agent.fsm
    if not sm.states or sm.initial_state is None:
        return []
    if not any(_is_substantive_state(s) for s in sm.states):
        return []
    blocks: list[str] = ["## Internal Workflow"]
    blocks.append(
        f"Work through the steps below in order, starting at "
        f"`{sm.initial_state.name}`."
    )
    states = _ordered_states(sm)
    final_ids = {id(s) for s in sm.final_states}
    lines: list[str] = []
    for idx, state in enumerate(states, start=1):
        marks: list[str] = []
        if state is sm.initial_state:
            marks.append("start")
        if id(state) in final_ids:
            marks.append("end")
        marks.extend(_legacy_extra_marks(state))
        mark_str = f" ({', '.join(marks)})" if marks else ""
        head = f"{idx}. **{state.name}**{mark_str}"
        head += _describe_legacy_step(state)
        head += _describe_access(state)
        lines.append(head)
        is_choice = _unguarded_is_else(state)
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
    """"## Exits" — 출력 포트(transfer_on) 기반 (WP-AF).

    호출자 그래프가 이 이름들로 분기하므로, 에이전트는 종료 시 자신이 어느
    출구로 끝났는지 명시해야 한다. description이 있으면 판정 기준으로 병기.
    """
    return _exits_section(agent.output_ports())
