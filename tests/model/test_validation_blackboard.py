"""WP-BB Part E: 블랙보드 접근 선언 검증 규칙 2종 테스트.

  dangling_blackboard_ref (경고) — reads/writes 문자열이 프로젝트 블랙보드에 없음
  orphan_blackboard_field (경고) — 어떤 상태도 참조하지 않는 필드

각 규칙 검출+미검출 + 등급 + 에이전트 FSM 재귀 검출.
"""
from __future__ import annotations

from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import CompositeState, ParallelState, Region, SimpleState
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import WARNING_RULES, Validator


def _rules(errors) -> set[str]:
    return {e.rule for e in errors}


def _blackboard() -> Blackboard:
    return Blackboard(class_definitions=[
        DynamicClass(
            name="TaskState",
            description="",
            fields=[DynamicField(name="step", field_type=FieldType.INT)],
        ),
    ])


def _skill_with_state(state: SimpleState) -> ProceduralSkill:
    fsm = StateMachine(name="f", states=[state], initial_state=state)
    return ProceduralSkill(fsm=fsm, name="proc", description="d")


# ── dangling_blackboard_ref ──


def test_dangling_blackboard_ref_detected_class():
    s = SimpleState(name="s", reads=["Ghost"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_detected_field():
    s = SimpleState(name="s", writes=["TaskState.ghost_field"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_not_detected_class():
    s = SimpleState(name="s", reads=["TaskState"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "dangling_blackboard_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_not_detected_field():
    s = SimpleState(name="s", writes=["TaskState.step"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "dangling_blackboard_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_empty_string_skipped():
    s = SimpleState(name="s", reads=[""])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "dangling_blackboard_ref" not in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_is_warning():
    assert "dangling_blackboard_ref" in WARNING_RULES


def test_dangling_blackboard_ref_detected_on_agent_fsm():
    s = SimpleState(name="s", reads=["Ghost"])
    fsm = StateMachine(name="af", states=[s], initial_state=s)
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    proj = PluginProject(name="p", agents=[agent], blackboard=_blackboard())
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_detected_in_nested_composite():
    """CompositeState.sub_machine 내부 상태도 재귀 검출된다."""
    inner = SimpleState(name="inner", reads=["Ghost"])
    inner_sm = StateMachine(name="inner_sm", states=[inner], initial_state=inner)
    comp = CompositeState(name="comp", sub_machine=inner_sm)
    fsm = StateMachine(name="af", states=[comp], initial_state=comp)
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    proj = PluginProject(name="p", agents=[agent], blackboard=_blackboard())
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_detected_in_region():
    """ParallelState.regions 내부 상태도 재귀 검출된다."""
    inner = SimpleState(name="inner", writes=["Ghost"])
    inner_sm = StateMachine(name="inner_sm", states=[inner], initial_state=inner)
    region = Region(name="r1", sub_machine=inner_sm)
    from daedalus.model.fsm.state import ParallelState as _PS
    par = _PS(name="par", regions=[region])
    fsm = StateMachine(name="af", states=[par], initial_state=par)
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    proj = PluginProject(name="p", agents=[agent], blackboard=_blackboard())
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


def test_dangling_blackboard_ref_detected_on_project_graph():
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.model.fsm.transition import Transition

    s = SimpleState(name="s", reads=["Ghost"])
    proj = PluginProject(name="p", blackboard=_blackboard())
    entry = next(st for st in proj.graph.states if isinstance(st, EntryPoint))
    proj.graph.states.append(s)
    proj.graph.transitions.append(Transition(source=entry, target=s))
    assert "dangling_blackboard_ref" in _rules(Validator.validate_project(proj))


# ── orphan_blackboard_field ──


def test_orphan_blackboard_field_detected():
    """아무 상태도 필드를 참조하지 않으면 경고."""
    s = SimpleState(name="s", reads=["OtherClass"])
    bb = Blackboard(class_definitions=[
        DynamicClass(name="TaskState", description="", fields=[
            DynamicField(name="step", field_type=FieldType.INT),
        ]),
        DynamicClass(name="OtherClass", description="", fields=[]),
    ])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=bb)
    errs = [e for e in Validator.validate_project(proj) if e.rule == "orphan_blackboard_field"]
    assert any("TaskState.step" in e.message for e in errs)


def test_orphan_blackboard_field_not_detected_when_field_referenced():
    s = SimpleState(name="s", writes=["TaskState.step"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "orphan_blackboard_field" not in _rules(Validator.validate_project(proj))


def test_orphan_blackboard_field_not_detected_when_class_referenced():
    """클래스 전체 참조는 그 클래스의 모든 필드를 커버한 것으로 간주."""
    s = SimpleState(name="s", reads=["TaskState"])
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "orphan_blackboard_field" not in _rules(Validator.validate_project(proj))


def test_orphan_blackboard_field_skipped_when_no_declarations_at_all():
    """프로젝트 전체에 접근 선언이 하나도 없으면 스킵 (경고 폭주 방지)."""
    s = SimpleState(name="s")
    proj = PluginProject(name="p", skills=[_skill_with_state(s)], blackboard=_blackboard())
    assert "orphan_blackboard_field" not in _rules(Validator.validate_project(proj))


def test_orphan_blackboard_field_no_classes_no_warning():
    s = SimpleState(name="s")
    proj = PluginProject(name="p", skills=[_skill_with_state(s)])
    assert "orphan_blackboard_field" not in _rules(Validator.validate_project(proj))


def test_orphan_blackboard_field_is_warning():
    assert "orphan_blackboard_field" in WARNING_RULES
