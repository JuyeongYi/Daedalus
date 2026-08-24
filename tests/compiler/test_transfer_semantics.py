"""transition skill(TransferSkill) 산출 의미론 + 재사용 금지 (A11).

**고장이었다:** 도착 스킬의 "진입 맥락"은 "transition skill X의 지침을 수행한
상태다"라고 가정하는데, 출발 스킬의 "다음 단계"에는 그것을 **수행하라는 지시가
없었다** — 아무도 transition skill을 실행하지 않는 구조였다. 에이전트 .md의 호출
계약도 호출 전이의 transfer를 언급하지 않았다.
"""
from __future__ import annotations

import pytest

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator


def _proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="s")
    return ProceduralSkill(
        fsm=StateMachine(name=f"{name}-fsm", initial_state=s, states=[s]),
        name=name, description="d",
    )


def _transfer(name: str, description: str = "") -> TransferSkill:
    s = SimpleState(name="s")
    return TransferSkill(
        fsm=StateMachine(name=f"{name}-fsm", initial_state=s, states=[s]),
        name=name, description=description,
    )


def _agent(name: str = "runner") -> AgentDefinition:
    entry = EntryPoint(name="e")
    return AgentDefinition(
        fsm=StateMachine(name=f"{name}-fsm", initial_state=entry, states=[entry]),
        name=name, description="d", transfer_on=[EventDef(name="ok")],
    )


@pytest.fixture
def scenario():
    """alpha --done(validate)--> beta, alpha --delegate(validate2)--> runner --ok--> beta"""
    alpha, beta = _proc("alpha"), _proc("beta")
    alpha.transfer_on = [EventDef(name="done")]
    alpha.call_agents = [EventDef(name="delegate")]
    validate = _transfer("validate", "검증 규칙")
    handoff = _transfer("handoff")
    agent = _agent()

    project = PluginProject(
        name="p", skills=[alpha, beta, validate, handoff], agents=[agent],
    )
    na = SimpleState(name="alpha", skill_ref=alpha)
    nb = SimpleState(name="beta", skill_ref=beta)
    ng = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([na, nb, ng])
    project.graph.transitions.extend([
        Transition(
            source=na, target=nb, trigger=CompletionEvent(name="done"),
            skill_ref=validate,
        ),
        Transition(
            source=na, target=ng, trigger=CompletionEvent(name="delegate"),
            skill_ref=handoff,
        ),
        Transition(source=ng, target=nb, trigger=CompletionEvent(name="ok")),
    ])
    return project, alpha, beta, agent, validate, handoff


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return heading + (rest if end < 0 else rest[:end])


# --- 1. 출발 스킬 "다음 단계"가 transition skill을 수행하라고 지시한다 ---


def test_next_step_instructs_running_the_transfer_skill(scenario):
    project, alpha, *_ = scenario
    section = _section(compile_skill(alpha, project=project), "## Next Steps")

    assert "transition skill `validate`" in section
    assert ", then" in section
    assert "invoke skill `beta`" in section


def test_transfer_description_is_carried(scenario):
    project, alpha, *_ = scenario
    section = _section(compile_skill(alpha, project=project), "## Next Steps")
    assert "`검증 규칙`" in section


def test_delegation_line_also_runs_the_transfer(scenario):
    project, alpha, *_ = scenario
    section = _section(compile_skill(alpha, project=project), "## Next Steps")
    assert "follow transition skill `handoff`, then delegate to agent `runner`" in section


def test_no_transfer_keeps_the_plain_wording():
    """transfer가 없으면 기존 문구 그대로 — 하위 호환."""
    alpha, beta = _proc("alpha"), _proc("beta")
    alpha.transfer_on = [EventDef(name="done")]
    project = PluginProject(name="p", skills=[alpha, beta])
    na = SimpleState(name="alpha", skill_ref=alpha)
    nb = SimpleState(name="beta", skill_ref=beta)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(
        Transition(source=na, target=nb, trigger=CompletionEvent(name="done"))
    )

    section = _section(compile_skill(alpha, project=project), "## Next Steps")
    assert "transition skill" not in section
    assert "- [completion event `done`] → invoke skill `beta`" in section


def test_delegation_inline_followup_carries_its_own_transfer():
    """위임 인라인("after the agent returns: …")의 후속 전이도 각자의 transfer를 갖는다."""
    alpha, beta = _proc("alpha"), _proc("beta")
    alpha.call_agents = [EventDef(name="delegate")]
    after = _transfer("after-agent")
    agent = _agent()
    project = PluginProject(name="p", skills=[alpha, beta, after], agents=[agent])
    na = SimpleState(name="alpha", skill_ref=alpha)
    nb = SimpleState(name="beta", skill_ref=beta)
    ng = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([na, nb, ng])
    project.graph.transitions.extend([
        Transition(source=na, target=ng, trigger=CompletionEvent(name="delegate")),
        Transition(
            source=ng, target=nb, trigger=CompletionEvent(name="ok"), skill_ref=after,
        ),
    ])

    section = _section(compile_skill(alpha, project=project), "## Next Steps")
    assert "after the agent returns:" in section
    assert "follow transition skill `after-agent`, then invoke skill `beta`" in section


# --- 2. 에이전트 호출 계약이 transfer를 언급한다 ---


def test_call_contract_mentions_the_transfer(scenario):
    project, _alpha, _beta, agent, *_ = scenario
    section = _section(compile_agent(agent, project=project), "## Invocation Contract")
    assert "the caller follows transition skill `handoff` before delegating" in section


def test_call_contract_without_transfer_is_unchanged():
    alpha = _proc("alpha")
    alpha.call_agents = [EventDef(name="delegate")]
    agent = _agent()
    project = PluginProject(name="p", skills=[alpha], agents=[agent])
    na = SimpleState(name="alpha", skill_ref=alpha)
    ng = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([na, ng])
    project.graph.transitions.append(
        Transition(source=na, target=ng, trigger=CompletionEvent(name="delegate"))
    )

    section = _section(compile_agent(agent, project=project), "## Invocation Contract")
    assert "transition skill" not in section
    assert "- from `alpha` via port `delegate`" in section


# --- 3. 도착 스킬 "진입 맥락"은 기존 문구 유지 (수행된 것을 전제로 읽는다) ---


def test_entry_context_still_assumes_the_transfer_ran(scenario):
    project, _alpha, beta, *_ = scenario
    section = _section(compile_skill(beta, project=project), "## Entry Context")
    assert (
        "transition skill `validate` (`검증 규칙`) has already been followed"
        in section
    )


# --- 4. 재사용 금지 규칙 ---


def _reuse_errors(project) -> list:
    return [
        e for e in Validator.validate_project(project)
        if e.rule == "transfer_skill_reused"
    ]


def test_single_use_passes(scenario):
    project, *_ = scenario
    assert _reuse_errors(project) == []


def test_two_transitions_is_an_error(scenario):
    project, alpha, beta, _agent, validate, _handoff = scenario
    # validate를 두 번째 전이에도 붙인다
    na = next(
        s for s in project.graph.states if getattr(s, "skill_ref", None) is alpha
    )
    nb = next(
        s for s in project.graph.states if getattr(s, "skill_ref", None) is beta
    )
    project.graph.transitions.append(
        Transition(
            source=nb, target=na, trigger=CompletionEvent(name="back"),
            skill_ref=validate,
        )
    )

    errors = _reuse_errors(project)
    assert len(errors) == 1
    assert errors[0].source == "validate"
    assert errors[0].is_warning is False  # 에러 등급
    assert errors[0].subject is validate


def test_error_message_lists_where(scenario):
    """어디에 붙었는지 알려 줘야 고칠 수 있다."""
    project, alpha, beta, _agent, validate, _handoff = scenario
    na = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is alpha)
    nb = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is beta)
    project.graph.transitions.append(
        Transition(source=nb, target=na, skill_ref=validate)
    )

    message = _reuse_errors(project)[0].message
    assert "alpha→beta" in message
    assert "beta→alpha" in message


def test_reuse_across_skill_fsm_is_caught():
    """프로젝트 그래프 밖(스킬 자체 FSM)의 전이도 순회 범위다."""
    host = _proc("host")
    other = _proc("other")
    shared = _transfer("shared")
    project = PluginProject(name="p", skills=[host, other, shared])

    na = SimpleState(name="host", skill_ref=host)
    nb = SimpleState(name="other", skill_ref=other)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(
        Transition(source=na, target=nb, skill_ref=shared)
    )
    # 같은 transition skill이 host의 자체 FSM 전이에도 붙어 있다
    inner_a = SimpleState(name="x")
    inner_b = SimpleState(name="y")
    host.fsm.states.extend([inner_a, inner_b])
    host.fsm.transitions.append(
        Transition(source=inner_a, target=inner_b, skill_ref=shared)
    )

    errors = _reuse_errors(project)
    assert len(errors) == 1
    assert "project:" in errors[0].message
    assert "skill:host" in errors[0].message


def test_reuse_inside_composite_is_caught():
    """CompositeState.sub_machine 재귀 — 블랙보드 규칙과 같은 범위."""
    from daedalus.model.fsm.state import CompositeState

    host = _proc("host")
    shared = _transfer("shared")
    project = PluginProject(name="p", skills=[host, shared])

    a, b = SimpleState(name="a"), SimpleState(name="b")
    sub = StateMachine(name="sub", initial_state=a, states=[a, b])
    sub.transitions.append(Transition(source=a, target=b, skill_ref=shared))
    composite = CompositeState(name="c", sub_machine=sub)

    outer_a, outer_b = SimpleState(name="oa"), SimpleState(name="ob")
    host.fsm.states.extend([composite, outer_a, outer_b])
    host.fsm.transitions.append(
        Transition(source=outer_a, target=outer_b, skill_ref=shared)
    )

    assert len(_reuse_errors(project)) == 1


def test_two_different_transfer_skills_are_fine(scenario):
    project, *_ = scenario
    assert _reuse_errors(project) == []


def test_three_uses_reported_once(scenario):
    """한 스킬이 세 번 붙어도 에러는 1건 — 같은 사실을 세 번 말하지 않는다."""
    project, alpha, beta, _agent, validate, _handoff = scenario
    na = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is alpha)
    nb = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is beta)
    project.graph.transitions.append(
        Transition(source=nb, target=na, skill_ref=validate)
    )
    project.graph.transitions.append(
        Transition(source=na, target=nb, skill_ref=validate)
    )

    errors = _reuse_errors(project)
    assert len(errors) == 1
    assert "3곳" in errors[0].message


def test_compile_gate_rejects_reuse(scenario, tmp_path):
    """에러 등급이므로 컴파일이 거부된다."""
    from daedalus.compiler.project_compiler import compile_project

    project, alpha, beta, _agent, validate, _handoff = scenario
    na = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is alpha)
    nb = next(s for s in project.graph.states if getattr(s, "skill_ref", None) is beta)
    project.graph.transitions.append(
        Transition(source=nb, target=na, skill_ref=validate)
    )

    result = compile_project(project, tmp_path)
    assert not result.ok
    assert "transfer_skill_reused" in {e.rule for e in result.errors}
