"""빌드 엔티티 계층 (사용자 확정 2026-09-17) — 추상/구체·필드 순서·매트릭스 키.

"구체 클래스가 구체 클래스를 상속하지 않는다"가 이 계층의 규칙이다:
스킬 추상(`StepSkill`/`ForkSkill`)과 에이전트 추상(`Agent`)이 공통을 담고,
`kind`를 말하는 클래스만 구체다.
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import Agent, AgentDefinition, ForkAgent
from daedalus.model.plugin.base import PluginComponent
from daedalus.model.plugin.config import (
    AgentConfig,
    AgentConfigBase,
    AsyncForkSkillConfig,
    ComponentConfig,
    DeclarativeSkillConfig,
    ForkAgentConfig,
    ForkSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SkillConfig,
    StepSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.field_matrix import (
    AGENT_FIELD_MATRIX,
    SKILL_FIELD_MATRIX,
    matrix_for,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ForkSkill,
    ProceduralSkill,
    ReferenceSkill,
    Skill,
    StepSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)


def _fsm(name: str = "m") -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name=name, states=[s], initial_state=s)


#: (클래스, 생성 kwargs) — 구체 컴포넌트 9종… 중 스킬 7종 + 에이전트 2종.
def _components() -> list[object]:
    return [
        ProceduralSkill(fsm=_fsm(), name="p", description="d"),
        SyncForkSkill(fsm=_fsm(), name="sf", description="d"),
        AsyncForkSkill(fsm=_fsm(), name="af", description="d"),
        WrappedSkill(fsm=_fsm(), name="w", description="d"),
        TransferSkill(fsm=_fsm(), name="t", description="d"),
        DeclarativeSkill(name="dc", description="d"),
        ReferenceSkill(name="r", description="d"),
        AgentDefinition(fsm=_fsm(), name="a", description="d"),
        ForkAgent(name="fa", description="d"),
    ]


# ── 추상성 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "cls", [Skill, StepSkill, ForkSkill, Agent, PluginComponent]
)
def test_abstract_component_classes_reject_instantiation(cls):
    """`kind`를 말하지 않는 클래스는 인스턴스화되지 않는다(CLAUDE.md ABC 규칙)."""
    with pytest.raises(TypeError):
        cls(name="x", description="d")


@pytest.mark.parametrize(
    "cls",
    [ComponentConfig, SkillConfig, StepSkillConfig, ForkSkillConfig, AgentConfigBase],
)
def test_abstract_config_classes_reject_instantiation(cls):
    with pytest.raises(TypeError):
        cls()


def test_concrete_classes_do_not_inherit_concrete_classes():
    """구체 클래스의 부모는 전부 추상이다 — fork가 절차형을 상속하던 관계가 갈라졌다."""
    abstract_bases = {
        Skill, StepSkill, ForkSkill, Agent, PluginComponent,
        ComponentConfig, SkillConfig, StepSkillConfig, ForkSkillConfig,
        AgentConfigBase,
    }
    concrete = [
        ProceduralSkill, SyncForkSkill, AsyncForkSkill, WrappedSkill,
        TransferSkill, DeclarativeSkill, ReferenceSkill,
        AgentDefinition, ForkAgent,
        ProceduralSkillConfig, SyncForkSkillConfig, AsyncForkSkillConfig,
        WrappedSkillConfig, TransferSkillConfig, DeclarativeSkillConfig,
        ReferenceSkillConfig, AgentConfig, ForkAgentConfig,
    ]
    for cls in concrete:
        for base in cls.__mro__[1:]:
            if base is object or base.__module__.startswith("abc"):
                continue
            if not base.__module__.startswith("daedalus."):
                continue
            assert base in abstract_bases or base.__module__.endswith("base"), (
                f"{cls.__name__}이 구체 클래스 {base.__name__}을 상속한다"
            )


def test_step_skill_covers_procedural_and_both_forks():
    """`StepSkill` = 워크플로 단계(fork 포함). `ProceduralSkill`은 절차형만."""
    assert isinstance(ProceduralSkill(fsm=_fsm(), name="p", description="d"), StepSkill)
    for cls in (SyncForkSkill, AsyncForkSkill):
        skill = cls(fsm=_fsm(), name="f", description="d")
        assert isinstance(skill, StepSkill)
        assert isinstance(skill, ForkSkill)
        assert not isinstance(skill, ProceduralSkill)
    # WrappedSkill은 단계지만 계열이 다르다(본문 정본이 외부).
    assert not isinstance(
        WrappedSkill(fsm=_fsm(), name="w", description="d"), StepSkill
    )


def test_fork_agent_is_agent_but_not_workflow_agent():
    fa = ForkAgent(name="fa", description="d")
    assert isinstance(fa, Agent)
    assert not isinstance(fa, AgentDefinition)
    assert not hasattr(fa, "fsm")
    assert not hasattr(fa, "transfer_on")
    assert not hasattr(fa, "call_agents")


# ── 필드 순서 (계층을 갈라도 생성자 시그니처가 바뀌지 않는다) ────────────

def test_dataclass_field_order_is_unchanged():
    """계층 분리 전과 **같은** 생성자 순서.

    2026-09-19 실측 정정: "위치 인수로 만드는 코드가 있다"는 앞선 주석은 거짓
    이었다 — 9종 구체 컴포넌트의 위치 인수 생성자 호출은 `daedalus/` 0건,
    `tests/` 0건이다(전부 키워드). 순서를 고정하는 진짜 이유는 다중 상속
    dataclass의 **필드 순서 제약**이다(CLAUDE.md "dataclass 다중 상속 필드
    순서"): 부모의 required 필드 앞에 default 필드가 오면 클래스 정의 자체가
    TypeError이고, 기저에 필드를 올리는 리팩토링은 이 순서를 조용히 바꾼다.
    그래서 "필드를 한 개도 기저로 올리지 않는다"는 규약의 게이트가 이 단언이다.
    """
    step_order = [
        "fsm", "name", "description", "when_to_use", "config", "body",
        "transfer_on", "call_agents", "id",
    ]
    for cls in (ProceduralSkill, SyncForkSkill, AsyncForkSkill, WrappedSkill):
        assert list(inspect.signature(cls).parameters) == step_order, cls.__name__
    # 그래프 소유 필드 4종(execution_policy/reference_placements/graph_layout/
    # edge_layout)은 2026-09-19(WP-1 D8)에 퇴역했다 — 에이전트는 그래프에
    # 놓이는 노드이지 그래프를 소유하지 않는다.
    assert list(inspect.signature(AgentDefinition).parameters) == [
        "fsm", "name", "description", "config", "body", "transfer_on",
        "call_agents", "id",
    ]
    assert list(inspect.signature(ForkAgent).parameters) == [
        "name", "description", "config", "body", "id",
    ]


def test_config_field_order_is_unchanged():
    step_cfg = [
        "model", "effort", "hooks", "argument_hint", "allowed_tools", "paths",
        "disable_model_invocation", "user_invocable", "shell",
    ]
    assert [f.name for f in dataclasses.fields(ProceduralSkillConfig)] == step_cfg
    for cls in (SyncForkSkillConfig, AsyncForkSkillConfig):
        assert [f.name for f in dataclasses.fields(cls)] == step_cfg + ["agent"]
    agent_common = [
        "model", "effort", "hooks", "tools", "disallowed_tools",
        "permission_mode", "max_turns", "skills", "mcp_servers", "memory",
    ]
    assert [f.name for f in dataclasses.fields(AgentConfig)] == (
        agent_common + ["background", "isolation", "color"]
    )
    # fork 에이전트에는 background·isolation이 없다(색만 붙는다).
    assert [f.name for f in dataclasses.fields(ForkAgentConfig)] == (
        agent_common + ["color"]
    )


def test_id_is_kw_only_and_excluded_from_equality():
    for cls in (SyncForkSkill, AsyncForkSkill, ProceduralSkill):
        fld = next(f for f in dataclasses.fields(cls) if f.name == "id")
        assert fld.kw_only and not fld.compare
    for cls in (AgentDefinition, ForkAgent):
        fld = next(f for f in dataclasses.fields(cls) if f.name == "id")
        assert fld.kw_only and not fld.compare


# ── kind ↔ config.kind ↔ 매트릭스 키 ────────────────────────────────────

_EXPECTED_KINDS = {
    "procedural_skill": "procedural",
    "sync_fork_skill": "sync_fork",
    "async_fork_skill": "async_fork",
    "wrapped_skill": "wrapped",
    "transfer_skill": "transfer",
    "declarative_skill": "declarative",
    "reference_skill": "reference",
    "agent": "agent",
    "fork_agent": "fork_agent",
}


def test_every_component_kind_pairs_with_its_config_kind():
    """클래스 종류 ↔ config 종류 짝은 전수 고정이다 — 산출이 두 사실을 말하면 안 된다."""
    pairs = {c.kind: c.config.kind for c in _components()}
    assert pairs == _EXPECTED_KINDS


def test_every_config_kind_has_a_matrix():
    """모든 config 종류가 실제 표를 가진다 — 없으면 프론트매터를 못 만든다."""
    for comp in _components():
        rules = matrix_for(comp)
        assert rules, f"{comp.kind} 표가 비어 있다"
        key = comp.config.kind
        assert key in SKILL_FIELD_MATRIX or key in AGENT_FIELD_MATRIX


def test_matrix_for_says_why_it_cannot_choose():
    """조용한 빈 dict도, 이유 없는 KeyError도 아니다 — 이유를 말하는 ValueError다."""
    class _Bogus:
        name = "bogus"

        class config:  # noqa: N801 — 테스트용 스텁
            kind = "nonsense"

    with pytest.raises(ValueError, match="nonsense"):
        matrix_for(_Bogus())

    class _NoConfig:
        name = "nc"

    with pytest.raises(ValueError, match="config.kind"):
        matrix_for(_NoConfig())
