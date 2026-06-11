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
from daedalus.view.canvas.node_item import _delegation_badge
from daedalus.view.viewmodel.state_vm import StateViewModel


# ─────────────────────── _delegation_badge 함수 단위 ───────────────────────

def test_badge_team_spawn_no_flags():
    """TeamSpawnDef, WAIT, EXPLICIT → 뱃지 없음."""
    d = TeamSpawnDef(name="t", description="")
    assert _delegation_badge(d) == ""


def test_badge_fire_and_forget():
    """wait_mode=FIRE_AND_FORGET → 🔥 포함."""
    d = TeamSpawnDef(name="t", description="", wait_mode=WaitMode.FIRE_AND_FORGET)
    badge = _delegation_badge(d)
    assert "🔥" in badge


def test_badge_guided_composition():
    """composition=GUIDED → ✨ 포함."""
    d = DynamicWorkflowDef(name="w", description="", composition=CompositionMode.GUIDED)
    badge = _delegation_badge(d)
    assert "✨" in badge


def test_badge_both_flags():
    """FIRE_AND_FORGET + GUIDED → 🔥 + ✨ 둘 다."""
    d = AgoraDispatchDef(
        name="a", description="",
        wait_mode=WaitMode.FIRE_AND_FORGET,
        composition=CompositionMode.GUIDED,
    )
    badge = _delegation_badge(d)
    assert "🔥" in badge
    assert "✨" in badge


def test_badge_non_delegation_returns_empty():
    """DelegationDef가 아닌 객체(AgentDefinition 등)는 빈 문자열."""
    class _FakeAgent:
        kind = "agent"
        wait_mode = None
        composition = None

    assert _delegation_badge(_FakeAgent()) == ""
    assert _delegation_badge(None) == ""


def test_badge_all_three_kinds(qapp):
    """3종 kind 모두 FIRE_AND_FORGET+GUIDED 조합에서 뱃지가 생성된다."""
    for cls in [TeamSpawnDef, DynamicWorkflowDef, AgoraDispatchDef]:
        d = cls(
            name="x", description="",
            wait_mode=WaitMode.FIRE_AND_FORGET,
            composition=CompositionMode.GUIDED,
        )
        badge = _delegation_badge(d)
        assert "🔥" in badge and "✨" in badge, f"{cls.__name__} 뱃지 생성 실패: {badge!r}"


# ─────────────────────── StateNodeItem type style ───────────────────────

def test_node_item_type_style_has_delegation_kinds(qapp):
    """_TYPE_STYLE에 3종 delegation kind가 정의되어 있다."""
    from daedalus.view.canvas.node_item import _TYPE_STYLE
    for kind in ("team_spawn", "dynamic_workflow", "agora_dispatch"):
        assert kind in _TYPE_STYLE, f"_TYPE_STYLE에 '{kind}'가 없다"
