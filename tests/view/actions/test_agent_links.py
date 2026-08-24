"""에이전트 호출자 유도 (A9-4) — 공유 함수.

누가 이 에이전트를 부르는지는 모델 어디에도 적혀 있지 않고 프로젝트 그래프에서
유도할 뿐이다(WP-CT). 컴파일의 "## Invocation Contract"과 **같은 유도**여야 화면과 산출이
같은 말을 한다.
"""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.actions.agent_links import callers_of


def _proc(name: str, call_ports: list[EventDef] | None = None) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name=name, description="d")
    if call_ports:
        skill.call_agents = list(call_ports)
    return skill


def _agent(name: str = "runner") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="af", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name=name, description="d", transfer_on=[EventDef(name="done")],
    )


def _wire(project, source_state, target_state, trigger: str | None):
    trans = Transition(
        source=source_state, target=target_state,
        trigger=CompletionEvent(name=trigger) if trigger else None,
    )
    project.graph.transitions.append(trans)
    return trans


def test_no_callers_is_empty():
    agent = _agent()
    project = PluginProject(name="p", agents=[agent])
    project.graph.states.append(SimpleState(name="runner", skill_ref=agent))
    assert callers_of(agent, project) == []


def test_caller_with_port_and_description():
    port = EventDef(name="analyze", description="파일 목록을 넘긴다")
    caller = _proc("driver", [port])
    agent = _agent()
    project = PluginProject(name="p", skills=[caller], agents=[agent])
    ns = SimpleState(name="driver", skill_ref=caller)
    na = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([ns, na])
    _wire(project, ns, na, "analyze")

    (ref,) = callers_of(agent, project)
    assert ref.caller is caller
    assert ref.caller_name == "driver"
    assert ref.port == "analyze"
    assert ref.description == "파일 목록을 넘긴다"
    assert ref.source_state is ns
    assert ref.label == "driver · analyze"


def test_label_without_port():
    caller = _proc("driver")
    agent = _agent()
    project = PluginProject(name="p", skills=[caller], agents=[agent])
    ns = SimpleState(name="driver", skill_ref=caller)
    na = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([ns, na])
    _wire(project, ns, na, None)

    (ref,) = callers_of(agent, project)
    assert ref.label == "driver"


def test_sorted_by_caller_then_port():
    """정렬 기준이 컴파일의 호출 계약과 같아야 둘을 나란히 놓고 볼 수 있다."""
    a = _proc("zeta", [EventDef(name="b"), EventDef(name="a")])
    b = _proc("alpha", [EventDef(name="x")])
    agent = _agent()
    project = PluginProject(name="p", skills=[a, b], agents=[agent])
    na_z = SimpleState(name="zeta", skill_ref=a)
    na_a = SimpleState(name="alpha", skill_ref=b)
    tgt = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([na_z, na_a, tgt])
    _wire(project, na_z, tgt, "b")
    _wire(project, na_z, tgt, "a")
    _wire(project, na_a, tgt, "x")

    assert [r.label for r in callers_of(agent, project)] == [
        "alpha · x", "zeta · a", "zeta · b",
    ]


def test_empty_source_node_is_skipped():
    """빈 노드에서 온 전이는 가리킬 호출자가 없다."""
    agent = _agent()
    project = PluginProject(name="p", agents=[agent])
    empty = SimpleState(name="empty")
    tgt = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([empty, tgt])
    _wire(project, empty, tgt, "x")
    assert callers_of(agent, project) == []


def test_other_agents_transitions_are_excluded():
    caller = _proc("driver", [EventDef(name="go")])
    a1, a2 = _agent("one"), _agent("two")
    project = PluginProject(name="p", skills=[caller], agents=[a1, a2])
    ns = SimpleState(name="driver", skill_ref=caller)
    n1 = SimpleState(name="one", skill_ref=a1)
    n2 = SimpleState(name="two", skill_ref=a2)
    project.graph.states.extend([ns, n1, n2])
    _wire(project, ns, n1, "go")

    assert [r.caller_name for r in callers_of(a1, project)] == ["driver"]
    assert callers_of(a2, project) == []


def test_matches_compiler_call_contract():
    """컴파일 산출의 호출 계약과 같은 (호출자, 포트) 쌍을 낸다."""
    from daedalus.compiler.emit import compile_agent

    caller = _proc("driver", [EventDef(name="analyze", description="넘긴다")])
    agent = _agent()
    project = PluginProject(name="p", skills=[caller], agents=[agent])
    ns = SimpleState(name="driver", skill_ref=caller)
    na = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([ns, na])
    _wire(project, ns, na, "analyze")

    text = compile_agent(agent, project=project)
    (ref,) = callers_of(agent, project)
    assert "## Invocation Contract" in text
    assert ref.caller_name in text
    assert ref.port in text


def test_no_graph_is_safe():
    assert callers_of(_agent(), None) == []
