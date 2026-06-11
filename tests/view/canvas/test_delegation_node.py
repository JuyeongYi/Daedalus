"""위임 노드 아이템 뱃지 분기 테스트."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DynamicWorkflowDef,
    TeamSpawnDef,
    WaitMode,
)
from daedalus.view.canvas.node_badges import badges_for
from daedalus.view.viewmodel.state_vm import StateViewModel


def _emojis(component: object) -> str:
    """badges_for 결과에서 이모지만 이어 붙인 문자열 (기존 테스트 비교 포맷)."""
    return " ".join(e for e, _ in badges_for(component))


# ─────────────────────── badges_for — DelegationDef 단위 ───────────────────────

def test_badge_team_spawn_no_flags():
    """TeamSpawnDef, WAIT, EXPLICIT → 뱃지 없음."""
    d = TeamSpawnDef(name="t", description="")
    assert badges_for(d) == []


def test_badge_fire_and_forget():
    """wait_mode=FIRE_AND_FORGET → 🔥 포함."""
    d = TeamSpawnDef(name="t", description="", wait_mode=WaitMode.FIRE_AND_FORGET)
    emojis = _emojis(d)
    assert "🔥" in emojis


def test_badge_guided_composition():
    """composition=GUIDED → ✨ 포함."""
    d = DynamicWorkflowDef(name="w", description="", composition=CompositionMode.GUIDED)
    emojis = _emojis(d)
    assert "✨" in emojis


def test_badge_both_flags():
    """FIRE_AND_FORGET + GUIDED → 🔥 + ✨ 둘 다."""
    d = AgoraDispatchDef(
        name="a", description="",
        wait_mode=WaitMode.FIRE_AND_FORGET,
        composition=CompositionMode.GUIDED,
    )
    emojis = _emojis(d)
    assert "🔥" in emojis
    assert "✨" in emojis


def test_badge_non_delegation_returns_empty():
    """DelegationDef가 아닌 객체(config 없음)는 빈 목록."""
    class _FakeAgent:
        kind = "agent"
        wait_mode = None
        composition = None

    assert badges_for(_FakeAgent()) == []
    assert badges_for(None) == []  # type: ignore[arg-type]


def test_badge_all_three_kinds(qapp):
    """3종 kind 모두 FIRE_AND_FORGET+GUIDED 조합에서 뱃지가 생성된다."""
    for cls in [TeamSpawnDef, DynamicWorkflowDef, AgoraDispatchDef]:
        d = cls(
            name="x", description="",
            wait_mode=WaitMode.FIRE_AND_FORGET,
            composition=CompositionMode.GUIDED,
        )
        emojis = _emojis(d)
        assert "🔥" in emojis and "✨" in emojis, f"{cls.__name__} 뱃지 생성 실패: {emojis!r}"


# ─────────────────────── StateNodeItem type style ───────────────────────

def test_node_item_type_style_has_delegation_kinds(qapp):
    """_TYPE_STYLE에 3종 delegation kind가 정의되어 있다."""
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    for kind in ("team_spawn", "dynamic_workflow", "agora_dispatch"):
        assert kind in _TYPE_STYLE, f"_TYPE_STYLE에 '{kind}'가 없다"
