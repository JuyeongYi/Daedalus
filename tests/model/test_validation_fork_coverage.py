"""fork 스킬(sync/async)의 단계 스킬 검증 커버리지 (WP-A 리뷰 반영).

계층이 `ForkSkill ⊂ ProceduralSkill`에서 `ForkSkill ⊂ StepSkill`로 갈라지면서
`isinstance(x, ProceduralSkill)` 판정 세 곳이 **테스트 실패 없이** fork 스킬을
놓칠 수 있었다(조용한 커버리지 소실). 세 규칙 각각에 sync/async fork 케이스를
고정해 그 구멍이 다시 열리지 않게 한다.

- `transfer_on_not_empty` (machine_rules)
- `trigger_unknown_event` (machine_rules)
- `mid_chain_user_invocable` (project_rules/workflow)
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import AsyncForkSkill, SyncForkSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator

_FORK_CLASSES = [SyncForkSkill, AsyncForkSkill]


def _fork(cls, name: str, transfer_on: list | None = None):
    s = SimpleState(name="s")
    fsm = StateMachine(name=f"{name}-fsm", initial_state=s, states=[s], final_states=[s])
    return cls(
        fsm=fsm, name=name, description="d", transfer_on=list(transfer_on or []),
    )


def _sm(states, transitions=()):
    return StateMachine(
        name="t", states=list(states), transitions=list(transitions),
        initial_state=states[0],
    )


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_transfer_on_not_empty_covers_fork_skills(cls):
    """fork 스킬도 갈래를 선언해야 한다 — 보고의 EXIT 줄이 그 갈래다."""
    skill = _fork(cls, "probe")
    sm = _sm([SimpleState(name="node", skill_ref=skill)])
    errors = Validator.validate(sm)
    assert [e.rule for e in errors if e.rule == "transfer_on_not_empty"] == [
        "transfer_on_not_empty"
    ]


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_transfer_on_not_empty_passes_for_fork_with_events(cls):
    skill = _fork(cls, "probe", [EventDef("done")])
    sm = _sm([SimpleState(name="node", skill_ref=skill)])
    errors = Validator.validate(sm)
    assert not any(e.rule == "transfer_on_not_empty" for e in errors)


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_trigger_unknown_event_covers_fork_skills(cls):
    skill = _fork(cls, "probe", [EventDef("success")])
    node = SimpleState(name="node", skill_ref=skill)
    nxt = SimpleState(name="next")
    sm = _sm(
        [node, nxt],
        [Transition(source=node, target=nxt, trigger=CompletionEvent(name="ghost"))],
    )
    errors = Validator.validate(sm)
    matching = [e for e in errors if e.rule == "trigger_unknown_event"]
    assert len(matching) == 1
    assert "ghost" in matching[0].message


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_trigger_known_event_passes_for_fork_skills(cls):
    skill = _fork(cls, "probe", [EventDef("done")])
    node = SimpleState(name="node", skill_ref=skill)
    nxt = SimpleState(name="next")
    sm = _sm(
        [node, nxt],
        [Transition(source=node, target=nxt, trigger=CompletionEvent(name="done"))],
    )
    errors = Validator.validate(sm)
    assert not any(e.rule == "trigger_unknown_event" for e in errors)


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_mid_chain_user_invocable_covers_fork_skills(cls):
    """체인 중간의 fork 스킬도 user-invocable 경고 대상이다 (A3)."""
    first = _fork(SyncForkSkill, "first", [EventDef("done")])
    second = _fork(cls, "second", [EventDef("done")])
    second.config.user_invocable = True
    project = PluginProject(name="p", skills=[first, second])
    n1 = SimpleState(name="first", skill_ref=first)
    n2 = SimpleState(name="second", skill_ref=second)
    project.graph.states.extend([n1, n2])
    project.graph.transitions.append(Transition(source=n1, target=n2))

    sources = [
        e.source for e in Validator.validate_project(project)
        if e.rule == "mid_chain_user_invocable"
    ]
    assert sources == ["second"]


@pytest.mark.parametrize("cls", _FORK_CLASSES)
def test_mid_chain_user_invocable_off_passes_for_fork_skills(cls):
    first = _fork(SyncForkSkill, "first", [EventDef("done")])
    second = _fork(cls, "second", [EventDef("done")])
    second.config.user_invocable = False
    project = PluginProject(name="p", skills=[first, second])
    n1 = SimpleState(name="first", skill_ref=first)
    n2 = SimpleState(name="second", skill_ref=second)
    project.graph.states.extend([n1, n2])
    project.graph.transitions.append(Transition(source=n1, target=n2))

    assert not any(
        e.rule == "mid_chain_user_invocable"
        for e in Validator.validate_project(project)
    )
