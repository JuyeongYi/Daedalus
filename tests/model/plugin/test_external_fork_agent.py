"""외부 fork 에이전트 (`ExternalForkAgent`) — WP-EX/WP-A, 사용자 확정 2026-09-19.

다른 플러그인의 서브에이전트를 쓰는 길은 둘이고, **등록 시점에 고정된다**:
그래프 노드(`ExternalAgent`)이거나 fork 스킬의 실행 기반(`ExternalForkAgent`)
이거나. 전환은 없고, 같은 source를 두 번 등록하면 에러다.

이 파일이 지키는 것은 "종류가 하나 늘었다"가 아니라 **그 종류가 지나는 모든
표면이 파생으로 따라왔는가**다: 선언·직렬화·후보·검증·컴파일 이름 해소·MCP.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.plugin.agent import (
    AgentDefinition,
    ExternalAgent,
    ExternalForkAgent,
    ForkAgent,
)
from daedalus.model.plugin.config import (
    ExternalAgentConfig,
    ExternalForkAgentConfig,
    SyncForkSkillConfig,
)
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.roles import BodySource, Bucket, OutputLocation, PlacementRole
from daedalus.model.plugin.skill import SyncForkSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator

_SOURCE = "review-pack@mkt:critic"


def _base(name: str = "critic", source: str = _SOURCE) -> ExternalForkAgent:
    return ExternalForkAgent(
        name=name, description="External fork base.",
        config=ExternalForkAgentConfig(source=source),
    )


def _fork(name: str = "scout", agent: str = "critic") -> SyncForkSkill:
    entry = EntryPoint(name="s")
    return SyncForkSkill(
        fsm=StateMachine(name=name, states=[entry], initial_state=entry),
        name=name, description="Forked step.",
        config=SyncForkSkillConfig(agent=agent),
    )


def _project(*, declared: bool = True, **kwargs) -> PluginProject:
    project = PluginProject(
        name="p", skills=[_fork()], agents=[_base()], **kwargs,
    )
    if declared:
        project.external_plugins = ["review-pack@mkt"]
    return project


def _rules(project) -> dict[str, bool]:
    return {e.rule: e.is_warning for e in Validator.validate_project(project)}


# ── 능력 선언 ────────────────────────────────────────────────────────────

def test_declarations_split_role_from_ownership():
    """선언 네 칸이 이 종류의 정체다 — 배치 없음 · 산출 없음 · 외부 본문 · fork 기반.

    `ForkAgent`와는 "우리가 파일을 내는가"만 다르고, `ExternalAgent`와는
    "그래프에 놓이는가"만 다르다. 한 칸도 상속으로 흘러들어 오면 안 된다.
    """
    assert ExternalForkAgent.BUCKET is Bucket.AGENTS
    assert ExternalForkAgent.PLACEMENT is PlacementRole.NONE
    assert ExternalForkAgent.OUTPUT_LOCATION is OutputLocation.NONE
    assert ExternalForkAgent.BODY_SOURCE is BodySource.EXTERNAL
    assert ExternalForkAgent.IS_FORK_BASE is True
    assert ExternalForkAgent.REQUIRES_OUTPUT_PORTS is False
    assert ExternalForkAgent.DELEGATION_TARGET is True
    assert ExternalForkAgent.CONVERT_FAMILY is None
    assert not _base().emits_output()


def test_it_is_not_a_fork_agent_subclass():
    """구체가 구체를 상속하면 `isinstance(a, ForkAgent)`가 두 역할을 함께 잡는다."""
    base = _base()
    assert not isinstance(base, (ForkAgent, ExternalAgent, AgentDefinition))
    assert not hasattr(base, "transfer_on")
    assert not hasattr(base, "call_agents")
    assert not hasattr(base, "fsm")


def test_external_source_hooks_are_shared_with_the_node_role():
    """두 외부 종류가 **같은 구현**을 쓴다 — 복제면 한쪽만 고치는 편집이 지나간다."""
    node = ExternalAgent(name="n", description="d", config=ExternalAgentConfig(source=_SOURCE))
    base = _base()
    assert base.external_source == node.external_source == _SOURCE
    assert base.external_plugin_refs() == node.external_plugin_refs() == ["review-pack@mkt"]
    # 빈 값은 `None`이 아니다 — None이면 형식 경고가 조용히 건너뛴다.
    assert _base(source="").external_source == ""
    assert _base(source="").external_plugin_refs() == []
    assert _base(source="plugin-only").external_plugin_refs() == []


# ── 직렬화 ───────────────────────────────────────────────────────────────

def test_round_trips_through_the_registry():
    """`SERIALIZED_FIELDS` 선언만으로 왕복한다 — 직렬화에 종류 사다리가 없다."""
    project = _project()
    loaded = deserialize_project(serialize_project(project))
    (agent,) = loaded.agents
    assert type(agent) is ExternalForkAgent
    assert agent.kind == "external_fork_agent"
    assert agent.config.kind == "external_fork_agent"
    assert agent.config.source == _SOURCE
    assert loaded.skills[0].config.agent == "critic"


def test_stored_kind_distinguishes_the_two_roles():
    """저장 파일의 `kind`가 역할을 고정한다 — 같은 source라도 다른 종류다."""
    node = serialize_project(PluginProject(
        name="p", agents=[ExternalAgent(
            name="n", description="d", config=ExternalAgentConfig(source=_SOURCE),
        )],
    ))["agents"][0]
    base = serialize_project(PluginProject(name="p", agents=[_base()]))["agents"][0]
    assert node["kind"] == "external_agent"
    assert base["kind"] == "external_fork_agent"
    assert node["config"]["kind"] == "external_agent"
    assert base["config"]["kind"] == "external_fork_agent"


# ── 검증 ─────────────────────────────────────────────────────────────────

def test_a_registered_base_is_quiet():
    assert _rules(_project()) == {}


def test_undeclared_plugin_is_the_only_warning_left():
    """사용 선언 누락은 **경고 한 갈래**다 — 종전 fork 쪽 에러 등급은 사라졌다."""
    found = _rules(_project(declared=False))
    assert found == {"undeclared_external_plugin": True}


def test_empty_source_is_caught_by_the_generalized_rule():
    project = _project()
    project.agents[0].config.source = ""
    found = _rules(project)
    assert found.get("external_source_missing") is True
    # 빈 source는 역할 충돌 판정에서 제외된다(편집 중일 수 있다).
    assert "external_source_role_conflict" not in found


def test_unused_base_warns_like_its_own_kind_counterpart():
    project = PluginProject(name="p", agents=[_base()])
    project.external_plugins = ["review-pack@mkt"]
    assert _rules(project).get("unused_fork_agent") is True


def test_registering_the_same_source_twice_is_a_role_conflict():
    """그래프 노드 + fork 기반으로 같은 source를 등록하면 **둘 다** 에러다."""
    project = _project()
    project.agents.append(ExternalAgent(
        name="critic-node", description="d",
        config=ExternalAgentConfig(source=_SOURCE),
    ))
    conflicts = [
        e for e in Validator.validate_project(project)
        if e.rule == "external_source_role_conflict"
    ]
    assert len(conflicts) == 2
    assert all(not e.is_warning for e in conflicts)
    # 문구가 **두 역할을 모두 지목**한다 — 어느 하나만 옳다고 말하지 않는다.
    assert "external_fork_agent" in conflicts[0].message
    assert "external_agent" in conflicts[0].message


def test_role_conflict_matches_the_source_verbatim():
    """`alpha@mkt:x`와 `alpha:x`는 설치 대상이 다를 수 있어 충돌이 아니다."""
    project = _project()
    project.agents.append(_base(name="critic-bare", source="review-pack:critic"))
    assert "external_source_role_conflict" not in _rules(project)


# ── 컴파일: 산출 0개 + 이름 해소 ─────────────────────────────────────────

def test_it_has_no_emitter():
    from daedalus.compiler.emit.emitters import EMITTERS, emitter_for

    assert ExternalForkAgent.KIND not in EMITTERS
    with pytest.raises(ValueError, match="external_fork_agent"):
        emitter_for(_base())


def test_compile_writes_no_file_for_it(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = _project(build_target=BuildTarget.LOCAL)
    result = compile_project(project, tmp_path)
    assert not result.errors
    assert not list((tmp_path / ".claude" / "agents").glob("*")) or not any(
        p.name == "critic.md" for p in (tmp_path / ".claude" / "agents").iterdir()
    )


@pytest.mark.parametrize(
    "target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL],
    ids=lambda t: t.value,
)
def test_fork_agent_line_is_the_source_verbatim_on_both_targets(target):
    """CC는 설치된 플러그인에서 **정확 일치**로 찾는다 — 타깃이 이름을 바꾸지 않는다."""
    from daedalus.compiler.emit.common import agent_invocation_name
    from daedalus.compiler.emit.emitters import compile_skill

    project = _project(build_target=target)
    assert agent_invocation_name(project.skills[0], project) == _SOURCE
    assert f"agent: {_SOURCE}" in compile_skill(project.skills[0], project=project)


def test_a_broken_source_omits_the_agent_line_instead_of_inventing_one():
    """빈/깨진 source는 `general-purpose`로 떨어지지 않고 그 줄 자체가 빠진다.

    떨어뜨리면 산출이 조용히 **다른 에이전트**를 지목하고 컴파일은
    `external_source_missing` 경고만 낸 채 성공한다(원칙 5).
    """
    from daedalus.compiler.emit.common import agent_invocation_name
    from daedalus.compiler.emit.emitters import compile_skill

    project = _project()
    for broken in ("", "review-pack", "review-pack:"):
        project.agents[0].config.source = broken
        assert agent_invocation_name(project.skills[0], project) is None
        text = compile_skill(project.skills[0], project=project)
        assert "agent:" not in text
        assert "general-purpose" not in text


def test_own_fork_agents_still_resolve_by_build_target():
    """자체 fork 에이전트의 타깃별 이름 규칙은 그대로다(회귀 방지)."""
    from daedalus.compiler.emit.common import agent_invocation_name

    project = PluginProject(
        name="p", skills=[_fork(agent="helper")],
        agents=[ForkAgent(name="helper", description="d")],
    )
    project.build_target = BuildTarget.MARKETPLACE
    assert agent_invocation_name(project.skills[0], project) == "p:helper"
    project.build_target = BuildTarget.LOCAL
    assert agent_invocation_name(project.skills[0], project) == "helper"
