# tests/compiler/test_frontmatter.py
"""프론트매터 생성 골든 테스트 — 4종 스킬 + 에이전트."""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.fsm.section import Section
from daedalus.model.plugin.config import (
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    ModelType,
    PermissionMode,
)

from tests.compiler.builders import (
    make_agent,
    make_declarative,
    make_procedural,
    make_reference,
    make_transfer,
)


def _frontmatter(text: str) -> str:
    """--- ... --- 사이의 프론트매터 블록을 추출."""
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    return text[4:end]


# ─────────────────────── when_to_use 합성 ───────────────────────


def test_description_when_to_use_synthesis():
    skill = make_procedural(
        description="Does a thing", when_to_use="the user wants a thing"
    )
    fm = _frontmatter(compile_skill(skill))
    assert "description: Does a thing. Use when the user wants a thing" in fm


def test_description_ends_with_period_no_double():
    skill = make_procedural(description="Already a sentence.", when_to_use="X happens")
    fm = _frontmatter(compile_skill(skill))
    assert "description: Already a sentence. Use when X happens" in fm
    assert ".. Use" not in fm


def test_description_only_when_no_when_to_use():
    skill = make_procedural(description="Just description", when_to_use="")
    fm = _frontmatter(compile_skill(skill))
    assert "description: Just description" in fm
    assert "Use when" not in fm


# ─────────────────────── kebab-case 키 ───────────────────────


def test_frontmatter_keys_are_kebab_case():
    skill = make_procedural(
        config=ProceduralSkillConfig(
            model=ModelType.SONNET, argument_hint="<a>", allowed_tools=["Read"]
        )
    )
    fm = _frontmatter(compile_skill(skill))
    assert "argument-hint:" in fm
    assert "allowed-tools:" in fm
    assert "argument_hint:" not in fm
    assert "allowed_tools:" not in fm


# ─────────────────────── INHERIT 생략 ───────────────────────


def test_model_inherit_omitted():
    skill = make_procedural(config=ProceduralSkillConfig(model=ModelType.INHERIT))
    fm = _frontmatter(compile_skill(skill))
    assert "model:" not in fm


def test_model_explicit_emitted_as_value():
    skill = make_procedural(config=ProceduralSkillConfig(model=ModelType.OPUS))
    fm = _frontmatter(compile_skill(skill))
    assert "model: opus" in fm


# ─────────────────────── 기본값 생략 ───────────────────────


def test_default_value_optional_omitted():
    # context는 ProceduralSkill에서 OPTIONAL, 기본값 INLINE → 기본값이면 생략
    skill = make_procedural(config=ProceduralSkillConfig(model=ModelType.SONNET))
    fm = _frontmatter(compile_skill(skill))
    assert "context:" not in fm
    assert "shell:" not in fm  # 기본 BASH
    assert "disable-model-invocation:" not in fm  # 기본 False
    assert "user-invocable:" not in fm  # procedural 기본 True


def test_non_default_optional_emitted():
    skill = make_procedural(
        config=ProceduralSkillConfig(model=ModelType.SONNET, effort=EffortLevel.HIGH)
    )
    fm = _frontmatter(compile_skill(skill))
    assert "effort: high" in fm


# ─────────────────────── FIXED 강제 ───────────────────────


def test_transfer_fixed_values_forced():
    skill = make_transfer()
    fm = _frontmatter(compile_skill(skill))
    # transfer 매트릭스: DISABLE_MODEL FIXED True, USER_INVOCABLE FIXED False
    assert "disable-model-invocation: true" in fm
    assert "user-invocable: false" in fm


def test_reference_user_invocable_fixed_false():
    skill = make_reference()
    fm = _frontmatter(compile_skill(skill))
    assert "user-invocable: false" in fm


def test_local_procedural_context_fixed_fork():
    skill = make_procedural(name="local-skill")
    fm = _frontmatter(compile_skill(skill, local=True))
    # local_procedural: CONTEXT FIXED FORK, DISABLE_MODEL FIXED True
    assert "context: fork" in fm
    assert "disable-model-invocation: true" in fm


# ─────────────────────── 종류별 name/description 항상 ───────────────────────


def test_all_kinds_emit_name_and_description():
    for skill in (make_procedural(), make_declarative(), make_transfer(), make_reference()):
        fm = _frontmatter(compile_skill(skill))
        assert "name:" in fm
        assert "description:" in fm


# ─────────────────────── 에이전트 프론트매터 ───────────────────────


def test_agent_frontmatter_selects_emit_frontmatter_only():
    agent = make_agent()
    agent.config = AgentConfig(
        model=ModelType.SONNET,
        color=AgentColor.BLUE,
        permission_mode=PermissionMode.ACCEPT_EDITS,
        max_turns=5,  # INVOCATION — 프론트매터에 없어야
        isolation=AgentIsolation.WORKTREE,  # INVOCATION
    )
    fm = _frontmatter(compile_agent(agent))
    assert "name: worker" in fm
    assert "color: blue" in fm
    assert "permission-mode: acceptEdits" in fm
    # INVOCATION 필드는 프론트매터에 없음
    assert "max-turns:" not in fm
    assert "isolation:" not in fm


def test_agent_permission_mode_default_omitted():
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.SONNET)  # permission default
    fm = _frontmatter(compile_agent(agent))
    assert "permission-mode:" not in fm


def test_agent_model_inherit_omitted():
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.INHERIT)
    fm = _frontmatter(compile_agent(agent))
    assert "model:" not in fm
