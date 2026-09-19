"""외부 fork 에이전트 로드 마이그레이션 (WP-EX/WP-A, 2026-09-19) — format 2 내용 스니핑.

fork 스킬의 `agent`가 `플러그인:이름` 원문이면 그 원문마다 `external_fork_agent`
컴포넌트 하나를 만들고 스킬이 그 이름을 가리키게 바꾼다(역할 고정). 리뷰에서
드러난 두 결함 — 기존 컴포넌트를 못 보고 중복 생성, 이름 규약 위반 — 을 여기서
고정한다.
"""
from __future__ import annotations

import copy
import json

from daedalus.model.plugin.agent import ExternalForkAgent
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.serialize.migrate import (
    migrate_external_fork_agents,
    needs_external_fork_agent_migration,
)
from daedalus.model.validation import Validator


def _fork(name: str, agent: str, sid: str) -> dict:
    return {
        "kind": "sync_fork_skill", "id": sid, "name": name,
        "description": "d", "when_to_use": "", "body": "",
        "config": {"kind": "sync_fork", "agent": agent},
        "fsm": {"name": f"{name}-fsm", "states": [], "transitions": []},
    }


def _base(name: str, source: str, aid: str) -> dict:
    return {
        "kind": "external_fork_agent", "id": aid, "name": name, "description": "d",
        "body": "", "config": {"kind": "external_fork_agent", "source": source},
    }


def _data(skills, agents=()) -> dict:
    return {
        "format": 2, "name": "p",
        "external_plugins": ["hookify@mkt"],
        "skills": list(skills), "agents": list(agents),
        "graph": {"name": "g", "states": [], "transitions": []},
    }


def test_gate_sees_raw_refs_only():
    assert needs_external_fork_agent_migration(_data([_fork("s", "hookify:x", "s1")]))
    assert not needs_external_fork_agent_migration(_data([_fork("s", "critic", "s1")]))
    assert not needs_external_fork_agent_migration(_data([_fork("s", "general-purpose", "s1")]))


def test_one_component_per_source_and_skills_repointed():
    warnings: list[str] = []
    data = _data([_fork("a", "hookify:x", "s1"), _fork("b", "hookify:x", "s2"),
                  _fork("c", "other:y", "s3")])
    migrate_external_fork_agents(data, warnings)
    agents = data["agents"]
    assert [a["kind"] for a in agents] == ["external_fork_agent"] * 2
    assert {a["config"]["source"] for a in agents} == {"hookify:x", "other:y"}
    by_source = {a["config"]["source"]: a["name"] for a in agents}
    assert data["skills"][0]["config"]["agent"] == by_source["hookify:x"]
    assert data["skills"][1]["config"]["agent"] == by_source["hookify:x"]
    assert data["skills"][2]["config"]["agent"] == by_source["other:y"]
    assert len(warnings) == 2
    assert not needs_external_fork_agent_migration(data)


def test_existing_registered_component_is_reused():
    """이미 같은 source의 외부 fork 에이전트가 있으면 새로 만들지 않는다 —
    두 개면 `external_source_role_conflict` 에러가 새로 생긴다(리뷰 재현)."""
    warnings: list[str] = []
    data = _data([_fork("a", "hookify:x", "s1")], [_base("already", "hookify:x", "a1")])
    migrate_external_fork_agents(data, warnings)
    assert [a["name"] for a in data["agents"]] == ["already"]
    assert data["skills"][0]["config"]["agent"] == "already"
    assert warnings == []
    project = deserialize_project(_data([_fork("a", "hookify:x", "s1")],
                                        [_base("already", "hookify:x", "a1")]))
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "external_source_role_conflict" not in rules


def test_generated_names_follow_component_name_rules():
    """`hookify:Hook_Doctor` → `hook-doctor` — 규약 밖 이름을 만들면
    `invalid_component_name` 경고를 새로 낸다(리뷰 재현)."""
    data = _data([_fork("a", "hookify:Hook_Doctor", "s1"),
                  _fork("b", "pack:sub:Deep Name", "s2")])
    migrate_external_fork_agents(data, [])
    names = sorted(a["name"] for a in data["agents"])
    assert names == ["hook-doctor", "sub-deep-name"]
    project = deserialize_project(data)
    assert "invalid_component_name" not in [
        e.rule for e in Validator.validate_project(project)
    ]


def test_name_collision_falls_back_to_plugin_prefix():
    data = _data([_fork("x", "hookify:x", "s1")])  # 스킬 이름 `x`가 이미 있다
    migrate_external_fork_agents(data, [])
    assert data["agents"][0]["name"] == "hookify-x"


def test_migration_is_deterministic_across_loads():
    """두 번 로드해 직렬화하면 바이트가 같다 — id가 source 해시라 흔들리지 않는다."""
    raw = _data([_fork("a", "hookify:x", "s1")])

    def components() -> str:
        # 그래프 id는 픽스처에 없어 로드마다 새로 난다 — 마이그레이션 산물인
        # 컴포넌트(에이전트·스킬)만 비교한다.
        out = serialize_project(deserialize_project(copy.deepcopy(raw)))
        # 스킬의 fsm id도 픽스처에 없어 새로 난다 — 마이그레이션이 정하는 값만.
        return json.dumps({
            "agents": out["agents"],
            "skills": [(s["name"], s["config"]["agent"]) for s in out["skills"]],
        }, ensure_ascii=False, sort_keys=True)

    assert components() == components()
    project = deserialize_project(copy.deepcopy(raw))
    base = next(a for a in project.agents if isinstance(a, ExternalForkAgent))
    assert base.config.source == "hookify:x"
    assert project.skills[0].config.agent == base.name


def test_load_emits_a_warning_per_registration():
    warnings: list[str] = []
    deserialize_project(_data([_fork("a", "hookify:x", "s1")]), collect_warnings=warnings)
    assert any("hookify:x" in w and "외부 fork 에이전트" in w for w in warnings)
