"""fork 에이전트 검증 (사용자 확정 2026-09-13)."""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import (
    AgentDefinition,
    ExternalForkAgent,
    ForkAgent,
)
from daedalus.model.plugin.config import (
    AgentConfig,
    ExternalForkAgentConfig,
    ForkAgentConfig,
    SyncForkSkillConfig,
)
from daedalus.model.plugin.enums import EffortLevel, ModelType
from daedalus.model.plugin.skill import AsyncForkSkill, ForkSkill, SyncForkSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator


def _agent(name: str, model=ModelType.INHERIT, calls=(), **cfg) -> AgentDefinition:
    entry = EntryPoint(name="s")
    return AgentDefinition(
        fsm=StateMachine(name=name, states=[entry], initial_state=entry),
        name=name, description=f"{name}.",
        config=AgentConfig(model=model, **cfg),
        transfer_on=[EventDef(name="done")],
        call_agents=[EventDef(name=c) for c in calls],
    )


def _fork_agent(name: str, model=ModelType.INHERIT, **cfg) -> ForkAgent:
    """fork 실행 기반 에이전트 (배치 불가 종류)."""
    return ForkAgent(
        name=name, description=f"{name}.", config=ForkAgentConfig(model=model, **cfg),
    )


def _fork(agent: str, model=ModelType.INHERIT, calls=(), effort=None,
          cls=SyncForkSkill, name="scout") -> ForkSkill:
    entry = EntryPoint(name="s")
    return cls(
        fsm=StateMachine(name="f", states=[entry], initial_state=entry),
        name=name, description=f"{name}.",
        config=SyncForkSkillConfig(agent=agent, model=model, effort=effort),
        call_agents=[EventDef(name=c) for c in calls],
    )


def _found(project) -> dict[str, bool]:
    """규칙 이름 → 경고인가."""
    return {e.rule: e.is_warning for e in Validator.validate_project(project)}


def test_builtin_agent_passes():
    project = PluginProject(name="p", skills=[_fork("Explore")])
    assert not any(r.startswith("fork_") for r in _found(project))


def test_unknown_agent_is_error():
    found = _found(PluginProject(name="p", skills=[_fork("explore")]))  # 대소문자 틀림
    assert found.get("fork_agent_missing") is False


def test_unregistered_plugin_agent_string_is_missing():
    """`플러그인:이름` 원문을 그대로 적으면 **등록되지 않은 이름**이다 (WP-EX).

    역할 고정 이후 외부 에이전트도 먼저 컴포넌트로 등록한다 — 등록하지 않은
    이름은 자체 fork 에이전트를 잘못 적은 경우와 **똑같이** `fork_agent_missing`
    이고, 종전의 별도 등급(`fork_agent_undeclared_plugin`)은 사라졌다.
    """
    project = PluginProject(name="p", skills=[_fork("tools:reviewer")])
    found = _found(project)
    assert found.get("fork_agent_missing") is False
    assert "fork_agent_undeclared_plugin" not in found
    # 사용 선언만으로는 달라지지 않는다 — 등록이 필요하다.
    project.external_plugins = ["tools@market"]
    assert _found(project).get("fork_agent_missing") is False


def _external_fork_agent(name: str, source: str) -> ExternalForkAgent:
    return ExternalForkAgent(
        name=name, description=f"{name}.",
        config=ExternalForkAgentConfig(source=source),
    )


def test_registered_external_fork_agent_passes():
    """등록한 외부 fork 에이전트를 이름으로 고르면 fork 규칙은 조용하다 (WP-EX).

    남는 것은 **사용 선언** 한 갈래뿐이다 — 선언이 없으면
    `undeclared_external_plugin` 경고이고, 선언하면 아무 경고도 없다.
    """
    project = PluginProject(
        name="p",
        skills=[_fork("critic")],
        agents=[_external_fork_agent("critic", "tools@market:reviewer")],
    )
    found = _found(project)
    assert not any(r.startswith("fork_") for r in found)
    assert found.get("undeclared_external_plugin") is True
    project.external_plugins = ["tools@market"]
    found = _found(project)
    assert not any(r.startswith("fork_") for r in found)
    assert "undeclared_external_plugin" not in found
    assert "unused_external_plugin" not in found


def test_unused_external_fork_agent_warns():
    """아무 fork 스킬도 부르지 않으면 자체 fork 에이전트와 같은 경고다."""
    project = PluginProject(
        name="p", agents=[_external_fork_agent("critic", "tools@market:reviewer")],
    )
    assert _found(project).get("unused_fork_agent") is True


def test_workflow_agent_as_fork_agent_is_error():
    """워크플로 에이전트는 fork 에이전트가 될 수 없다 — 배치 여부와 무관하다."""
    helper = _agent("helper")
    project = PluginProject(name="p", skills=[_fork("helper")], agents=[helper])
    assert _found(project).get("fork_agent_wrong_kind") is False
    # 배치돼 있어도 같은 에러 1건이다 (배치는 더 이상 판정 근거가 아니다).
    project.graph.states.append(SimpleState(name="helper", skill_ref=helper))
    errors = [
        e for e in Validator.validate_project(project)
        if e.rule == "fork_agent_wrong_kind"
    ]
    assert len(errors) == 1
    assert "워크플로 에이전트" in errors[0].message


def test_fork_agent_kind_passes():
    project = PluginProject(
        name="p", skills=[_fork("helper")], agents=[_fork_agent("helper")],
    )
    assert not any(r.startswith("fork_") for r in _found(project))
    assert "unused_fork_agent" not in _found(project)


def test_async_fork_agent_kind_passes():
    project = PluginProject(
        name="p",
        skills=[_fork("helper", cls=AsyncForkSkill)],
        agents=[_fork_agent("helper")],
    )
    assert not any(r.startswith("fork_") for r in _found(project))


def test_unreferenced_fork_agent_warns():
    project = PluginProject(name="p", agents=[_fork_agent("idle")])
    assert _found(project).get("unused_fork_agent") is True


def test_unreferenced_fork_agent_warns_once_per_agent():
    project = PluginProject(
        name="p",
        skills=[_fork("used"), _fork("used", name="scout2")],
        agents=[_fork_agent("used"), _fork_agent("idle")],
    )
    warned = [
        e.source for e in Validator.validate_project(project)
        if e.rule == "unused_fork_agent"
    ]
    assert warned == ["idle"]


def test_unplaced_workflow_agent_is_not_unused_fork_agent():
    """워크플로 에이전트는 이 경고 대상이 아니다 (캔버스 노드로 불린다)."""
    project = PluginProject(name="p", agents=[_agent("solo")])
    assert "unused_fork_agent" not in _found(project)


def test_model_clash_warns_only_when_both_set_and_differ():
    def found(skill_model, agent_model, skill_effort=None, agent_effort=None):
        helper = _fork_agent("helper", model=agent_model, effort=agent_effort)
        fork = _fork("helper", model=skill_model, effort=skill_effort)
        return _found(PluginProject(name="p", skills=[fork], agents=[helper]))

    assert found(ModelType.OPUS, ModelType.HAIKU).get("fork_model_overrides_agent") is True
    assert "fork_model_overrides_agent" not in found(ModelType.INHERIT, ModelType.HAIKU)
    assert "fork_model_overrides_agent" not in found(ModelType.OPUS, ModelType.OPUS)
    assert "fork_model_overrides_agent" in found(
        ModelType.INHERIT, ModelType.INHERIT, EffortLevel.LOW, EffortLevel.HIGH
    )


def test_isolation_rule_is_retired():
    """fork_agent_isolation_ignored 퇴역 — ForkAgentConfig에 isolation이 없다.

    실측 재확인 2026-09-18(CC 2.1.274): fork 실행에는 isolation이 적용되지 않는다.
    필드 자체를 없앴으므로 경고할 대상이 남지 않는다(퇴역 개념은 흔적 없이).
    """
    from daedalus.model.validation import WARNING_RULES

    assert "fork_agent_isolation_ignored" not in WARNING_RULES
    assert not hasattr(ForkAgentConfig(), "isolation")
    project = PluginProject(
        name="p", skills=[_fork("helper")], agents=[_fork_agent("helper")],
    )
    assert "fork_agent_isolation_ignored" not in _found(project)


def _fork_calls(fork: ForkSkill, *agents: AgentDefinition) -> PluginProject:
    """fork → agents[0] → agents[1] → … 호출 체인."""
    project = PluginProject(name="p", skills=[fork], agents=list(agents))
    nodes = [SimpleState(name=fork.name, skill_ref=fork)]
    nodes += [SimpleState(name=a.name, skill_ref=a) for a in agents]
    project.graph.states.extend(nodes)
    callers = [fork, *agents]
    for i in range(len(agents)):
        project.graph.transitions.append(Transition(
            source=nodes[i], target=nodes[i + 1],
            trigger=CompletionEvent(name=callers[i].call_agents[0].name),
        ))
    return project


def test_fork_counts_as_one_agent_layer():
    ok = _fork_calls(_fork("Explore", calls=["a"]), _agent("a", calls=["b"]), _agent("b"))
    assert "agent_chain_too_deep" not in _found(ok)
    deep = _fork_calls(
        _fork("Explore", calls=["a"]),
        _agent("a", calls=["b"]), _agent("b", calls=["c"]), _agent("c"),
    )
    assert _found(deep).get("agent_chain_too_deep") is False


def test_fork_calling_higher_model_uses_body_model_when_skill_empty():
    helper = _fork_agent("helper", model=ModelType.HAIKU)
    project = _fork_calls(_fork("helper", calls=["a"]), _agent("a", model=ModelType.OPUS))
    project.agents.append(helper)
    assert _found(project).get("agent_calls_higher_model") is False
