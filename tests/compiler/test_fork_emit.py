"""fork 스킬 산출 (사용자 확정 2026-09-13/2026-09-17) — emit/fork.py, 동기·비동기 2종."""
from __future__ import annotations

import pytest

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import ForkAgent
from daedalus.model.plugin.config import (
    AsyncForkSkillConfig,
    ForkAgentConfig,
    SyncForkSkillConfig,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import AsyncForkSkill, ForkSkill, SyncForkSkill
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural

#: 종류 → (스킬 클래스, config 클래스, 산출될 background 값).
FORK_KINDS = {
    "sync": (SyncForkSkill, SyncForkSkillConfig, "false"),
    "async": (AsyncForkSkill, AsyncForkSkillConfig, "true"),
}


def _fork(
    name: str = "scout", agent: str = "general-purpose", flavor: str = "sync",
) -> ForkSkill:
    cls, cfg_cls, _bg = FORK_KINDS[flavor]
    s = SimpleState(name="s")
    return cls(
        fsm=StateMachine(name=name, states=[s], initial_state=s),
        name=name, description="Scout the code.", body="Look around.",
        config=cfg_cls(agent=agent),
    )


def _placed(fork: ForkSkill, *, with_next: bool = True, **proj):
    project = PluginProject(name="p", skills=[fork], **proj)
    sf = SimpleState(name=fork.name, skill_ref=fork)
    project.graph.states.append(sf)
    if with_next:
        nxt = make_procedural(name="next")
        project.skills.append(nxt)
        sn = SimpleState(name="next", skill_ref=nxt)
        project.graph.states.append(sn)
        project.graph.transitions.append(
            Transition(source=sf, target=sn, trigger=CompletionEvent(name="done"))
        )
    return project


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_project_agent_name_marketplace_is_scoped(flavor):
    fork = _fork(agent="helper", flavor=flavor)
    project = PluginProject(
        name="p", skills=[fork], agents=[ForkAgent(name="helper", description="d")]
    )
    assert "agent: p:helper" in compile_skill(fork, project=project)


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_project_agent_name_local_is_bare(flavor):
    fork = _fork(agent="helper", flavor=flavor)
    project = PluginProject(
        name="p", skills=[fork], agents=[ForkAgent(name="helper", description="d")],
        build_target=BuildTarget.LOCAL,
    )
    text = compile_skill(fork, project=project)
    assert "agent: helper" in text
    assert "p:helper" not in text


def test_builtin_and_external_names_written_as_is():
    for agent in ("Explore", "other-plugin:reviewer"):
        fork = _fork(agent=agent)
        project = PluginProject(name="p", skills=[fork])
        assert f"agent: {agent}" in compile_skill(fork, project=project)


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_placed_fork_waits_and_reports_instead_of_next_steps(flavor):
    fork = _fork(flavor=flavor)
    text = compile_skill(fork, project=_placed(fork))
    assert f"background: {FORK_KINDS[flavor][2]}" in text
    assert "## Report" in text
    assert "EXIT: <branch> / NEXT:" in text
    assert "`next`" in text  # 갈래 목록은 유지
    assert "Main conversation: run `daedalus-bb" in text
    assert "## Next Steps" not in text
    assert "## Resuming Work" not in text


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_placed_fork_keeps_procedure_sections(flavor):
    """fork도 단계 스킬이다 — 절차·도구 선반 단락이 절차형과 같이 나온다."""
    fork = _fork(flavor=flavor)
    text = compile_skill(fork, project=_placed(fork))
    assert "## Procedure" in text


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_placed_terminal_fork_reports_end(flavor):
    fork = _fork(flavor=flavor)
    text = compile_skill(fork, project=_placed(fork, with_next=False))
    assert "EXIT: done / NEXT: (end)" in text
    assert "--current done" in text
    assert "## Finishing Up" not in text


# ── "## Report" 도입 문구는 종류가 가른다 (WP-FK2 C1) ──


def test_sync_fork_report_intro_says_main_waits():
    fork = _fork(flavor="sync")
    text = compile_skill(fork, project=_placed(fork))
    assert (
        "You run in a forked subagent. Do not start the next step and do not "
        "update `state/__progress__.json`" in text
    )
    # 동기 fork에는 강제 인라인 단서도 `current` 선행 조건도 없다.
    assert "task notification" not in text
    assert "Only if `current` is still" not in text


def test_async_fork_report_intro_keeps_forced_inline_caveat():
    """`background: true`도 환경에 따라 인라인으로 돌아온다 — 단정하지 않는다.

    "메인은 기다리지 않는다"고만 쓰면 인라인으로 돌아온 경우 메인이 오지 않을
    작업 알림을 기다린다(공식 문서 2026-09-17: 비대화 `-p`/Agent SDK,
    `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, 재진입 호출, 스케줄 작업).
    """
    fork = _fork(flavor="async")
    text = compile_skill(fork, project=_placed(fork))
    assert "The main conversation usually does not wait for you" in text
    assert "later as a task notification" in text
    assert "it is delivered inline instead" in text
    assert "do not start the next step and do not update the progress file" in text


@pytest.mark.parametrize("terminal", [False, True])
def test_async_fork_report_gates_progress_on_current(terminal):
    """비동기 fork 보고의 진행 명령 앞에 `current` 확인 선행 조건이 온다 (규약 2단계).

    뒤늦게 온 보고가 이미 앞으로 나간 워크플로의 `current`를 과거로 되돌리는
    것을 막는다.
    """
    fork = _fork(flavor="async")
    text = compile_skill(fork, project=_placed(fork, with_next=not terminal))
    pre = (
        "- Main conversation: run `daedalus-bb --schemas ${ROOT}"
        "/schemas/p.json progress read` first. Only if `current` is still "
        "`scout` run the progress command below and continue with NEXT; if it "
        "moved on, do not touch the progress file — report this result to the "
        "user and stop."
    )
    assert pre in text
    # 선행 조건은 진행 명령 **앞**에 온다(같은 목록의 앞 항목).
    assert text.index(pre) < text.index(
        "- Main conversation: run `daedalus-bb --schemas ${ROOT}"
        "/schemas/p.json progress set"
    )


def test_sync_fork_report_has_no_current_precondition():
    fork = _fork(flavor="sync")
    text = compile_skill(fork, project=_placed(fork))
    assert "Only if `current` is still" not in text


# ── 호출자 쪽: 비동기 fork 갈래 접미 + `current` 소유 이관 (WP-FK2 C1, 규약 1단계) ──


def _caller_of(fork: ForkSkill) -> tuple[object, PluginProject]:
    """caller ─(done)→ fork 로 이어진 프로젝트. caller는 절차형(메인에서 돈다)."""
    caller = make_procedural(name="caller")
    project = PluginProject(name="p", skills=[caller, fork])
    sc = SimpleState(name="caller", skill_ref=caller)
    sf = SimpleState(name=fork.name, skill_ref=fork)
    project.graph.states += [sc, sf]
    project.graph.transitions.append(
        Transition(source=sc, target=sf, trigger=CompletionEvent(name="done"))
    )
    return caller, project


def test_caller_branch_to_async_fork_gets_do_not_block_suffix():
    fork = _fork(flavor="async")
    caller, project = _caller_of(fork)
    text = compile_skill(caller, project=project)
    assert (
        "invoke skill `scout` (background fork — do not block on it; act on its "
        "report as soon as you have it, whether it comes back inline in this "
        "turn or later as a task notification)" in text
    )


def test_caller_branch_to_sync_fork_is_unchanged():
    fork = _fork(flavor="sync")
    caller, project = _caller_of(fork)
    text = compile_skill(caller, project=project)
    assert "invoke skill `scout`" in text
    assert "background fork" not in text
    assert "awaiting background fork" not in text


def test_caller_hands_current_to_async_fork():
    """넘길 때 `current`를 그 fork에게 준다 — 진행 파일에 "도는 중"을 적을 자리다."""
    fork = _fork(flavor="async")
    caller, project = _caller_of(fork)
    text = compile_skill(caller, project=project)
    assert "Handing off to a background fork (`scout`)" in text
    assert '--note "awaiting background fork"' in text
    # 일반 진행 명령은 그대로 남는다(비동기 갈래만 규약이 다르다).
    assert "--completed <this skill> --current <next target>" in text


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_unplaced_fork_emits_background_but_no_report(flavor):
    """background는 FIXED라 **항상** 나간다 — 키가 없으면 CC가 백그라운드로 돈다.

    미배치 fork에는 보고 단락이 없다(분기할 그래프가 없다).
    """
    fork = _fork(flavor=flavor)
    text = compile_skill(fork, project=PluginProject(name="p", skills=[fork]))
    assert f"background: {FORK_KINDS[flavor][2]}" in text
    assert "## Report" not in text


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_fork_frontmatter_key_order(flavor):
    """프론트매터 키 순서는 enum 선언 순서다 — context → agent → background."""
    text = compile_skill(_fork(flavor=flavor))
    lines = [ln.split(":")[0] for ln in text.splitlines()]
    assert lines.index("context") < lines.index("agent") < lines.index("background")


def test_entry_context_from_async_fork_says_it_reported():
    """비동기 fork 다음 스킬의 진입 맥락은 "background fork `X` reported"다.

    그 fork는 스스로 다음 단계를 부르지 않았다 — 보고를 받은 메인이 시작시켰다.
    """
    fork = _fork(flavor="async")
    project = _placed(fork)
    nxt = next(s for s in project.skills if s.name == "next")
    text = compile_skill(nxt, project=project)
    assert "- entered when background fork `scout` reported" in text
    assert "- entered from `scout`" not in text


def test_entry_context_from_sync_fork_is_unchanged():
    fork = _fork(flavor="sync")
    project = _placed(fork)
    nxt = next(s for s in project.skills if s.name == "next")
    text = compile_skill(nxt, project=project)
    assert "- entered from `scout`" in text
    assert "background fork" not in text


def test_fork_agent_contract_names_fork_skill():
    helper = ForkAgent(name="helper", description="Helper.")
    fork = _fork(agent="helper")
    project = PluginProject(name="p", skills=[fork], agents=[helper])
    text = compile_agent(helper, project=project)
    assert "## Invocation Contract" in text
    assert "Execution base of fork skill `scout`" in text
    # fork 에이전트는 그래프 노드가 아니다 — 출구·위임·내부 워크플로가 없다.
    assert "## Exits" not in text
    assert "## Delegation" not in text
    assert "## Internal Workflow" not in text


def test_fork_agent_compiles_without_project():
    """project=None이어도 예외가 없다 — 그래프 유도 단락이 전부 건너뛰어진다."""
    helper = ForkAgent(
        name="helper", description="Helper.", body="Do the work.",
        config=ForkAgentConfig(),
    )
    text = compile_agent(helper)
    assert "name: helper" in text
    assert "Do the work." in text
    # fork 에이전트 표에 없는 두 행은 프론트매터에 나오지 않는다.
    assert "background:" not in text
    assert "isolation:" not in text
    # 그래프 유도 단락은 하나도 없다(가드가 `is_workflow` 하나다).
    for heading in (
        "## Invocation Contract", "## Delegation", "## Exits",
        "## Internal Workflow",
    ):
        assert heading not in text


@pytest.mark.parametrize("flavor", sorted(FORK_KINDS))
def test_fork_agent_in_project_compiles_with_only_the_base_contract(flavor):
    """fork 2종 어느 쪽이 써도 fork 에이전트 산출은 실행 기반 줄 하나다."""
    helper = ForkAgent(name="helper", description="Helper.", body="Work.")
    fork = _fork(agent="helper", flavor=flavor)
    project = _placed(fork, agents=[helper])
    text = compile_agent(helper, project=project)
    assert text.count("## Invocation Contract") == 1
    assert "- Execution base of fork skill `scout`" in text
    # 그래프 유도 항목("- from `X` via port …")은 구조적으로 나올 수 없다.
    assert "- from `" not in text
    for heading in ("## Delegation", "## Exits", "## Internal Workflow"):
        assert heading not in text


def test_unused_fork_agent_has_no_contract_section():
    """아무 fork 스킬도 가리키지 않으면 단락을 내지 않는다 — 경고가 따로 짚는다."""
    lonely = ForkAgent(name="lonely", description="Nobody calls me.", body="Idle.")
    project = PluginProject(name="p", agents=[lonely])
    assert "## Invocation Contract" not in compile_agent(lonely, project=project)


def test_workflow_agent_never_gets_a_fork_base_line():
    """워크플로 에이전트는 fork 에이전트가 될 수 없다 — 실행 기반 줄이 없다."""
    worker = make_agent(name="helper")
    fork = _fork(agent="helper")
    project = PluginProject(name="p", skills=[fork], agents=[worker])
    project.graph.states.append(SimpleState(name="helper", skill_ref=worker))
    text = compile_agent(worker, project=project)
    assert "Execution base of fork skill" not in text
    # 배치된 워크플로 에이전트는 출구 단락을 그대로 받는다.
    assert "## Exits" in text


def test_placed_agent_keeps_exits():
    helper = make_agent(name="helper")
    project = PluginProject(name="p", agents=[helper])
    project.graph.states.append(SimpleState(name="helper", skill_ref=helper))
    assert "## Exits" in compile_agent(helper, project=project)
