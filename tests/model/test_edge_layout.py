"""WP-ER Part D-1 — edge_layout(엣지 웨이포인트) 직렬화 왕복.

graph_layout 전례를 미러링 — 키는 Transition.id, 값은 [x, y] 목록.
"""
from __future__ import annotations

import json

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _mk_skill_fsm(name: str) -> StateMachine:
    s = SimpleState(name="start")
    return StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)


def _mk_proc(name: str) -> ProceduralSkill:
    return ProceduralSkill(fsm=_mk_skill_fsm(name), name=name, description=f"{name}.")


# ─────────────────────── 기본값 ───────────────────────


def test_default_edge_layout_empty_project():
    p = PluginProject(name="p")
    assert p.edge_layout == {}


def test_agent_has_no_edge_layout():
    """에이전트의 `edge_layout`은 퇴역했다 (2026-09-19) — 그래프는 프로젝트 소유다."""
    e = EntryPoint(name="entry")
    x = ExitPoint(name="done")
    fsm = StateMachine(name="af", initial_state=e, states=[e, x], final_states=[x])
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    assert not hasattr(agent, "edge_layout")


# ─────────────────────── 프로젝트 그래프 왕복 ───────────────────────


def test_edge_layout_roundtrip_project():
    a = _mk_proc("a")
    b = _mk_proc("b")
    p = PluginProject(name="proj", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    p.graph.states += [sa, sb]
    t = Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    p.graph.transitions.append(t)
    p.edge_layout[t.id] = [[50.0, 60.0], [70.0, 80.0]]

    p2 = deserialize_project(json.loads(json.dumps(serialize_project(p))))

    t2 = p2.graph.transitions[0]
    assert t2.id in p2.edge_layout
    assert p2.edge_layout[t2.id] == [[50.0, 60.0], [70.0, 80.0]]


def test_old_version_without_edge_layout_key_project():
    """구버전 dict(edge_layout 키 없음) → 빈 dict + 경고 없음(하위 호환)."""
    data = {"format": 1, "name": "old", "skills": [], "agents": []}
    warns: list[str] = []
    p = deserialize_project(data, collect_warnings=warns)
    assert warns == []
    assert p.edge_layout == {}


# ─────────────────────── 에이전트 FSM 왕복 ───────────────────────


def test_agent_edge_layout_key_is_not_serialized():
    """에이전트 dict에 경유점 키가 나가지 않는다 — 구버전 키는 로드에서 무시된다.

    2026-09-19 퇴역: 에이전트는 그래프에 놓이는 노드이지 그래프를 소유하지
    않는다. 경유점 왕복의 실체는 `PluginProject.edge_layout` 하나다.
    """
    e = EntryPoint(name="entry")
    x = ExitPoint(name="done")
    fsm = StateMachine(name="af", initial_state=e, states=[e, x], final_states=[x])
    agent = AgentDefinition(fsm=fsm, name="ag", description="d")
    p = PluginProject(name="P", agents=[agent])

    data = serialize_project(p)
    assert "edge_layout" not in data["agents"][0]
    assert "graph_layout" not in data["agents"][0]

    data["agents"][0]["edge_layout"] = {"t-legacy": [[1.0, 2.0]]}
    p2 = deserialize_project(json.loads(json.dumps(data)))
    assert not hasattr(p2.agents[0], "edge_layout")
