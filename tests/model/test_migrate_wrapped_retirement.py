# tests/model/test_migrate_wrapped_retirement.py
"""랩핑 스킬 퇴역 마이그레이션 고정 (WP-10, 2026-09-19).

`WrappedSkill`은 종류로서 사라지고 저장 파일은 **단방향**으로 흡수된다
(원칙 7 — 호환 잔재를 모델에 남기지 않는다). 무엇이 무엇이 되는지, 무엇이
경고로 알려지는지, 안정 id가 이어지는지를 여기서 못 박는다 — 변환 규칙이
조용히 바뀌면 사용자 파일이 말없이 다른 물건이 된다.

변환 규칙(사용자 확정 2026-09-19):
  - `enabled == False`      → 드롭 + 경고 1건 (참조 배치도 함께 걷는다)
  - `usage == "reference"`  → `reference_skill` (본문 첫 줄에 원본 source)
  - 그 밖(state·미정·부재) → `external_agent` (source·포트 승계, fsm 드롭)
"""
from __future__ import annotations

import copy

from daedalus.model.plugin.agent import ExternalAgent
from daedalus.model.plugin.skill import ReferenceSkill
from daedalus.model.serialize import deserialize_project
from daedalus.model.serialize.migrate import (
    migrate_wrapped_retirement,
    needs_wrapped_retirement_migration,
)


def _wrapped(name: str, *, usage: str, enabled: bool = True, **over) -> dict:
    d = {
        "kind": "wrapped_skill",
        "id": f"id-{name}",
        "name": name,
        "description": f"{name} description",
        "when_to_use": "when it comes up",
        "body": "",
        "config": {
            "kind": "wrapped",
            "model": "inherit",
            "effort": None,
            "hooks": None,
            "argument_hint": None,
            "allowed_tools": [],
            "paths": None,
            "source": f"ext-pack:{name}-source",
            "usage": usage,
            "enabled": enabled,
            "disable_model_invocation": None,
            "user_invocable": None,
        },
        "fsm": {
            "kind": "state_machine", "name": name, "states": [], "transitions": [],
        },
        "transfer_on": [{"name": "done", "color": "#4488ff", "description": ""}],
        "call_agents": [{"name": "helper", "color": "#888888", "description": ""}],
    }
    d.update(over)
    return d


def _project(*skills: dict, **over) -> dict:
    data = {
        "format": 2,
        "name": "proj",
        "description": "",
        "version": "0.1.0",
        "skills": list(skills),
        "agents": [],
        "external_plugins": ["ext-pack"],
    }
    data.update(over)
    return data


# ─────────────────────────── 게이트 ───────────────────────────

def test_gate_detects_wrapped_skill_only():
    assert needs_wrapped_retirement_migration(_project(_wrapped("w", usage="state")))
    assert not needs_wrapped_retirement_migration(_project())


# ─────────────────────── state 용도 → 외부 에이전트 ───────────────────────

def test_state_usage_becomes_external_agent_keeping_id_source_and_ports():
    data = _project(_wrapped("stepper", usage="state"))
    warnings: list[str] = []
    migrate_wrapped_retirement(data, warnings)

    assert data["skills"] == []
    (agent,) = data["agents"]
    assert agent["kind"] == "external_agent"
    assert agent["id"] == "id-stepper"
    assert agent["name"] == "stepper"
    assert agent["description"] == "stepper description"
    assert agent["config"] == {
        "kind": "external_agent", "source": "ext-pack:stepper-source",
    }
    # 포트는 승계한다 — 그래프 전이가 이 이름으로 이어져 있다.
    assert [e["name"] for e in agent["transfer_on"]] == ["done"]
    assert [e["name"] for e in agent["call_agents"]] == ["helper"]
    # 내부 FSM은 외부 에이전트에 없는 개념이다.
    assert "fsm" not in agent
    assert warnings == [
        "랩핑 스킬 'stepper'을(를) 외부 플러그인 에이전트로 이관했습니다 — "
        "source 'ext-pack:stepper-source'가 이제 **에이전트** 이름을 "
        "가리키므로 `플러그인[@마켓]:에이전트` 형식이 맞는지 확인하세요."
    ]


def test_undecided_and_missing_usage_follow_the_state_branch():
    """미정("")·키 부재는 state다 — 종전 `effective_placement`의 판정 그대로."""
    missing = _wrapped("nokey", usage="state")
    del missing["config"]["usage"]
    data = _project(_wrapped("blank", usage=""), missing)
    migrate_wrapped_retirement(data, [])

    assert [a["name"] for a in data["agents"]] == ["blank", "nokey"]


def test_graph_skill_ref_follows_by_stable_id():
    """배치된 랩핑 스킬 → 같은 id의 외부 에이전트. 노드는 그대로 살아 있다."""
    data = _project(
        _wrapped("stepper", usage="state"),
        graph={
            "kind": "state_machine", "name": "graph",
            "states": [
                {"kind": "simple", "name": "stepper", "skill_ref": "id-stepper"},
            ],
            "transitions": [],
        },
    )
    warnings: list[str] = []
    project = deserialize_project(copy.deepcopy(data), collect_warnings=warnings)

    assert project.skills == []
    (agent,) = project.agents
    assert isinstance(agent, ExternalAgent)
    assert agent.id == "id-stepper"
    assert agent.config.source == "ext-pack:stepper-source"
    (node,) = project.graph.states
    assert node.skill_ref is agent
    # dangling 경고가 아니라 이관 경고 하나만 난다.
    assert len(warnings) == 1 and "외부 플러그인 에이전트" in warnings[0]


# ──────────────────── reference 용도 → 참조 스킬 ────────────────────

def test_reference_usage_becomes_reference_skill_with_source_line():
    data = _project(_wrapped("guide", usage="reference"))
    warnings: list[str] = []
    migrate_wrapped_retirement(data, warnings)

    assert data["agents"] == []
    (skill,) = data["skills"]
    assert skill["kind"] == "reference_skill"
    assert skill["id"] == "id-guide"
    assert skill["body"] == "Source: `ext-pack:guide-source`\n"
    # 랩핑 전용 config 키는 떤다 — 퇴역 개념의 잔재를 새 종류에 남기지 않는다.
    assert skill["config"] == {
        "kind": "reference",
        "model": "inherit",
        "effort": None,
        "hooks": None,
        "argument_hint": None,
        "allowed_tools": [],
        "paths": None,
        "user_invocable": None,
    }
    # 참조 스킬에는 FSM도 포트도 없다.
    assert not ({"fsm", "transfer_on", "call_agents"} & set(skill))
    assert warnings == [
        "랩핑 스킬 'guide'을(를) 참조 스킬로 이관했습니다 — 본문 첫 줄에 "
        "원본 source를 남겼습니다(정본이 외부라는 사실은 더 이상 모델에 "
        "없습니다)."
    ]


def test_reference_usage_keeps_existing_body_below_the_source_line():
    data = _project(_wrapped("guide", usage="reference", body="# Notes\n\nUse it.\n"))
    migrate_wrapped_retirement(data, [])

    (skill,) = data["skills"]
    assert skill["body"] == (
        "Source: `ext-pack:guide-source`\n\n# Notes\n\nUse it.\n"
    )


def test_reference_usage_loads_as_reference_skill():
    data = _project(
        _wrapped("guide", usage="reference"),
        reference_placements=[{
            "skill_name": "guide", "x": 1.0, "y": 2.0, "connected_states": ["n"],
        }],
    )
    project = deserialize_project(data)

    (skill,) = project.skills
    assert isinstance(skill, ReferenceSkill)
    assert skill.id == "id-guide"
    # 참조 배치는 그대로다 — 이름이 바뀌지 않았다.
    assert [rp.skill_name for rp in project.reference_placements] == ["guide"]


# ─────────────────────── enabled=False → 드롭 ───────────────────────

def test_disabled_wrapped_is_dropped_with_one_warning():
    data = _project(
        _wrapped("retired", usage="state", enabled=False),
        _wrapped("also-retired", usage="reference", enabled=False),
        reference_placements=[
            {"skill_name": "also-retired", "x": 0.0, "y": 0.0,
             "connected_states": []},
            {"skill_name": "keeper", "x": 0.0, "y": 0.0, "connected_states": []},
        ],
    )
    warnings: list[str] = []
    migrate_wrapped_retirement(data, warnings)

    assert data["skills"] == [] and data["agents"] == []
    # 가리킬 대상이 없어진 참조 배치도 함께 걷는다.
    assert [rp["skill_name"] for rp in data["reference_placements"]] == ["keeper"]
    assert warnings == [
        "비활성 랩핑 스킬 'retired'을(를) 드롭했습니다 — 랩핑 스킬은 퇴역한 "
        "개념이고, 꺼 둔 랩퍼는 산출·배선 어디에도 나가지 않았습니다.",
        "비활성 랩핑 스킬 'also-retired'을(를) 드롭했습니다 — 랩핑 스킬은 "
        "퇴역한 개념이고, 꺼 둔 랩퍼는 산출·배선 어디에도 나가지 않았습니다.",
    ]


# ─────────────────────────── 형식 1 파일 ───────────────────────────

def test_v1_file_is_migrated_too():
    data = _project(_wrapped("stepper", usage="state"), format=1)
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)

    assert project.skills == []
    assert [type(a) for a in project.agents] == [ExternalAgent]


def test_other_skill_kinds_are_untouched():
    other = {
        "kind": "procedural_skill", "id": "id-p", "name": "p", "description": "",
        "when_to_use": "", "body": "", "config": {"kind": "procedural"},
        "fsm": {"kind": "state_machine", "name": "p", "states": [],
                "transitions": []},
        "transfer_on": [{"name": "done", "color": "#4488ff", "description": ""}],
        "call_agents": [],
    }
    data = _project(other)
    before = copy.deepcopy(data)
    warnings: list[str] = []
    migrate_wrapped_retirement(data, warnings)

    assert data == before and warnings == []
