"""MCP `place_component`의 배치 가능 게이트 (A4 — WP-A 리뷰 반영).

오늘까지 이 도구에는 종류 가드가 **전혀 없어서** 배경/전이 스킬·fork
에이전트도 상태 노드로 놓였다. 결과는 예외가 아니라 조용한 거짓이다 —
캔버스는 일반 상태로 그리고, 호출자 산출은 에이전트 파일에 `/skill` 호출을
쓴다. 판정의 실체는 `model/plugin/placement.is_state_placeable` 하나다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


@pytest.mark.parametrize("kind", ["procedural", "sync_fork", "async_fork", "wrapped"])
def test_step_skills_are_placeable(tools, kind):
    tools.create_skill(f"s-{kind}", kind=kind)
    out = tools.place_component(f"s-{kind}", x=10, y=20)
    assert out["placed"] == f"s-{kind}"


def test_workflow_agent_is_placeable(tools):
    tools.create_agent("worker")
    assert tools.place_component("worker", x=0, y=0)["placed"] == "worker"


def test_fork_agent_is_rejected(tools):
    """fork 에이전트는 fork 스킬의 실행 기반이지 그래프 노드가 아니다."""
    tools.create_agent("helper", kind="fork_agent")
    with pytest.raises(ValueError, match="배치되지 않는 종류"):
        tools.place_component("helper", x=0, y=0)


@pytest.mark.parametrize("kind", ["declarative", "transfer"])
def test_non_node_skills_are_rejected(tools, kind):
    tools.create_skill(f"s-{kind}", kind=kind)
    with pytest.raises(ValueError, match="배치되지 않는 종류"):
        tools.place_component(f"s-{kind}", x=0, y=0)


def test_reference_skill_is_rejected_and_points_at_place_reference(tools):
    """참조는 상태 노드가 아니라 참조 노드다 — 거부는 갈 곳을 말한다(원칙 5)."""
    tools.create_skill("guide", kind="reference")
    with pytest.raises(ValueError, match="place_reference"):
        tools.place_component("guide", x=0, y=0)
    # 올바른 경로는 여전히 열려 있다.
    tools.place_reference("guide", x=0, y=0)
    assert [r.model.name for r in tools._vm.reference_vms] == ["guide"]


def test_rejected_placement_leaves_no_node_and_no_undo_entry(tools, window):
    """거절은 게이트에서 끝난다 — 커맨드가 쌓이면 undo가 빈 편집을 되돌린다."""
    tools.create_skill("bg", kind="declarative")
    stack = window._project_vm.command_stack
    before = len(stack.history)
    with pytest.raises(ValueError):
        tools.place_component("bg", x=0, y=0)
    assert window._project_vm.state_vms == []
    assert len(stack.history) == before


# ---------------------------------------------------------------------------
# 용도 미정 랩핑 스킬 — GUI와 같게 "state"로 고정하고 1 undo로 묶는다
# (사용자 확정 2026-09-18: 거부하지 않는다. 오늘 되던 배치를 깨지 않는다.)
# ---------------------------------------------------------------------------

def test_undecided_wrapped_placement_fixes_usage_to_state(tools, window):
    tools.create_skill("w", kind="wrapped")
    comp = next(s for s in window._project.skills if s.name == "w")
    assert comp.config.usage == ""

    out = tools.place_component("w", x=5, y=6)
    assert out["usage_fixed"] == "state"
    assert comp.config.usage == "state"


def test_usage_fix_and_placement_are_one_undo(tools, window):
    """따로 되돌리면 용도만 고정된 반쪽 상태가 남는다 — 캔버스 드롭과 같은 묶음."""
    tools.create_skill("w", kind="wrapped")
    comp = next(s for s in window._project.skills if s.name == "w")
    tools.place_component("w", x=5, y=6)

    tools.undo()
    assert window._project_vm.state_vms == []
    assert comp.config.usage == ""


def test_already_fixed_wrapped_placement_says_nothing_about_usage(tools, window):
    """이미 고정된 용도는 배치가 건드리지 않는다 — 응답에도 키가 없다."""
    tools.create_skill("w", kind="wrapped", source="other@mkt:x", usage="state")
    out = tools.place_component("w", x=0, y=0)
    assert "usage_fixed" not in out
    comp = next(s for s in window._project.skills if s.name == "w")
    assert comp.config.usage == "state"
