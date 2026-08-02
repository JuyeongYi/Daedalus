"""WP-IC Part A/E: entry_paths(EventDef 리스트) + Transition.target_port 직렬화 왕복.

단일 진실: docs/plans/2026-08-02-wp-ic-input-ports-entry-context.md Part A/E-1.
"""
from __future__ import annotations

import json

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _roundtrip(project: PluginProject) -> PluginProject:
    return deserialize_project(json.loads(json.dumps(serialize_project(project))))


# ─────────────────────── entry_paths 왕복 ───────────────────────


def test_procedural_skill_entry_paths_roundtrip():
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    skill = ProceduralSkill(
        fsm=fsm, name="proc", description="d",
        entry_paths=[EventDef("main", color="#112233", description="일반 진입")],
    )
    p = PluginProject(name="P", skills=[skill])
    p2 = _roundtrip(p)
    ep = p2.skills[0].entry_paths
    assert len(ep) == 1
    assert ep[0].name == "main"
    assert ep[0].color == "#112233"
    assert ep[0].description == "일반 진입"


def test_declarative_skill_entry_paths_roundtrip():
    skill = DeclarativeSkill(
        name="know", description="d",
        entry_paths=[EventDef("main"), EventDef("retry")],
    )
    p = PluginProject(name="P", skills=[skill])
    p2 = _roundtrip(p)
    ep = p2.skills[0].entry_paths
    assert [e.name for e in ep] == ["main", "retry"]


def test_agent_entry_paths_roundtrip():
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    afsm = StateMachine(name="af", initial_state=entry, states=[entry, done], final_states=[done])
    agent = AgentDefinition(
        fsm=afsm, name="ag", description="d",
        entry_paths=[EventDef("main", color="#aabbcc")],
    )
    p = PluginProject(name="P", agents=[agent])
    p2 = _roundtrip(p)
    ep = p2.agents[0].entry_paths
    assert len(ep) == 1
    assert ep[0].name == "main"
    assert ep[0].color == "#aabbcc"


def test_procedural_skill_entry_paths_missing_key_defaults_to_empty():
    """구버전 파일(entry_paths 키 부재) → 빈 리스트(기본 포트 1개), 경고 없음."""
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    skill = ProceduralSkill(fsm=fsm, name="proc", description="d")
    p = PluginProject(name="P", skills=[skill])
    data = serialize_project(p)
    del data["skills"][0]["entry_paths"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.skills[0].entry_paths == []
    assert warnings == []


def test_declarative_skill_entry_paths_missing_key_defaults_to_empty():
    skill = DeclarativeSkill(name="know", description="d")
    p = PluginProject(name="P", skills=[skill])
    data = serialize_project(p)
    del data["skills"][0]["entry_paths"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.skills[0].entry_paths == []
    assert warnings == []


def test_agent_entry_paths_missing_key_defaults_to_empty():
    entry = EntryPoint(name="entry")
    afsm = StateMachine(name="af", initial_state=entry, states=[entry])
    agent = AgentDefinition(fsm=afsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])
    data = serialize_project(p)
    del data["agents"][0]["entry_paths"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.agents[0].entry_paths == []
    assert warnings == []


# ─────────────────────── Transition.target_port 왕복 ───────────────────────


def test_transition_target_port_roundtrip():
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm = StateMachine(name="f", initial_state=a, states=[a, b])
    fsm.transitions.append(
        Transition(
            source=a, target=b, trigger=CompletionEvent(name="done"),
            target_port="retry",
        )
    )
    skill = ProceduralSkill(fsm=fsm, name="proc", description="d")
    p = PluginProject(name="P", skills=[skill])
    p2 = _roundtrip(p)
    t2 = p2.skills[0].fsm.transitions[0]
    assert t2.target_port == "retry"


def test_transition_target_port_default_empty_roundtrips():
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm = StateMachine(name="f", initial_state=a, states=[a, b])
    fsm.transitions.append(
        Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    )
    skill = ProceduralSkill(fsm=fsm, name="proc", description="d")
    p = PluginProject(name="P", skills=[skill])
    p2 = _roundtrip(p)
    assert p2.skills[0].fsm.transitions[0].target_port == ""


def test_transition_target_port_missing_key_defaults_to_empty():
    """구버전 파일(target_port 키 부재) → 빈 값(기본 포트), 경고 없음."""
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm = StateMachine(name="f", initial_state=a, states=[a, b])
    fsm.transitions.append(
        Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    )
    skill = ProceduralSkill(fsm=fsm, name="proc", description="d")
    p = PluginProject(name="P", skills=[skill])
    data = serialize_project(p)
    del data["skills"][0]["fsm"]["transitions"][0]["target_port"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.skills[0].fsm.transitions[0].target_port == ""
    assert warnings == []


# 프로젝트 그래프(project.graph)에 배치된 전이에도 동일하게 적용된다(그래프도
# _ser_machine/_deser_machine을 공유하므로 별도 분기 없음 — 회귀 방지용 확인).


def test_project_graph_transition_target_port_roundtrip():
    skill = ProceduralSkill(
        fsm=StateMachine(
            name="f",
            initial_state=(s := SimpleState(name="s")),
            states=[s],
        ),
        name="proc", description="d",
        entry_paths=[EventDef("retry")],
    )
    a = SimpleState(name="a")
    b = SimpleState(name="b", skill_ref=skill)
    p = PluginProject(name="P", skills=[skill])
    p.graph.states += [a, b]
    p.graph.transitions.append(
        Transition(
            source=a, target=b, trigger=CompletionEvent(name="done"),
            target_port="retry",
        )
    )
    p2 = _roundtrip(p)
    graph_t = [t for t in p2.graph.transitions if t.target.name == "b"][0]
    assert graph_t.target_port == "retry"
