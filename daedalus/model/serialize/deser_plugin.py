# daedalus/model/serialize/deser_plugin.py
"""역방향 직렬화 — 플러그인 계층 (WP-SZ 관례 분해, 이동만).

``deser.py``에서 Claude 플러그인 메타데이터(본문·출력 포트·config·정책·
스킬·에이전트·참조 배치·훅·작업 폴더 문서·도구)의 역직렬화를 그대로 옮겨 온
형제 모듈이다. FSM 계층(``deser_fsm``)을 수입하는 한 방향만 있고 그 반대는
없다.

``deser.py``가 여기 이름을 전부 재수입하므로 ``serialize/__init__.py`` 파사드와
``daedalus.model.serialize.deser`` 경로는 분해 전과 동일하게 동작한다.
"""
from __future__ import annotations

from typing import Any

from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import (
    WrappedSkillConfig,
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
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
from daedalus.model.plugin.policy import ExecutionPolicy
from daedalus.model.plugin.skill import (
    WrappedSkill,
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
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import ReferencePlacement
from daedalus.model.serialize.deser_fsm import (
    _Registry,
    _deser_machine,
    _new_id,
    _to_enum,
)


def _deser_body(d: dict) -> str:
    """스킬/에이전트 본문 역직렬화 — v2는 ``body``가 단일 진실이다.

    구버전 ``sections`` 트리·경로 변수 치환은 ``_migrate_v1``이 처리한다.
    """
    return d.get("body") or ""


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

    if kind == "wrapped":
        # WP-WR — source는 외부 스킬 참조 문자열(plugin@marketplace:skill).
        # usage 키 부재는 구버전 파일 — 그때는 state 용도만 있었다.
        c = WrappedSkillConfig(
            source=d.get("source", ""),
            usage=str(d.get("usage", "state") or ""),
            enabled=bool(d.get("enabled", True)),
            disable_model_invocation=d.get("disable_model_invocation"),  # tri-state
            user_invocable=d.get("user_invocable"),
        )
    elif kind == "procedural":
        c = ProceduralSkillConfig(
            # tri-state (A8) — 키 부재는 **미지정(None)**이다. 저장된 true/false는
            # 그대로 왕복한다(스크럽 금지 — 사용자가 명시 지정한 값이다).
            disable_model_invocation=d.get("disable_model_invocation"),
            user_invocable=d.get("user_invocable"),
            context=_to_enum(SkillContext, d.get("context"), SkillContext.INLINE),
            agent=d.get("agent"),
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    elif kind == "declarative":
        c = DeclarativeSkillConfig(
            disable_model_invocation=d.get("disable_model_invocation"),  # tri-state (A8)
            user_invocable=d.get("user_invocable"),
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
    body = _deser_body(d)

    skill: Any
    if kind == "procedural_skill":
        fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
        skill = ProceduralSkill(
            fsm=fsm, name=name, description=desc, id=sid,
            config=config or ProceduralSkillConfig(),
            body=body,
            transfer_on=[_deser_eventdef(e) for e in d.get("transfer_on", [])],
            call_agents=[_deser_eventdef(e) for e in d.get("call_agents", [])],
        )
    elif kind == "wrapped_skill":
        # WP-WR — body는 구조상 왕복하되 정본은 config.source의 외부 스킬이다.
        fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
        skill = WrappedSkill(
            fsm=fsm, name=name, description=desc, id=sid,
            config=config or WrappedSkillConfig(),
            body=body,
            transfer_on=[_deser_eventdef(e) for e in d.get("transfer_on", [])],
            call_agents=[_deser_eventdef(e) for e in d.get("call_agents", [])],
        )
    elif kind == "transfer_skill":
        fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
        skill = TransferSkill(
            fsm=fsm, name=name, description=desc, id=sid,
            config=config or TransferSkillConfig(),
            body=body,
        )
    elif kind == "declarative_skill":
        skill = DeclarativeSkill(
            name=name, description=desc, id=sid,
            config=config or DeclarativeSkillConfig(),
            body=body,
        )
    elif kind == "reference_skill":
        skill = ReferenceSkill(
            name=name, description=desc, id=sid,
            config=config or ReferenceSkillConfig(),
            body=body,
        )
    else:
        skill = DeclarativeSkill(name=name, description=desc, id=sid)

    skill.when_to_use = d.get("when_to_use", "")
    reg.components[sid] = skill
    return skill


def _deser_agent(d: dict, reg: _Registry) -> AgentDefinition:
    sid = d.get("id") or _new_id()
    fsm = _deser_machine(d["fsm"], reg, parent_bb=None)
    agent = AgentDefinition(
        fsm=fsm,
        name=d.get("name", ""),
        description=d.get("description", ""),
        id=sid,
        config=_deser_config(d["config"]) if d.get("config") else AgentConfig(),
        execution_policy=_deser_policy(d.get("execution_policy")),
        body=_deser_body(d),
        reference_placements=[
            _deser_ref_placement(r) for r in d.get("reference_placements", [])
        ],
        graph_layout={k: list(v) for k, v in d.get("graph_layout", {}).items()},
        # WP-ER — 구버전 키 부재 → 빈 dict (경고 없음).
        edge_layout={
            k: [list(pt) for pt in v] for k, v in d.get("edge_layout", {}).items()
        },
        # WP-AF — 출력 포트가 단일 진실. v1의 ExitPoint 승계는 _migrate_v1 소관.
        transfer_on=[_deser_eventdef(e) for e in d.get("transfer_on", [])],
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


# ── hook library ──

def _deser_hook_handler(d: dict):
    """dict → 훅 핸들러. 미지 kind는 None(호출부가 건너뛴다)."""
    from dataclasses import fields as dc_fields

    from daedalus.model.plugin.hook import HOOK_HANDLER_TYPES, HookShell

    cls = HOOK_HANDLER_TYPES.get(str(d.get("kind", "")))
    if cls is None:
        return None
    kwargs: dict = {}
    for f in dc_fields(cls):
        if f.name == "id" or f.name not in d:
            continue
        value = d[f.name]
        if f.name == "shell":
            value = _to_enum(HookShell, value, HookShell.DEFAULT)
        kwargs[f.name] = value
    return cls(**kwargs, id=d.get("id") or _new_id())


def _deser_workspace_doc(d) -> WorkspaceDoc | None:
    """작업 폴더 문서 (WP-WD). 비-dict는 None. paths(A13) 키 부재는 빈 리스트(하위 호환)."""
    if not isinstance(d, dict):
        return None
    return WorkspaceDoc(d.get("name", ""), d.get("body", ""), list(d.get("paths") or []), id=d.get("id") or _new_id())


def _deser_workspace_docs(raw) -> list[WorkspaceDoc]:
    """규칙 문서 목록 — 읽을 수 없는 항목은 빼고, 키 부재는 빈 리스트."""
    return [d for d in map(_deser_workspace_doc, raw or []) if d is not None]


def _deser_hook(d: dict) -> HookDef:
    """훅 역직렬화 — 구버전(커맨드 하나짜리) 형태는 _migrate_v1이 handlers로
    감싸 두므로 여기서는 v2 형태만 읽는다. 미지 kind 핸들러는 건너뛴다."""
    handlers = [
        h
        for h in (_deser_hook_handler(x) for x in d.get("handlers", []))
        if h is not None
    ]

    return HookDef(
        name=d.get("name", ""),
        description=d.get("description", ""),
        event=_to_enum(HookEvent, d.get("event"), HookEvent.PRE_TOOL_USE),
        matcher=d.get("matcher", ""),
        # 키 부재(구버전 파일)는 True — 그때는 선별 개념이 없었고 라이브러리에
        # 있는 훅은 참조되면 배출됐다.
        enabled=bool(d.get("enabled", True)),
        handlers=handlers,
        id=d.get("id") or _new_id(),
    )


# ── tool shelf ──

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
