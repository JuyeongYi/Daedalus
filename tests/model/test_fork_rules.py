"""fork 에이전트 검증 (사용자 확정 2026-09-13)."""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import AgentConfig, SyncForkSkillConfig
from daedalus.model.plugin.enums import AgentIsolation, EffortLevel, ModelType
from daedalus.model.plugin.skill import ForkSkill, SyncForkSkill
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


def _fork(agent: str, model=ModelType.INHERIT, calls=(), effort=None) -> ForkSkill:
    entry = EntryPoint(name="s")
    return SyncForkSkill(
        fsm=StateMachine(name="f", states=[entry], initial_state=entry),
        name="scout", description="scout.",
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


def test_undeclared_plugin_agent_is_error_declared_passes():
    project = PluginProject(name="p", skills=[_fork("tools:reviewer")])
    assert _found(project).get("fork_agent_undeclared_plugin") is False
    project.external_plugins = ["tools@market"]
    assert "fork_agent_undeclared_plugin" not in _found(project)


def test_placed_fork_agent_is_error():
    helper = _agent("helper")
    project = PluginProject(name="p", skills=[_fork("helper")], agents=[helper])
    assert "fork_agent_placed" not in _found(project)
    project.graph.states.append(SimpleState(name="helper", skill_ref=helper))
    assert _found(project).get("fork_agent_placed") is False


def test_model_clash_warns_only_when_both_set_and_differ():
    def found(skill_model, agent_model, skill_effort=None, agent_effort=None):
        helper = _agent("helper", model=agent_model, effort=agent_effort)
        fork = _fork("helper", model=skill_model, effort=skill_effort)
        return _found(PluginProject(name="p", skills=[fork], agents=[helper]))

    assert found(ModelType.OPUS, ModelType.HAIKU).get("fork_model_overrides_agent") is True
    assert "fork_model_overrides_agent" not in found(ModelType.INHERIT, ModelType.HAIKU)
    assert "fork_model_overrides_agent" not in found(ModelType.OPUS, ModelType.OPUS)
    assert "fork_model_overrides_agent" in found(
        ModelType.INHERIT, ModelType.INHERIT, EffortLevel.LOW, EffortLevel.HIGH
    )


def test_body_isolation_warns():
    helper = _agent("helper", isolation=AgentIsolation.WORKTREE)
    project = PluginProject(name="p", skills=[_fork("helper")], agents=[helper])
    assert _found(project).get("fork_agent_isolation_ignored") is True


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
    helper = _agent("helper", model=ModelType.HAIKU)
    project = _fork_calls(_fork("helper", calls=["a"]), _agent("a", model=ModelType.OPUS))
    project.agents.append(helper)
    assert _found(project).get("agent_calls_higher_model") is False
