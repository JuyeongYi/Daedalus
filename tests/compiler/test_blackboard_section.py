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


# ─────────────────────── WP-BB Part D-2: 접근 선언 기반 구체화 ───────────────────────


def _project_with_two_classes(**kwargs) -> PluginProject:
    task = DynamicClass(
        name="TaskState", description="작업 진행 상태",
        fields=[DynamicField(name="step", field_type=FieldType.INT)],
    )
    findings = DynamicClass(
        name="ReviewFindings", description="리뷰 결과",
        fields=[DynamicField(name="files", field_type=FieldType.LIST)],
    )
    return PluginProject(
        name="p", blackboard=Blackboard(class_definitions=[task, findings]), **kwargs
    )


def test_skill_with_access_declarations_shows_specific_reads_writes():
    """스킬 FSM 상태에 reads/writes가 있으면 일반 안내 대신 구체적 문구가 나온다."""
    a = make_procedural(name="a")
    s = a.fsm.states[0]  # analyze
    s.reads = ["TaskState"]
    s.writes = ["ReviewFindings.files"]
    project = _project_with_two_classes(skills=[a])

    text = compile_skill(a, project=project)
    assert "## 공유 상태 (블랙보드)" in text
    assert "이 스킬이 읽는 것: `TaskState`" in text
    assert "이 스킬이 쓰는 것: `ReviewFindings.files`" in text
    # 관련 클래스만 나열 — TaskState/ReviewFindings 둘 다 관련.
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "`ReviewFindings` → `state/ReviewFindings.json`" in text


def test_skill_access_declarations_narrow_file_list_to_relevant_classes():
    """선언된 클래스만 파일 목록에 나온다 — 무관한 클래스는 제외."""
    a = make_procedural(name="a")
    s = a.fsm.states[0]
    s.reads = ["TaskState"]
    project = _project_with_two_classes(skills=[a])

    text = compile_skill(a, project=project)
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "`ReviewFindings` → `state/ReviewFindings.json`" not in text


def test_skill_no_access_declarations_falls_back_to_general_guidance():
    """접근 선언이 없으면 기존(전 클래스 일반 안내) 동작 그대로 — 하위 호환."""
    a = make_procedural(name="a")
    project = _project_with_two_classes(skills=[a])
    text = compile_skill(a, project=project)
    assert "이 스킬이 읽는 것" not in text
    assert "이 스킬이 쓰는 것" not in text
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "`ReviewFindings` → `state/ReviewFindings.json`" in text


def test_skill_access_declarations_include_graph_placement_own_access():
    """FSM 내부 상태뿐 아니라 프로젝트 그래프 placement 자체의 reads/writes도 합류."""
    a = make_procedural(name="a")
    project = _project_with_two_classes(skills=[a])
    sa = SimpleState(name="a-placement", skill_ref=a, reads=["ReviewFindings"])
    project.graph.states.append(sa)

    text = compile_skill(a, project=project)
    assert "이 스킬이 읽는 것: `ReviewFindings`" in text


def test_agent_with_access_declarations_shows_specific_reads_writes():
    agent = make_agent("worker")
    work = next(s for s in agent.fsm.states if s.name == "work")
    work.writes = ["TaskState.step"]
    project = _project_with_two_classes(agents=[agent])

    text = compile_agent(agent, project=project)
    assert "이 에이전트가 쓰는 것: `TaskState.step`" in text
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "`ReviewFindings` → `state/ReviewFindings.json`" not in text


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
