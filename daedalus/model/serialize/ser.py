# daedalus/model/serialize/ser.py
"""정방향 직렬화 — 모델 → JSON 호환 dict (WP-SZ 분해, 이동만).

``serialize_project`` 와 그것이 부르는 ``_ser_*`` 헬퍼 전부. 원칙(참조 평탄화·
``kind`` 다형성 태그·enum ``.value``)은 패키지 ``__init__`` 의 모듈 독스트링을 보라.

``FORMAT_VERSION`` 은 여기가 단일 진실이다 — 쓰는 쪽이 포맷 버전을 선언하고,
읽는 쪽(``deser``)과 마이그레이션(``migrate``)이 그것을 참조한다.
"""
from __future__ import annotations

import copy

from typing import Any

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import BlackboardTrigger, Event
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.model.fsm.section import EventDef
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
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import Variable
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import (
    WrappedSkillConfig,
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.hook import HookDef
from daedalus.model.plugin.policy import ExecutionPolicy
from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill, WrappedSkill
from daedalus.model.plugin.tool import BuiltinTool, MCPTool, Tool, UserDefinedTool
from daedalus.model.project import PluginProject, ReferencePlacement

FORMAT_VERSION = 2


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
        "tool_shelf": [_ser_tool(t) for t in project.tool_shelf],
        "hook_library": [_ser_hook(h) for h in project.hook_library],
        "blackboard": _ser_blackboard(project.blackboard),
        # 프로젝트 워크플로 그래프 — 노드/전이를 정식 FSM으로 왕복 (버그 1 수정).
        # skill_ref는 _ser_machine이 component id로 평탄화 → 역직렬화 2-pass가 해소.
        "graph": _ser_machine(project.graph),
        "graph_layout": {k: list(v) for k, v in project.graph_layout.items()},
        # WP-ER — 전이 엣지 경유점(waypoint). 키는 Transition.id.
        "edge_layout": {
            k: [list(pt) for pt in v] for k, v in project.edge_layout.items()
        },
        # WP-RS Part B — 구버전 파일(키 부재)은 역직렬화 시 기본 True로 취급.
        "emit_progress_hook": project.emit_progress_hook,
        # WP-TG — 구버전 파일(키 부재)은 역직렬화 시 MARKETPLACE로 취급(경고 없음).
        "build_target": project.build_target.value,
        # WP-MW — MCP 서버 정의(이름 → .mcp.json 서버 객체). 구버전 파일(키 부재)은 빈 dict.
        "mcp_server_defs": {k: dict(v) for k, v in project.mcp_server_defs.items()},
        # WP-WR — 사용 외부 플러그인 id 목록("이름[@마켓]"). 키 부재는 빈 리스트.
        "external_plugins": list(project.external_plugins),
        # WP-WS — 작업 폴더 settings 베이크 원본(JSON 호환 dict). 키 부재는 빈 dict.
        "workspace_settings": copy.deepcopy(project.workspace_settings),
        # WP-WD — 작업 폴더 문서. 구버전 파일(키 부재)은 각각 None / 빈 리스트.
        "claude_md": _ser_workspace_doc(project.claude_md),
        "rules": [_ser_workspace_doc(doc) for doc in project.rules],
    }


# ── workspace docs (WP-WD) ──

def _ser_workspace_doc(doc):
    """WorkspaceDoc → dict. None이면 None(키는 남긴다 — 부재와 빈 문서를 구분한다)."""
    if doc is None:
        return None
    # paths(A13)는 규칙 전용이지만 문서 표현은 하나로 유지한다 — claude_md에서는
    # 항상 빈 리스트다.
    return {
        "id": doc.id, "name": doc.name, "body": doc.body,
        "paths": list(doc.paths),
    }


# ── hook library ──

def _ser_hook_handler(h) -> dict:
    """훅 핸들러 → dict. kind를 다형성 태그로 쓴다(Skill/Tool 선례와 동일)."""
    from dataclasses import fields as dc_fields
    from enum import Enum

    out: dict = {"kind": h.kind, "id": h.id}
    for f in dc_fields(h):
        if f.name == "id":
            continue
        value = getattr(h, f.name)
        out[f.name] = value.value if isinstance(value, Enum) else value
    return out


def _ser_hook(h: HookDef) -> dict:
    return {
        "id": h.id,
        "name": h.name,
        "description": h.description,
        "event": h.event.value,
        "matcher": h.matcher,
        "handlers": [_ser_hook_handler(x) for x in h.handlers],
    }


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
            "ser.py의 _KNOWN_TOOL_KINDS/_ser_tool과 deser.py의 _deser_tool에 분기를 추가하라"
        )
    if isinstance(t, BuiltinTool):
        d["allowed_arguments_note"] = t.allowed_arguments_note
    elif isinstance(t, MCPTool):
        d.update(server=t.server, tool_name=t.tool_name)
    elif isinstance(t, UserDefinedTool):
        d.update(body=t.body, shell=t.shell.value)
    return d


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
        # WP-BB — 상태 접근 선언 (블랙보드 "Class"/"Class.field" 문자열 참조).
        "reads": list(s.reads),
        "writes": list(s.writes),
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
            "ser.py의 _KNOWN_STATE_KINDS/_ser_state와 deser.py의 _deser_state에 분기를 추가하라"
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
    if isinstance(c, WrappedSkillConfig):
        d.update(
            source=c.source,
            disable_model_invocation=c.disable_model_invocation,
            user_invocable=c.user_invocable,
        )
    elif isinstance(c, ProceduralSkillConfig):
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
        "body": s.body,
        "config": _ser_config(s.config),
    }
    if isinstance(s, (ProceduralSkill, TransferSkill, WrappedSkill)):
        d["fsm"] = _ser_machine(s.fsm)
    if isinstance(s, (ProceduralSkill, WrappedSkill)):
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
        "body": a.body,
        "reference_placements": [
            _ser_ref_placement(r) for r in a.reference_placements
        ],
        "graph_layout": {k: list(v) for k, v in a.graph_layout.items()},
        # WP-ER — 전이 엣지 경유점(waypoint). 키는 Transition.id.
        "edge_layout": {
            k: [list(pt) for pt in v] for k, v in a.edge_layout.items()
        },
        # WP-AF — 출력 포트. v1 파일의 ExitPoint는 _migrate_v1이 승계한다.
        "transfer_on": [_ser_eventdef(e) for e in a.transfer_on],
    }


def _ser_ref_placement(r: ReferencePlacement) -> dict:
    return {
        "skill_name": r.skill_name,
        "x": r.x,
        "y": r.y,
        "connected_states": list(r.connected_states),
    }
