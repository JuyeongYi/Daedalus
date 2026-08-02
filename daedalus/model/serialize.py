# daedalus/model/serialize.py
"""프로젝트 모델 ↔ JSON 호환 dict 직렬화 계층 (순수 모델 — Qt 무관).

원칙
----
- **소유 객체는 인라인, 참조는 ID 문자열로 평탄화한다.**
  - 참조 필드: ``Transition.source/target`` (state id), ``SimpleState.skill_ref``
    (component id), ``Transition.skill_ref`` (transfer skill id),
    ``StateMachine.initial_state/final_states`` (state id),
    ``Delegation`` 의 ``agent_ref`` (agent id) 등.
- 다형성은 각 클래스의 ``kind`` property를 태그로 재사용한다. State 계열은
  kind property가 있으므로 그대로 사용한다.
- enum 은 ``.value`` 로 직렬화하고 역직렬화 시 enum 타입으로 복원한다.
- ``Blackboard.parent`` 는 ID 가 아니라 **소유 구조로 재연결**한다
  (sub_machine 역직렬화 시 부모 blackboard 를 구조적으로 다시 연결).

역직렬화는 2-pass 다:
  1. 객체 생성 + id→객체 레지스트리 구축
  2. 참조 해소 (state/skill/agent id → 실제 객체)

dangling id 는 ValueError 가 아니라 None 처리하고 경고를 수집한다.
"""
from __future__ import annotations

from typing import Any

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.blackboard import (
    Blackboard,
    CollectionType,
    DynamicClass,
    DynamicField,
)
from daedalus.model.fsm.event import (
    BlackboardTrigger,
    CompletionEvent,
    Event,
)
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import (
    ChoiceState,
    EntryPoint,
    ExitPoint,
    TerminateState,
)
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    Region,
    SimpleState,
    State,
)
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ExpressionEvaluation,
    LLMEvaluation,
    LLMExecution,
    MCPEvaluation,
    MCPExecution,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.transition import Transition, TransitionType
from daedalus.model.fsm.variable import (
    ConflictResolution,
    FieldType,
    Variable,
    VariableScope,
)
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import (
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DispatchMode,
    DynamicWorkflowDef,
    PhaseSpec,
    TeamSpawnDef,
    TeammateSpec,
    WaitMode,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillShell,
)
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.plugin.tool import (
    BuiltinTool,
    MCPTool,
    Tool,
    UserDefinedTool,
)
from daedalus.model.project import (
    PluginProject,
    ReferencePlacement,
    _make_project_graph,
)

FORMAT_VERSION = 1


# ───────────────────────── enum 헬퍼 ─────────────────────────

def _enum_val(e: Any) -> Any:
    """enum 이면 .value, 아니면 그대로 (model: ModelType | str 처럼 union 대응)."""
    return e.value if hasattr(e, "value") and not isinstance(e, str) else e


def _enum_opt(e: Any) -> Any:
    return None if e is None else _enum_val(e)


# ═══════════════════════ 직렬화 (serialize) ═══════════════════════


def serialize_project(project: PluginProject) -> dict:
    """PluginProject → JSON 호환 dict."""
    return {
        "format": FORMAT_VERSION,
        "name": project.name,
        "description": project.description,
        "version": project.version,
        "skills": [_ser_skill(s) for s in project.skills],
        "agents": [_ser_agent(a) for a in project.agents],
        "reference_placements": [
            _ser_ref_placement(r) for r in project.reference_placements
        ],
        "delegations": [_ser_delegation(d) for d in project.delegations],
        "tool_shelf": [_ser_tool(t) for t in project.tool_shelf],
        "hook_library": [_ser_hook(h) for h in project.hook_library],
        "blackboard": _ser_blackboard(project.blackboard),
        # 프로젝트 워크플로 그래프 — 노드/전이를 정식 FSM으로 왕복 (버그 1 수정).
        # skill_ref는 _ser_machine이 component id로 평탄화 → 역직렬화 2-pass가 해소.
        "graph": _ser_machine(project.graph),
        "graph_layout": {k: list(v) for k, v in project.graph_layout.items()},
    }


# ── hook library ──

def _ser_hook(h: HookDef) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "description": h.description,
        "event": h.event.value,
        "matcher": h.matcher,
        "command": h.command,
        "timeout": h.timeout,
    }


def _deser_hook(d: dict) -> HookDef:
    return HookDef(
        name=d.get("name", ""),
        description=d.get("description", ""),
        event=_to_enum(HookEvent, d.get("event"), HookEvent.PRE_TOOL_USE),
        matcher=d.get("matcher", ""),
        command=d.get("command", ""),
        timeout=d.get("timeout"),
        id=d.get("id") or _new_id(),
    )


# ── tool shelf ──

# 직렬화가 인지하는 Tool kind 전체 — 새 Tool 서브클래스 추가 시 여기와
# _ser_tool/_deser_tool 분기를 함께 갱신해야 한다 (미등록 시 명시 에러).
_KNOWN_TOOL_KINDS = {"builtin", "mcp", "user"}


def _ser_tool(t: Tool) -> dict:
    d: dict[str, Any] = {
        "kind": t.kind,
        "id": t.id,
        "name": t.name,
        "description": t.description,
    }
    if t.kind not in _KNOWN_TOOL_KINDS:
        raise TypeError(
            f"직렬화 미지원 Tool kind: {t.kind!r} ({type(t).__name__}) — "
            "serialize.py의 _KNOWN_TOOL_KINDS/_ser_tool/_deser_tool에 분기를 추가하라"
        )
    if isinstance(t, BuiltinTool):
        d["allowed_arguments_note"] = t.allowed_arguments_note
    elif isinstance(t, MCPTool):
        d.update(server=t.server, tool_name=t.tool_name)
    elif isinstance(t, UserDefinedTool):
        d.update(body=t.body, shell=t.shell.value)
    return d


def _deser_tool(d: dict) -> Tool:
    kind = d.get("kind")
    name = d.get("name", "")
    desc = d.get("description", "")
    tid = d.get("id") or _new_id()
    tool: Tool
    if kind == "builtin":
        tool = BuiltinTool(
            name=name, description=desc, id=tid,
            allowed_arguments_note=d.get("allowed_arguments_note", ""),
        )
    elif kind == "mcp":
        tool = MCPTool(
            name=name, description=desc, id=tid,
            server=d.get("server", ""), tool_name=d.get("tool_name", ""),
        )
    elif kind == "user":
        tool = UserDefinedTool(
            name=name, description=desc, id=tid,
            body=d.get("body", ""),
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    else:
        # 조용한 강등은 데이터 손실을 은폐한다 — 명시 실패 (State 패턴과 동일).
        raise ValueError(f"역직렬화 미지원 Tool kind: {kind!r}")
    return tool


# ── 변수 / 액션 / 전략 / 이벤트 / 가드 ──

def _ser_variable(v: Variable) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "description": v.description,
        "scope": v.scope.value,
        "field_type": v.field_type.value,
        "required": v.required,
        "default": v.default,
        "conflict_resolution": v.conflict_resolution.value,
    }


def _ser_eval(s: EvaluationStrategy) -> dict:
    d: dict[str, Any] = {"kind": s.kind}
    if isinstance(s, LLMEvaluation):
        d["prompt"] = s.prompt
    elif isinstance(s, ToolEvaluation):
        d.update(tool=s.tool, command=s.command, success_condition=s.success_condition)
    elif isinstance(s, MCPEvaluation):
        d.update(
            server=s.server, tool=s.tool, arguments=dict(s.arguments),
            success_condition=s.success_condition,
        )
    elif isinstance(s, ExpressionEvaluation):
        d["expression"] = s.expression
    elif isinstance(s, CompositeEvaluation):
        d["operator"] = s.operator
        d["children"] = [_ser_eval(c) for c in s.children]
    return d


def _ser_exec(s: ExecutionStrategy) -> dict:
    d: dict[str, Any] = {"kind": s.kind}
    if isinstance(s, LLMExecution):
        d["prompt"] = s.prompt
    elif isinstance(s, ToolExecution):
        d.update(tool=s.tool, command=s.command)
    elif isinstance(s, MCPExecution):
        d.update(server=s.server, tool=s.tool, arguments=dict(s.arguments))
    elif isinstance(s, CompositeExecution):
        d["mode"] = s.mode
        d["children"] = [_ser_exec(c) for c in s.children]
    return d


def _ser_action(a: Action) -> dict:
    return {
        "name": a.name,
        "execution": _ser_exec(a.execution),
        "output_variable": _ser_variable(a.output_variable) if a.output_variable else None,
    }


def _ser_actions(lst: list[Action]) -> list[dict]:
    return [_ser_action(a) for a in lst]


def _ser_guard(g: Guard | None) -> dict | None:
    if g is None:
        return None
    return {"evaluation": _ser_eval(g.evaluation)}


def _ser_event(e: Event | None) -> dict | None:
    if e is None:
        return None
    d: dict[str, Any] = {"kind": e.kind, "name": e.name}
    if isinstance(e, BlackboardTrigger):
        d["variable"] = e.variable
        d["condition"] = _ser_eval(e.condition) if e.condition else None
    return d


# ── blackboard ──

def _ser_dynamic_field(f: DynamicField) -> dict:
    return {
        "name": f.name,
        "field_type": f.field_type.value,
        "collection": f.collection.value,
        "default": f.default,
        "required": f.required,
    }


def _ser_dynamic_class(c: DynamicClass) -> dict:
    return {
        "name": c.name,
        "description": c.description,
        "fields": [_ser_dynamic_field(f) for f in c.fields],
    }


def _ser_blackboard(bb: Blackboard) -> dict:
    """parent 는 소유 구조로 재연결하므로 직렬화하지 않는다."""
    return {
        "class_definitions": [_ser_dynamic_class(c) for c in bb.class_definitions],
        "variables": {k: _ser_variable(v) for k, v in bb.variables.items()},
    }


# ── 상태 / 전이 / 머신 ──

def _ser_state_common(s: State) -> dict:
    return {
        "kind": s.kind,
        "id": s.id,
        "name": s.name,
        "on_entry_start": _ser_actions(s.on_entry_start),
        "on_entry": _ser_actions(s.on_entry),
        "on_entry_end": _ser_actions(s.on_entry_end),
        "on_exit_start": _ser_actions(s.on_exit_start),
        "on_exit": _ser_actions(s.on_exit),
        "on_exit_end": _ser_actions(s.on_exit_end),
        "on_active": _ser_actions(s.on_active),
        "custom_events": {k: _ser_actions(v) for k, v in s.custom_events.items()},
        "inputs": [_ser_variable(v) for v in s.inputs],
        "outputs": [_ser_variable(v) for v in s.outputs],
    }


# 직렬화가 인지하는 State kind 전체 — 새 State 서브클래스 추가 시 여기와
# _ser_state/_deser_state 분기를 함께 갱신해야 한다 (미등록 시 명시 에러).
_KNOWN_STATE_KINDS = {
    "simple", "composite", "parallel",
    "choice", "terminate", "entry_point", "exit_point",
}


def _ser_state(s: State) -> dict:
    d = _ser_state_common(s)
    if d["kind"] not in _KNOWN_STATE_KINDS:
        raise TypeError(
            f"직렬화 미지원 State kind: {d['kind']!r} ({type(s).__name__}) — "
            "serialize.py의 _KNOWN_STATE_KINDS/_ser_state/_deser_state에 분기를 추가하라"
        )
    if isinstance(s, SimpleState):
        # skill_ref 는 component id 참조로 평탄화
        d["skill_ref"] = s.skill_ref.id if s.skill_ref is not None else None
    elif isinstance(s, CompositeState):
        d["sub_machine"] = _ser_machine(s.sub_machine)
    elif isinstance(s, ParallelState):
        d["regions"] = [_ser_region(r) for r in s.regions]
        d["join"] = s.join.value
        d["join_count"] = s.join_count
    elif isinstance(s, ExitPoint):
        d["color"] = s.color
    return d


def _ser_region(r: Region) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "sub_machine": _ser_machine(r.sub_machine),
    }


def _ser_transition(t: Transition) -> dict:
    return {
        "id": t.id,
        "source": t.source.id,
        "target": t.target.id,
        "type": t.type.value,
        "trigger": _ser_event(t.trigger),
        "guard": _ser_guard(t.guard),
        "on_guard_check": _ser_actions(t.on_guard_check),
        "on_traverse_start": _ser_actions(t.on_traverse_start),
        "on_traverse": _ser_actions(t.on_traverse),
        "on_traverse_end": _ser_actions(t.on_traverse_end),
        "custom_events": {k: _ser_actions(v) for k, v in t.custom_events.items()},
        "data_map": dict(t.data_map),
        # transfer skill 참조 — id (없으면 None)
        "skill_ref": t.skill_ref.id if t.skill_ref is not None else None,
    }


def _ser_machine(m: StateMachine) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "states": [_ser_state(s) for s in m.states],
        "transitions": [_ser_transition(t) for t in m.transitions],
        "initial_state": m.initial_state.id if m.initial_state is not None else None,
        "final_states": [s.id for s in m.final_states],
        "blackboard": _ser_blackboard(m.blackboard),
    }


# ── section / eventdef ──

def _ser_section(s: Section) -> dict:
    return {
        "title": s.title,
        "content": s.content,
        "children": [_ser_section(c) for c in s.children],
    }


def _ser_eventdef(e: EventDef) -> dict:
    return {"name": e.name, "color": e.color, "description": e.description}


# ── config / policy ──

def _ser_config(c: Any) -> dict:
    """ComponentConfig 계열 — kind 태그 + 모든 필드."""
    d: dict[str, Any] = {
        "kind": c.kind,
        "model": _enum_val(c.model),
        "effort": _enum_opt(c.effort),
        "hooks": c.hooks,
    }
    # SkillConfig 공통
    if hasattr(c, "argument_hint"):
        d["argument_hint"] = c.argument_hint
        d["allowed_tools"] = list(c.allowed_tools)
        d["paths"] = c.paths
    if isinstance(c, ProceduralSkillConfig):
        d.update(
            disable_model_invocation=c.disable_model_invocation,
            user_invocable=c.user_invocable,
            context=c.context.value,
            agent=c.agent,
            shell=c.shell.value,
        )
    elif isinstance(c, DeclarativeSkillConfig):
        d.update(
            disable_model_invocation=c.disable_model_invocation,
            user_invocable=c.user_invocable,
        )
    elif isinstance(c, TransferSkillConfig):
        d.update(
            disable_model_invocation=c.disable_model_invocation,
            user_invocable=c.user_invocable,
            context=c.context.value,
            shell=c.shell.value,
        )
    elif isinstance(c, ReferenceSkillConfig):
        d["user_invocable"] = c.user_invocable
    elif isinstance(c, AgentConfig):
        d.update(
            tools=c.tools,
            disallowed_tools=c.disallowed_tools,
            permission_mode=c.permission_mode.value,
            max_turns=c.max_turns,
            skills=list(c.skills),
            mcp_servers=c.mcp_servers,
            memory=_enum_opt(c.memory),
            background=c.background,
            isolation=c.isolation.value,
            color=_enum_opt(c.color),
        )
    return d


def _ser_policy(p: ExecutionPolicy) -> dict:
    return {
        "mode": p.mode,
        "count": p.count,
        "join": p.join.value,
        "join_count": p.join_count,
    }


# ── skill / agent ──

def _ser_skill(s: Any) -> dict:
    d: dict[str, Any] = {
        "kind": s.kind,
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "when_to_use": s.when_to_use,
        "sections": [_ser_section(sec) for sec in s.sections],
        "config": _ser_config(s.config),
    }
    if isinstance(s, (ProceduralSkill, TransferSkill)):
        d["fsm"] = _ser_machine(s.fsm)
    if isinstance(s, ProceduralSkill):
        d["transfer_on"] = [_ser_eventdef(e) for e in s.transfer_on]
        d["call_agents"] = [_ser_eventdef(e) for e in s.call_agents]
    return d


def _ser_agent(a: AgentDefinition) -> dict:
    return {
        "kind": a.kind,
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "fsm": _ser_machine(a.fsm),
        "config": _ser_config(a.config),
        "execution_policy": _ser_policy(a.execution_policy),
        "sections": [_ser_section(s) for s in a.sections],
        # 로컬 스킬 — 소유 인라인
        "skills": [_ser_skill(s) for s in a.skills],
        "reference_placements": [
            _ser_ref_placement(r) for r in a.reference_placements
        ],
        "caller_contracts": [_ser_section(s) for s in a.caller_contracts],
        "graph_layout": {k: list(v) for k, v in a.graph_layout.items()},
    }


def _ser_ref_placement(r: ReferencePlacement) -> dict:
    return {
        "skill_name": r.skill_name,
        "x": r.x,
        "y": r.y,
        "connected_states": list(r.connected_states),
    }


def _ser_delegation(d: Any) -> dict:
    out: dict[str, Any] = {
        "kind": d.kind,
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "wait_mode": d.wait_mode.value,
        "composition": d.composition.value,
        "guidance": d.guidance,
    }
    if isinstance(d, TeamSpawnDef):
        out["teammates"] = [
            {
                "agent_ref": tm.agent_ref.id if tm.agent_ref is not None else None,
                "count": tm.count,
                "role_note": tm.role_note,
            }
            for tm in d.teammates
        ]
    elif isinstance(d, DynamicWorkflowDef):
        out["objective"] = d.objective
        out["phases"] = [
            {
                "title": p.title,
                "detail": p.detail,
                "agent_ref": p.agent_ref.id if p.agent_ref is not None else None,
            }
            for p in d.phases
        ]
    elif isinstance(d, AgoraDispatchDef):
        out.update(
            mode=d.mode.value,
            target=d.target,
            msgtype=d.msgtype,
            payload_note=d.payload_note,
        )
    return out


# ═══════════════════════ 역직렬화 (deserialize) ═══════════════════════


class _Registry:
    """2-pass 역직렬화 컨텍스트.

    id→객체 매핑(states/components)과 미해소 참조 콜백을 모은다.
    경고는 ``warnings`` 리스트에 수집(dangling id).
    """

    def __init__(self) -> None:
        self.states: dict[str, State] = {}
        self.components: dict[str, Any] = {}  # skill/agent id → 객체
        self._pending: list[Any] = []  # 2-pass 참조 해소 콜백
        self.warnings: list[str] = []

    def add_pending(self, fn: Any) -> None:
        self._pending.append(fn)

    def resolve_state(self, sid: str | None) -> State | None:
        if sid is None:
            return None
        st = self.states.get(sid)
        if st is None:
            self.warnings.append(f"dangling state id: {sid}")
        return st

    def resolve_component(self, cid: str | None) -> Any:
        if cid is None:
            return None
        c = self.components.get(cid)
        if c is None:
            self.warnings.append(f"dangling component id: {cid}")
        return c

    def run_pending(self) -> None:
        for fn in self._pending:
            fn()


def deserialize_project(
    data: dict,
    *,
    collect_warnings: list[str] | None = None,
) -> PluginProject:
    """JSON 호환 dict → PluginProject. 2-pass 참조 해소.

    collect_warnings: 호출자가 리스트를 주면 역직렬화 중 발생한 dangling id
      경고 문자열을 해당 리스트에 채워준다. None이면 경고를 버린다(기존 동작).
      반환 타입은 항상 PluginProject — 변경 없음.
    """
    fmt = data.get("format")
    if fmt != FORMAT_VERSION:
        raise ValueError(
            f"지원하지 않는 파일 형식 버전: {fmt!r} (지원: {FORMAT_VERSION})"
        )
    reg = _Registry()

    # ── pass 1: 컴포넌트(skill/agent) 객체 생성 + 등록 ──
    skills = [_deser_skill(s, reg) for s in data.get("skills", [])]
    agents = [_deser_agent(a, reg) for a in data.get("agents", [])]

    blackboard = _deser_blackboard(data.get("blackboard"), parent=None)

    # 프로젝트 그래프 — 노드/전이를 정식 FSM으로 복원. skill_ref(component id)는
    # 이미 pass1에서 등록된 skills/agents를 가리키며 pass2 pending이 해소한다.
    # 하위 호환: "graph" 키 부재(구버전 파일) → default와 동일한 빈 그래프 생성.
    graph_data = data.get("graph")
    if graph_data is not None:
        graph = _deser_machine(graph_data, reg, parent_bb=blackboard)
    else:
        graph = _make_project_graph()

    project = PluginProject(
        name=data.get("name", ""),
        description=data.get("description", ""),
        version=data.get("version", "0.1.0"),
        skills=skills,
        agents=agents,
        reference_placements=[
            _deser_ref_placement(r) for r in data.get("reference_placements", [])
        ],
        delegations=[_deser_delegation(d, reg) for d in data.get("delegations", [])],
        tool_shelf=[_deser_tool(t) for t in data.get("tool_shelf", [])],
        hook_library=[_deser_hook(h) for h in data.get("hook_library", [])],
        blackboard=blackboard,
        graph=graph,
        graph_layout={k: list(v) for k, v in data.get("graph_layout", {}).items()},
    )

    # ── pass 2: 모든 참조(state/skill/agent id) 해소 ──
    reg.run_pending()

    # ── 블랙보드 parent 구조 재연결 (최상위) ──
    # 역직렬화도 생성 경로다 — view 생성 경로(_register_component / 로컬 스킬 생성)와
    # 동일한 스코핑을 복원한다: 최상위 스킬/에이전트 FSM → 프로젝트 블랙보드,
    # 에이전트 로컬 스킬 FSM → 소유 에이전트 FSM 블랙보드. 중첩 sub_machine은
    # _deser_machine의 parent_bb 전달로 이미 구조 재연결되어 있다.
    for skill in project.skills:
        fsm = getattr(skill, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = project.blackboard
    for agent in project.agents:
        if agent.fsm.blackboard.parent is None:
            agent.fsm.blackboard.parent = project.blackboard
        for local in agent.skills:
            lfsm = getattr(local, "fsm", None)
            if lfsm is not None and lfsm.blackboard.parent is None:
                lfsm.blackboard.parent = agent.fsm.blackboard

    # ── 경고 전달 ──
    if collect_warnings is not None:
        collect_warnings.extend(reg.warnings)

    return project


# ── enum 복원 헬퍼 ──

def _to_enum(enum_cls: Any, val: Any, default: Any = None) -> Any:
    if val is None:
        return default
    try:
        return enum_cls(val)
    except ValueError:
        return default


# ── 변수 / 액션 / 전략 / 이벤트 / 가드 ──

def _deser_variable(d: dict) -> Variable:
    return Variable(
        name=d["name"],
        description=d.get("description", ""),
        scope=_to_enum(VariableScope, d.get("scope"), VariableScope.LOCAL),
        field_type=_to_enum(FieldType, d.get("field_type"), FieldType.ANY),
        required=d.get("required", False),
        default=d.get("default"),
        conflict_resolution=_to_enum(
            ConflictResolution, d.get("conflict_resolution"),
            ConflictResolution.LAST_WRITE,
        ),
        id=d.get("id") or _new_id(),
    )


_EVAL_BUILDERS = {
    "llm_evaluation": lambda d: LLMEvaluation(prompt=d.get("prompt", "")),
    "tool_evaluation": lambda d: ToolEvaluation(
        tool=d.get("tool", ""), command=d.get("command", ""),
        success_condition=d.get("success_condition", ""),
    ),
    "mcp_evaluation": lambda d: MCPEvaluation(
        server=d.get("server", ""), tool=d.get("tool", ""),
        arguments=dict(d.get("arguments", {})),
        success_condition=d.get("success_condition", ""),
    ),
    "expression_evaluation": lambda d: ExpressionEvaluation(
        expression=d.get("expression", "")
    ),
}


def _deser_eval(d: dict) -> EvaluationStrategy:
    kind = d.get("kind")
    if kind == "composite_evaluation":
        return CompositeEvaluation(
            operator=d.get("operator", "and"),
            children=[_deser_eval(c) for c in d.get("children", [])],
        )
    builder = _EVAL_BUILDERS.get(kind)
    if builder is not None:
        return builder(d)
    return LLMEvaluation(prompt=d.get("prompt", ""))


_EXEC_BUILDERS = {
    "llm_execution": lambda d: LLMExecution(prompt=d.get("prompt", "")),
    "tool_execution": lambda d: ToolExecution(
        tool=d.get("tool", ""), command=d.get("command", "")
    ),
    "mcp_execution": lambda d: MCPExecution(
        server=d.get("server", ""), tool=d.get("tool", ""),
        arguments=dict(d.get("arguments", {})),
    ),
}


def _deser_exec(d: dict) -> ExecutionStrategy:
    kind = d.get("kind")
    if kind == "composite_execution":
        return CompositeExecution(
            mode=d.get("mode", "sequential"),
            children=[_deser_exec(c) for c in d.get("children", [])],
        )
    builder = _EXEC_BUILDERS.get(kind)
    if builder is not None:
        return builder(d)
    return LLMExecution(prompt=d.get("prompt", ""))


def _deser_action(d: dict) -> Action:
    ov = d.get("output_variable")
    return Action(
        name=d["name"],
        execution=_deser_exec(d["execution"]),
        output_variable=_deser_variable(ov) if ov else None,
    )


def _deser_actions(lst: list | None) -> list[Action]:
    return [_deser_action(a) for a in (lst or [])]


def _deser_guard(d: dict | None) -> Guard | None:
    if d is None:
        return None
    return Guard(evaluation=_deser_eval(d["evaluation"]))


def _deser_event(d: dict | None) -> Event | None:
    if d is None:
        return None
    kind = d.get("kind")
    if kind == "blackboard_trigger":
        cond = d.get("condition")
        return BlackboardTrigger(
            name=d.get("name", ""),
            variable=d.get("variable", ""),
            condition=_deser_eval(cond) if cond else None,
        )
    # 기본 / completion
    return CompletionEvent(name=d.get("name", ""))


# ── blackboard ──

def _deser_dynamic_field(d: dict) -> DynamicField:
    return DynamicField(
        name=d["name"],
        field_type=_to_enum(FieldType, d.get("field_type"), FieldType.ANY),
        collection=_to_enum(CollectionType, d.get("collection"), CollectionType.NONE),
        default=d.get("default"),
        required=d.get("required", False),
    )


def _deser_dynamic_class(d: dict) -> DynamicClass:
    return DynamicClass(
        name=d["name"],
        description=d.get("description", ""),
        fields=[_deser_dynamic_field(f) for f in d.get("fields", [])],
    )


def _deser_blackboard(d: dict | None, parent: Blackboard | None) -> Blackboard:
    if d is None:
        return Blackboard(parent=parent)
    return Blackboard(
        class_definitions=[
            _deser_dynamic_class(c) for c in d.get("class_definitions", [])
        ],
        variables={k: _deser_variable(v) for k, v in d.get("variables", {}).items()},
        parent=parent,
    )


# ── 상태 / 전이 / 머신 ──

def _new_id() -> str:
    from uuid import uuid4
    return uuid4().hex


def _apply_state_common(s: State, d: dict) -> None:
    s.on_entry_start = _deser_actions(d.get("on_entry_start"))
    s.on_entry = _deser_actions(d.get("on_entry"))
    s.on_entry_end = _deser_actions(d.get("on_entry_end"))
    s.on_exit_start = _deser_actions(d.get("on_exit_start"))
    s.on_exit = _deser_actions(d.get("on_exit"))
    s.on_exit_end = _deser_actions(d.get("on_exit_end"))
    s.on_active = _deser_actions(d.get("on_active"))
    s.custom_events = {
        k: _deser_actions(v) for k, v in d.get("custom_events", {}).items()
    }
    s.inputs = [_deser_variable(v) for v in d.get("inputs", [])]
    s.outputs = [_deser_variable(v) for v in d.get("outputs", [])]


def _deser_state(d: dict, reg: _Registry, parent_bb: Blackboard | None) -> State:
    """parent_bb: 이 상태를 소유한 머신의 blackboard. 중첩 sub_machine 의
    blackboard.parent 로 구조적 재연결된다."""
    kind = d.get("kind")
    sid = d.get("id") or _new_id()
    name = d.get("name", "")
    s: State
    if kind == "simple":
        s = SimpleState(name=name, id=sid)
        ref_id = d.get("skill_ref")
        if ref_id is not None:
            reg.add_pending(
                lambda s=s, ref_id=ref_id: setattr(
                    s, "skill_ref", reg.resolve_component(ref_id)
                )
            )
    elif kind == "composite":
        sub = _deser_machine(d["sub_machine"], reg, parent_bb=parent_bb)
        s = CompositeState(name=name, id=sid, sub_machine=sub)
    elif kind == "parallel":
        s = ParallelState(
            name=name, id=sid,
            join=_to_enum(JoinStrategy, d.get("join"), JoinStrategy.ALL),
            join_count=d.get("join_count"),
        )
        s.regions = [_deser_region(r, reg, parent_bb) for r in d.get("regions", [])]
    elif kind == "choice":
        s = ChoiceState(name=name, id=sid)
    elif kind == "terminate":
        s = TerminateState(name=name, id=sid)
    elif kind == "entry_point":
        s = EntryPoint(name=name, id=sid)
    elif kind == "exit_point":
        s = ExitPoint(name=name, id=sid, color=d.get("color", "#cc6666"))
    else:
        # SimpleState로 조용히 강등하면 데이터 손실이 은폐된다 — 명시 실패.
        raise ValueError(f"역직렬화 미지원 State kind: {kind!r}")
    _apply_state_common(s, d)
    reg.states[sid] = s
    return s


def _deser_region(d: dict, reg: _Registry, parent_bb: Blackboard | None) -> Region:
    sub = _deser_machine(d["sub_machine"], reg, parent_bb=parent_bb)
    return Region(name=d.get("name", ""), sub_machine=sub, id=d.get("id") or _new_id())


def _deser_transition(d: dict, reg: _Registry) -> Transition:
    # source/target 는 pass1 에서 같은 머신 states 가 이미 등록됨 → 즉시 해소 가능하나,
    # 안전하게 pending 으로 미룬다(머신 단위 순서 보장).
    src = reg.states.get(d["source"])
    tgt = reg.states.get(d["target"])
    # source/target 은 NonNull 이어야 하므로, 없으면 임시 placeholder 후 pending 보정
    placeholder = src or tgt
    t = Transition(
        source=src or placeholder,  # type: ignore[arg-type]
        target=tgt or placeholder,  # type: ignore[arg-type]
        id=d.get("id") or _new_id(),
        type=_to_enum(TransitionType, d.get("type"), TransitionType.EXTERNAL),
        trigger=_deser_event(d.get("trigger")),
        guard=_deser_guard(d.get("guard")),
        on_guard_check=_deser_actions(d.get("on_guard_check")),
        on_traverse_start=_deser_actions(d.get("on_traverse_start")),
        on_traverse=_deser_actions(d.get("on_traverse")),
        on_traverse_end=_deser_actions(d.get("on_traverse_end")),
        custom_events={
            k: _deser_actions(v) for k, v in d.get("custom_events", {}).items()
        },
        data_map=dict(d.get("data_map", {})),
    )

    def _resolve(t=t, d=d):
        rs = reg.resolve_state(d["source"])
        rt = reg.resolve_state(d["target"])
        if rs is not None:
            t.source = rs
        if rt is not None:
            t.target = rt
        ref_id = d.get("skill_ref")
        if ref_id is not None:
            t.skill_ref = reg.resolve_component(ref_id)

    reg.add_pending(_resolve)
    return t


def _deser_machine(
    d: dict, reg: _Registry, parent_bb: Blackboard | None
) -> StateMachine:
    # blackboard 를 먼저 만들어, 중첩 sub_machine(composite/region)의 blackboard.parent
    # 로 구조적 재연결한다.
    bb = _deser_blackboard(d.get("blackboard"), parent=parent_bb)
    states = [_deser_state(s, reg, parent_bb=bb) for s in d.get("states", [])]
    # initial_state 는 머신 내 state — pending 으로 해소
    init_id = d.get("initial_state")
    initial = reg.states.get(init_id) if init_id else None
    placeholder = initial or (states[0] if states else None)
    machine = StateMachine(
        name=d.get("name", ""),
        initial_state=initial or placeholder,  # type: ignore[arg-type]
        id=d.get("id") or _new_id(),
        states=states,
        transitions=[],
        final_states=[],
        blackboard=bb,
    )
    machine.transitions = [_deser_transition(t, reg) for t in d.get("transitions", [])]

    def _resolve(machine=machine, d=d):
        ist = reg.resolve_state(d.get("initial_state"))
        if ist is not None:
            machine.initial_state = ist
        machine.final_states = [
            st for st in (reg.resolve_state(fid) for fid in d.get("final_states", []))
            if st is not None
        ]

    reg.add_pending(_resolve)
    return machine


# ── section / eventdef ──

def _deser_section(d: dict) -> Section:
    return Section(
        title=d.get("title", ""),
        content=d.get("content", ""),
        children=[_deser_section(c) for c in d.get("children", [])],
    )


def _deser_eventdef(d: dict) -> EventDef:
    return EventDef(
        name=d.get("name", ""),
        color=d.get("color", "#4488ff"),
        description=d.get("description", ""),
    )


# ── config / policy ──

def _deser_config(d: dict) -> Any:
    kind = d.get("kind")
    model = d.get("model")
    model_v = _to_enum(ModelType, model, model)  # ModelType | str — enum 실패 시 문자열 보존
    effort = _to_enum(EffortLevel, d.get("effort"))
    hooks = d.get("hooks")

    if kind == "procedural":
        c = ProceduralSkillConfig(
            disable_model_invocation=d.get("disable_model_invocation", False),
            user_invocable=d.get("user_invocable", True),
            context=_to_enum(SkillContext, d.get("context"), SkillContext.INLINE),
            agent=d.get("agent"),
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    elif kind == "declarative":
        c = DeclarativeSkillConfig(
            disable_model_invocation=d.get("disable_model_invocation", False),
            user_invocable=d.get("user_invocable", True),
        )
    elif kind == "transfer":
        c = TransferSkillConfig(
            disable_model_invocation=d.get("disable_model_invocation", False),
            user_invocable=d.get("user_invocable", False),
            context=_to_enum(SkillContext, d.get("context"), SkillContext.INLINE),
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    elif kind == "reference":
        c = ReferenceSkillConfig(user_invocable=d.get("user_invocable", False))
    elif kind == "agent":
        c = AgentConfig(
            tools=d.get("tools"),
            disallowed_tools=d.get("disallowed_tools"),
            permission_mode=_to_enum(
                PermissionMode, d.get("permission_mode"), PermissionMode.DEFAULT
            ),
            max_turns=d.get("max_turns"),
            skills=list(d.get("skills", [])),
            mcp_servers=d.get("mcp_servers"),
            memory=_to_enum(MemoryScope, d.get("memory")),
            background=d.get("background", False),
            isolation=_to_enum(AgentIsolation, d.get("isolation"), AgentIsolation.NONE),
            color=_to_enum(AgentColor, d.get("color")),
        )
    else:
        c = ProceduralSkillConfig()

    c.model = model_v
    c.effort = effort
    c.hooks = hooks
    # SkillConfig 공통
    if hasattr(c, "argument_hint"):
        c.argument_hint = d.get("argument_hint")
        c.allowed_tools = list(d.get("allowed_tools", []))
        c.paths = d.get("paths")
    return c


def _deser_policy(d: dict | None) -> ExecutionPolicy:
    if d is None:
        return ExecutionPolicy()
    return ExecutionPolicy(
        mode=d.get("mode", "fixed"),
        count=d.get("count", 1),
        join=_to_enum(JoinStrategy, d.get("join"), JoinStrategy.ALL),
        join_count=d.get("join_count"),
    )


# ── skill / agent ──

def _deser_skill(d: dict, reg: _Registry) -> Any:
    kind = d.get("kind")
    sid = d.get("id") or _new_id()
    name = d.get("name", "")
    desc = d.get("description", "")
    config = _deser_config(d["config"]) if d.get("config") else None
    sections = [_deser_section(s) for s in d.get("sections", [])]

    skill: Any
    if kind == "procedural_skill":
        fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
        skill = ProceduralSkill(
            fsm=fsm, name=name, description=desc, id=sid,
            config=config or ProceduralSkillConfig(),
            sections=sections,
            transfer_on=[_deser_eventdef(e) for e in d.get("transfer_on", [])],
            call_agents=[_deser_eventdef(e) for e in d.get("call_agents", [])],
        )
    elif kind == "transfer_skill":
        fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
        skill = TransferSkill(
            fsm=fsm, name=name, description=desc, id=sid,
            config=config or TransferSkillConfig(),
            sections=sections,
        )
    elif kind == "declarative_skill":
        skill = DeclarativeSkill(
            name=name, description=desc, id=sid,
            config=config or DeclarativeSkillConfig(),
            sections=sections,
        )
    elif kind == "reference_skill":
        skill = ReferenceSkill(
            name=name, description=desc, id=sid,
            config=config or ReferenceSkillConfig(),
            sections=sections,
        )
    else:
        skill = DeclarativeSkill(name=name, description=desc, id=sid)

    skill.when_to_use = d.get("when_to_use", "")
    reg.components[sid] = skill
    return skill


def _deser_agent(d: dict, reg: _Registry) -> AgentDefinition:
    sid = d.get("id") or _new_id()
    fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
    # 로컬 스킬도 컴포넌트 레지스트리에 등록 (전이의 transfer skill_ref 가 가리킬 수 있음)
    skills = [_deser_skill(s, reg) for s in d.get("skills", [])]
    agent = AgentDefinition(
        fsm=fsm,
        name=d.get("name", ""),
        description=d.get("description", ""),
        id=sid,
        config=_deser_config(d["config"]) if d.get("config") else AgentConfig(),
        execution_policy=_deser_policy(d.get("execution_policy")),
        sections=[_deser_section(s) for s in d.get("sections", [])],
        skills=skills,
        reference_placements=[
            _deser_ref_placement(r) for r in d.get("reference_placements", [])
        ],
        caller_contracts=[_deser_section(s) for s in d.get("caller_contracts", [])],
        graph_layout={k: list(v) for k, v in d.get("graph_layout", {}).items()},
    )
    reg.components[sid] = agent
    return agent


def _deser_ref_placement(d: dict) -> ReferencePlacement:
    return ReferencePlacement(
        skill_name=d.get("skill_name", ""),
        x=d.get("x", 0.0),
        y=d.get("y", 0.0),
        connected_states=list(d.get("connected_states", [])),
    )


def _deser_delegation(d: dict, reg: _Registry) -> Any:
    kind = d.get("kind")
    name = d.get("name", "")
    desc = d.get("description", "")
    did = d.get("id") or _new_id()
    wait = _to_enum(WaitMode, d.get("wait_mode"), WaitMode.WAIT)
    composition = _to_enum(CompositionMode, d.get("composition"), CompositionMode.EXPLICIT)
    guidance = d.get("guidance", "")

    deleg: Any
    if kind == "team_spawn":
        deleg = TeamSpawnDef(name=name, description=desc, id=did, wait_mode=wait,
                             composition=composition, guidance=guidance)
        for tm in d.get("teammates", []):
            spec = TeammateSpec(
                agent_ref=None,  # type: ignore[arg-type]
                count=tm.get("count", 1),
                role_note=tm.get("role_note", ""),
            )
            deleg.teammates.append(spec)
            ref_id = tm.get("agent_ref")
            if ref_id is not None:
                reg.add_pending(
                    lambda spec=spec, ref_id=ref_id: setattr(
                        spec, "agent_ref", reg.resolve_component(ref_id)
                    )
                )
    elif kind == "dynamic_workflow":
        deleg = DynamicWorkflowDef(
            name=name, description=desc, id=did, wait_mode=wait,
            composition=composition, guidance=guidance,
            objective=d.get("objective", ""),
        )
        for p in d.get("phases", []):
            spec = PhaseSpec(title=p.get("title", ""), detail=p.get("detail", ""))
            deleg.phases.append(spec)
            ref_id = p.get("agent_ref")
            if ref_id is not None:
                reg.add_pending(
                    lambda spec=spec, ref_id=ref_id: setattr(
                        spec, "agent_ref", reg.resolve_component(ref_id)
                    )
                )
    elif kind == "agora_dispatch":
        deleg = AgoraDispatchDef(
            name=name, description=desc, id=did, wait_mode=wait,
            composition=composition, guidance=guidance,
            mode=_to_enum(DispatchMode, d.get("mode"), DispatchMode.DISPATCH),
            target=d.get("target", ""),
            msgtype=d.get("msgtype", ""),
            payload_note=d.get("payload_note", ""),
        )
    else:
        deleg = TeamSpawnDef(name=name, description=desc, id=did, wait_mode=wait,
                             composition=composition, guidance=guidance)
    return deleg
