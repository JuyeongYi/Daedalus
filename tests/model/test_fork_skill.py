"""fork 스킬 종류 (사용자 확정 2026-09-13/2026-09-17) — 모델·직렬화·마이그레이션·프론트매터."""
from __future__ import annotations

import pytest

from daedalus.compiler.emit.skill import compile_skill
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import (
    AsyncForkSkillConfig,
    ForkSkillConfig,
    SyncForkSkillConfig,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    ForkSkill,
    ProceduralSkill,
    StepSkill,
    SyncForkSkill,
    TransferSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _fsm(name: str) -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name=name, states=[s], initial_state=s)


def _fork(
    name: str = "scout", agent: str = "general-purpose", cls=SyncForkSkill,
) -> ForkSkill:
    cfg_cls = SyncForkSkillConfig if cls is SyncForkSkill else AsyncForkSkillConfig
    return cls(
        fsm=_fsm(name), name=name, description="d", config=cfg_cls(agent=agent),
    )


@pytest.mark.parametrize(
    ("cls", "kind", "cfg_kind"),
    [
        (SyncForkSkill, "sync_fork_skill", "sync_fork"),
        (AsyncForkSkill, "async_fork_skill", "async_fork"),
    ],
)
def test_fork_skills_are_step_skills_not_procedural(cls, kind, cfg_kind):
    skill = _fork(cls=cls)
    assert skill.kind == kind
    assert skill.config.kind == cfg_kind
    assert isinstance(skill, StepSkill)
    assert isinstance(skill, ForkSkill)
    # fork는 더 이상 절차형의 하위 종류가 아니다 — 형제다(계층 분리 2026-09-17).
    assert not isinstance(skill, ProceduralSkill)
    assert skill.config.agent == "general-purpose"
    assert [e.name for e in skill.transfer_on] == ["done"]


def test_abstract_fork_classes_cannot_be_instantiated():
    """`ForkSkill`·`ForkSkillConfig`는 추상이다 — 종류를 말하지 않는 fork는 없다."""
    with pytest.raises(TypeError):
        ForkSkill(fsm=_fsm("x"), name="x", description="d")
    with pytest.raises(TypeError):
        ForkSkillConfig()


@pytest.mark.parametrize("cls", [SyncForkSkill, AsyncForkSkill])
def test_roundtrip_keeps_kind_and_agent(cls):
    project = PluginProject(name="p")
    project.skills.append(_fork(agent="Explore", cls=cls))
    again = deserialize_project(serialize_project(project))
    skill = again.skills[0]
    assert type(skill) is cls
    assert skill.config.agent == "Explore"


def _saved_with_context(skill, context: str, **extra) -> tuple[dict, list[str]]:
    project = PluginProject(name="p")
    project.skills.append(skill)
    data = serialize_project(project)
    data["skills"][0]["config"].update(context=context, **extra)
    return data, []


def test_format2_procedural_fork_context_becomes_sync_fork_skill():
    proc = ProceduralSkill(fsm=_fsm("old"), name="old", description="d")
    proc.config.allowed_tools = ["Read"]
    data, warnings = _saved_with_context(proc, "fork", agent="Plan")
    project = deserialize_project(data, collect_warnings=warnings)
    skill = project.skills[0]
    assert type(skill) is SyncForkSkill
    assert skill.config.agent == "Plan"
    assert skill.config.allowed_tools == []  # fork에서 효과 없음 — 버리고 경고
    assert any("old" in w and "Read" in w for w in warnings)
    # v1 파일에는 "이전 산출"이 없다 — fork_split의 미배치 경고를 겹쳐 내지 않는다.
    assert not any("미배치 fork" in w for w in warnings)


def test_format2_fork_context_without_agent_gets_general_purpose():
    proc = ProceduralSkill(fsm=_fsm("old"), name="old", description="d")
    data, warnings = _saved_with_context(proc, "fork", agent=None)
    skill = deserialize_project(data, collect_warnings=warnings).skills[0]
    assert skill.config.agent == "general-purpose"


def test_inline_context_key_dropped_silently():
    proc = ProceduralSkill(fsm=_fsm("plain"), name="plain", description="d")
    data, warnings = _saved_with_context(proc, "inline", agent=None)
    skill = deserialize_project(data, collect_warnings=warnings).skills[0]
    assert type(skill) is ProceduralSkill
    assert warnings == []
    assert "context" not in serialize_project(
        deserialize_project(data)
    )["skills"][0]["config"]


def test_transfer_fork_context_dropped_with_warning():
    tr = TransferSkill(fsm=_fsm("t"), name="t", description="d")
    data, warnings = _saved_with_context(tr, "fork")
    skill = deserialize_project(data, collect_warnings=warnings).skills[0]
    assert isinstance(skill, TransferSkill)
    assert any("'t'" in w for w in warnings)


@pytest.mark.parametrize(
    ("cls", "background"), [(SyncForkSkill, "false"), (AsyncForkSkill, "true")]
)
def test_frontmatter_emits_context_agent_background_without_allowed_tools(
    cls, background,
):
    skill = _fork(agent="Explore", cls=cls)
    skill.config.allowed_tools = ["Bash"]  # 매트릭스에 없는 필드 — 배출 금지
    text = compile_skill(skill)
    assert "context: fork" in text
    assert "agent: Explore" in text
    assert f"background: {background}" in text
    assert "allowed-tools" not in text


def test_frontmatter_emits_default_agent_explicitly():
    assert "agent: general-purpose" in compile_skill(_fork())


def test_procedural_frontmatter_has_no_context_agent_or_background():
    proc = ProceduralSkill(fsm=_fsm("p"), name="p", description="d")
    text = compile_skill(proc)
    assert "context:" not in text
    assert "agent:" not in text
    assert "background:" not in text
