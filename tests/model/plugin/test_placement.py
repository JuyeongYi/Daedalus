"""배치 가능 판정 + fork 스킬 역참조 — model/plugin/placement.py.

**두 판정이다.** 하나로 합치면 참조 스킬 경로가 죽는다: 참조 스킬은 상태 노드가
될 수 없지만 캔버스에는 참조 노드로 놓인다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.config import (
    AsyncForkSkillConfig,
    SyncForkSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.placement import (
    fork_skills_using,
    is_canvas_placeable,
    is_state_placeable,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)
from daedalus.model.project import PluginProject


def _fsm() -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name="m", states=[s], initial_state=s)


def _wrapped(usage: str) -> WrappedSkill:
    return WrappedSkill(
        fsm=_fsm(), name="w", description="d",
        config=WrappedSkillConfig(source="p:s", usage=usage),
    )


_STATE_PLACEABLE = [
    ProceduralSkill(fsm=_fsm(), name="p", description="d"),
    SyncForkSkill(fsm=_fsm(), name="sf", description="d"),
    AsyncForkSkill(fsm=_fsm(), name="af", description="d"),
    AgentDefinition(fsm=_fsm(), name="a", description="d"),
    _wrapped("state"),
    _wrapped(""),  # 용도 미정 — 배치 경로가 state로 고정한다(오늘 동작 유지)
]

_NOT_STATE_PLACEABLE = [
    DeclarativeSkill(name="dc", description="d"),
    TransferSkill(fsm=_fsm(), name="t", description="d"),
    ReferenceSkill(name="r", description="d"),
    _wrapped("reference"),
    ForkAgent(name="fa", description="d"),
]


@pytest.mark.parametrize("comp", _STATE_PLACEABLE, ids=lambda c: c.kind + "/" + c.name)
def test_state_placeable(comp):
    assert is_state_placeable(comp) is True
    assert is_canvas_placeable(comp) is True


@pytest.mark.parametrize(
    "comp", _NOT_STATE_PLACEABLE, ids=lambda c: c.kind + "/" + c.name
)
def test_not_state_placeable(comp):
    assert is_state_placeable(comp) is False


def test_reference_nodes_are_canvas_placeable_but_not_state_placeable():
    """참조는 상태 노드가 아니지만 캔버스에는 놓인다 — 두 판정이 갈리는 지점."""
    for comp in (ReferenceSkill(name="r", description="d"), _wrapped("reference")):
        assert is_state_placeable(comp) is False
        assert is_canvas_placeable(comp) is True


def test_fork_agent_is_not_placeable_at_all():
    fa = ForkAgent(name="fa", description="d")
    assert is_state_placeable(fa) is False
    assert is_canvas_placeable(fa) is False


def test_non_components_are_not_placeable():
    for value in (None, "procedural", 3):
        assert is_state_placeable(value) is False
        assert is_canvas_placeable(value) is False


# ── fork_skills_using ───────────────────────────────────────────────────

def test_fork_skills_using_is_sorted_and_kind_filtered():
    helper = ForkAgent(name="helper", description="d")
    forks = [
        SyncForkSkill(
            fsm=_fsm(), name="zulu", description="d",
            config=SyncForkSkillConfig(agent="helper"),
        ),
        AsyncForkSkill(
            fsm=_fsm(), name="alpha", description="d",
            config=AsyncForkSkillConfig(agent="helper"),
        ),
        SyncForkSkill(
            fsm=_fsm(), name="other", description="d",
            config=SyncForkSkillConfig(agent="Explore"),
        ),
    ]
    proc = ProceduralSkill(fsm=_fsm(), name="plain", description="d")
    project = PluginProject(name="p", skills=[*forks, proc], agents=[helper])
    assert fork_skills_using(helper, project) == ["alpha", "zulu"]


def test_fork_skills_using_tolerates_missing_project_pieces():
    helper = ForkAgent(name="helper", description="d")
    assert fork_skills_using(helper, None) == []
    assert fork_skills_using(helper, PluginProject(name="p")) == []


def test_compiler_reexport_is_the_same_function():
    """컴파일러의 종전 임포트 경로는 살아 있되 실체는 모델 하나다(원칙 1)."""
    from daedalus.compiler.emit.fork import fork_skills_using as reexported

    assert reexported is fork_skills_using
