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

import dataclasses

from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import Agent, AgentDefinition
from daedalus.model.plugin.config import (
    WrappedSkillConfig,
    AgentConfig,
    AsyncForkSkillConfig,
    DeclarativeSkillConfig,
    ForkAgentConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.kinds import config_kinds_in, spec_by_kind
from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillShell,
)
from daedalus.model.plugin.hook import HookDef, HookEvent
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

#: 읽을 수 있는 config `kind` 전수 — **레지스트리에서 파생**한다(WP-3).
#: 미지 kind는 **ValueError**다(조용한 강등 금지 — 원칙 5). 키 자체가 없으면
#: "미지"가 아니라 "미기재"라 None을 돌려주고 호출자가 자기 분기의 기본 config를
#: 쓴다(구버전·손편집 파일).
#:
#: 베껴 쓴 목록이었을 때는 새 종류가 여기 빠지면 그 종류의 설정이 통째로
#: "알 수 없는 config"로 거절돼 프로젝트가 아예 열리지 않았다 — 그리고 그
#: 사실을 알려 주는 것은 사용자의 버그 리포트뿐이었다.
_CONFIG_KINDS: tuple[str, ...] = (
    config_kinds_in(Bucket.SKILLS) + config_kinds_in(Bucket.AGENTS)
)


def _deser_config(d: dict) -> Any:
    kind = d.get("kind")
    if kind is None:
        return None
    if kind not in _CONFIG_KINDS:
        raise ValueError(
            f"알 수 없는 config 종류: {kind!r} "
            f"(사용 가능: {', '.join(_CONFIG_KINDS)})"
        )
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
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    elif kind in ("sync_fork", "async_fork"):
        fork_cls = SyncForkSkillConfig if kind == "sync_fork" else AsyncForkSkillConfig
        c = fork_cls(
            disable_model_invocation=d.get("disable_model_invocation"),  # tri-state (A8)
            user_invocable=d.get("user_invocable"),
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
            agent=d.get("agent") or "general-purpose",
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
            shell=_to_enum(SkillShell, d.get("shell"), SkillShell.BASH),
        )
    elif kind == "reference":
        c = ReferenceSkillConfig(user_invocable=d.get("user_invocable", False))
    elif kind in ("agent", "fork_agent"):
        common = dict(
            tools=d.get("tools"),
            disallowed_tools=d.get("disallowed_tools"),
            permission_mode=_to_enum(
                PermissionMode, d.get("permission_mode"), PermissionMode.DEFAULT
            ),
            max_turns=d.get("max_turns"),
            skills=list(d.get("skills", [])),
            mcp_servers=d.get("mcp_servers"),
            memory=_to_enum(MemoryScope, d.get("memory")),
            color=_to_enum(AgentColor, d.get("color")),
        )
        if kind == "fork_agent":
            # background·isolation은 fork 에이전트에 없다 — 파일에 남아 있어도
            # 흡수하지 않는다(퇴역 개념의 잔재 금지).
            c = ForkAgentConfig(**common)
        else:
            c = AgentConfig(
                **common,
                background=d.get("background", False),
                isolation=_to_enum(
                    AgentIsolation, d.get("isolation"), AgentIsolation.NONE
                ),
            )
    else:  # pragma: no cover — _CONFIG_KINDS 게이트가 앞에서 걸러낸다
        raise ValueError(f"알 수 없는 config 종류: {kind!r}")

    c.model = model_v
    c.effort = effort
    c.hooks = hooks
    # SkillConfig 공통
    if hasattr(c, "argument_hint"):
        c.argument_hint = d.get("argument_hint")
        c.allowed_tools = list(d.get("allowed_tools", []))
        c.paths = d.get("paths")
    return c


# ── skill / agent ──

def _coerce_config(config, expected_cls, *, kind: str, name: str, reg: _Registry):
    """config가 이 종류의 config 클래스인지 강제한다 (역직렬화 계약).

    `config.kind`가 매트릭스 키가 된 뒤로 클래스는 더 이상 유일 심판이 아니다 —
    어긋난 조합(`procedural_skill` + `sync_fork` config)이 파일에서 들어오면
    프론트매터는 `context: fork`를, 본문 조립은 "fork 아님"을 말해 **산출이 두
    가지 사실을 말한다**. 그래서 여기서 기본 config로 강등하고 경고 1건을 낸다
    (조용히 버리지 않는다 — 원칙 5).
    """
    if isinstance(config, expected_cls):
        return config
    if config is not None:
        reg.warnings.append(
            f"'{name}'의 config 종류('{getattr(config, 'kind', '?')}')가 "
            f"종류('{kind}')와 달라 기본 config로 대체했습니다."
        )
    return expected_cls()


def _build_component(d: dict, reg: _Registry, spec) -> Any:
    """행이 가리키는 클래스로 컴포넌트 한 개를 조립한다 — **필드 유무가 분기다**.

    종류별 if 사다리(M5) 대신 `dataclasses.fields`로 "이 종류가 fsm/포트/
    when_to_use를 갖는가"를 묻는다. 사다리였을 때는 종류를 하나 더할 때마다
    가지를 하나 더 쳐야 했고, 빠뜨리면 그 종류만 "알 수 없는 종류"로 거절됐다.

    부수효과가 있는 호출의 **순서는 종전 그대로**다(config dict → fsm →
    config 강제 → 나머지). `reg.warnings`가 쌓이는 순서가 곧 사용자가 보는
    경고 순서라, 순서를 바꾸면 동작 불변이 아니다.
    """
    cls = spec.component_cls
    field_names = {f.name for f in dataclasses.fields(cls)}
    name = d.get("name", "")
    raw_config = _deser_config(d["config"]) if d.get("config") else None

    kwargs: dict[str, Any] = {"name": name, "description": d.get("description", "")}
    if "fsm" in field_names:
        kwargs["fsm"] = _deser_machine(d["fsm"], reg, parent_bb=None)
    kwargs["config"] = _coerce_config(
        raw_config, spec.config_cls, kind=spec.kind, name=name, reg=reg
    )
    kwargs["body"] = _deser_body(d)
    if "when_to_use" in field_names:
        kwargs["when_to_use"] = d.get("when_to_use", "")
    for port in ("transfer_on", "call_agents"):
        # 키 부재(구버전 파일) → 빈 목록, 경고 없음. dataclass 기본값으로
        # 떨어지면 키 없는 파일에 포트 `done`이 **발명**된다(§2-d 부재 의미론).
        if port in field_names:
            kwargs[port] = [_deser_eventdef(e) for e in d.get(port, [])]

    sid = d.get("id") or _new_id()
    component = cls(**kwargs, id=sid)
    reg.components[sid] = component
    return component


def _deser_skill(d: dict, reg: _Registry) -> Any:
    """스킬 역직렬화 — 종류 해소는 **레지스트리**가 한다 (WP-3).

    버킷을 함께 넘기는 것이 게이트다: 스킬 목록에 적힌 ``"agent"``는 에이전트를
    만드는 것이 아니라 거절이다(손편집·손상 파일이 스킬 자리에 에이전트를
    앉히면 저장·산출까지 어긋남이 따라간다).
    """
    name = d.get("name", "")
    spec = spec_by_kind(
        d.get("kind"), bucket=Bucket.SKILLS, subject=f"스킬 '{name}'"
    )
    return _build_component(d, reg, spec)


def _deser_agent(d: dict, reg: _Registry) -> Agent:
    """에이전트 역직렬화 — `kind`가 종류를 가른다.

    키 부재는 구버전 파일이라 **워크플로 에이전트**로 읽는다(그때는 종류가
    하나뿐이었다). 미지 kind는 ValueError다.
    """
    name = d.get("name", "")
    spec = spec_by_kind(
        d.get("kind") or AgentDefinition.KIND,
        bucket=Bucket.AGENTS,
        subject=f"에이전트 '{name}'",
    )
    return _build_component(d, reg, spec)


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
