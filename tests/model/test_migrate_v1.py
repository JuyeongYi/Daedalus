# tests/model/test_migrate_v1.py
"""직렬화 포맷 v2 (WP-RF-1b) — v1 픽스처 마이그레이션 고정 + v2 왕복 항등.

v1 픽스처는 실제 구버전 파일이 가졌던 형태를 dict로 보관한다 — ``_migrate_v1``
이 다루는 각 축(sections 트리, ExitPoint 출력 포트, entry_paths/target_port/
caller_contracts 잔존, NUMBER 필드, delegations, 구버전 훅)을 고정한다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.hook import HookDef, CommandHook
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import (
    FORMAT_VERSION,
    deserialize_project,
    serialize_project,
)


# ─────────────────────── 포맷 게이트 ───────────────────────


def test_serialize_writes_format_2():
    assert FORMAT_VERSION == 2
    assert serialize_project(PluginProject(name="p"))["format"] == 2


def test_unknown_higher_format_raises():
    with pytest.raises(ValueError):
        deserialize_project({"format": 3, "name": "future"})


def test_missing_format_treated_as_v1():
    """키 부재 구버전 파일도 _migrate_v1을 태워 읽는다 (에러 아님)."""
    p = deserialize_project({"name": "ancient"})
    assert p.name == "ancient"


def test_migration_does_not_mutate_input_dict():
    data = {"format": 1, "name": "p", "delegations": [{"name": "wf"}]}
    deserialize_project(data)
    assert data["format"] == 1
    assert "delegations" in data  # 입력 dict는 변형되지 않는다 (deepcopy)


# ─────────────────────── v1 픽스처 마이그레이션 ───────────────────────


def _v1_base() -> dict:
    """빈 v1 프로젝트 dict."""
    return {"format": 1, "name": "legacy", "skills": [], "agents": []}


def test_v1_sections_tree_flattened_to_body():
    data = _v1_base()
    data["skills"].append({
        "kind": "declarative_skill", "id": "s1", "name": "kb", "description": "d",
        "sections": [
            {"title": "Top", "content": "root", "children": [
                {"title": "Mid", "content": "mid", "children": []},
            ]},
        ],
    })
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    assert p.skills[0].body == "# Top\n\nroot\n\n## Mid\n\nmid"
    assert warnings == []


def test_v1_legacy_file_refs_replaced_in_body():
    """WP-RT — ${CLAUDE_PLUGIN_ROOT}/files/ → ${ROOT}/files/ (files/ 참조만)."""
    data = _v1_base()
    data["skills"].append({
        "kind": "declarative_skill", "id": "s1", "name": "kb", "description": "d",
        "body": (
            "참조: ${CLAUDE_PLUGIN_ROOT}/files/doc.txt\n"
            "스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"
        ),
    })
    p = deserialize_project(data)
    assert "${ROOT}/files/doc.txt" in p.skills[0].body
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" in p.skills[0].body


def test_v1_exit_points_inherited_as_transfer_on():
    """WP-AF — transfer_on 키 부재 시 내부 FSM ExitPoint의 이름·색 승계."""
    data = _v1_base()
    data["agents"].append({
        "kind": "agent", "id": "a1", "name": "worker", "description": "d",
        "fsm": {
            "id": "f1", "name": "af",
            "states": [
                {"kind": "entry_point", "id": "e1", "name": "entry"},
                {"kind": "exit_point", "id": "x1", "name": "ok", "color": "#44aa44"},
                {"kind": "exit_point", "id": "x2", "name": "fail", "color": "#aa4444"},
            ],
            "transitions": [], "initial_state": "e1", "final_states": ["x1", "x2"],
        },
    })
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    ag = p.agents[0]
    assert [(e.name, e.color) for e in ag.transfer_on] == [
        ("ok", "#44aa44"), ("fail", "#aa4444"),
    ]
    assert warnings == []


def test_v1_explicit_transfer_on_wins_over_exit_points():
    """transfer_on이 이미 있으면 ExitPoint 승계는 일어나지 않는다."""
    data = _v1_base()
    data["agents"].append({
        "kind": "agent", "id": "a1", "name": "worker", "description": "d",
        "transfer_on": [{"name": "done", "color": "#123456", "description": ""}],
        "fsm": {
            "id": "f1", "name": "af",
            "states": [
                {"kind": "entry_point", "id": "e1", "name": "entry"},
                {"kind": "exit_point", "id": "x1", "name": "stale", "color": "#000000"},
            ],
            "transitions": [], "initial_state": "e1", "final_states": [],
        },
    })
    p = deserialize_project(data)
    assert [e.name for e in p.agents[0].transfer_on] == ["done"]


def test_v1_retired_keys_silently_dropped():
    """entry_paths / target_port / caller_contracts — 퇴역 개념, 경고 없이 드롭."""
    data = _v1_base()
    data["skills"].append({
        "kind": "procedural_skill", "id": "s1", "name": "proc", "description": "d",
        "entry_paths": [{"name": "main", "color": "#112233", "description": ""}],
        "fsm": {
            "id": "f1", "name": "f",
            "states": [
                {"kind": "simple", "id": "st1", "name": "a"},
                {"kind": "simple", "id": "st2", "name": "b"},
            ],
            "transitions": [{
                "id": "t1", "source": "st1", "target": "st2",
                "trigger": {"kind": "completion", "name": "done"},
                "target_port": "retry",
            }],
            "initial_state": "st1", "final_states": ["st2"],
        },
    })
    data["agents"].append({
        "kind": "agent", "id": "a1", "name": "worker", "description": "d",
        "entry_paths": [{"name": "in", "color": "#aabbcc", "description": ""}],
        "caller_contracts": [
            {"title": "caller: proc (done)", "content": "입력", "children": []},
        ],
        "transfer_on": [{"name": "done", "color": "#4488ff", "description": ""}],
        "fsm": {
            "id": "f2", "name": "af",
            "states": [{"kind": "entry_point", "id": "e1", "name": "entry"}],
            "transitions": [], "initial_state": "e1", "final_states": [],
        },
    })
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    assert warnings == []
    skill = p.skills[0]
    agent = p.agents[0]
    assert not hasattr(skill, "entry_paths")
    assert not hasattr(agent, "entry_paths")
    assert not hasattr(agent, "caller_contracts")
    assert not hasattr(skill.fsm.transitions[0], "target_port")
    # 재직렬화(v2)에도 퇴역 키가 나가지 않는다
    out = serialize_project(p)
    text = json.dumps(out, ensure_ascii=False)
    for key in ("entry_paths", "target_port", "caller_contracts"):
        assert key not in text


def test_v1_number_field_type_becomes_float():
    """FieldType.NUMBER 퇴역 — v1의 "number"는 FLOAT으로 읽는다 (블랙보드/변수)."""
    data = _v1_base()
    data["blackboard"] = {
        "class_definitions": [{
            "name": "TaskState", "description": "",
            "fields": [
                {"name": "score", "field_type": "number", "collection": "none",
                 "default": None, "required": False},
            ],
        }],
        "variables": {
            "v": {"id": "v1", "name": "v", "description": "", "scope": "blackboard",
                  "field_type": "number", "required": False, "default": None,
                  "conflict_resolution": "last_write"},
        },
    }
    p = deserialize_project(data)
    assert p.blackboard.class_definitions[0].fields[0].field_type is FieldType.FLOAT
    assert p.blackboard.variables["v"].field_type is FieldType.FLOAT


def test_v1_delegations_dropped_with_warning():
    data = _v1_base()
    data["delegations"] = [
        {"kind": "dynamic_workflow", "id": "d1", "name": "wf", "description": "d"},
    ]
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    assert not hasattr(p, "delegations")
    assert any("위임 정의 1건" in w and "드롭" in w for w in warnings)


# ─────────────────────── 로컬 스킬 → 전역 승격 (WP-RF-1c) ───────────────────────


def _v1_agent_with_local(local: dict, agent_extra: dict | None = None) -> dict:
    data = _v1_base()
    agent = {
        "kind": "agent", "id": "a1", "name": "worker", "description": "d",
        "fsm": {
            "id": "f1", "name": "af",
            "states": [{"kind": "entry_point", "id": "e1", "name": "entry"}],
            "transitions": [], "initial_state": "e1", "final_states": [],
        },
        "skills": [local],
    }
    agent.update(agent_extra or {})
    data["agents"].append(agent)
    return data


def _v1_local_proc(name: str = "helper", **extra) -> dict:
    d = {
        "kind": "procedural_skill", "id": "ls1", "name": name, "description": "ld",
        "fsm": {
            "id": "lf1", "name": "lf",
            "states": [{"kind": "simple", "id": "ss1", "name": "start"}],
            "transitions": [], "initial_state": "ss1", "final_states": [],
        },
    }
    d.update(extra)
    return d


def test_v1_local_skill_promoted_to_global_with_warning():
    """v1 에이전트 로컬 스킬은 전역 스킬로 승격된다 — 경고 1건, id 보존."""
    warnings: list[str] = []
    p = deserialize_project(
        _v1_agent_with_local(_v1_local_proc()), collect_warnings=warnings,
    )
    names = [s.name for s in p.skills]
    assert names == ["helper"]
    assert p.skills[0].id == "ls1"
    assert not hasattr(p.agents[0], "skills")
    assert any(
        "worker" in w and "helper" in w and "승격" in w for w in warnings
    ), warnings


def test_v1_promoted_local_skill_renamed_on_conflict():
    """전역 이름 충돌 시 '<agent>--<name>'으로 개명하고 경고에 명시한다."""
    data = _v1_agent_with_local(_v1_local_proc(name="helper"))
    data["skills"].append({
        "kind": "declarative_skill", "id": "g1", "name": "helper", "description": "d",
    })
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    names = {s.name for s in p.skills}
    assert names == {"helper", "worker--helper"}
    promoted = next(s for s in p.skills if s.name == "worker--helper")
    assert promoted.id == "ls1"
    assert any("개명" in w and "worker--helper" in w for w in warnings), warnings


def test_v1_promoted_local_skill_blackboard_parent_is_project():
    """승격된 스킬의 fsm 블랙보드 parent는 전역 스킬과 동일 경로 — 프로젝트
    블랙보드로 배선된다 (소유 에이전트 FSM 블랙보드가 아니다)."""
    p = deserialize_project(_v1_agent_with_local(_v1_local_proc()))
    promoted = p.skills[0]
    assert promoted.fsm.blackboard.parent is p.blackboard


def test_v1_promoted_local_skill_body_migrated():
    """승격된 스킬도 본문 마이그레이션(sections 평탄화 + 경로 변수 치환)을
    전역 스킬과 동일하게 받는다."""
    local = _v1_local_proc()
    local["sections"] = [{
        "title": "Top",
        "content": "${CLAUDE_PLUGIN_ROOT}/files/x.txt",
        "children": [],
    }]
    p = deserialize_project(_v1_agent_with_local(local))
    assert p.skills[0].body == "# Top\n\n${ROOT}/files/x.txt"


def test_v1_local_transfer_skill_ref_resolves_after_promotion():
    """에이전트 FSM 전이의 transfer skill_ref(id 참조)는 승격 후에도 해소된다."""
    local = {
        "kind": "transfer_skill", "id": "lt1", "name": "edge", "description": "d",
        "fsm": {
            "id": "tf1", "name": "tf",
            "states": [{"kind": "simple", "id": "ts1", "name": "s"}],
            "transitions": [], "initial_state": "ts1", "final_states": [],
        },
    }
    data = _v1_agent_with_local(local)
    agent = data["agents"][0]
    agent["fsm"]["states"].append({"kind": "simple", "id": "n1", "name": "step"})
    agent["fsm"]["transitions"].append({
        "id": "t1", "source": "e1", "target": "n1", "type": "external",
        "skill_ref": "lt1",
    })
    warnings: list[str] = []
    p = deserialize_project(data, collect_warnings=warnings)
    promoted = next(s for s in p.skills if s.name == "edge")
    trans = p.agents[0].fsm.transitions[0]
    assert trans.skill_ref is promoted
    assert not any("dangling" in w for w in warnings), warnings


def test_v1_legacy_hook_wrapped_as_command_handler():
    data = _v1_base()
    data["hook_library"] = [{
        "id": "h1", "name": "lint", "description": "", "event": "PostToolUse",
        "matcher": "Edit", "command": "run-lint", "timeout": 9,
    }]
    p = deserialize_project(data)
    handler = p.hook_library[0].handlers[0]
    assert handler.kind == "command"
    assert handler.script == "run-lint"
    assert handler.timeout == 9


# ─────────────────────── v2 왕복 항등 ───────────────────────


def _rich_project() -> PluginProject:
    s1 = SimpleState(name="analyze")
    s2 = SimpleState(name="report")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1, s2], final_states=[s2])
    fsm.transitions.append(
        Transition(source=s1, target=s2, trigger=CompletionEvent(name="done"))
    )
    proc = ProceduralSkill(
        fsm=fsm, name="proc", description="d",
        transfer_on=[EventDef("done", description="정상 완료")],
        call_agents=[EventDef("call-worker", color="#8a4a4a")],
        body="# 절차\n\n${ROOT}/files/doc.txt 참조",
    )
    decl = DeclarativeSkill(name="kb", description="지식", body="배경")
    e = EntryPoint(name="entry")
    entry_fsm = StateMachine(name="af", initial_state=e, states=[e])
    agent = AgentDefinition(
        fsm=entry_fsm, name="worker", description="일꾼",
        transfer_on=[EventDef("ok"), EventDef("fail", color="#aa4444")],
        body="에이전트 본문",
    )
    project = PluginProject(
        name="rich", description="v2 왕복", skills=[proc, decl], agents=[agent],
        hook_library=[HookDef(name="h", description="",
                              handlers=[CommandHook(script="echo hi")])],
    )
    pa = SimpleState(name="proc", skill_ref=proc)
    pb = SimpleState(name="worker", skill_ref=agent)
    project.graph.states += [pa, pb]
    project.graph.transitions.append(
        Transition(source=pa, target=pb, trigger=CompletionEvent(name="call-worker"))
    )
    project.graph_layout[pa.id] = [10.0, 20.0]
    project.edge_layout[project.graph.transitions[0].id] = [[5.0, 6.0]]
    return project


def test_v2_roundtrip_identity():
    """serialize → (json 왕복) → deserialize → serialize 가 항등이다.

    안정 ID 덕에 dict 차원에서 완전 동일해야 한다 — v2 리더가 어떤 키라도
    잃으면 여기서 잡힌다.
    """
    project = _rich_project()
    data1 = json.loads(json.dumps(serialize_project(project)))
    restored = deserialize_project(data1)
    data2 = json.loads(json.dumps(serialize_project(restored)))
    assert data2 == data1


def test_v2_read_has_no_migration_side_effects():
    """format 2 데이터는 마이그레이션 없이 그대로 읽힌다 — v1에서만 치환되는
    구버전 경로 변수(${CLAUDE_PLUGIN_ROOT}/files/)가 v2 본문에서는 보존된다."""
    p = PluginProject(name="p", skills=[
        DeclarativeSkill(name="kb", description="d",
                         body="${CLAUDE_PLUGIN_ROOT}/files/x.txt"),
    ])
    restored = deserialize_project(serialize_project(p))
    assert restored.skills[0].body == "${CLAUDE_PLUGIN_ROOT}/files/x.txt"
