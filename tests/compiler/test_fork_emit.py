"""fork 스킬 산출 (사용자 확정 2026-09-13) — emit/fork.py."""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import ForkSkillConfig
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import ForkSkill
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


def _fork(name: str = "scout", agent: str = "general-purpose") -> ForkSkill:
    s = SimpleState(name="s")
    return ForkSkill(
        fsm=StateMachine(name=name, states=[s], initial_state=s),
        name=name, description="Scout the code.", body="Look around.",
        config=ForkSkillConfig(agent=agent),
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


def test_project_agent_name_marketplace_is_scoped():
    fork = _fork(agent="helper")
    project = PluginProject(name="p", skills=[fork], agents=[make_agent(name="helper")])
    assert "agent: p:helper" in compile_skill(fork, project=project)


def test_project_agent_name_local_is_bare():
    fork = _fork(agent="helper")
    project = PluginProject(
        name="p", skills=[fork], agents=[make_agent(name="helper")],
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


def test_placed_fork_waits_and_reports_instead_of_next_steps():
    fork = _fork()
    text = compile_skill(fork, project=_placed(fork))
    assert "background: false" in text
    assert "## Report" in text
    assert "EXIT: <branch> / NEXT:" in text
    assert "`next`" in text  # 갈래 목록은 유지
    assert "Main conversation: run `daedalus-bb" in text
    assert "## Next Steps" not in text
    assert "## Resuming Work" not in text


def test_placed_terminal_fork_reports_end():
    fork = _fork()
    text = compile_skill(fork, project=_placed(fork, with_next=False))
    assert "EXIT: done / NEXT: (end)" in text
    assert "--current done" in text
    assert "## Finishing Up" not in text


def test_unplaced_fork_has_no_background_or_report():
    fork = _fork()
    text = compile_skill(fork, project=PluginProject(name="p", skills=[fork]))
    assert "background:" not in text
    assert "## Report" not in text


def test_fork_agent_contract_names_fork_skill():
    helper = make_agent(name="helper")
    fork = _fork(agent="helper")
    project = PluginProject(name="p", skills=[fork], agents=[helper])
    text = compile_agent(helper, project=project)
    assert "## Invocation Contract" in text
    assert "Execution base of fork skill `scout`" in text
    # 캔버스 밖 fork 에이전트는 출구 단락을 내지 않는다 — fork 보고 양식과 부딪힌다.
    assert "## Exits" not in text


def test_placed_agent_keeps_exits():
    helper = make_agent(name="helper")
    project = PluginProject(name="p", agents=[helper])
    project.graph.states.append(SimpleState(name="helper", skill_ref=helper))
    assert "## Exits" in compile_agent(helper, project=project)
