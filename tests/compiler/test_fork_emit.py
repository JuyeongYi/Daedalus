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


def test_placed_terminal_fork_reports_end():
    fork = _fork()
    text = compile_skill(fork, project=_placed(fork, with_next=False))
    assert "EXIT: done / NEXT: (end)" in text
    assert "--current done" in text
    assert "## Finishing Up" not in text


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


def test_placed_agent_keeps_exits():
    helper = make_agent(name="helper")
    project = PluginProject(name="p", agents=[helper])
    project.graph.states.append(SimpleState(name="helper", skill_ref=helper))
    assert "## Exits" in compile_agent(helper, project=project)
