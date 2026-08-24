# tests/compiler/test_blackboard_section.py
"""WP-T Part B: 블랙보드 사용 지침 단락 ('## Shared State (Blackboard)')."""
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
    assert "## Shared State (Blackboard)" in text
    assert "`TaskState` → `state/TaskState.json`" in text
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


def test_compile_agent_has_blackboard_section_at_end():
    agent = make_agent("worker")
    project = _project_with_classes(agents=[agent])
    text = compile_agent(agent, project=project)
    assert "## Shared State (Blackboard)" in text
    # 본문 마지막 단락 — 다른 텍스트가 이후에 없어야 한다
    assert text.rstrip().endswith(
        "- Always fill every field the schema marks as required."
    )


# ─────────────────────── WP-BB2: CLI 우선 지시 ───────────────────────


def test_blackboard_section_includes_cli_directive_before_rules():
    """CLI 유무 확인 지시가 기존 3줄 규칙 앞에 나온다."""
    a = make_procedural(name="a")
    project = _project_with_classes(skills=[a])
    text = compile_skill(a, project=project)
    assert "`command -v daedalus-bb`" in text
    cli_idx = text.index("command -v daedalus-bb")
    rule_idx = text.index("Rules:\n- Always read a state file")
    assert cli_idx < rule_idx


def test_cli_directive_does_not_instruct_package_install():
    """설치 명령을 지시하지 않는다 — PyPI의 동명 무관 패키지를 깔거나 실패한다."""
    a = make_procedural(name="a")
    project = _project_with_classes(skills=[a])
    text = compile_skill(a, project=project)
    assert "uv tool install" not in text
    assert "pip install" not in text


def test_blackboard_section_cli_directive_matches_actual_cli_surface():
    """지시문에 적힌 명령·옵션 이름이 daedalus/cli/blackboard.py의 실제 파서와 일치한다."""
    from daedalus.cli.blackboard import build_parser

    a = make_procedural(name="a")
    project = _project_with_classes(skills=[a])
    text = compile_skill(a, project=project)

    parser = build_parser()
    sub_actions = [
        action
        for action in parser._subparsers._group_actions  # type: ignore[union-attr]
        if hasattr(action, "choices")
    ]
    commands = set(sub_actions[0].choices.keys())
    assert {"read", "write", "validate"} <= commands

    write_parser = sub_actions[0].choices["write"]
    write_option_strings = {
        s for action in write_parser._actions for s in action.option_strings
    }
    assert {"--set", "--append", "--remove"} <= write_option_strings

    # 지시문은 `daedalus-bb --schemas <경로> <명령>` 형태라 명령 이름이
    # 실행 파일 바로 뒤에 붙지 않는다 — 토큰 단위로 대조한다.
    assert "daedalus-bb" in text
    for token in ("read <Class>", "write <Class>", "validate",
                  "--set", "--append", "--remove"):
        assert token in text


def test_cli_directive_passes_schemas_path_as_neutral_root_token():
    """CLI 기본 스키마 경로는 cwd 기준이라 지시문이 경로를 명시해야 한다.

    정본은 타깃 중립 토큰 ``${ROOT}``이고 컴파일이 타깃별 CC 변수로 확장한다.
    """
    a = make_procedural(name="a")
    project = _project_with_classes(skills=[a])
    text = compile_skill(a, project=project)
    assert "--schemas ${ROOT}/schemas/schemas.json" in text


def test_cli_schemas_path_expands_per_build_target(tmp_path):
    """MARKETPLACE는 플러그인 루트, LOCAL은 작업 폴더 루트로 확장된다.

    두 타깃 모두 ``<루트>/schemas/schemas.json``에 스키마를 산출하므로 토큰
    하나가 양쪽에서 실제로 존재하는 경로를 가리킨다.
    """
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.compiler.project_compiler import compile_project

    for target, expected, rel in (
        (BuildTarget.MARKETPLACE, "${CLAUDE_PLUGIN_ROOT}", "skills/a/SKILL.md"),
        (BuildTarget.LOCAL, "${CLAUDE_PROJECT_DIR}", ".claude/skills/a/SKILL.md"),
    ):
        out = tmp_path / target.value
        a = make_procedural(name="a")
        project = _project_with_classes(skills=[a])
        project.build_target = target
        result = compile_project(project, out)
        assert result.ok, result.errors
        text = (out / rel).read_text(encoding="utf-8")
        assert f"--schemas {expected}/schemas/schemas.json" in text
        assert "${ROOT}" not in text
        # 지시문이 가리키는 경로에 스키마가 실제로 산출됐는지.
        assert (out / "schemas" / "schemas.json").is_file()


def test_cli_directive_present_in_access_declared_branch():
    """reads/writes 선언이 있는(=union) 분기에도 CLI 지시가 규칙 앞에 나온다.

    _blackboard_section에는 return이 둘이라, 선언 없는 프로젝트만 검사하면
    union 분기가 통째로 비어도 초록이 된다.
    """
    a = make_procedural(name="a")
    a.fsm.states[0].reads = ["TaskState"]
    a.fsm.states[0].writes = ["ReviewFindings.files"]
    project = _project_with_two_classes(skills=[a])
    text = compile_skill(a, project=project)

    assert "This skill reads: `TaskState`" in text  # union 분기임을 확정
    assert "`command -v daedalus-bb`" in text
    assert "--schemas ${ROOT}/schemas/schemas.json" in text
    assert text.index("command -v daedalus-bb") < text.index(
        "Rules:\n- Always read a state file"
    )


def test_cli_directive_present_in_agent_access_declared_branch():
    """에이전트 산출의 union 분기도 동일 — 마지막 단락 순서까지 고정."""
    agent = make_agent("worker")
    work = next(s for s in agent.fsm.states if s.name == "work")
    work.writes = ["TaskState.step"]
    project = _project_with_two_classes(agents=[agent])
    text = compile_agent(agent, project=project)

    assert "This agent writes: `TaskState.step`" in text
    assert "`command -v daedalus-bb`" in text
    assert text.index("command -v daedalus-bb") < text.index(
        "Rules:\n- Always read a state file"
    )


def test_no_class_definitions_no_cli_directive():
    """블랙보드 정의가 없으면 단락 자체가 없으므로 CLI 지시도 없다 — 산출 완전 불변."""
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])
    text = compile_skill(a, project=project)
    assert "daedalus-bb" not in text


def test_only_blackboard_section_differs_outside_it_is_byte_identical():
    """블랙보드 단락(CLI 지시 포함)을 걷어내면 나머지 산출은 클래스 정의 유무와
    무관하게 완전히 동일해야 한다 — WP-BB2 변경이 다른 단락으로 새지 않았음을
    스스로 확인한다."""
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project_with = _project_with_classes(skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project_with.graph.states += [sa, sb]
    project_with.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text_with = compile_skill(a, project=project_with)

    a2 = make_procedural(name="a")
    b2 = make_procedural(name="b")
    project_without = PluginProject(name="p", skills=[a2, b2])
    sa2 = SimpleState(name="a", skill_ref=a2)
    sb2 = SimpleState(name="b", skill_ref=b2)
    project_without.graph.states += [sa2, sb2]
    project_without.graph.transitions.append(
        Transition(source=sa2, target=sb2, trigger=CompletionEvent(name="done"))
    )
    text_without = compile_skill(a2, project=project_without)

    start = text_with.index("## Shared State (Blackboard)")
    end = text_with.index("## Next Steps")
    stripped = text_with[:start] + text_with[end:]
    assert stripped == text_without


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
    assert "## Shared State (Blackboard)" in text
    assert "This skill reads: `TaskState`" in text
    assert "This skill writes: `ReviewFindings.files`" in text
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
    assert "This skill reads" not in text
    assert "This skill writes" not in text
    assert "`TaskState` → `state/TaskState.json`" in text
    assert "`ReviewFindings` → `state/ReviewFindings.json`" in text


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


def test_declared_branch_keeps_overview_paragraph():
    """선언이 있어도 총론(디렉토리·schemas.json 안내)은 유지된다 (리뷰 지적 1)."""
    from daedalus.model.fsm.blackboard import DynamicClass, DynamicField
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.variable import FieldType
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.model.project import PluginProject
    from daedalus.compiler.emit import compile_skill

    s = SimpleState(name="s")
    s.writes = ["Findings.files"]
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name="alpha", description="d")
    project = PluginProject(name="p", skills=[skill])
    project.blackboard.class_definitions.append(DynamicClass(
        name="Findings", description="",
        fields=[DynamicField(name="files", field_type=FieldType.LIST)],
    ))
    text = compile_skill(skill, project=project)
    assert "schemas/schemas.json" in text          # 총론 유지
    assert "This skill writes" in text                        # 선언 문구 병존
