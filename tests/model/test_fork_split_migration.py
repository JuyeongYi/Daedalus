"""fork 2종 분리 마이그레이션 (2026-09-17) — format 2 내용 스니핑.

format은 그대로(2)고 **내용**이 구버전인 파일을 로드 시 흡수한다
(`migrate_skill_context` 선례):
  1. `fork_skill` → `sync_fork_skill` (오늘 산출이 배치된 fork에 `background:
     false`를 냈으므로 동기가 종전 동작이다).
  2. 미배치 + fork 스킬이 참조하는 프로젝트 에이전트 → `fork_agent` 종류.
"""
from __future__ import annotations

import copy

from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.config import (
    AsyncForkSkillConfig,
    ForkAgentConfig,
    SyncForkSkillConfig,
)
from daedalus.model.plugin.skill import AsyncForkSkill, SyncForkSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import (
    deserialize_project,
    migrate_fork_split,
    needs_fork_split_migration,
    serialize_project,
)


def _legacy_fork_project() -> dict:
    """구 단일 fork 종류 + 미배치 fork 에이전트를 가진 format 2 dict."""
    return {
        "format": 2,
        "name": "p",
        "skills": [
            {
                "kind": "fork_skill", "id": "s1", "name": "scout",
                "description": "d", "when_to_use": "", "body": "",
                "config": {"kind": "fork", "agent": "helper"},
                "fsm": {"name": "f", "states": [], "transitions": []},
            },
        ],
        "agents": [
            {
                "kind": "agent", "id": "a1", "name": "helper", "description": "d",
                "body": "", "config": {"kind": "agent", "background": True,
                                       "isolation": "worktree", "skills": []},
                "fsm": {"name": "af", "states": [], "transitions": []},
                "transfer_on": [{"name": "done"}],
                "call_agents": [],
                "execution_policy": {"mode": "fixed", "count": 1},
                "reference_placements": [],
                "graph_layout": {},
                "edge_layout": {},
            },
        ],
        "graph": {"name": "g", "states": [], "transitions": []},
    }


def test_gate_detects_legacy_content_and_ignores_current_files():
    assert needs_fork_split_migration(_legacy_fork_project()) is True
    project = PluginProject(name="p")
    project.skills.append(
        SyncForkSkill(
            fsm=None, name="scout", description="d",  # type: ignore[arg-type]
            config=SyncForkSkillConfig(agent="Explore"),
        )
    )
    # 새 형식은 게이트를 통과하지 않는다(재마이그레이션 없음).
    assert needs_fork_split_migration({"skills": [], "agents": []}) is False


def test_legacy_fork_becomes_sync_fork_and_agent_is_reclassified():
    warnings: list[str] = []
    project = deserialize_project(_legacy_fork_project(), collect_warnings=warnings)

    skill = project.skills[0]
    assert type(skill) is SyncForkSkill
    assert type(skill.config) is SyncForkSkillConfig
    assert skill.config.agent == "helper"

    agent = project.agents[0]
    assert type(agent) is ForkAgent
    assert type(agent.config) is ForkAgentConfig
    # 없는 개념의 잔재를 남기지 않는다.
    assert not hasattr(agent, "fsm")
    assert not hasattr(agent.config, "background")
    assert not hasattr(agent.config, "isolation")

    assert any("미배치 fork" in w and "scout" in w for w in warnings)
    assert any("fork 에이전트 종류로 이관" in w and "helper" in w for w in warnings)


def test_placed_fork_is_migrated_without_a_warning():
    """배치된 fork는 오늘도 `background: false`로 나갔다 — 동작이 바뀌지 않는다."""
    data = _legacy_fork_project()
    data["graph"]["states"] = [
        {"kind": "simple", "id": "st1", "name": "scout", "skill_ref": "s1"}
    ]
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert type(project.skills[0]) is SyncForkSkill
    assert not any("미배치 fork" in w for w in warnings)


def test_pseudo_states_without_skill_ref_do_not_crash():
    """pseudo 상태에는 `skill_ref` 키가 아예 없다 — 맨 첨자면 실존 파일이 전부 깨진다."""
    data = _legacy_fork_project()
    data["graph"]["states"] = [{"kind": "entry_point", "id": "e1", "name": "entry"}]
    warnings: list[str] = []
    migrate_fork_split(data, warnings)
    assert data["agents"][0]["kind"] == "fork_agent"


def test_missing_graph_and_config_keys_are_normal_input():
    """graph 키 부재(구버전)·config 키 부재(손편집)는 정상 입력이다."""
    data = _legacy_fork_project()
    del data["graph"]
    del data["agents"][0]["config"]
    warnings: list[str] = []
    migrate_fork_split(data, warnings)
    assert data["agents"][0]["kind"] == "fork_agent"
    assert data["agents"][0]["config"] == {"kind": "fork_agent"}


def test_unreferenced_unplaced_agent_stays_a_workflow_agent():
    data = _legacy_fork_project()
    data["skills"][0]["config"]["agent"] = "Explore"  # 프로젝트 에이전트를 안 쓴다
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert type(project.agents[0]) is AgentDefinition
    assert not any("fork 에이전트 종류로 이관" in w for w in warnings)


def test_external_plugin_fork_target_touches_nothing():
    """`플러그인:이름`은 프로젝트 에이전트가 아니다 — 아무것도 바뀌지 않는다."""
    data = _legacy_fork_project()
    data["skills"][0]["config"]["agent"] = "hookify:conversation-analyzer"
    before = copy.deepcopy(data["agents"])
    warnings: list[str] = []
    migrate_fork_split(data, warnings)
    assert data["agents"] == before


def test_v1_file_without_graph_migrates_cleanly():
    data = _legacy_fork_project()
    data["format"] = 1
    del data["graph"]
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert type(project.skills[0]) is SyncForkSkill
    assert type(project.agents[0]) is ForkAgent


def test_v1_context_fork_skill_gets_no_double_warning():
    """`migrate_skill_context`가 방금 fork로 바꾼 스킬에는 미배치 경고를 겹치지 않는다.

    그 경고문("이전 산출은 background 키가 없었다")은 v1 파일에는 거짓이다.
    """
    data = _legacy_fork_project()
    data["format"] = 1
    data["skills"][0]["kind"] = "procedural_skill"
    data["skills"][0]["config"] = {"kind": "procedural", "context": "fork", "agent": "helper"}
    warnings: list[str] = []
    project = deserialize_project(data, collect_warnings=warnings)
    assert type(project.skills[0]) is SyncForkSkill
    assert any("fork 스킬로 바꿨습니다" in w for w in warnings)
    assert not any("미배치 fork" in w for w in warnings)


# ── 새 형식 왕복 ────────────────────────────────────────────────────────

def test_async_fork_roundtrips_and_is_not_remigrated():
    project = PluginProject(name="p")
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState

    s = SimpleState(name="s")
    project.skills.append(
        AsyncForkSkill(
            fsm=StateMachine(name="f", states=[s], initial_state=s),
            name="scout", description="d",
            config=AsyncForkSkillConfig(agent="helper"),
        )
    )
    project.agents.append(ForkAgent(name="helper", description="d"))
    data = serialize_project(project)
    assert needs_fork_split_migration(data) is False
    warnings: list[str] = []
    again = deserialize_project(data, collect_warnings=warnings)
    assert warnings == []
    assert type(again.skills[0]) is AsyncForkSkill
    assert type(again.agents[0]) is ForkAgent
