"""WP-IC Part D: dangling_target_port 검증 규칙.

Transition.target_port가 비어 있지 않은데 타깃 skill_ref의 entry_paths 이름
집합에 없으면 경고(trigger_unknown_event의 입력판). 타깃이 skill_ref 없는
상태면 스킵. 단일 진실: docs/plans/2026-08-02-wp-ic-input-ports-entry-context.md Part D.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.validation import WARNING_RULES, Validator


def _sm(states, transitions=None, *, initial=None) -> StateMachine:
    if transitions is None:
        transitions = []
    return StateMachine(
        name="test", states=states, transitions=transitions,
        initial_state=initial or states[0],
    )


def _procedural(name: str, entry_paths=None) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name=name, description="", entry_paths=entry_paths or [])


def test_dangling_target_port_is_a_registered_warning_rule():
    assert "dangling_target_port" in WARNING_RULES


def test_dangling_target_port_warns_for_unknown_name():
    skill = _procedural("t", entry_paths=[EventDef("main"), EventDef("retry")])
    target = SimpleState(name="node", skill_ref=skill)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="ghost")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "dangling_target_port"]
    assert len(matching) == 1
    assert "ghost" in matching[0].message
    assert matching[0].is_warning


def test_dangling_target_port_passes_for_known_name():
    skill = _procedural("t", entry_paths=[EventDef("main"), EventDef("retry")])
    target = SimpleState(name="node", skill_ref=skill)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="retry")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "dangling_target_port" for e in errors)


def test_dangling_target_port_skips_empty_target_port():
    """target_port가 비어있으면(기본 포트) 항상 스킵 — entry_paths 유무와 무관."""
    skill = _procedural("t", entry_paths=[EventDef("main")])
    target = SimpleState(name="node", skill_ref=skill)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "dangling_target_port" for e in errors)


def test_dangling_target_port_skips_target_without_skill_ref():
    """타깃이 skill_ref 없는 상태(빈 SimpleState 등)면 스킵."""
    target = SimpleState(name="bare")
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="anything")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    assert not any(e.rule == "dangling_target_port" for e in errors)


def test_dangling_target_port_warns_when_no_entry_paths_declared():
    """entry_paths가 아예 빈 스킬(기본 포트 1개)에 target_port를 지정해도
    entry_paths 이름 집합이 비어 있으므로 dangling으로 경고한다."""
    skill = _procedural("t", entry_paths=[])
    target = SimpleState(name="node", skill_ref=skill)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="main")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "dangling_target_port"]
    assert len(matching) == 1


def test_dangling_target_port_warns_for_declarative_skill_target():
    skill = DeclarativeSkill(name="know", description="", entry_paths=[EventDef("main")])
    target = SimpleState(name="node", skill_ref=skill)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="ghost")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "dangling_target_port" for e in errors)


def test_dangling_target_port_warns_for_agent_target():
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    afsm = StateMachine(name="a_fsm", states=[entry, done], initial_state=entry, final_states=[done])
    agent = AgentDefinition(fsm=afsm, name="worker", description="", entry_paths=[EventDef("main")])
    target = SimpleState(name="node", skill_ref=agent)
    src = SimpleState(name="src")
    t = Transition(source=src, target=target, target_port="ghost")
    sm = _sm([src, target], [t])
    errors = Validator.validate(sm)
    assert any(e.rule == "dangling_target_port" for e in errors)
