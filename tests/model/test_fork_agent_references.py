"""fork 에이전트 참조 — 개명·끊긴 참조·역참조 (2026-09-17).

`rename_component`의 불변식: "대상이 그대로 있는데 참조만 끊기면 그 편집이
조용히 고장을 만든다". fork 스킬의 `config.agent`가 가리키는 주 대상이 바로
fork 에이전트이므로, 개명 게이트가 에이전트 두 종류를 모두 봐야 한다.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import ForkAgent
from daedalus.model.plugin.config import ForkAgentConfig, SyncForkSkillConfig
from daedalus.model.plugin.skill import SyncForkSkill
from daedalus.model.project import PluginProject, rename_component
from daedalus.model.validation import Validator


def _fsm() -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name="m", states=[s], initial_state=s)


def _project(*, agent_skills=()) -> PluginProject:
    fork = SyncForkSkill(
        fsm=_fsm(), name="scout", description="d",
        config=SyncForkSkillConfig(agent="helper"),
    )
    helper = ForkAgent(
        name="helper", description="d",
        config=ForkAgentConfig(skills=list(agent_skills)),
    )
    return PluginProject(name="p", skills=[fork], agents=[helper])


def test_renaming_a_fork_agent_carries_the_fork_skill_reference():
    project = _project()
    rename_component(project, project.agents[0], "analyst")
    assert project.skills[0].config.agent == "analyst"


def test_renaming_a_skill_carries_fork_agent_config_skills():
    """`skills`는 AgentConfigBase 필드다 — fork 에이전트도 따라가야 한다."""
    project = _project(agent_skills=["scout"])
    rename_component(project, project.skills[0], "recon")
    assert project.agents[0].config.skills == ["recon"]


def test_dangling_fork_agent_skill_reference_is_reported():
    project = _project(agent_skills=["nope"])
    rules = [e.rule for e in Validator.validate_project(project)]
    assert rules.count("dangling_string_reference") == 1


def test_fork_skills_using_backs_the_delete_report():
    from daedalus.model.plugin.placement import fork_skills_using

    project = _project()
    assert fork_skills_using(project.agents[0], project) == ["scout"]
