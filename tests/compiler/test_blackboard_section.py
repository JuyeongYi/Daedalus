# tests/compiler/test_blackboard_section.py
"""WP-T Part B: 블랙보드 사용 지침 단락 ('## 공유 상태 (블랙보드)')."""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_declarative, make_procedural


def _project_with_classes(**kwargs) -> PluginProject:
    dc = DynamicClass(
        name="TaskState",
        description="작업 진행 상태",
        fields=[DynamicField(name="step", field_type=FieldType.INT)],
    )
    return PluginProject(
        name="p", blackboard=Blackboard(class_definitions=[dc]), **kwargs
    )


def test_global_procedural_skill_has_blackboard_section_before_next_steps():
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project = _project_with_classes(skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )

    text = compile_skill(a, project=project)
    assert "## 공유 상태 (블랙보드)" in text
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "## 다음 단계" in text
    assert text.index("## 공유 상태 (블랙보드)") < text.index("## 다음 단계")


def test_no_class_definitions_no_section():
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])
    text = compile_skill(a, project=project)
    assert "## 공유 상태 (블랙보드)" not in text


def test_local_skill_no_section():
    """로컬 스킬(에이전트 소유)은 단락을 받지 않는다 — 에이전트 .md가 이미 받는다."""
    a = make_procedural(name="local-proc")
    project = _project_with_classes()
    text = compile_skill(a, local=True, project=project)
    assert "## 공유 상태 (블랙보드)" not in text


def test_declarative_skill_no_section():
    kb = make_declarative("kb")
    project = _project_with_classes(skills=[kb])
    text = compile_skill(kb, project=project)
    assert "## 공유 상태 (블랙보드)" not in text


def test_compile_agent_has_blackboard_section_at_end():
    agent = make_agent("worker")
    project = _project_with_classes(agents=[agent])
    text = compile_agent(agent, project=project)
    assert "## 공유 상태 (블랙보드)" in text
    # 본문 마지막 단락 — 다른 텍스트가 이후에 없어야 한다
    assert text.rstrip().endswith(
        "- 스키마의 required 필드는 항상 채워라."
    )


def test_description_less_class_no_suffix():
    dc = DynamicClass(
        name="Plain", description="",
        fields=[DynamicField(name="x", field_type=FieldType.STRING)],
    )
    project = PluginProject(
        name="p", blackboard=Blackboard(class_definitions=[dc]),
        skills=[make_procedural(name="a")],
    )
    text = compile_skill(project.skills[0], project=project)
    assert "`Plain` → `state/Plain.json`" in text
    assert "`Plain` → `state/Plain.json` —" not in text
