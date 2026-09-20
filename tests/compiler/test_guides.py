# tests/compiler/test_guides.py
"""WP-FK2 C3: 공통 안내 파일 `guides/<플러그인>/workflow.md`·`blackboard.md`.

고정하는 계약 5가지:
  1. 게이트 — 말할 것이 있을 때만 만들고, **포인터가 하나도 없으면 만들지 않는다**.
  2. 포인터 — 프론트매터 직후 1줄, 대상별로 문구가 다르다(fork는 보고 전용).
  3. 경로 규약 — 가이드에는 치환 변수가 없고(`<SCHEMAS>` 자리표시자), 포인터를
     받은 컴포넌트에는 확장되는 실제 경로가 남는다.
  4. 도구 이름·인자가 `daedalus/cli/mcp_server.py`의 실제 서버 표면과 일치한다
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
from daedalus.compiler.project_compiler import compile_project
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import ExternalAgent, ForkAgent
from daedalus.model.plugin.config import ExternalAgentConfig, SyncForkSkillConfig
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import SyncForkSkill
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
        f"reports) and `{_BB}` (shared state and its tools)." in text
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
        f'Read `{_WF}` section "Fork reports" for the report format. Updating the '
        f"progress record and the resume rules in that guide belong to the main "
        f"conversation, not to you." in text
    )
    assert "Before you start, read" not in text


def test_fork_output_never_forbids_what_its_entry_context_demands():
    """배치 fork는 "## Entry Context"에서 `prev`/`note`를 확인하라는 지시를 받는다.

    그 지시를 이행할 유일한 수단이 가이드 2절의 `progress read`이므로, 같은
    산출(포인터 + 가이드)이 "진행 명령을 일절 쓰지 말라"고 말하면 안 된다 —
    금지는 **갱신**에만 걸린다(원칙 5: 서로 모순되는 두 지시를 내지 않는다).
    """
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
    guide = compile_workflow_guide(project)
    assert "Check `prev` and the branch in `note`" in text
    for forbidden in ("do not run any progress command", "do not read"):
        assert forbidden not in text
        assert forbidden not in guide
    assert "do not update the progress record" in guide
    assert "you may read the record for your entry context" in guide


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
def test_guides_name_the_tools_literally(kind):
    """자리표시자가 없다 (WP-BM) — 도구 이름에는 경로가 없어 우회할 것이 없다.

    종전에는 `<SCHEMAS>` 자리표시자 + "너를 보낸 파일의 `--schemas` 경로를
    쓰라"는 우회가 있었다. 도구 이름은 치환 변수를 타지 않으므로 가이드가
    **그대로** 적는다.
    """
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_guide(project, kind)
    assert "<SCHEMAS>" not in text
    assert "--schemas" not in text
    assert "mcp__plugin_p_bb-p__" in text


def test_pointer_line_names_the_server_for_every_pointed_component():
    """포인터를 받으면 **무조건** 서버·도구 접두 한 줄이 따라온다 (WP-BM).

    종전 `State CLI:` 줄은 "이 산출에 확장되는 스키마 경로가 없을 때만" 붙는
    조건부였다. 도구 이름에는 경로가 없으므로 그 조건이 사라졌고, 대신 도구가
    안 보일 때 **무엇이 안 떠 있는지** 말할 수 있도록 서버 이름을 남긴다.
    """
    project, a, _ = _placed_pair(blackboard=_blackboard())
    text = compile_skill(a, project=project)
    assert "State CLI:" not in text
    assert "--schemas" not in text
    assert (
        "Blackboard tools: `mcp__plugin_p_bb-p__*` (MCP server `bb-p`) — "
        "the guide lists them." in text
    )


@pytest.mark.parametrize("kind", ["agent", "fork_agent", "unplaced"])
def test_components_without_a_progress_command_get_a_tools_line(kind):
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
    assert "Blackboard tools: `mcp__plugin_p_bb-p__*`" in text


def test_tools_line_is_emitted_without_a_blackboard_too():
    """가이드 종류와 무관하게 서버 이름이 남는다.

    블랙보드 클래스가 없어도 진행 기록은 같은 서버가 쥐고 있으므로, 워크플로
    가이드만 가리키는 컴포넌트도 "어느 서버인가"를 알아야 한다(원칙 5).
    """
    project, _, _ = _placed_pair()
    worker = make_agent("worker")
    project.agents.append(worker)
    project.graph.states.append(SimpleState(name="worker", skill_ref=worker))
    text = compile_agent(worker, project=project)
    assert _WF in text
    assert "Blackboard tools: `mcp__plugin_p_bb-p__*` (MCP server `bb-p`)" in text


def test_a_component_without_a_pointer_gets_no_tools_line():
    """서버를 말할 의무는 포인터를 받은 컴포넌트에만 있다."""
    project, _, _ = _placed_pair()
    idle = make_procedural("idle")
    project.skills.append(idle)
    text = compile_skill(idle, project=project)
    assert "guides/" not in text
    assert "Blackboard tools:" not in text


def test_pointer_targets_are_exactly_the_components_that_get_a_file():
    """포인터 판정 대상 집합 == 계획이 파일을 내는 집합 (판정의 실체는 하나다)."""
    from daedalus.compiler.emit.common import emitted_components
    from daedalus.compiler.plan import _plan_outputs

    project, _, _ = _placed_pair(blackboard=_blackboard())
    project.skills.append(_fork(agent="helper"))
    project.agents.append(ForkAgent(name="helper", description="H.", body="Work."))
    project.agents.append(ExternalAgent(
        name="ref", description="An external reviewer.",
        config=ExternalAgentConfig(source="other:doc"),
        transfer_on=[EventDef(name="done")],
    ))

    plan, errors, _ = _plan_outputs(project)
    assert not errors, [e.message for e in errors]
    planned = [p.component for p in plan if p.kind in ("skill", "agent")]
    pointed = emitted_components(project)
    assert {id(c) for c in pointed} == {id(c) for c in planned}
    # 산출 파일이 없는 종류는 양쪽 모두에서 빠진다(파일도, 포인터도 없다).
    assert "ref" not in {c.name for c in pointed}


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


def test_blackboard_guide_names_match_the_actual_server_surface():
    """가이드에 적힌 도구 이름이 실제 서버의 도구·인자와 일치한다 (WP-BM).

    산문과 서버가 어긋나면 모델이 없는 도구를 부르거나 없는 인자를 넘긴다.
    """
    import inspect

    from daedalus.cli.mcp_server import TOOLS

    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)

    by_name = dict(TOOLS)
    assert {"list", "read", "init", "write", "validate"} <= set(by_name)
    write_args = set(inspect.signature(by_name["write"]).parameters) - {"self"}
    assert {"cls", "set", "append", "remove"} <= write_args

    for name in ("list", "read", "init", "write", "validate"):
        assert f"mcp__plugin_p_bb-p__{name}`" in text
    for token in ("`cls`", "`field`", "`set`", "`append`", "`remove`"):
        assert token in text


def test_workflow_guide_progress_names_match_the_actual_server_surface():
    import inspect

    from daedalus.cli.mcp_server import TOOLS

    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)

    by_name = dict(TOOLS)
    assert {"progress_read", "progress_set"} <= set(by_name)
    set_args = set(inspect.signature(by_name["progress_set"]).parameters) - {"self"}
    assert {"current", "completed", "note", "prev"} <= set_args

    for token in ("mcp__plugin_p_bb-p__progress_read",
                  "mcp__plugin_p_bb-p__progress_set",
                  "`current`", "`completed`", "`note`", "`prev`"):
        assert token in text


def test_cli_directive_does_not_instruct_package_install():
    """설치 명령을 지시하지 않는다 — PyPI의 동명 무관 패키지를 깔거나 실패한다."""
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)
    assert "uv tool install" not in text
    assert "pip install" not in text
    assert "ships with Daedalus" in text


def test_blackboard_guide_keeps_the_tool_section_before_the_rules():
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)
    assert text.index("## Blackboard tools") < text.index(
        "- Always read a state file before changing it"
    )


def test_blackboard_guide_explains_the_error_kinds():
    """오류 kind 셋의 뜻을 가이드가 말한다 — exit code 해석 계층의 대체물이다."""
    project, _, _ = _placed_pair(blackboard=_blackboard())
    text = compile_blackboard_guide(project)
    for kind in ("not_found", "usage", "rejected"):
        assert f"`{kind}`" in text
    assert "the file is unchanged" in text


# ─────────────────── 5) 본문 계약 (제2부 C3·결정 항목 1 ③) ───────────────────


def test_workflow_guide_warns_forked_subagents_off_sections_2_and_3():
    project, _, _ = _placed_pair()
    text = compile_workflow_guide(project)
    sentence = (
        "Sections 2-3 are for the main conversation only. If you are running "
        "inside a forked subagent, do not update the progress record and do not "
        "ask the user anything — you may read the record for your entry context "
        "(section 4), and your outcome goes into your report (section 5) instead "
        "of into the record."
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


def test_workflow_guide_carries_the_missing_tools_fallback_once():
    """도구가 없을 때의 지침은 **고치지 말고 말하라**다 (WP-BM).

    종전 폴백은 "CLI가 없으면 손으로 고치되 남의 키는 건드리지 말라"였다.
    손편집이야말로 이 도구들이 막으려던 것이고(공유 파일·스키마 검증), 그
    지침을 남겨 두면 서버가 안 떠 있을 때마다 모델이 정확히 그 사고를 낸다.
    """
    project, a, _ = _placed_pair()
    text = compile_workflow_guide(project)
    assert text.count("do not edit the state files or the progress file") == 1
    assert "by hand: they are validated on write" in text
    # 컴포넌트 잔여에는 없다(반복을 없애는 것이 공통 안내 파일의 목적이다).
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
