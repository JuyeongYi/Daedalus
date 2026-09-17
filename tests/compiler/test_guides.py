# tests/compiler/test_guides.py
"""WP-FK2 C3: 공통 안내 파일 `guides/<플러그인>/workflow.md`·`blackboard.md`.

고정하는 계약 5가지:
  1. 게이트 — 말할 것이 있을 때만 만들고, **포인터가 하나도 없으면 만들지 않는다**.
  2. 포인터 — 프론트매터 직후 1줄, 대상별로 문구가 다르다(fork는 보고 전용).
  3. 경로 규약 — 가이드에는 치환 변수가 없고(`<SCHEMAS>` 자리표시자), 포인터를
     받은 컴포넌트에는 확장되는 실제 경로가 남는다.
  4. CLI 문자열이 `daedalus/cli/blackboard.py`의 실제 파서와 일치한다
     (원래 `test_blackboard_section.py`가 지키던 계약 — 문장이 옮겨 갔으니
     고정도 함께 옮긴다).
  5. 결정적 — 같은 모델 → 같은 텍스트.
"""
from __future__ import annotations

import pytest

from daedalus.compiler.emit import (
    compile_agent,
    compile_blackboard_guide,
    compile_guide,
    compile_skill,
    compile_workflow_guide,
    guide_pointer_line,
)
from daedalus.compiler.emit.guides import (
    BLACKBOARD_GUIDE_KIND,
    WORKFLOW_GUIDE_KIND,
    blackboard_guide_referenced,
    workflow_guide_referenced,
    workflow_pointer_kind,
)
from daedalus.compiler.emit.wrapped import compile_wrapped_runner
from daedalus.compiler.project_compiler import compile_project
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import ForkAgent
from daedalus.model.plugin.config import SyncForkSkillConfig, WrappedSkillConfig
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import SyncForkSkill, WrappedSkill
from daedalus.model.project import PluginProject

from tests.compiler.builders import (
    make_agent,
    make_declarative,
    make_procedural,
    make_transfer,
)

_WF = "${ROOT}/guides/p/workflow.md"
_BB = "${ROOT}/guides/p/blackboard.md"


def _blackboard() -> Blackboard:
    return Blackboard(class_definitions=[
        DynamicClass(
            name="TaskState", description="the unit of work",
            fields=[DynamicField(name="step", field_type=FieldType.INT)],
        ),
    ])


def _placed_pair(**kwargs):
    """a ─(done)→ b 배치 + 전달받은 추가 필드."""
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    skills = [a, b] + list(kwargs.pop("skills", []))
    project = PluginProject(name="p", skills=skills, **kwargs)
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    return project, a, b


def _fork(name="scout", agent="general-purpose") -> SyncForkSkill:
    s = SimpleState(name="s")
    return SyncForkSkill(
        fsm=StateMachine(name=name, states=[s], initial_state=s),
        name=name, description="Scout the code.", body="Look around.",
        config=SyncForkSkillConfig(agent=agent),
    )


# ─────────────────────────── 1) 게이트 ───────────────────────────


def test_workflow_guide_is_none_without_placements():
    project = PluginProject(name="p", skills=[make_procedural("a")])
    assert compile_workflow_guide(project) is None
    assert workflow_guide_referenced(project) is False


def test_blackboard_guide_is_none_without_class_definitions():
    project, _, _ = _placed_pair()
    assert compile_blackboard_guide(project) is None
    assert blackboard_guide_referenced(project) is False


def test_guides_are_not_written_when_nothing_points_at_them(tmp_path):
    """고아 파일 없음 — 포인터가 0이면 계획에도 오르지 않는다."""
    project = PluginProject(name="p", skills=[make_procedural("a")])
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert not (tmp_path / "guides").exists()
    assert all("guides/" not in p.as_posix() for p in result.written)


def test_blackboard_guide_alone_when_there_is_no_graph(tmp_path):
    """블랙보드 클래스만 있고 배치가 없으면 blackboard.md만 나간다."""
    a = make_procedural("a")
    project = PluginProject(name="p", skills=[a], blackboard=_blackboard())
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    rel = {p.relative_to(tmp_path).as_posix() for p in result.written}
    assert "guides/p/blackboard.md" in rel
    assert "guides/p/workflow.md" not in rel


def test_both_guides_written_for_a_placed_project_with_state(tmp_path):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    rel = {p.relative_to(tmp_path).as_posix() for p in result.written}
    assert {"guides/p/workflow.md", "guides/p/blackboard.md"} <= rel


# ─────────────────────────── 2) 포인터 ───────────────────────────


def test_pointer_is_the_first_block_after_the_frontmatter():
    project, a, _ = _placed_pair(blackboard=_blackboard())
    text = compile_skill(a, project=project)
    fm_end = text.index("\n---\n") + len("\n---\n")
    pointer_idx = text.index("Before you start, read")
    assert fm_end <= pointer_idx < text.index("## Resuming Work")


def test_pointer_names_both_guides_when_both_exist():
    project, a, _ = _placed_pair(blackboard=_blackboard())
    text = compile_skill(a, project=project)
    assert (
        f"Before you start, read `{_WF}` (how this workflow runs, progress record, "
        f"reports) and `{_BB}` (shared state and the daedalus-bb CLI)." in text
    )


def test_pointer_names_only_the_workflow_guide_without_state():
    project, a, _ = _placed_pair()
    text = compile_skill(a, project=project)
    assert f"Before you start, read `{_WF}` (how this workflow runs" in text
    assert _BB not in text


def test_unplaced_skill_gets_only_the_blackboard_pointer():
    """미배치 스킬은 워크플로 가이드 대상이 아니다 — 돌릴 워크플로 자리가 없다."""
    project, _, _ = _placed_pair(blackboard=_blackboard())
    idle = make_procedural("idle")
    project.skills.append(idle)
    text = compile_skill(idle, project=project)
    assert _WF not in text
    assert f"Before you start, read `{_BB}`" in text


def test_placed_declarative_and_transfer_get_the_main_pointer():
    project, a, _ = _placed_pair()
    know = make_declarative("know")
    edge = make_transfer("edge-skill")
    project.skills += [know, edge]
    project.graph.states.append(SimpleState(name="know", skill_ref=know))
    for skill in (know, edge):
        assert f"Before you start, read `{_WF}`" in compile_skill(
            skill, project=project
        )


def test_placed_agent_gets_the_main_pointer():
    project, _, _ = _placed_pair()
    worker = make_agent("worker")
    project.agents.append(worker)
    project.graph.states.append(SimpleState(name="worker", skill_ref=worker))
    assert f"Before you start, read `{_WF}`" in compile_agent(worker, project=project)


def test_fork_skill_gets_the_report_only_pointer():
    """fork에는 2·3절(진행 기록·사용자 확인)이 적용되지 않는다 — 보고 양식만 가리킨다."""
    fork = _fork()
    project, a, _ = _placed_pair()
    project.skills.append(fork)
    sf = SimpleState(name="scout", skill_ref=fork)
    project.graph.states.append(sf)
    project.graph.transitions.append(
        Transition(
            source=project.graph.states[-2], target=sf,
            trigger=CompletionEvent(name="survey"),
        )
    )
    text = compile_skill(fork, project=project)
    assert workflow_pointer_kind(fork, project) == "fork"
    assert (
        f'Read `{_WF}` section "Fork reports" for the report format. The progress '
        f"record and resume rules in that guide belong to the main conversation, "
        f"not to you." in text
    )
    assert "Before you start, read" not in text


def test_fork_agent_gets_only_the_blackboard_pointer():
    """fork 에이전트는 그래프 노드가 아니다 — 워크플로 가이드 대상이 아니다."""
    fork = _fork(agent="helper")
    project, _, _ = _placed_pair(blackboard=_blackboard())
    project.skills.append(fork)
    helper = ForkAgent(name="helper", description="Helper.", body="Work.")
    project.agents.append(helper)
    text = compile_agent(helper, project=project)
    assert _WF not in text
    assert f"Before you start, read `{_BB}`" in text


def test_wrapped_runner_gets_no_pointer():
    """랩핑 실행 서브에이전트는 포인터 대상이 아니다(블랙보드 단락도 없다)."""
    wrapped = WrappedSkill(
        fsm=StateMachine(name="w", initial_state=SimpleState(name="s"),
                         states=[SimpleState(name="s")]),
        name="wrap", description="Wrap it.",
        config=WrappedSkillConfig(source="other:thing", usage="state"),
    )
    text = compile_wrapped_runner(wrapped)
    assert "guides/" not in text


def test_guide_pointer_line_is_none_without_project():
    a = make_procedural("a")
    assert guide_pointer_line(a, None) is None


# ─────────────────── 3) 경로 규약 (제2부 C3 (a)(b)(c)) ───────────────────


@pytest.mark.parametrize("kind", [WORKFLOW_GUIDE_KIND, BLACKBOARD_GUIDE_KIND])
def test_guides_have_no_substitution_tokens(kind):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_guide(project, kind)
    assert text
    assert "${ROOT}" not in text
    assert "${CLAUDE_" not in text


@pytest.mark.parametrize("kind", [WORKFLOW_GUIDE_KIND, BLACKBOARD_GUIDE_KIND])
def test_guides_explain_the_schemas_placeholder(kind):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_guide(project, kind)
    assert "<SCHEMAS>" in text
    assert (
        "use the `--schemas <path>` value written in the skill or agent file that "
        "sent you here" in text
    )


def test_placed_skill_keeps_its_progress_command_instead_of_a_state_cli_line():
    """배치 스킬에는 진행 명령이 이미 확장 경로를 남긴다 — 줄을 더하지 않는다."""
    project, a, _ = _placed_pair(blackboard=_blackboard())
    text = compile_skill(a, project=project)
    assert "State CLI:" not in text
    assert "--schemas ${ROOT}/schemas/p.json progress" in text


@pytest.mark.parametrize("kind", ["agent", "fork_agent", "unplaced"])
def test_components_without_a_progress_command_get_a_state_cli_line(kind):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    if kind == "unplaced":
        comp = make_procedural("idle")
        project.skills.append(comp)
        text = compile_skill(comp, project=project)
    elif kind == "agent":
        comp = make_agent("worker")
        project.agents.append(comp)
        text = compile_agent(comp, project=project)
    else:
        project.skills.append(_fork(agent="helper"))
        comp = ForkAgent(name="helper", description="Helper.", body="Work.")
        project.agents.append(comp)
        text = compile_agent(comp, project=project)
    assert (
        "State CLI: `daedalus-bb --schemas ${ROOT}/schemas/p.json "
        "<read|write|validate> ...`" in text
    )


@pytest.mark.parametrize(
    "target,expected",
    [
        (BuildTarget.MARKETPLACE, "${CLAUDE_PLUGIN_ROOT}"),
        (BuildTarget.LOCAL, "${CLAUDE_PROJECT_DIR}"),
    ],
)
def test_pointer_path_expands_per_build_target(tmp_path, target, expected):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    project.build_target = target
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    prefix = ".claude/" if target is BuildTarget.LOCAL else ""
    text = (tmp_path / f"{prefix}skills/a/SKILL.md").read_text(encoding="utf-8")
    assert f"{expected}/guides/p/workflow.md" in text
    assert "${ROOT}" not in text
    # 포인터가 가리키는 파일이 실제로 그 자리에 산출됐는지.
    assert (tmp_path / "guides" / "p" / "workflow.md").is_file()


# ─────────────────── 4) CLI 문자열 ↔ 실제 파서 ───────────────────


def test_blackboard_guide_cli_matches_the_actual_cli_surface():
    """가이드에 적힌 명령·옵션 이름이 daedalus/cli/blackboard.py 파서와 일치한다."""
    from daedalus.cli.blackboard import build_parser

    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)

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

    assert "daedalus-bb" in text
    for token in ("read <Class>", "write <Class>", "validate",
                  "--set", "--append", "--remove"):
        assert token in text


def test_workflow_guide_progress_cli_matches_the_actual_cli_surface():
    from daedalus.cli.blackboard import build_parser

    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)

    parser = build_parser()
    sub_actions = [
        action
        for action in parser._subparsers._group_actions  # type: ignore[union-attr]
        if hasattr(action, "choices")
    ]
    progress = sub_actions[0].choices["progress"]
    progress_subs = [
        a for a in progress._actions if hasattr(a, "choices") and a.choices
    ][0].choices
    assert {"read", "set"} <= set(progress_subs)
    set_options = {
        s for action in progress_subs["set"]._actions for s in action.option_strings
    }
    assert {"--current", "--completed", "--note", "--prev"} <= set_options

    for token in ("progress read", "progress set", "--current", "--completed",
                  "--note", "--prev"):
        assert token in text


def test_cli_directive_does_not_instruct_package_install():
    """설치 명령을 지시하지 않는다 — PyPI의 동명 무관 패키지를 깔거나 실패한다."""
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)
    assert "uv tool install" not in text
    assert "pip install" not in text
    assert "ships with Daedalus" in text


def test_blackboard_guide_keeps_the_cli_check_before_the_rules():
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)
    assert text.index("command -v daedalus-bb") < text.index(
        "- Always read a state file before changing it"
    )


# ─────────────────── 5) 본문 계약 (제2부 C3·결정 항목 1 ③) ───────────────────


def test_workflow_guide_warns_forked_subagents_off_sections_2_and_3():
    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)
    sentence = (
        "Sections 2-3 are for the main conversation only. If you are running "
        "inside a forked subagent, do not run any progress command and do not ask "
        "the user anything — report instead (section 5)."
    )
    assert sentence in text
    assert text.index(sentence) < text.index("## 2. The progress record")


def test_resume_rules_say_a_running_background_fork_is_not_a_question():
    """결정 항목 1 ③ — current가 도는 중인 비동기 fork면 사용자 확인 대상이 아니다."""
    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)
    assert (
        "`current` is a background fork that is still running" in text
        and "This is not a case to ask the user about" in text
        and "leave the progress file alone" in text
    )


def test_resume_rules_say_the_called_skill_is_the_start_on_exit_3():
    """"처음부터"가 아니라 "지금 불린 스킬이 시작점"이다 — 잔여와 어긋나지 않게."""
    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)
    assert (
        "the skill you were just asked to run is the starting point" in text
    )


def test_workflow_guide_carries_the_report_format_section():
    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)
    assert "## 5. Fork reports" in text
    for form in ("EXIT: <branch> / NEXT: /<skill>",
                 "EXIT: <branch> / NEXT: agent <name>",
                 "EXIT: done / NEXT: (end)"):
        assert form in text


def test_workflow_guide_carries_the_manual_fallback_once():
    project, a, _ = _placed_pair()
    text = compile_workflow_guide(project)
    assert text.count("edit `state/__progress__.json` by hand") == 1
    # 컴포넌트 잔여에는 더 이상 없다(반복을 없애는 것이 이 WP의 목적이다).
    assert "by hand" not in compile_skill(a, project=project)


# ─────────────────────────── 6) 결정성 ───────────────────────────


@pytest.mark.parametrize("kind", [WORKFLOW_GUIDE_KIND, BLACKBOARD_GUIDE_KIND])
def test_guide_text_is_deterministic(kind):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    assert compile_guide(project, kind) == compile_guide(project, kind)


def test_guide_files_are_byte_identical_across_compiles(tmp_path):
    project, _, _ = _placed_pair(blackboard=_blackboard())
    first, second = tmp_path / "a", tmp_path / "b"
    compile_project(project, first)
    compile_project(project, second)
    for rel in ("guides/p/workflow.md", "guides/p/blackboard.md"):
        assert (first / rel).read_bytes() == (second / rel).read_bytes()


def test_compile_guide_rejects_an_unknown_kind():
    project, _, _ = _placed_pair()
    with pytest.raises(ValueError):
        compile_guide(project, "guide_nonsense")
