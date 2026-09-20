# tests/compiler/test_blackboard_section.py
"""WP-T Part B / WP-BB Part D-2: 컴포넌트 잔여 단락 '## Shared State (Blackboard)'.

WP-FK2 C3 이후 이 단락에는 **이 컴포넌트에만 해당하는 사실**만 남는다 — 무엇을
읽고 쓰는가와 그에 해당하는 상태 파일 목록. 총론·CLI 사용법·규칙은
`guides/<플러그인>/blackboard.md`로 갔고, 그쪽 고정은 `test_guides.py`에 있다.
"""
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


# ─────────────────────── 배출 게이트 ───────────────────────


def test_global_procedural_skill_has_blackboard_section_before_next_steps():
    a = make_procedural(name="a")
    a.fsm.states[0].reads = ["TaskState"]
    b = make_procedural(name="b")
    project = _project_with_classes(skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )

    text = compile_skill(a, project=project)
    assert "## Shared State (Blackboard)" in text
    assert "`TaskState` → `state/p/TaskState.json`" in text
    assert "## Next Steps" in text
    assert text.index("## Shared State (Blackboard)") < text.index("## Next Steps")


def test_no_class_definitions_no_section():
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])
    text = compile_skill(a, project=project)
    assert "## Shared State (Blackboard)" not in text


def test_declarative_skill_no_section():
    kb = make_declarative("kb")
    project = _project_with_classes(skills=[kb])
    text = compile_skill(kb, project=project)
    assert "## Shared State (Blackboard)" not in text


def test_no_access_declarations_omits_the_section_entirely():
    """선언이 비면 단락 자체가 없다 — 총론은 가이드가 전부 말한다(WP-FK2 C3).

    잔여로 남길 **고유 정보가 없는데** 헤딩만 내면 스킬마다 같은 문장이 다시
    반복된다. 그것을 없애자는 것이 공통 안내 파일의 이유다.
    """
    a = make_procedural(name="a")
    project = _project_with_two_classes(skills=[a])
    text = compile_skill(a, project=project)
    assert "## Shared State (Blackboard)" not in text
    assert "This skill reads" not in text
    assert "This skill writes" not in text
    # 총론·도구 사용법·규칙 문장은 컴포넌트 산출에서 사라졌다 — 포인터 줄의
    # "Blackboard tools:" 한 줄만 남는다(어느 서버인지 말하는 자리).
    assert "## Blackboard tools" not in text
    assert "`progress_set`" not in text
    assert "Rules:\n- Always read a state file" not in text


def test_compile_agent_has_blackboard_section_at_end():
    agent = make_agent("worker")
    work = next(s for s in agent.fsm.states if s.name == "work")
    work.writes = ["TaskState.step"]
    project = _project_with_classes(agents=[agent])
    text = compile_agent(agent, project=project)
    assert "## Shared State (Blackboard)" in text
    # 본문 마지막 단락 — 다른 텍스트가 이후에 없어야 한다
    assert text.rstrip().endswith(
        "- `TaskState` → `state/p/TaskState.json` — 작업 진행 상태"
    )


def test_no_class_definitions_no_tool_directive():
    """블랙보드 정의가 없으면 가이드도 포인터도 없다 — 도구 이름이 아예 안 나온다."""
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])
    text = compile_skill(a, project=project)
    assert "bb-p__" not in text


def test_only_the_declared_access_changes_the_output():
    """선언의 차이는 두 자리에만 나타난다 — 이 단락과 유도된 도구 권한.

    WP-BM 전에는 단락 하나뿐이었다. 이제 reads 선언이 프론트매터의
    `allowed-tools`로도 번역되므로(캔버스 📖 뱃지와 산출 권한이 같은 사실을
    말한다) 두 자리다 — 그 **둘 말고는** 새지 않았음을 고정한다.
    """
    def _text(declare: bool) -> str:
        a = make_procedural(name="a")
        b = make_procedural(name="b")
        project = _project_with_classes(skills=[a, b])
        # 선언은 **그래프 placement** 쪽에 둔다 — 스킬 FSM 상태에 두면 절차
        # 단락의 접근 접미(`_describe_access`)까지 달라져 비교 대상이 둘이 된다.
        sa = SimpleState(
            name="a", skill_ref=a, reads=["TaskState"] if declare else [],
        )
        sb = SimpleState(name="b", skill_ref=b)
        project.graph.states += [sa, sb]
        project.graph.transitions.append(
            Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
        )
        return compile_skill(a, project=project)

    def _strip(text: str) -> str:
        """블랙보드 단락과 `allowed-tools` 줄을 뺀 나머지."""
        lines = [
            line for line in text.splitlines(keepends=True)
            if not line.startswith("allowed-tools:")
        ]
        rest = "".join(lines)
        head = "## Shared State (Blackboard)"
        if head not in rest:
            return rest
        return rest[:rest.index(head)] + rest[rest.index("## Next Steps"):]

    assert _strip(_text(True)) == _strip(_text(False))


# ─────────────────────── WP-BB Part D-2: 접근 선언 기반 구체화 ───────────────────────


def test_skill_with_access_declarations_shows_specific_reads_writes():
    """스킬 FSM 상태에 reads/writes가 있으면 그것과 관련 파일만 나온다."""
    a = make_procedural(name="a")
    s = a.fsm.states[0]  # analyze
    s.reads = ["TaskState"]
    s.writes = ["ReviewFindings.files"]
    project = _project_with_two_classes(skills=[a])

    text = compile_skill(a, project=project)
    assert "## Shared State (Blackboard)" in text
    assert "This skill reads: `TaskState`" in text
    assert "This skill writes: `ReviewFindings.files`" in text
    assert "`TaskState` → `state/p/TaskState.json`" in text
    assert "`ReviewFindings` → `state/p/ReviewFindings.json`" in text


def test_skill_access_declarations_narrow_file_list_to_relevant_classes():
    """선언된 클래스만 파일 목록에 나온다 — 무관한 클래스는 제외."""
    a = make_procedural(name="a")
    s = a.fsm.states[0]
    s.reads = ["TaskState"]
    project = _project_with_two_classes(skills=[a])

    text = compile_skill(a, project=project)
    assert "`TaskState` → `state/p/TaskState.json`" in text
    assert "`ReviewFindings` → `state/p/ReviewFindings.json`" not in text


def test_skill_access_declarations_include_graph_placement_own_access():
    """FSM 내부 상태뿐 아니라 프로젝트 그래프 placement 자체의 reads/writes도 합류."""
    a = make_procedural(name="a")
    project = _project_with_two_classes(skills=[a])
    sa = SimpleState(name="a-placement", skill_ref=a, reads=["ReviewFindings"])
    project.graph.states.append(sa)

    text = compile_skill(a, project=project)
    assert "This skill reads: `ReviewFindings`" in text


def test_agent_with_access_declarations_shows_specific_reads_writes():
    agent = make_agent("worker")
    work = next(s for s in agent.fsm.states if s.name == "work")
    work.writes = ["TaskState.step"]
    project = _project_with_two_classes(agents=[agent])

    text = compile_agent(agent, project=project)
    assert "This agent writes: `TaskState.step`" in text
    assert "`TaskState` → `state/p/TaskState.json`" in text
    assert "`ReviewFindings` → `state/p/ReviewFindings.json`" not in text


def test_description_less_class_no_suffix():
    dc = DynamicClass(
        name="Plain", description="",
        fields=[DynamicField(name="x", field_type=FieldType.STRING)],
    )
    a = make_procedural(name="a")
    a.fsm.states[0].reads = ["Plain"]
    project = PluginProject(
        name="p", blackboard=Blackboard(class_definitions=[dc]), skills=[a],
    )
    text = compile_skill(a, project=project)
    assert "`Plain` → `state/p/Plain.json`" in text
    assert "`Plain` → `state/p/Plain.json` —" not in text
