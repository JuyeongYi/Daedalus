"""신규 Validator 규칙 테스트 (감사 2-3 WP-I).

규칙 8종:
  머신 수준 (5종):
    transition_endpoint_not_in_states
    duplicate_state_name
    unreachable_state
    invalid_data_map_source
    trigger_unknown_event
  프로젝트 수준 (3종):
    duplicate_component_name
    invalid_component_name
    dangling_string_reference

추가:
  ValidationError.path 누적 검증 (중첩 sub_machine)
"""
from __future__ import annotations

from daedalus.model.validation import ValidationError, Validator
from daedalus.model.fsm.state import SimpleState, CompositeState
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.variable import Variable
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig, AgentConfig
from daedalus.model.project import PluginProject, ReferencePlacement


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _sm(states, transitions=None, *, initial=None) -> StateMachine:
    if transitions is None:
        transitions = []
    return StateMachine(
        name="test",
        states=states,
        transitions=transitions,
        initial_state=initial or states[0],
    )


def _procedural(name: str, transfer_on=None) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(
        fsm=fsm,
        name=name,
        description="d",
        transfer_on=transfer_on or [EventDef("done")],
    )


def _agent_def(name: str, exit_names=("done",)) -> AgentDefinition:
    entry = EntryPoint(name="entry")
    exits = [ExitPoint(name=n) for n in exit_names]
    fsm = StateMachine(
        name=f"{name}_fsm",
        states=[entry, *exits],
        initial_state=entry,
        final_states=exits,
    )
    return AgentDefinition(fsm=fsm, name=name, description="")


# ===========================================================================
# ① ValidationError 필드 (subject / path 기본값 호환성)
# ===========================================================================

def test_validation_error_defaults():
    """subject/path 기본값이 존재하고 기존 생성자(rule, message, source)와 호환."""
    e = ValidationError(rule="test", message="m", source="s")
    assert e.subject is None
    assert e.path == ()


def test_validation_error_with_subject_and_path():
    obj = object()
    e = ValidationError(rule="r", message="m", source="s", subject=obj, path=("a", "b"))
    assert e.subject is obj
    assert e.path == ("a", "b")


# ===========================================================================
# ② 머신 수준 신규 규칙 5종
# ===========================================================================

# ---------------------------------------------------------------------------
# transition_endpoint_not_in_states
# ---------------------------------------------------------------------------

def test_transition_source_not_in_states_errors():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    orphan = SimpleState(name="orphan")  # states에 없음
    t = Transition(source=orphan, target=s1)
    sm = _sm([s1, s2], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "transition_endpoint_not_in_states"]
    assert len(matching) >= 1
    assert any("orphan" in e.message for e in matching)


def test_transition_target_not_in_states_errors():
    s1 = SimpleState(name="A")
    orphan = SimpleState(name="orphan")  # states에 없음
    t = Transition(source=s1, target=orphan)
    sm = _sm([s1], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "transition_endpoint_not_in_states"]
    assert len(matching) >= 1
    assert any("orphan" in e.message for e in matching)


def test_transition_endpoints_in_states_passes():
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    t = Transition(source=s1, target=s2)
    sm = _sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "transition_endpoint_not_in_states" for e in errors)


# ---------------------------------------------------------------------------
# duplicate_state_name
# ---------------------------------------------------------------------------

def test_duplicate_state_name_warns():
    s1 = SimpleState(name="Alpha")
    s2 = SimpleState(name="Alpha")  # 동명
    sm = _sm([s1, s2])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "duplicate_state_name"]
    assert len(matching) == 1
    assert "Alpha" in matching[0].message


def test_unique_state_names_passes():
    s1 = SimpleState(name="Alpha")
    s2 = SimpleState(name="Beta")
    sm = _sm([s1, s2])
    errors = Validator.validate(sm)
    assert not any(e.rule == "duplicate_state_name" for e in errors)


# ---------------------------------------------------------------------------
# unreachable_state
# ---------------------------------------------------------------------------

def test_unreachable_state_warns():
    s1 = SimpleState(name="start")
    s2 = SimpleState(name="reachable")
    s3 = SimpleState(name="island")   # s3으로 오는 전이 없음
    t = Transition(source=s1, target=s2)
    sm = _sm([s1, s2, s3], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "unreachable_state"]
    assert any("island" in e.message for e in matching)


def test_all_states_reachable_passes():
    s1 = SimpleState(name="start")
    s2 = SimpleState(name="next")
    s3 = SimpleState(name="end")
    t1 = Transition(source=s1, target=s2)
    t2 = Transition(source=s2, target=s3)
    sm = _sm([s1, s2, s3], [t1, t2])
    errors = Validator.validate(sm)
    assert not any(e.rule == "unreachable_state" for e in errors)


def test_entry_point_counts_as_start_for_reachability():
    """EntryPoint는 시작점으로 간주 — 해당 EP에서만 닿는 상태도 도달 가능."""
    ep = EntryPoint(name="ep")
    s1 = SimpleState(name="start")
    s2 = SimpleState(name="ep_target")
    t1 = Transition(source=s1, target=ep)
    t2 = Transition(source=ep, target=s2)
    sm = _sm([s1, ep, s2], [t1, t2])
    errors = Validator.validate(sm)
    assert not any(e.rule == "unreachable_state" for e in errors)


# ---------------------------------------------------------------------------
# invalid_data_map_source
# ---------------------------------------------------------------------------

def test_invalid_data_map_key_warns():
    s1 = SimpleState(
        name="A",
        outputs=[Variable(name="real_output", description="r")],
    )
    s2 = SimpleState(name="B")
    # data_map key "typo_key"는 s1.outputs에 없음
    t = Transition(source=s1, target=s2, data_map={"typo_key": "b_input"})
    sm = _sm([s1, s2], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "invalid_data_map_source"]
    assert len(matching) == 1
    assert "typo_key" in matching[0].message


def test_valid_data_map_key_passes():
    s1 = SimpleState(
        name="A",
        outputs=[Variable(name="result", description="r")],
    )
    s2 = SimpleState(
        name="B",
        inputs=[Variable(name="data", description="d", required=True)],
    )
    t = Transition(source=s1, target=s2, data_map={"result": "data"})
    sm = _sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "invalid_data_map_source" for e in errors)


def test_data_map_source_skips_pseudo_states():
    """pseudo 상태(EntryPoint 등) source는 스킵 — data_map key 검사 안 함."""
    ep = EntryPoint(name="ep")
    s1 = SimpleState(name="A")
    # EntryPoint는 pseudo 상태 → 검사 스킵 (에러 없음)
    t = Transition(source=ep, target=s1, data_map={"ghost_key": "x"})
    sm = _sm([ep, s1], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "invalid_data_map_source" for e in errors)


# ---------------------------------------------------------------------------
# trigger_unknown_event
# ---------------------------------------------------------------------------

def test_trigger_unknown_event_warns_for_procedural_skill():
    skill = _procedural("my-skill", transfer_on=[EventDef("success"), EventDef("fail")])
    state = SimpleState(name="node", skill_ref=skill)
    next_s = SimpleState(name="next")
    t = Transition(
        source=state,
        target=next_s,
        trigger=CompletionEvent(name="ghost"),  # 없는 이벤트
    )
    sm = _sm([state, next_s], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "trigger_unknown_event"]
    assert len(matching) == 1
    assert "ghost" in matching[0].message


def test_trigger_known_event_passes_for_procedural_skill():
    skill = _procedural("my-skill", transfer_on=[EventDef("done")])
    state = SimpleState(name="node", skill_ref=skill)
    next_s = SimpleState(name="next")
    t = Transition(
        source=state,
        target=next_s,
        trigger=CompletionEvent(name="done"),
    )
    sm = _sm([state, next_s], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "trigger_unknown_event" for e in errors)


def test_trigger_unknown_event_warns_for_agent():
    agent = _agent_def("worker", exit_names=["ok", "err"])
    state = SimpleState(name="node", skill_ref=agent)
    next_s = SimpleState(name="next")
    t = Transition(
        source=state,
        target=next_s,
        trigger=CompletionEvent(name="unknown"),
    )
    sm = _sm([state, next_s], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "trigger_unknown_event"]
    assert len(matching) == 1


def test_trigger_done_on_composite_state_passes():
    """CompositeState는 ExitPoint 이름 + 'done'이 유효."""
    inner_s = SimpleState(name="s")
    inner_sm = StateMachine(name="inner", states=[inner_s], initial_state=inner_s)
    cs = CompositeState(name="agent", sub_machine=inner_sm)
    next_s = SimpleState(name="next")
    t = Transition(
        source=cs,
        target=next_s,
        trigger=CompletionEvent(name="done"),
    )
    sm = _sm([cs, next_s], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "trigger_unknown_event" for e in errors)


def test_trigger_unknown_event_skips_no_skill_ref():
    """skill_ref 없는 SimpleState는 스킵 — 에러 없음."""
    s1 = SimpleState(name="bare")
    s2 = SimpleState(name="next")
    t = Transition(
        source=s1,
        target=s2,
        trigger=CompletionEvent(name="ghost"),
    )
    sm = _sm([s1, s2], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "trigger_unknown_event" for e in errors)


# ===========================================================================
# ③ 프로젝트 수준 신규 규칙 3종
# ===========================================================================

# ---------------------------------------------------------------------------
# duplicate_component_name
# ---------------------------------------------------------------------------

def test_duplicate_component_name_errors():
    project = PluginProject(name="p")
    skill1 = _procedural("my-tool")
    skill2 = _procedural("my-tool")  # 동명
    project.skills.extend([skill1, skill2])
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "duplicate_component_name"]
    assert len(matching) == 1
    assert "my-tool" in matching[0].message


def test_duplicate_name_across_skills_and_agents():
    """스킬과 에이전트에 걸쳐 동명이면 에러."""
    project = PluginProject(name="p")
    skill = _procedural("worker")
    agent = _agent_def("worker")
    project.skills.append(skill)
    project.agents.append(agent)
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "duplicate_component_name"]
    assert len(matching) == 1


def test_unique_component_names_passes():
    project = PluginProject(name="p")
    project.skills.append(_procedural("skill-a"))
    project.agents.append(_agent_def("agent-b"))
    errors = Validator.validate_project(project)
    assert not any(e.rule == "duplicate_component_name" for e in errors)


# ---------------------------------------------------------------------------
# invalid_component_name
# ---------------------------------------------------------------------------

def test_invalid_name_uppercase_warns():
    project = PluginProject(name="p")
    skill = _procedural("MySkill")   # 대문자 포함
    project.skills.append(skill)
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "invalid_component_name"]
    assert len(matching) == 1
    assert "MySkill" in matching[0].message


def test_invalid_name_starts_with_dash_warns():
    project = PluginProject(name="p")
    skill = _procedural("-bad-start")
    project.skills.append(skill)
    errors = Validator.validate_project(project)
    assert any(e.rule == "invalid_component_name" for e in errors)


def test_valid_component_name_passes():
    project = PluginProject(name="p")
    project.skills.append(_procedural("my-skill-01"))
    project.agents.append(_agent_def("agent-x"))
    errors = Validator.validate_project(project)
    assert not any(e.rule == "invalid_component_name" for e in errors)


# ---------------------------------------------------------------------------
# dangling_string_reference
# ---------------------------------------------------------------------------

def test_dangling_procedural_config_agent_warns():
    """ProceduralSkillConfig.agent가 존재하지 않는 에이전트명이면 경고."""
    project = PluginProject(name="p")
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm,
        name="my-skill",
        description="d",
        config=ProceduralSkillConfig(agent="nonexistent-agent"),
    )
    project.skills.append(skill)
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "dangling_string_reference"]
    assert len(matching) == 1
    assert "nonexistent-agent" in matching[0].message


def test_valid_procedural_config_agent_passes():
    project = PluginProject(name="p")
    agent = _agent_def("my-agent")
    project.agents.append(agent)
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm,
        name="my-skill",
        description="d",
        config=ProceduralSkillConfig(agent="my-agent"),
    )
    project.skills.append(skill)
    errors = Validator.validate_project(project)
    assert not any(e.rule == "dangling_string_reference" for e in errors)


def test_dangling_agent_config_skills_warns():
    """AgentConfig.skills에 존재하지 않는 스킬명이 있으면 경고."""
    project = PluginProject(name="p")
    agent = _agent_def("worker")
    agent.config = AgentConfig(skills=["ghost-skill"])
    project.agents.append(agent)
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "dangling_string_reference"]
    assert len(matching) == 1
    assert "ghost-skill" in matching[0].message


def test_agent_config_skill_in_local_skills_passes():
    """AgentConfig.skills에 에이전트 로컬 스킬이 있으면 통과."""
    project = PluginProject(name="p")
    local_skill = _procedural("local-tool")
    agent = _agent_def("worker")
    agent.config = AgentConfig(skills=["local-tool"])
    agent.skills.append(local_skill)
    project.agents.append(agent)
    errors = Validator.validate_project(project)
    assert not any(e.rule == "dangling_string_reference" for e in errors)


def test_dangling_reference_placement_warns():
    """reference_placements.skill_name이 존재하지 않는 스킬이면 경고."""
    project = PluginProject(name="p")
    project.reference_placements.append(ReferencePlacement(skill_name="missing-ref"))
    errors = Validator.validate_project(project)
    matching = [e for e in errors if e.rule == "dangling_string_reference"]
    assert len(matching) == 1
    assert "missing-ref" in matching[0].message


def test_valid_reference_placement_passes():
    project = PluginProject(name="p")
    from daedalus.model.plugin.skill import ReferenceSkill
    ref_skill = ReferenceSkill(name="my-ref", description="d")
    project.skills.append(ref_skill)
    project.reference_placements.append(ReferencePlacement(skill_name="my-ref"))
    errors = Validator.validate_project(project)
    assert not any(e.rule == "dangling_string_reference" for e in errors)


# ===========================================================================
# ④ ValidationError.path 누적 — 중첩 sub_machine 위반이 path를 담는지
# ===========================================================================

def test_validation_error_path_accumulated_in_nested_machine():
    """CompositeState 내부 sub_machine 위반 시 path에 'agent:...' 가 포함된다."""
    # 내부 sub_machine에 duplicate_state_name 위반을 심음
    inner_dup1 = SimpleState(name="dup")
    inner_dup2 = SimpleState(name="dup")  # 동명
    inner_sm = StateMachine(
        name="inner_flow",
        states=[inner_dup1, inner_dup2],
        initial_state=inner_dup1,
    )
    cs = CompositeState(name="WriterAgent", sub_machine=inner_sm)
    outer_sm = _sm([cs])

    errors = Validator.validate(outer_sm)
    dup_errors = [e for e in errors if e.rule == "duplicate_state_name"]
    assert len(dup_errors) == 1
    assert "agent:WriterAgent" in dup_errors[0].path


def test_validate_project_injects_root_path():
    """validate_project가 최상위 스킬/에이전트 FSM 오류에 root path를 주입한다."""
    project = PluginProject(name="p")
    agent = _agent_def("worker")
    # 에이전트 FSM에 duplicate_state_name 위반 심기
    agent.fsm.states.append(SimpleState(name="entry"))  # EntryPoint 'entry'와 동명
    project.agents.append(agent)

    errors = Validator.validate_project(project)
    dup_errors = [e for e in errors if e.rule == "duplicate_state_name"]
    assert len(dup_errors) == 1
    assert dup_errors[0].path == ("agent:worker",)
