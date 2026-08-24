"""스킬 노드 액션 3종 — 미리보기 / 모델·effort / 관련 경고 (A9-1,2,3).

**로직은 여기서만 검사한다.** 캔버스 우클릭 메뉴와 에디터 버튼은 이 함수들을
부르는 호출부일 뿐이라, 그쪽 테스트는 "부르는가"만 본다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import EffortLevel, ModelType
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import ValidationError, Validator
from daedalus.view.actions import model_effort as me
from daedalus.view.actions.preview import preview_text, preview_title
from daedalus.view.actions.warnings import findings_for
from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _proc(name: str = "worker") -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def _agent(name: str = "runner") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="af", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name=name, description="d", transfer_on=[EventDef(name="done")],
    )


@pytest.fixture
def vm() -> ProjectViewModel:
    return ProjectViewModel()


# --- A9-1 컴파일 미리보기 ---


def test_preview_returns_skill_markdown():
    skill = _proc()
    skill.body = "## 절차\n\n하라."
    text = preview_text(skill)
    assert text.startswith("---")
    assert "name: worker" in text
    assert "## 절차" in text


def test_preview_matches_the_real_compiler():
    """미리보기가 컴파일과 다른 텍스트를 내면 미리보기가 아니다."""
    from daedalus.compiler.emit import compile_skill

    skill = _proc()
    project = PluginProject(name="p", skills=[skill])
    project.graph.states.append(SimpleState(name="worker", skill_ref=skill))
    assert preview_text(skill, project=project) == compile_skill(skill, project=project)


def test_preview_includes_graph_derived_sections():
    """project를 주면 그래프에서 유도되는 단락까지 실제와 같이 나온다."""
    a, b = _proc("alpha"), _proc("beta")
    project = PluginProject(name="p", skills=[a, b])
    na = SimpleState(name="alpha", skill_ref=a)
    nb = SimpleState(name="beta", skill_ref=b)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(Transition(source=na, target=nb))

    text = preview_text(a, project=project)
    assert "## Next Steps" in text
    assert "beta" in text


def test_preview_of_agent_uses_agent_compiler():
    agent = _agent()
    text = preview_text(agent)
    assert "name: runner" in text


def test_preview_title_names_the_output_file():
    assert preview_title(_proc()) == "컴파일 미리보기 — skills/worker/SKILL.md"
    assert preview_title(_agent()) == "컴파일 미리보기 — agents/runner.md"


# --- A9-2 모델 / effort ---


def test_supports_model_effort():
    assert me.supports_model_effort(_proc()) is True
    assert me.supports_model_effort(_agent()) is True
    assert me.supports_model_effort(None) is False


def test_set_model_is_undoable(vm):
    skill = _proc()
    assert me.set_model(vm, skill, ModelType.SONNET) is True
    assert skill.config.model is ModelType.SONNET

    vm.command_stack.undo()
    assert skill.config.model is ModelType.INHERIT


def test_set_effort_including_none(vm):
    skill = _proc()
    me.set_effort(vm, skill, EffortLevel.HIGH)
    assert skill.config.effort is EffortLevel.HIGH

    assert me.set_effort(vm, skill, None) is True
    assert skill.config.effort is None
    vm.command_stack.undo()
    assert skill.config.effort is EffortLevel.HIGH


def test_setting_the_same_value_is_a_no_op(vm):
    skill = _proc()
    assert me.set_model(vm, skill, ModelType.INHERIT) is False
    assert vm.command_stack.history == []


def test_agent_uses_the_same_path(vm):
    """config 필드 이름이 같으므로 에이전트도 같은 함수를 탄다."""
    agent = _agent()
    me.set_model(vm, agent, ModelType.OPUS)
    assert agent.config.model is ModelType.OPUS


def test_choice_tables_cover_the_enums():
    """콤보/메뉴가 이 표를 순회한다 — enum이 늘면 표도 늘어야 한다."""
    assert {m for m, _ in me.MODEL_CHOICES} == set(ModelType)
    assert {e for e, _ in me.EFFORT_CHOICES if e is not None} == set(EffortLevel)
    assert me.EFFORT_CHOICES[0][0] is None  # 미지정이 첫 항목


# --- A9-3 관련 경고 필터 ---


def _mid_chain_project() -> tuple[PluginProject, ProceduralSkill, ProceduralSkill]:
    a, b = _proc("alpha"), _proc("beta")
    project = PluginProject(name="p", skills=[a, b])
    na = SimpleState(name="alpha", skill_ref=a)
    nb = SimpleState(name="beta", skill_ref=b)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(Transition(source=na, target=nb))
    return project, a, b


def test_filter_catches_placement_subject():
    """mid_chain_user_invocable의 subject는 컴포넌트가 아니라 **placement 노드**다 —
    subject == component만 보면 통째로 놓친다."""
    project, _a, b = _mid_chain_project()
    errors = Validator.validate_project(project)
    found = findings_for(errors, b, project)
    assert [e.rule for e in found] == ["mid_chain_user_invocable"]


def test_filter_excludes_other_components():
    project, a, _b = _mid_chain_project()
    errors = Validator.validate_project(project)
    assert findings_for(errors, a, project) == []


def test_filter_catches_component_subject():
    agent = _agent()
    agent.body = "파일: ${CLAUDE_SKILL_DIR}/x.md"
    project = PluginProject(name="p", agents=[agent])
    errors = Validator.validate_project(project)
    found = findings_for(errors, agent, project)
    assert [e.rule for e in found] == ["skill_dir_token_in_agent"]


def test_filter_catches_root_path_findings():
    """자체 FSM 규칙은 path 루트(`skill:<이름>`)로만 이 컴포넌트에 묶인다."""
    skill = _proc("alpha")
    orphan = SimpleState(name="orphan")
    skill.fsm.states.append(orphan)
    project = PluginProject(name="p", skills=[skill])
    errors = Validator.validate_project(project)

    found = findings_for(errors, skill, project)
    assert any(e.rule == "unreachable_state" for e in found)
    assert all(e.path[0] == "skill:alpha" for e in found)


def test_filter_without_project_still_matches_subject_and_path():
    """project가 없어도 placement 외 두 경로는 동작한다."""
    error = ValidationError(rule="x", message="m", subject=None, path=("skill:alpha",))
    assert findings_for([error], _proc("alpha")) == [error]


def test_filter_on_empty_input():
    assert findings_for([], _proc()) == []
