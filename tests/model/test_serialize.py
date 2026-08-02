"""WP-F: 안정 ID + 직렬화/역직렬화 라운드트립 검증."""
import json

import pytest

from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    Region,
    SimpleState,
)
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType, Variable, VariableScope
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import TeamSpawnDef, TeammateSpec
from daedalus.model.plugin.enums import ModelType
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import (
    FORMAT_VERSION,
    deserialize_project,
    serialize_project,
)


# ─────────────────────── ID 부여 ───────────────────────


def test_state_auto_id_unique():
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    assert a.id and b.id
    assert a.id != b.id


def test_id_is_kw_only_not_positional():
    """id가 kw_only라 위치 인수로 들어가지 않는다 — 기존 위치 인수 생성 무사."""
    # name이 첫 위치 인수로 정상 바인딩되고 id는 자동 생성
    s = SimpleState("posname")
    assert s.name == "posname"
    assert s.id  # 자동 생성됨


def test_skill_id_excluded_from_equality():
    """Skill의 id는 compare=False라 값 동등성 비교에서 제외된다."""
    import dataclasses

    # 동일 sections 객체를 공유시켜 다른 필드를 동등하게 만든 뒤,
    # id만 차이나게 해도 == 가 성립함을 확인.
    shared_sections = [DeclarativeSkill(name="z", description="d").sections[0]]
    a = DeclarativeSkill(name="x", description="d", sections=shared_sections)
    b = DeclarativeSkill(name="x", description="d", sections=shared_sections)
    assert a.id != b.id
    assert a == b  # id가 달라도 값 동등

    # id 필드가 compare=False로 선언되었는지 직접 확인
    id_field = next(f for f in dataclasses.fields(a) if f.name == "id")
    assert id_field.compare is False


def test_eq_false_state_identity_preserved():
    """eq=False 상태는 identity 동등성/해시 유지 (id 무관)."""
    a = SimpleState(name="a")
    b = SimpleState(name="a")
    assert a != b  # identity 기준
    assert hash(a) != hash(b) or a is not b
    assert a in {a}  # hashable


# ─────────────────────── 직렬화 기본 ───────────────────────


def _make_proc_skill() -> tuple[ProceduralSkill, DeclarativeSkill]:
    shared = DeclarativeSkill(name="shared", description="공유")
    s1 = SimpleState(name="A", skill_ref=shared)
    s2 = SimpleState(name="B", skill_ref=shared)
    fsm = StateMachine(
        name="f",
        initial_state=s1,
        states=[s1, s2],
        transitions=[Transition(source=s1, target=s2, trigger=CompletionEvent(name="done"))],
        final_states=[s2],
    )
    proc = ProceduralSkill(fsm=fsm, name="proc", description="절차")
    return proc, shared


def test_format_version_present():
    p = PluginProject(name="P")
    data = serialize_project(p)
    assert data["format"] == FORMAT_VERSION


def test_json_dumpable():
    proc, shared = _make_proc_skill()
    p = PluginProject(name="P", skills=[shared, proc])
    data = serialize_project(p)
    # json.dumps 가능해야 함 (예외 없음)
    s = json.dumps(data, ensure_ascii=False)
    assert s


# ─────────────────────── 라운드트립 핵심 ───────────────────────


def _roundtrip(project: PluginProject) -> PluginProject:
    return deserialize_project(json.loads(json.dumps(serialize_project(project))))


def test_shared_skill_ref_preserved():
    """동일 skill을 참조하던 두 상태가 역직렬화 후에도 같은 객체를 참조."""
    proc, shared = _make_proc_skill()
    p = PluginProject(name="P", skills=[shared, proc])
    p2 = _roundtrip(p)

    proc2 = next(s for s in p2.skills if s.name == "proc")
    a, b = proc2.fsm.states
    assert a.skill_ref is b.skill_ref  # 참조 공유 보존
    shared2 = next(s for s in p2.skills if s.name == "shared")
    assert a.skill_ref is shared2  # 프로젝트 내 동일 객체


def test_transition_source_target_identity():
    """Transition.source/target이 states 내 객체와 identity 일치."""
    proc, shared = _make_proc_skill()
    p = PluginProject(name="P", skills=[shared, proc])
    p2 = _roundtrip(p)

    proc2 = next(s for s in p2.skills if s.name == "proc")
    t = proc2.fsm.transitions[0]
    assert t.source is proc2.fsm.states[0]
    assert t.target is proc2.fsm.states[1]


def test_machine_initial_and_final_identity():
    proc, shared = _make_proc_skill()
    p = PluginProject(name="P", skills=[shared, proc])
    p2 = _roundtrip(p)
    proc2 = next(s for s in p2.skills if s.name == "proc")
    assert proc2.fsm.initial_state is proc2.fsm.states[0]
    assert proc2.fsm.final_states[0] is proc2.fsm.states[1]


def test_graph_layout_keys_are_id():
    """graph_layout 키가 id로 보존."""
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="af", initial_state=entry, states=[entry, done], final_states=[done]
    )
    agent = AgentDefinition(
        fsm=fsm, name="ag", description="d",
        graph_layout={entry.id: [1.0, 2.0], done.id: [3.0, 4.0]},
    )
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    ag2 = p2.agents[0]
    entry2 = next(s for s in ag2.fsm.states if s.name == "entry")
    assert entry2.id in ag2.graph_layout
    assert ag2.graph_layout[entry2.id] == [1.0, 2.0]


def test_enum_restored():
    """enum 값이 enum 타입으로 복원."""
    v = Variable(name="v", description="", scope=VariableScope.BLACKBOARD,
                 field_type=FieldType.INT)
    fsm = StateMachine(
        name="af", initial_state=SimpleState(name="x"),
        states=[SimpleState(name="x")],
        blackboard=Blackboard(variables={"v": v}),
    )
    # initial_state must be in states — fix
    s = fsm.states[0]
    fsm.initial_state = s
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    agent.config.model = ModelType.OPUS
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    ag2 = p2.agents[0]
    v2 = ag2.fsm.blackboard.variables["v"]
    assert v2.scope is VariableScope.BLACKBOARD
    assert v2.field_type is FieldType.INT
    assert ag2.config.model is ModelType.OPUS


def test_nested_composite_and_region_restored():
    """중첩 sub_machine(CompositeState, Region) 복원."""
    inner_c = SimpleState(name="IC")
    comp_m = StateMachine(name="cm", initial_state=inner_c, states=[inner_c])
    comp = CompositeState(name="Comp", sub_machine=comp_m)

    inner_r = SimpleState(name="IR")
    reg_m = StateMachine(name="rm", initial_state=inner_r, states=[inner_r])
    region = Region(name="r1", sub_machine=reg_m)
    par = ParallelState(name="Par", regions=[region])

    fsm = StateMachine(name="af", initial_state=comp, states=[comp, par])
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)

    ag2 = p2.agents[0]
    comp2 = next(s for s in ag2.fsm.states if isinstance(s, CompositeState))
    assert comp2.sub_machine.states[0].name == "IC"
    par2 = next(s for s in ag2.fsm.states if isinstance(s, ParallelState))
    assert par2.regions[0].sub_machine.states[0].name == "IR"


def test_blackboard_parent_reconnected_structurally():
    """중첩 머신 blackboard.parent가 소유 구조로 재연결."""
    inner = SimpleState(name="I")
    inner_m = StateMachine(name="im", initial_state=inner, states=[inner],
                           blackboard=Blackboard())
    region = Region(name="r1", sub_machine=inner_m)
    par = ParallelState(name="Par", regions=[region])
    fsm = StateMachine(name="af", initial_state=par, states=[par],
                       blackboard=Blackboard())
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    ag2 = p2.agents[0]
    par2 = ag2.fsm.states[0]
    region2 = par2.regions[0]
    assert region2.sub_machine.blackboard.parent is ag2.fsm.blackboard


def test_blackboard_dynamic_class_restored():
    dc = DynamicClass(
        name="C", description="d",
        fields=[DynamicField(name="ff", field_type=FieldType.INT, required=True)],
    )
    fsm = StateMachine(
        name="af", initial_state=SimpleState(name="x"), states=[SimpleState(name="x")],
        blackboard=Blackboard(class_definitions=[dc]),
    )
    fsm.initial_state = fsm.states[0]
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    bb = p2.agents[0].fsm.blackboard
    assert bb.class_definitions[0].name == "C"
    assert bb.class_definitions[0].fields[0].field_type is FieldType.INT
    assert bb.class_definitions[0].fields[0].required is True


def test_transfer_skill_ref_on_transition():
    """Transition.skill_ref(transfer skill)가 id로 평탄화 후 동일 객체 복원."""
    ts_fsm = StateMachine(name="tf", initial_state=SimpleState(name="t"),
                          states=[SimpleState(name="t")])
    ts_fsm.initial_state = ts_fsm.states[0]
    transfer = TransferSkill(fsm=ts_fsm, name="checker", description="d")

    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    fsm = StateMachine(
        name="f", initial_state=s1, states=[s1, s2],
        transitions=[Transition(source=s1, target=s2, skill_ref=transfer)],
    )
    proc = ProceduralSkill(fsm=fsm, name="proc", description="d")
    p = PluginProject(name="P", skills=[transfer, proc])
    p2 = _roundtrip(p)

    transfer2 = next(s for s in p2.skills if s.name == "checker")
    proc2 = next(s for s in p2.skills if s.name == "proc")
    assert proc2.fsm.transitions[0].skill_ref is transfer2


def test_delegation_agent_ref_resolved():
    """DelegationDef의 agent_ref가 id로 평탄화 후 프로젝트 에이전트로 복원."""
    fsm = StateMachine(name="af", initial_state=EntryPoint(name="e"),
                       states=[EntryPoint(name="e")])
    fsm.initial_state = fsm.states[0]
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    team = TeamSpawnDef(name="team", description="d",
                        teammates=[TeammateSpec(agent_ref=agent, count=2)])
    p = PluginProject(name="P", agents=[agent], delegations=[team])
    p2 = _roundtrip(p)
    team2 = p2.delegations[0]
    assert team2.teammates[0].agent_ref is p2.agents[0]
    assert team2.teammates[0].count == 2


def test_reference_skill_and_placement_roundtrip():
    ref = ReferenceSkill(name="conv", description="참조")
    from daedalus.model.project import ReferencePlacement
    placement = ReferencePlacement(skill_name="conv", x=5.0, y=6.0,
                                   connected_states=["A"])
    p = PluginProject(name="P", skills=[ref], reference_placements=[placement])
    p2 = _roundtrip(p)
    assert p2.skills[0].name == "conv"
    assert p2.reference_placements[0].skill_name == "conv"
    assert p2.reference_placements[0].connected_states == ["A"]


def test_dangling_skill_ref_becomes_none():
    """존재하지 않는 skill_ref id는 None 처리 (ValueError 아님)."""
    proc, shared = _make_proc_skill()
    p = PluginProject(name="P", skills=[shared, proc])
    data = serialize_project(p)
    # shared 스킬을 제거 → 두 상태의 skill_ref가 dangling
    data["skills"] = [s for s in data["skills"] if s["name"] != "shared"]
    p2 = deserialize_project(data)  # 예외 없이 통과해야 함
    proc2 = next(s for s in p2.skills if s.name == "proc")
    assert proc2.fsm.states[0].skill_ref is None


# ─────────────────────── 순수성 ───────────────────────


def test_serialize_is_pyqt_free():
    """serialize.py(및 daedalus.model)가 PySide6 없이 import 가능해야 한다."""
    import subprocess
    import sys

    code = (
        "import builtins\n"
        "_real = builtins.__import__\n"
        "def _blocked(name, *a, **k):\n"
        "    if name == 'PySide6' or name.startswith('PySide6.'):\n"
        "        raise ImportError('PySide6 import blocked for purity test')\n"
        "    return _real(name, *a, **k)\n"
        "builtins.__import__ = _blocked\n"
        "from daedalus.model.serialize import serialize_project, deserialize_project\n"
        "from daedalus.model.project import PluginProject\n"
        "d = serialize_project(PluginProject(name='x'))\n"
        "assert deserialize_project(d).name == 'x'\n"
        "print('OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"PySide6 차단 하에 serialize import 실패:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "OK" in result.stdout


# ─────────────────────── WP-M/N 합류 라운드트립 ───────────────────────


def test_parallel_state_join_roundtrip():
    """ParallelState.join/join_count 직렬화 왕복."""
    from daedalus.model.fsm.join import JoinStrategy
    inner = SimpleState(name="I")
    inner_m = StateMachine(name="im", initial_state=inner, states=[inner])
    region = Region(name="r1", sub_machine=inner_m)
    par = ParallelState(name="Par", regions=[region],
                        join=JoinStrategy.N_OF, join_count=1)
    fsm = StateMachine(name="af", initial_state=par, states=[par])
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    par2 = p2.agents[0].fsm.states[0]
    assert par2.join is JoinStrategy.N_OF
    assert par2.join_count == 1


def test_parallel_state_join_default_roundtrip():
    from daedalus.model.fsm.join import JoinStrategy
    inner = SimpleState(name="I")
    inner_m = StateMachine(name="im", initial_state=inner, states=[inner])
    par = ParallelState(name="Par", regions=[Region(name="r", sub_machine=inner_m)])
    fsm = StateMachine(name="af", initial_state=par, states=[par])
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p2 = _roundtrip(PluginProject(name="P", agents=[agent]))
    par2 = p2.agents[0].fsm.states[0]
    assert par2.join is JoinStrategy.ALL
    assert par2.join_count is None


def test_project_blackboard_roundtrip():
    """PluginProject.blackboard(class_definitions/variables) 왕복."""
    dc = DynamicClass(
        name="TaskState", description="런타임 상태",
        fields=[DynamicField(name="step", field_type=FieldType.INT, required=True)],
    )
    v = Variable(name="phase", description="", scope=VariableScope.BLACKBOARD,
                 field_type=FieldType.STRING)
    p = PluginProject(
        name="P",
        blackboard=Blackboard(class_definitions=[dc], variables={"phase": v}),
    )
    p2 = _roundtrip(p)
    assert p2.blackboard.class_definitions[0].name == "TaskState"
    assert p2.blackboard.class_definitions[0].fields[0].field_type is FieldType.INT
    assert p2.blackboard.variables["phase"].scope is VariableScope.BLACKBOARD


def test_project_blackboard_default_empty():
    """기본 PluginProject.blackboard는 빈 블랙보드로 왕복."""
    p2 = _roundtrip(PluginProject(name="P"))
    assert p2.blackboard.class_definitions == []
    assert p2.blackboard.variables == {}
    assert p2.blackboard.parent is None


def test_toplevel_fsm_blackboard_parent_survives_roundtrip():
    """저장/로드 후에도 최상위 스킬/에이전트 FSM의 blackboard.parent가
    프로젝트 블랙보드로 재연결된다 (역직렬화 = 생성 경로)."""
    proc, shared = _make_proc_skill()
    entry = EntryPoint(name="e")
    afsm = StateMachine(name="af", initial_state=entry, states=[entry])
    agent = AgentDefinition(fsm=afsm, name="ag", description="d")
    p = PluginProject(name="P", skills=[shared, proc], agents=[agent])
    p2 = _roundtrip(p)

    proc2 = next(s for s in p2.skills if s.name == "proc")
    assert proc2.fsm.blackboard.parent is p2.blackboard
    assert p2.agents[0].fsm.blackboard.parent is p2.blackboard


def test_local_skill_fsm_blackboard_parent_survives_roundtrip():
    """에이전트 로컬 스킬 FSM의 blackboard.parent가 소유 에이전트 FSM
    블랙보드로 재연결된다."""
    entry = EntryPoint(name="e")
    afsm = StateMachine(name="af", initial_state=entry, states=[entry])
    agent = AgentDefinition(fsm=afsm, name="ag", description="d")

    ls = SimpleState(name="s")
    lfsm = StateMachine(name="lf", initial_state=ls, states=[ls])
    local = ProceduralSkill(fsm=lfsm, name="local-tool", description="d")
    agent.skills.append(local)

    p2 = _roundtrip(PluginProject(name="P", agents=[agent]))
    ag2 = p2.agents[0]
    assert ag2.skills[0].fsm.blackboard.parent is ag2.fsm.blackboard
    # 에이전트 자신은 프로젝트 블랙보드에 연결
    assert ag2.fsm.blackboard.parent is p2.blackboard


def test_delegation_placement_survives_round_trip():
    """위임 placement의 skill_ref가 저장/로드 왕복에서 유실되지 않는다 (WP-DG 리뷰 선재 결함)."""
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.delegation import DynamicWorkflowDef
    from daedalus.model.project import PluginProject
    from daedalus.model.serialize import deserialize_project, serialize_project

    deleg = DynamicWorkflowDef(name="wf", description="d", objective="do it")
    project = PluginProject(name="p", delegations=[deleg])
    project.graph.states.append(SimpleState(name="wf", skill_ref=deleg))

    warnings: list[str] = []
    restored = deserialize_project(serialize_project(project), collect_warnings=warnings)

    placements = [
        s for s in restored.graph.states
        if isinstance(s, SimpleState) and s.name == "wf"
    ]
    assert len(placements) == 1
    assert placements[0].skill_ref is restored.delegations[0]
    assert not warnings
