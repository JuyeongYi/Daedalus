"""에이전트가 에이전트를 부른다 — 호출 포트·깊이·모델 티어 (2026-09-12).

배경: CC가 서브에이전트의 중첩 스폰을 허용한다(주 대화 기준 3계층, 실측 확인).
그래서 에이전트에도 스킬과 **같은 `call_agents` 포트**를 둔다. 남은 제약 둘은
검증이 에러로 잡는다 — 깊이 한계(`agent_chain_too_deep`)와 상위 모델 호출
금지(`agent_calls_higher_model`, 사용자 확정).
"""
from __future__ import annotations

import pytest

from daedalus.compiler.emit import compile_agent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig
from daedalus.model.plugin.enums import MODEL_TIER, ModelType
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


def _agent(name: str, model: ModelType = ModelType.INHERIT, calls: list[str] | None = None):
    entry = EntryPoint(name="s")
    return AgentDefinition(
        fsm=StateMachine(name=f"{name}_fsm", states=[entry], initial_state=entry),
        name=name, description=f"{name} agent.",
        config=AgentConfig(model=model),
        transfer_on=[EventDef(name="done")],
        call_agents=[EventDef(name=c, description=f"{c} 작업") for c in (calls or [])],
    )


def _skill(name: str, calls: list[str] | None = None) -> ProceduralSkill:
    entry = EntryPoint(name="s")
    return ProceduralSkill(
        fsm=StateMachine(name=f"{name}_fsm", states=[entry], initial_state=entry),
        name=name, description=f"{name} skill.", config=ProceduralSkillConfig(),
        transfer_on=[EventDef(name="done")],
        call_agents=[EventDef(name=c) for c in (calls or [])],
    )


def _chain(*agents: AgentDefinition) -> PluginProject:
    """agents[0] → agents[1] → … 호출 체인을 가진 프로젝트."""
    project = PluginProject(name="p")
    project.agents.extend(agents)
    nodes = []
    for agent in agents:
        node = SimpleState(name=agent.name, skill_ref=agent)
        project.graph.states.append(node)
        nodes.append(node)
    for i in range(len(agents) - 1):
        port = agents[i].call_agents[0].name
        project.graph.transitions.append(Transition(
            source=nodes[i], target=nodes[i + 1], trigger=CompletionEvent(name=port),
        ))
    return project


def _node(project, component):
    """컴포넌트의 그래프 배치 노드. **인덱스로 찾지 마라** — graph.states[0]은
    EntryPoint(WP-EP)라 한 칸씩 밀린다."""
    return next(
        s for s in project.graph.states
        if getattr(s, "skill_ref", None) is component
    )


def _rules(project) -> list[str]:
    return [e.rule for e in Validator.validate_project(project)]


# ─────────────────────────── 모델 · 직렬화 ───────────────────────────


def test_agent_call_ports_roundtrip():
    project = PluginProject(name="p")
    project.agents.append(_agent("lead", calls=["research"]))
    loaded = deserialize_project(serialize_project(project))
    assert [e.name for e in loaded.agents[0].call_agents] == ["research"]
    assert loaded.agents[0].call_agents[0].description == "research 작업"


def test_legacy_file_without_call_agents_loads_empty():
    """구버전 파일(키 부재)은 빈 목록 — 경고 없이 조용히."""
    data = serialize_project(PluginProject(name="p", agents=[_agent("solo")]))
    del data["agents"][0]["call_agents"]
    assert deserialize_project(data).agents[0].call_agents == []


# ─────────────────────────── 깊이 규칙 ───────────────────────────


@pytest.mark.parametrize("count, expect_error", [(2, False), (3, False), (4, True)])
def test_agent_chain_depth_limit(count: int, expect_error: bool):
    agents = [_agent(f"a{i}", calls=["next"]) for i in range(count)]
    project = _chain(*agents)
    assert ("agent_chain_too_deep" in _rules(project)) is expect_error


def test_agent_chain_depth_reports_once_per_chain():
    """같은 체인을 노드마다 반복해 짚지 않는다 — 시작점에서 한 번."""
    project = _chain(*[_agent(f"a{i}", calls=["next"]) for i in range(5)])
    hits = [e for e in Validator.validate_project(project)
            if e.rule == "agent_chain_too_deep"]
    assert len(hits) == 1
    assert "a0" in hits[0].message


def test_agent_call_cycle_is_error():
    a, b = _agent("a", calls=["to_b"]), _agent("b", calls=["to_a"])
    project = _chain(a, b)
    project.graph.transitions.append(Transition(
        source=_node(project, b), target=_node(project, a),
        trigger=CompletionEvent(name="to_a"),
    ))
    hits = [e for e in Validator.validate_project(project)
            if e.rule == "agent_chain_too_deep"]
    assert hits and "순환" in hits[0].message


def test_skill_in_the_middle_resets_depth():
    """중간에 스킬을 끼우면 그 스킬이 메인 스레드에서 돌아 깊이가 다시 1부터다."""
    a1, a2 = _agent("a1", calls=["next"]), _agent("a2", calls=["next"])
    a3, a4 = _agent("a3", calls=["next"]), _agent("a4")
    project = _chain(a1, a2)
    project.agents.extend([a3, a4])
    relay = _skill("relay", calls=["next"])
    project.skills.append(relay)
    n_relay = SimpleState(name="relay", skill_ref=relay)
    n3 = SimpleState(name="a3", skill_ref=a3)
    n4 = SimpleState(name="a4", skill_ref=a4)
    project.graph.states.extend([n_relay, n3, n4])
    project.graph.transitions.extend([
        Transition(source=_node(project, a2), target=n_relay,
                   trigger=CompletionEvent(name="done")),
        Transition(source=n_relay, target=n3, trigger=CompletionEvent(name="next")),
        Transition(source=n3, target=n4, trigger=CompletionEvent(name="next")),
    ])
    assert "agent_chain_too_deep" not in _rules(project)


# ─────────────────────────── 모델 티어 규칙 ───────────────────────────


def test_calling_higher_model_agent_is_error():
    project = _chain(
        _agent("worker", ModelType.SONNET, calls=["review"]),
        _agent("judge", ModelType.OPUS),
    )
    hits = [e for e in Validator.validate_project(project)
            if e.rule == "agent_calls_higher_model"]
    assert hits
    assert "worker" in hits[0].message and "judge" in hits[0].message


@pytest.mark.parametrize("caller, callee", [
    (ModelType.OPUS, ModelType.SONNET),   # 하위 호출 — 정상
    (ModelType.OPUS, ModelType.OPUS),     # 동급 — 정상
    (ModelType.INHERIT, ModelType.OPUS),  # 미지정은 판정 불가 — 스킵
    (ModelType.SONNET, ModelType.INHERIT),
])
def test_same_or_lower_model_is_fine(caller: ModelType, callee: ModelType):
    project = _chain(_agent("a", caller, calls=["x"]), _agent("b", callee))
    assert "agent_calls_higher_model" not in _rules(project)


def test_model_tier_order():
    assert (MODEL_TIER[ModelType.HAIKU] < MODEL_TIER[ModelType.SONNET]
            < MODEL_TIER[ModelType.OPUS] < MODEL_TIER[ModelType.FABLE])
    assert ModelType.INHERIT not in MODEL_TIER


def test_skill_calling_higher_model_agent_is_fine():
    """스킬은 메인 스레드에서 돈다 — 상위 모델 에이전트를 불러도 된다."""
    project = PluginProject(name="p")
    skill = _skill("lead", calls=["review"])
    agent = _agent("judge", ModelType.FABLE)
    project.skills.append(skill)
    project.agents.append(agent)
    n_s = SimpleState(name="lead", skill_ref=skill)
    n_a = SimpleState(name="judge", skill_ref=agent)
    project.graph.states.extend([n_s, n_a])
    project.graph.transitions.append(Transition(
        source=n_s, target=n_a, trigger=CompletionEvent(name="review"),
    ))
    assert "agent_calls_higher_model" not in _rules(project)


# ─────────────────────────── 컴파일 ───────────────────────────


def test_delegation_section_in_caller_agent():
    project = _chain(_agent("lead", calls=["research"]), _agent("scout"))
    text = compile_agent(project.agents[0], project=project)
    assert "## Delegation" in text
    assert "- `research` → delegate to agent `scout`" in text
    assert "research 작업" in text  # 포트 description이 지시에 합류
    # 진행 기록은 메인 스레드 소유 — 중첩 구간에서 건드리라고 하지 않는다
    assert "summarize what" in text


def test_callee_agent_gets_invocation_contract():
    project = _chain(_agent("lead", calls=["research"]), _agent("scout"))
    text = compile_agent(project.agents[1], project=project)
    assert "## Invocation Contract" in text
    assert "from `lead` via port `research`" in text


def test_no_delegation_section_without_agent_targets():
    project = _chain(_agent("solo"))
    assert "## Delegation" not in compile_agent(project.agents[0], project=project)
