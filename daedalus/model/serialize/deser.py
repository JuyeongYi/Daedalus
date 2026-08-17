# daedalus/model/serialize/deser.py
"""역방향 직렬화 — JSON 호환 dict → 모델 (WP-SZ 분해, 이동만).

2-pass 다:
  1. 객체 생성 + id→객체 레지스트리 구축 (``_Registry``)
  2. 참조 해소 (state/skill/agent id → 실제 객체)

dangling id 는 ValueError 가 아니라 None 처리하고 경고를 수집한다.
구버전 파일은 ``migrate._migrate_v1`` 을 태운 뒤 v2 로 읽는다.
"""
from __future__ import annotations

import copy
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
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import (
    ChoiceState,
    EntryPoint,
    ExitPoint,
    TerminateState,
)
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
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    BuildTarget,
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
from daedalus.model.serialize.migrate import _migrate_v1, _promote_local_skills
from daedalus.model.serialize.ser import FORMAT_VERSION


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

    format 1(또는 키 부재 구버전)은 ``_migrate_v1``로 단방향 마이그레이션한
    뒤 읽는다. format 2는 마이그레이션 없이 읽는다. 미지의 상위 format은
    명시 에러(미래 버전 파일을 조용히 오독하지 않는다).
    """
    reg = _Registry()
    fmt = data.get("format")
    if fmt is None or fmt == 1:
        data = _migrate_v1(data, reg.warnings)
    elif fmt == FORMAT_VERSION:
        # RF-1b 시점(로컬 스킬 승격 이전)의 코드가 저장한 format 2 파일에는
        # 에이전트 인라인 로컬 스킬("skills" 키)이 남아 있을 수 있다 — format
        # 게이트만 보고 건너뛰면 스킬 이름·본문이 경고 없이 통째로 드롭된다.
        # v1과 동일한 승격 마이그레이션을 태운다 (WP-RF-1c 리뷰 지적).
        if any(a.get("skills") for a in data.get("agents", []) or []):
            data = copy.deepcopy(data)
            _promote_local_skills(data, reg.warnings)
    else:
        raise ValueError(
            f"지원하지 않는 파일 형식 버전: {fmt!r} "
            f"(지원: {FORMAT_VERSION}, 구버전 1은 로드 시 마이그레이션)"
        )

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
        tool_shelf=[_deser_tool(t) for t in data.get("tool_shelf", [])],
        hook_library=[_deser_hook(h) for h in data.get("hook_library", [])],
        blackboard=blackboard,
        graph=graph,
        graph_layout={k: list(v) for k, v in data.get("graph_layout", {}).items()},
        # WP-ER — 구버전 키 부재 → 빈 dict (경고 없음).
        edge_layout={
            k: [list(pt) for pt in v] for k, v in data.get("edge_layout", {}).items()
        },
        # WP-RS Part B — 구버전 파일(키 부재) → 기본 True.
        emit_progress_hook=data.get("emit_progress_hook", True),
        # WP-TG — 구버전 파일(키 부재) → MARKETPLACE(경고 없음, 하위 호환 게이트).
        build_target=_to_enum(
            BuildTarget, data.get("build_target"), BuildTarget.MARKETPLACE
        ),
        # WP-MW — 구버전 파일(키 부재) → 빈 dict (경고 없음).
        mcp_server_defs={
            k: dict(v) for k, v in data.get("mcp_server_defs", {}).items()
        },
    )

    # ── pass 2: 모든 참조(state/skill/agent id) 해소 ──
    reg.run_pending()

    # ── 블랙보드 parent 구조 재연결 (최상위) ──
    # 역직렬화도 생성 경로다 — view 생성 경로(_register_component)와 동일한
    # 스코핑을 복원한다: 최상위 스킬/에이전트 FSM → 프로젝트 블랙보드.
    # (v1 파일의 에이전트 로컬 스킬은 _migrate_v1이 전역 스킬로 승격하므로
    # 여기서 전역 스킬과 같은 경로를 탄다.) 중첩 sub_machine은 _deser_machine의
    # parent_bb 전달로 이미 구조 재연결되어 있다.
    for skill in project.skills:
        fsm = getattr(skill, "fsm", None)
        if fsm is not None and fsm.blackboard.parent is None:
            fsm.blackboard.parent = project.blackboard
    for agent in project.agents:
        if agent.fsm.blackboard.parent is None:
            agent.fsm.blackboard.parent = project.blackboard

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
    # WP-BB — 구버전 파일(키 부재) → 빈 리스트 (경고 없음).
    s.reads = list(d.get("reads", []))
    s.writes = list(d.get("writes", []))


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
