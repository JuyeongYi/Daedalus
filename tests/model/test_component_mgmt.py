"""tests/model/test_component_mgmt.py — rename_component / remove_component 단위 테스트."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject, ReferencePlacement, remove_component, rename_component


# ---------------------------------------------------------------------------
# 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}_fsm", initial_state=s, states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="")


def _make_agent(name: str) -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(name=f"{name}_fsm", initial_state=entry, states=[entry, done], final_states=[done])
    return AgentDefinition(fsm=fsm, name=name, description="")


def _make_project() -> PluginProject:
    return PluginProject(name="test-proj")


# ---------------------------------------------------------------------------
# rename_component 테스트
# ---------------------------------------------------------------------------

class TestRenameComponent:
    def test_renames_name(self):
        proj = _make_project()
        skill = _make_proc("foo")
        proj.skills.append(skill)

        rename_component(proj, skill, "bar")
        assert skill.name == "bar"

    def test_noop_on_same_name(self):
        proj = _make_project()
        skill = _make_proc("foo")
        proj.skills.append(skill)

        rename_component(proj, skill, "foo")
        assert skill.name == "foo"

    def test_updates_procedural_skill_config_agent(self):
        proj = _make_project()
        agent = _make_agent("my-agent")
        proj.agents.append(agent)

        other = _make_proc("caller")
        other.config = ProceduralSkillConfig(agent="my-agent")
        proj.skills.append(other)

        rename_component(proj, agent, "new-agent")
        assert other.config.agent == "new-agent"

    def test_does_not_update_unrelated_agent_ref(self):
        proj = _make_project()
        agent = _make_agent("my-agent")
        proj.agents.append(agent)

        other_agent = _make_agent("other-agent")
        proj.agents.append(other_agent)

        caller = _make_proc("caller")
        caller.config = ProceduralSkillConfig(agent="other-agent")
        proj.skills.append(caller)

        rename_component(proj, agent, "new-agent")
        assert caller.config.agent == "other-agent"  # 무관 참조 비변경

    def test_updates_agent_config_skills(self):
        proj = _make_project()
        skill = _make_proc("my-skill")
        proj.skills.append(skill)

        agent = _make_agent("ag")
        agent.config = AgentConfig(skills=["other-skill", "my-skill", "another"])
        proj.agents.append(agent)

        rename_component(proj, skill, "renamed-skill")
        assert "renamed-skill" in agent.config.skills
        assert "my-skill" not in agent.config.skills
        assert "other-skill" in agent.config.skills  # 무관 항목 유지

    def test_updates_project_reference_placements(self):
        proj = _make_project()
        ref = ReferenceSkill(name="ref-doc", description="")
        proj.skills.append(ref)
        proj.reference_placements.append(ReferencePlacement(skill_name="ref-doc", x=0, y=0))

        rename_component(proj, ref, "new-doc")
        assert proj.reference_placements[0].skill_name == "new-doc"

    def test_updates_agent_reference_placements(self):
        proj = _make_project()
        ref = ReferenceSkill(name="ref-doc", description="")
        proj.skills.append(ref)

        agent = _make_agent("ag")
        agent.reference_placements.append(ReferencePlacement(skill_name="ref-doc"))
        proj.agents.append(agent)

        rename_component(proj, ref, "new-doc")
        assert agent.reference_placements[0].skill_name == "new-doc"

    def test_does_not_touch_hooks_keys(self):
        """hooks 키는 hook_library HookDef.name 참조 — 컴포넌트 이름 변경과 무관."""
        proj = _make_project()
        skill = _make_proc("foo")
        skill.config.hooks = {"my-hook": {}}
        proj.skills.append(skill)

        rename_component(proj, skill, "bar")
        assert "my-hook" in skill.config.hooks  # hooks 키 비변경

    # --- 동명-다른타입 크로스타입 오갱신 방지 (리뷰 FAIL 1 회귀) ---

    def test_skill_rename_does_not_touch_agent_name_refs(self):
        """스킬 "x"와 에이전트 "x"가 동명일 때, 스킬 rename이
        ProceduralSkillConfig.agent(에이전트 이름 참조)를 오갱신하면 안 된다."""
        proj = _make_project()
        skill_x = _make_proc("x")
        agent_x = _make_agent("x")
        proj.skills.append(skill_x)
        proj.agents.append(agent_x)

        caller = _make_proc("caller")
        caller.config = ProceduralSkillConfig(agent="x")  # 에이전트 "x" 참조
        proj.skills.append(caller)

        rename_component(proj, skill_x, "skill-renamed")
        assert caller.config.agent == "x"  # 에이전트 참조 비변경
        assert skill_x.name == "skill-renamed"

    def test_agent_rename_does_not_touch_skill_name_refs(self):
        """에이전트 "x"와 스킬 "x"가 동명일 때, 에이전트 rename이
        AgentConfig.skills / ReferencePlacement.skill_name(스킬 이름 참조)을
        오갱신하면 안 된다."""
        proj = _make_project()
        skill_x = _make_proc("x")
        agent_x = _make_agent("x")
        proj.skills.append(skill_x)
        proj.agents.append(agent_x)

        user_agent = _make_agent("user")
        user_agent.config = AgentConfig(skills=["x"])  # 스킬 "x" 참조
        proj.agents.append(user_agent)
        proj.reference_placements.append(ReferencePlacement(skill_name="x"))

        rename_component(proj, agent_x, "agent-renamed")
        assert user_agent.config.skills == ["x"]  # 스킬 참조 비변경
        assert proj.reference_placements[0].skill_name == "x"
        assert agent_x.name == "agent-renamed"

    def test_agent_rename_updates_procedural_agent_ref(self):
        """에이전트 rename은 ProceduralSkillConfig.agent를 갱신해야 한다 (가드가
        정상 경로를 막지 않는지 확인)."""
        proj = _make_project()
        agent = _make_agent("ag")
        proj.agents.append(agent)
        caller = _make_proc("caller")
        caller.config = ProceduralSkillConfig(agent="ag")
        proj.skills.append(caller)

        rename_component(proj, agent, "new-ag")
        assert caller.config.agent == "new-ag"


# ---------------------------------------------------------------------------
# remove_component 테스트
# ---------------------------------------------------------------------------

class TestRemoveComponent:
    def test_removes_skill_from_project(self):
        proj = _make_project()
        skill = _make_proc("foo")
        proj.skills.append(skill)

        log = remove_component(proj, skill)
        assert skill not in proj.skills
        assert any("foo" in line for line in log)

    def test_removes_agent_from_project(self):
        proj = _make_project()
        agent = _make_agent("ag")
        proj.agents.append(agent)

        log = remove_component(proj, agent)
        assert agent not in proj.agents
        assert log  # 내역 있음

    def test_removes_graph_placement_and_transitions(self):
        proj = _make_project()
        skill = _make_proc("foo")
        proj.skills.append(skill)

        # graph에 placement 추가
        placement = SimpleState(name="foo-node")
        placement.skill_ref = skill
        entry = proj.graph.initial_state
        from daedalus.model.fsm.event import CompletionEvent
        trans = Transition(source=entry, target=placement, trigger=CompletionEvent(name="done"))
        proj.graph.states.append(placement)
        proj.graph.transitions.append(trans)
        proj.graph_layout[placement.id] = [100.0, 100.0]

        log = remove_component(proj, skill)
        assert placement not in proj.graph.states
        assert trans not in proj.graph.transitions
        assert placement.id not in proj.graph_layout
        assert any("캔버스" in line for line in log)

    def test_removes_reference_placements(self):
        proj = _make_project()
        ref = ReferenceSkill(name="ref-doc", description="")
        proj.skills.append(ref)
        proj.reference_placements.append(ReferencePlacement(skill_name="ref-doc"))

        agent = _make_agent("ag")
        agent.reference_placements.append(ReferencePlacement(skill_name="ref-doc"))
        proj.agents.append(agent)

        log = remove_component(proj, ref)
        assert len(proj.reference_placements) == 0
        assert len(agent.reference_placements) == 0
        assert any("참조 배치" in line for line in log)

    def test_nullifies_skill_ref_in_other_fsms(self):
        proj = _make_project()
        target = _make_proc("target")
        proj.skills.append(target)

        # 다른 스킬 FSM에 target을 skill_ref로 배치
        holder = _make_proc("holder")
        node = SimpleState(name="n")
        node.skill_ref = target
        holder.fsm.states.append(node)
        proj.skills.append(holder)

        log = remove_component(proj, target)
        assert node.skill_ref is None
        assert any("skill_ref" in line for line in log)

    def test_nullifies_skill_ref_in_nested_fsm(self):
        """CompositeState sub_machine 내부의 skill_ref도 None으로."""
        from daedalus.model.fsm.state import CompositeState

        proj = _make_project()
        target = _make_proc("target")
        proj.skills.append(target)

        # 에이전트 FSM 안에 skill_ref 배치
        agent = _make_agent("ag")
        inner_state = SimpleState(name="n")
        inner_state.skill_ref = target
        agent.fsm.states.append(inner_state)
        proj.agents.append(agent)

        remove_component(proj, target)
        assert inner_state.skill_ref is None

    def test_returns_log_list(self):
        proj = _make_project()
        skill = _make_proc("foo")
        proj.skills.append(skill)

        log = remove_component(proj, skill)
        assert isinstance(log, list)
        assert len(log) > 0

    # --- 동명-다른타입 오삭제 방지 + 삭제 후 검증 무크래시 (리뷰 FAIL 1/2 회귀) ---

    def test_agent_remove_preserves_same_name_skill_ref_placements(self):
        """에이전트 "x" 삭제 시 동명 스킬 "x"의 ReferencePlacement는 보존되어야 한다."""
        proj = _make_project()
        ref_x = ReferenceSkill(name="x", description="")
        agent_x = _make_agent("x")
        proj.skills.append(ref_x)
        proj.agents.append(agent_x)
        proj.reference_placements.append(ReferencePlacement(skill_name="x"))

        remove_component(proj, agent_x)
        assert len(proj.reference_placements) == 1  # 스킬 "x"의 배치 보존
        assert proj.reference_placements[0].skill_name == "x"

    def test_validate_project_no_crash_after_agent_remove(self):
        """에이전트 삭제 뒤 Validator.validate_project가 크래시 없이 동작해야 한다."""
        from daedalus.model.validation import Validator

        proj = _make_project()
        agent = _make_agent("my-ag")
        proj.agents.append(agent)

        remove_component(proj, agent)
        assert agent not in proj.agents

        errors = Validator.validate_project(proj)
        assert isinstance(errors, list)
