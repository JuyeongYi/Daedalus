# tests/compiler/builders.py
"""컴파일러 테스트용 모델 빌더 (순수 — Qt 무관)."""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import (
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DispatchMode,
    DynamicWorkflowDef,
    PhaseSpec,
    TeammateSpec,
    TeamSpawnDef,
    WaitMode,
)
from daedalus.model.plugin.enums import ModelType
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)


def make_linear_fsm(name: str = "m") -> StateMachine:
    """analyze → report (done) 2단계 선형 FSM."""
    s1 = SimpleState(name="analyze")
    s2 = SimpleState(name="report")
    sm = StateMachine(name=name, initial_state=s1, states=[s1, s2], final_states=[s2])
    sm.transitions.append(
        Transition(source=s1, target=s2, trigger=CompletionEvent(name="done"))
    )
    return sm


def make_procedural(
    name: str = "my-skill",
    *,
    description: str = "Does a thing",
    when_to_use: str = "the user wants a thing",
    config: ProceduralSkillConfig | None = None,
    sections: list[Section] | None = None,
    fsm: StateMachine | None = None,
) -> ProceduralSkill:
    return ProceduralSkill(
        fsm=fsm or make_linear_fsm(name),
        name=name,
        description=description,
        when_to_use=when_to_use,
        config=config or ProceduralSkillConfig(model=ModelType.SONNET),
        sections=sections or [Section("Instructions", "Do the work.")],
        transfer_on=[EventDef("done", description="success")],
    )


def make_declarative(name: str = "kb") -> DeclarativeSkill:
    return DeclarativeSkill(
        name=name,
        description="Background knowledge",
        when_to_use="reasoning about X",
        sections=[Section("Knowledge", "Facts here.")],
        config=DeclarativeSkillConfig(),
    )


def make_transfer(name: str = "edge-skill") -> TransferSkill:
    return TransferSkill(
        fsm=make_linear_fsm(name),
        name=name,
        description="Edge helper",
        when_to_use="on transition",
        sections=[Section("Instructions", "Run on edge.")],
        config=TransferSkillConfig(),
    )


def make_reference(name: str = "ref-doc") -> ReferenceSkill:
    return ReferenceSkill(
        name=name,
        description="Reference document",
        when_to_use="lookup",
        sections=[Section("Content", "Reference body.")],
        config=ReferenceSkillConfig(),
    )


def make_agent(name: str = "worker") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    work = SimpleState(name="work")
    done = ExitPoint(name="done")
    sm = StateMachine(
        name=f"{name}_fsm",
        initial_state=entry,
        states=[entry, work, done],
        final_states=[done],
    )
    sm.transitions.append(Transition(source=entry, target=work))
    sm.transitions.append(
        Transition(source=work, target=done, trigger=CompletionEvent(name="done"))
    )
    return AgentDefinition(
        fsm=sm,
        name=name,
        description="A worker agent",
        config=AgentConfig(model=ModelType.SONNET),
        sections=[Section("instruction", "Do agent work.")],
    )


def make_team_spawn(
    name: str,
    teammate_agent: AgentDefinition,
    *,
    composition: CompositionMode = CompositionMode.EXPLICIT,
    wait_mode: WaitMode = WaitMode.WAIT,
    guidance: str = "",
) -> TeamSpawnDef:
    return TeamSpawnDef(
        name=name,
        description="Spawn a team",
        composition=composition,
        wait_mode=wait_mode,
        guidance=guidance,
        teammates=[TeammateSpec(agent_ref=teammate_agent, count=2, role_note="reviewer")],
    )


def make_dynamic_workflow(
    name: str,
    *,
    composition: CompositionMode = CompositionMode.EXPLICIT,
    wait_mode: WaitMode = WaitMode.WAIT,
    guidance: str = "",
    phase_agent: AgentDefinition | None = None,
) -> DynamicWorkflowDef:
    return DynamicWorkflowDef(
        name=name,
        description="Run a workflow",
        composition=composition,
        wait_mode=wait_mode,
        guidance=guidance,
        objective="ship the feature",
        phases=[PhaseSpec(title="design", detail="sketch it", agent_ref=phase_agent)],
    )


def make_agora_dispatch(
    name: str,
    *,
    composition: CompositionMode = CompositionMode.EXPLICIT,
    wait_mode: WaitMode = WaitMode.WAIT,
    mode: DispatchMode = DispatchMode.DISPATCH,
) -> AgoraDispatchDef:
    return AgoraDispatchDef(
        name=name,
        description="Send to agora",
        composition=composition,
        wait_mode=wait_mode,
        mode=mode,
        target="inst-1",
        msgtype="task.assign",
        payload_note="include the spec",
    )


def make_delegation_skill(
    deleg, name: str = "deleg-skill",
) -> ProceduralSkill:
    """위임 노드 하나를 SimpleState로 배치한 ProceduralSkill."""
    node = SimpleState(name=deleg.name, skill_ref=deleg)
    end = SimpleState(name="end")
    sm = StateMachine(
        name=f"{name}_fsm",
        initial_state=node,
        states=[node, end],
        final_states=[end],
    )
    sm.transitions.append(
        Transition(source=node, target=end, trigger=CompletionEvent(name="done"))
    )
    return ProceduralSkill(
        fsm=sm,
        name=name,
        description="Skill with delegation",
        when_to_use="delegating",
        config=ProceduralSkillConfig(),
        sections=[Section("Instructions", "Delegate the work.")],
        transfer_on=[EventDef("done")],
    )
