"""node_badges.badges_for — 노드 뱃지 단위 테스트.

노이즈 방지 원칙:
  - config 선언 기본값과 동일한 값 → 뱃지 없음
  - 선언 기본값과 다른 값만 뱃지화
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.config import (
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.enums import (
    EffortLevel,
    ModelType,
    SkillContext,
)
from daedalus.model.fsm.state import SimpleState
from daedalus.view.canvas.node_badges import badges_for, state_access_badges


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

class _FakeSkill:
    """테스트용 가짜 Skill — config만 가진 최소 컴포넌트."""

    def __init__(self, config: object) -> None:
        self.config = config


def _emojis(component: object) -> str:
    return " ".join(e for e, _ in badges_for(component))


def _tooltips(component: object) -> list[str]:
    return [tip for _, tip in badges_for(component)]


# ---------------------------------------------------------------------------
# ProceduralSkill 기본값 → 뱃지 없음 (노이즈 방지)
# ---------------------------------------------------------------------------

def test_procedural_default_no_badges():
    """ProceduralSkillConfig 선언 기본값 그대로면 뱃지 없음."""
    skill = _FakeSkill(ProceduralSkillConfig())
    assert badges_for(skill) == []


def test_declarative_default_no_badges():
    """DeclarativeSkillConfig 선언 기본값 그대로면 뱃지 없음."""
    skill = _FakeSkill(DeclarativeSkillConfig())
    assert badges_for(skill) == []


def test_transfer_default_no_badges():
    """TransferSkillConfig: user_invocable=False가 선언 기본값이므로 뱃지 없음."""
    skill = _FakeSkill(TransferSkillConfig())
    assert badges_for(skill) == [], "FIXED 기본값이 노이즈가 되어서는 안 된다"


def test_reference_default_no_badges():
    """ReferenceSkillConfig: user_invocable=False가 선언 기본값이므로 뱃지 없음."""
    skill = _FakeSkill(ReferenceSkillConfig())
    assert badges_for(skill) == []


def test_agent_default_no_badges():
    """AgentConfig 선언 기본값 그대로면 뱃지 없음."""
    skill = _FakeSkill(AgentConfig())
    assert badges_for(skill) == []


# ---------------------------------------------------------------------------
# user_invocable — 기본 True에서 False로 → ⛔
# ---------------------------------------------------------------------------

def test_user_invocable_off_badge():
    """ProceduralSkill에서 user_invocable=False(기본 True와 다름) → ⛔ 뱃지."""
    cfg = ProceduralSkillConfig(user_invocable=False)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⛔" in emojis


def test_user_invocable_on_badge_when_default_false():
    """ReferenceSkillConfig user_invocable=True(기본 False와 다름) → ↪ 뱃지."""
    cfg = ReferenceSkillConfig(user_invocable=True)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "↪" in emojis


# ---------------------------------------------------------------------------
# disable_model_invocation=True → 🚫
# ---------------------------------------------------------------------------

def test_disable_model_invocation_badge():
    cfg = ProceduralSkillConfig(disable_model_invocation=True)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🚫" in emojis


def test_disable_model_invocation_default_no_badge():
    cfg = ProceduralSkillConfig(disable_model_invocation=False)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🚫" not in emojis


# ---------------------------------------------------------------------------
# context=FORK → 🍴
# ---------------------------------------------------------------------------

def test_context_fork_badge():
    cfg = ProceduralSkillConfig(context=SkillContext.FORK)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🍴" in emojis


def test_context_inline_no_badge():
    cfg = ProceduralSkillConfig(context=SkillContext.INLINE)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🍴" not in emojis


# ---------------------------------------------------------------------------
# model != INHERIT → Ⓞ/Ⓢ/Ⓗ
# ---------------------------------------------------------------------------

def test_model_opus_badge():
    cfg = ProceduralSkillConfig(model=ModelType.OPUS)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "Ⓞ" in emojis


def test_model_sonnet_badge():
    cfg = ProceduralSkillConfig(model=ModelType.SONNET)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "Ⓢ" in emojis


def test_model_haiku_badge():
    cfg = ProceduralSkillConfig(model=ModelType.HAIKU)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "Ⓗ" in emojis


def test_model_inherit_no_badge():
    cfg = ProceduralSkillConfig(model=ModelType.INHERIT)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    for m_emoji in ("Ⓞ", "Ⓢ", "Ⓗ"):
        assert m_emoji not in emojis


# ---------------------------------------------------------------------------
# effort HIGH/MAX → ⚡
# ---------------------------------------------------------------------------

def test_effort_high_badge():
    cfg = ProceduralSkillConfig(effort=EffortLevel.HIGH)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⚡" in emojis


def test_effort_max_badge():
    cfg = ProceduralSkillConfig(effort=EffortLevel.MAX)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⚡" in emojis


def test_effort_low_no_badge():
    cfg = ProceduralSkillConfig(effort=EffortLevel.LOW)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⚡" not in emojis


def test_effort_none_no_badge():
    """effort=None(기본값) → 뱃지 없음."""
    cfg = ProceduralSkillConfig(effort=None)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⚡" not in emojis


# ---------------------------------------------------------------------------
# hooks 비어있지 않은 dict → 🪝
# ---------------------------------------------------------------------------

def test_hooks_nonempty_badge():
    cfg = ProceduralSkillConfig(hooks={"stop": {}})
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🪝" in emojis


def test_hooks_none_no_badge():
    cfg = ProceduralSkillConfig(hooks=None)
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🪝" not in emojis


def test_hooks_empty_dict_no_badge():
    """빈 dict는 노이즈 — 뱃지 없음."""
    cfg = ProceduralSkillConfig(hooks={})
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "🪝" not in emojis


# ---------------------------------------------------------------------------
# 툴팁 내용 검증
# ---------------------------------------------------------------------------

def test_tooltip_model_opus():
    cfg = ProceduralSkillConfig(model=ModelType.OPUS)
    skill = _FakeSkill(cfg)
    tips = _tooltips(skill)
    assert any("opus" in t for t in tips)


def test_tooltip_effort_max():
    cfg = ProceduralSkillConfig(effort=EffortLevel.MAX)
    skill = _FakeSkill(cfg)
    tips = _tooltips(skill)
    assert any("max" in t for t in tips)


# ---------------------------------------------------------------------------
# TransferSkill: user_invocable=False가 선언 기본값이므로 뱃지 없음 (FIXED 노이즈 방지)
# ---------------------------------------------------------------------------

def test_transfer_user_invocable_false_no_badge():
    """TransferSkillConfig.user_invocable=False는 선언 기본값 → 뱃지 없음."""
    cfg = TransferSkillConfig()
    assert cfg.user_invocable is False  # FIXED 확인
    skill = _FakeSkill(cfg)
    emojis = _emojis(skill)
    assert "⛔" not in emojis
    assert "↪" not in emojis


# ---------------------------------------------------------------------------
# state_access_badges (WP-BB Part C-2) — State.reads/writes
# ---------------------------------------------------------------------------

def test_state_no_access_no_badges():
    s = SimpleState(name="s")
    assert state_access_badges(s) == []


def test_state_writes_badge():
    s = SimpleState(name="s", writes=["TaskState.step"])
    result = state_access_badges(s)
    assert ("✏", "블랙보드 쓰기: TaskState.step") in result


def test_state_reads_only_badge():
    s = SimpleState(name="s", reads=["TaskState"])
    result = state_access_badges(s)
    assert ("📖", "블랙보드 읽기: TaskState") in result


def test_state_both_reads_and_writes_show_both_badges():
    """읽기+쓰기가 모두 선언되어 있으면 두 뱃지가 모두 렌더된다."""
    s = SimpleState(name="s", reads=["A"], writes=["B"])
    emojis = [e for e, _ in state_access_badges(s)]
    assert "✏" in emojis
    assert "📖" in emojis
