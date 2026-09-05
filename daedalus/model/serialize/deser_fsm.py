# daedalus/model/serialize/deser_fsm.py
"""역방향 직렬화 — FSM 계층 (WP-SZ 관례 분해, 이동만).

``deser.py``에서 순수 FSM 개념(변수·전략·액션·가드·이벤트·블랙보드·상태·
전이·머신)의 역직렬화를 그대로 옮겨 온 형제 모듈이다. 2-pass 컨텍스트인
``_Registry``도 여기 산다 — FSM 계층이 그것을 **소비**하는 최하위 계층이라,
상위(``deser_plugin`` → ``deser``)가 그것을 재수입하면 의존 방향이
단방향으로 유지된다(반대로 두면 FSM 계층이 상위 모듈을 임포트해야 한다).

``deser.py``가 여기 이름을 전부 재수입하므로 ``serialize/__init__.py`` 파사드와
``daedalus.model.serialize.deser`` 경로는 분해 전과 동일하게 동작한다.
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
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import (
    ChoiceState,
    EntryPoint,
    ExitPoint,
    TerminateState,
)
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


# ── 2-pass 컨텍스트 ──


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
