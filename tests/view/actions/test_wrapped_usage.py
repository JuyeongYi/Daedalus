# tests/view/actions/test_wrapped_usage.py
"""랩핑 스킬 용도 전환 (WP-WR) — state ↔ reference.

최초 배치가 고정하지만 **바꿀 길은 있어야 한다**(사용자 보고 2026-09-07):
배치가 없으면 바로, 있으면 force로 배치까지 함께 정리하고 1 undo로 묶는다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject
from daedalus.view.actions.creation import create_wrapped_skill
from daedalus.view.actions.wrapped_usage import (
    change_wrapped_usage,
    placement_counts,
)


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _placements(window, comp) -> list:
    return [
        s for s in window._project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is comp
    ]


# ─────────────────────────── 배치 없음 — 바로 전환 ───────────────────────────


def test_change_usage_without_placement(window):
    comp = create_wrapped_skill(window, "alpha@mkt:review")  # state, 미배치
    out = change_wrapped_usage(window, comp, "reference")

    assert out == {
        "changed": True, "old": "state", "new": "reference",
        "removed": {"states": 0, "transitions": 0, "references": 0},
    }
    assert comp.config.usage == "reference"

    window._undo()
    assert comp.config.usage == "state"


def test_same_usage_is_noop(window):
    comp = create_wrapped_skill(window, "alpha@mkt:review")
    before = len(window._project_vm.command_stack.history)
    out = change_wrapped_usage(window, comp, "state")

    assert out["changed"] is False
    # 값이 같은데 커맨드를 쌓으면 Ctrl+Z가 빈 단계를 센다
    assert len(window._project_vm.command_stack.history) == before


def test_unknown_usage_rejected(window):
    comp = create_wrapped_skill(window, "alpha@mkt:review")
    with pytest.raises(ValueError, match="알 수 없는 용도"):
        change_wrapped_usage(window, comp, "backdrop")


def test_non_wrapped_rejected(window):
    from daedalus.view.actions.creation import make_component

    comp = make_component(window, "procedural", "plain")
    window._register_component(comp)
    with pytest.raises(ValueError, match="랩핑 스킬이 아닙니다"):
        change_wrapped_usage(window, comp, "reference")


# ─────────────────────────── 배치 있음 — 기본 거부 ───────────────────────────


def test_placed_state_rejected_without_force(window):
    comp = create_wrapped_skill(window, "alpha@mkt:review", x=10, y=20)
    with pytest.raises(ValueError, match="이미 캔버스에 놓여 있습니다"):
        change_wrapped_usage(window, comp, "reference")
    # 거부면 아무것도 바뀌지 않는다
    assert comp.config.usage == "state"
    assert len(_placements(window, comp)) == 1


def _wire_two_nodes(window):
    """캔버스 편집과 **같은 경로**로 wrapped 노드 + 후속 노드 + 전이를 만든다.

    모델에 Transition을 직접 꽂으면 뷰모델이 없어 실사용과 다른 상태가 된다
    (정리 커맨드는 VM을 기준으로 조립한다) — 그래서 MCP 도구를 쓴다.
    """
    from daedalus.mcp.tools import DaedalusTools

    tools = DaedalusTools(window)
    comp = create_wrapped_skill(window, "alpha@mkt:review", x=10, y=20)
    tools.create_skill("next-step", x=200, y=20)
    tools.connect_states("review", "next-step", trigger="done")
    return comp


def test_rejection_message_lists_what_blocks(window):
    """무엇을 지워야 하는지 말해야 한다 — 전이까지 포함."""
    comp = _wire_two_nodes(window)
    counts = placement_counts(window._project, window._project_vm, comp)
    assert counts == {"states": 1, "transitions": 1, "references": 0}

    with pytest.raises(ValueError) as exc:
        change_wrapped_usage(window, comp, "reference")
    assert "워크플로 노드 1개" in str(exc.value)
    assert "연결 전이 1개" in str(exc.value)


# ─────────────────────────── force — 배치 정리 + 전환 1 undo ───────────────────────────


def test_force_clears_state_placement_and_switches(window):
    comp = create_wrapped_skill(window, "alpha@mkt:review", x=10, y=20)
    before_history = len(window._project_vm.command_stack.history)

    out = change_wrapped_usage(window, comp, "reference", force=True)
    assert out["changed"] is True
    assert out["removed"]["states"] == 1
    assert comp.config.usage == "reference"
    assert _placements(window, comp) == []
    # 정리 + 전환이 **한 단위**
    assert len(window._project_vm.command_stack.history) == before_history + 1

    window._undo()
    assert comp.config.usage == "state"
    assert len(_placements(window, comp)) == 1


def test_force_clears_reference_placement_and_switches(window):
    comp = create_wrapped_skill(
        window, "alpha@mkt:review", x=10, y=20, usage="reference",
    )
    assert window._project.reference_placements[0].skill_name == "review"

    out = change_wrapped_usage(window, comp, "state", force=True)
    assert out["removed"]["references"] == 1
    assert comp.config.usage == "state"
    assert window._project_vm.reference_vms == []

    window._undo()
    assert comp.config.usage == "reference"
    assert len(window._project_vm.reference_vms) == 1


def test_force_removes_connected_transitions(window):
    comp = _wire_two_nodes(window)

    out = change_wrapped_usage(window, comp, "reference", force=True)
    assert out["removed"] == {"states": 1, "transitions": 1, "references": 0}
    assert window._project.graph.transitions == []
    # 다른 노드는 건드리지 않는다
    assert any(getattr(s, "name", "") == "next-step"
               for s in window._project.graph.states)

    window._undo()  # 전이까지 한 번에 복원
    assert len(window._project.graph.transitions) == 1


# ─────────────────────────── MCP 짝 ───────────────────────────


def test_mcp_set_wrapped_usage(window):
    from daedalus.mcp.tools import DaedalusTools

    tools = DaedalusTools(window)
    tools.create_skill("w", kind="wrapped", source="alpha@mkt:review")
    out = tools.set_wrapped_usage("w", "reference")
    assert out["component"] == "w"
    assert out["new"] == "reference"

    tools.undo()
    assert window._project.skills[0].config.usage == "state"


def test_mcp_set_wrapped_usage_requires_force_when_placed(window):
    from daedalus.mcp.tools import DaedalusTools

    tools = DaedalusTools(window)
    tools.create_skill("w", kind="wrapped", source="alpha@mkt:review", x=1, y=2)
    with pytest.raises(ValueError, match="이미 캔버스에 놓여 있습니다"):
        tools.set_wrapped_usage("w", "reference")
    out = tools.set_wrapped_usage("w", "reference", force=True)
    assert out["removed"]["states"] == 1
