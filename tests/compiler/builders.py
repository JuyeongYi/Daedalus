# tests/compiler/builders.py
"""컴파일러 테스트용 모델 빌더 (순수 — Qt 무관)."""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
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
    body: str | None = None,
    fsm: StateMachine | None = None,
) -> ProceduralSkill:
    return ProceduralSkill(
        fsm=fsm or make_linear_fsm(name),
        name=name,
        description=description,
        when_to_use=when_to_use,
        config=config or ProceduralSkillConfig(model=ModelType.SONNET),
        body=body if body is not None else "# Instructions\n\nDo the work.",
        transfer_on=[EventDef("done", description="success")],
    )


def make_declarative(name: str = "kb") -> DeclarativeSkill:
    return DeclarativeSkill(
        name=name,
        description="Background knowledge",
        when_to_use="reasoning about X",
        body="# Knowledge\n\nFacts here.",
        config=DeclarativeSkillConfig(),
    )


def make_transfer(name: str = "edge-skill") -> TransferSkill:
    return TransferSkill(
        fsm=make_linear_fsm(name),
        name=name,
        description="Edge helper",
        when_to_use="on transition",
        body="# Instructions\n\nRun on edge.",
        config=TransferSkillConfig(),
    )


def make_reference(name: str = "ref-doc") -> ReferenceSkill:
    return ReferenceSkill(
        name=name,
        description="Reference document",
        when_to_use="lookup",
        body="# Content\n\nReference body.",
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
        body="# instruction\n\nDo agent work.",
    )
