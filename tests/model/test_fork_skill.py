"""fork 스킬 종류 (사용자 확정 2026-09-13) — 모델·직렬화·마이그레이션·프론트매터."""
from __future__ import annotations

from daedalus.compiler.emit.skill import compile_skill
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.config import ForkSkillConfig
from daedalus.model.plugin.skill import ForkSkill, ProceduralSkill, TransferSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _fsm(name: str) -> StateMachine:
    s = SimpleState(name="s")
    return StateMachine(name=name, states=[s], initial_state=s)


def _fork(name: str = "scout", agent: str = "general-purpose") -> ForkSkill:
    return ForkSkill(
        fsm=_fsm(name), name=name, description="d",
        config=ForkSkillConfig(agent=agent),
    )


def test_fork_skill_is_procedural_subkind():
    skill = _fork()
    assert skill.kind == "fork_skill"
    assert isinstance(skill, ProceduralSkill)
    assert skill.config.agent == "general-purpose"
    assert [e.name for e in skill.transfer_on] == ["done"]


def test_roundtrip_keeps_kind_and_agent():
    project = PluginProject(name="p")
    project.skills.append(_fork(agent="Explore"))
    again = deserialize_project(serialize_project(project))
    skill = again.skills[0]
    assert isinstance(skill, ForkSkill)
    assert skill.config.agent == "Explore"


def _saved_with_context(skill, context: str, **extra) -> tuple[dict, list[str]]:
    project = PluginProject(name="p")
    project.skills.append(skill)
    data = serialize_project(project)
    data["skills"][0]["config"].update(context=context, **extra)
    return data, []


def test_format2_procedural_fork_context_becomes_fork_skill():
    proc = ProceduralSkill(fsm=_fsm("old"), name="old", description="d")
    proc.config.allowed_tools = ["Read"]
    data, warnings = _saved_with_context(proc, "fork", agent="Plan")
    project = deserialize_project(data, collect_warnings=warnings)
    skill = project.skills[0]
    assert isinstance(skill, ForkSkill)
    assert skill.config.agent == "Plan"
    assert skill.config.allowed_tools == []  # fork에서 효과 없음 — 버리고 경고
    assert any("old" in w and "Read" in w for w in warnings)


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


def test_frontmatter_emits_context_and_agent_without_allowed_tools():
    skill = _fork(agent="Explore")
    skill.config.allowed_tools = ["Bash"]  # 매트릭스에 없는 필드 — 배출 금지
    text = compile_skill(skill)
    assert "context: fork" in text
    assert "agent: Explore" in text
    assert "allowed-tools" not in text


def test_frontmatter_emits_default_agent_explicitly():
    assert "agent: general-purpose" in compile_skill(_fork())


def test_procedural_frontmatter_has_no_context():
    proc = ProceduralSkill(fsm=_fsm("p"), name="p", description="d")
    text = compile_skill(proc)
    assert "context:" not in text
    assert "agent:" not in text
