"""캔버스에서 컴포넌트 생성 + 배치 (A9-9) — 공유 함수 + 호출부."""
from __future__ import annotations

import pytest
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition, ForkAgent
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
)
from daedalus.model.project import PluginProject
from daedalus.view.actions.creation import create_and_place, make_component
from daedalus.view.app import MainWindow


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _placements(window) -> list[str]:
    return [
        s.name for s in window._project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is not None
    ]


# --- 모델 팩토리 ---


@pytest.mark.parametrize(
    "kind,cls",
    [
        ("procedural", ProceduralSkill),
        ("sync_fork", SyncForkSkill),
        ("async_fork", AsyncForkSkill),
        ("declarative", DeclarativeSkill),
        ("reference", ReferenceSkill),
        ("agent", AgentDefinition),
        ("fork_agent", ForkAgent),
    ],
)
def test_make_component_types(window, kind, cls):
    comp = make_component(window, kind, "made")
    assert isinstance(comp, cls)
    assert comp.name == "made"


def test_unknown_kind_is_none(window):
    assert make_component(window, "nope", "x") is None


def test_agent_gets_default_output_port(window):
    """레지스트리 생성 경로와 같은 물건이어야 한다."""
    agent = make_component(window, "agent", "a")
    assert [e.name for e in agent.transfer_on] == ["done"]


# --- 생성 + 배치 ---


def test_creates_and_places_procedural(window):
    scene = window._fsm_scene
    comp = create_and_place(scene, window, "procedural", "alpha", 120.0, 240.0)

    assert comp in window._project.skills
    assert _placements(window) == ["alpha"]
    vm = next(v for v in window._project_vm.state_vms if v.model.name == "alpha")
    assert (vm.x, vm.y) == (120.0, 240.0)


def test_creates_reference_as_reference_node(window):
    """참조 스킬은 상태 노드가 아니라 참조 노드로 놓인다."""
    scene = window._fsm_scene
    comp = create_and_place(scene, window, "reference", "doc", 50.0, 60.0)

    assert comp in window._project.skills
    assert _placements(window) == []
    assert [r.model.name for r in window._project_vm.reference_vms] == ["doc"]
    assert window._project.reference_placements[0].skill_name == "doc"


def _non_canvas_kinds() -> list[str]:
    """캔버스에 **아무 노드로도** 놓이지 않는 config 종류 — 선언에서 파생.

    예전에는 `creation.NO_PLACE_KINDS`라는 음성 목록 상수가 이 사실을 따로
    들고 있었다(WP-8에서 퇴역). 목록과 판정이 어긋나면 한쪽만 고친 날
    조용히 엉뚱한 노드가 생긴다 — 이제 배치 역할 선언 하나가 답한다.
    """
    from daedalus.model.plugin.kinds import KIND_REGISTRY
    from daedalus.model.plugin.roles import PlacementRole

    return sorted(
        spec.config_kind
        for spec in KIND_REGISTRY.values()
        if spec.placement not in (PlacementRole.STATE, PlacementRole.REFERENCE)
    )


@pytest.mark.parametrize("kind", _non_canvas_kinds())
def test_no_place_kinds_are_created_only(window, kind):
    """declarative/transfer/fork_agent는 캔버스 노드가 아니다 — 만들기만 한다.

    버킷은 종류가 정한다: fork_agent는 에이전트라 `project.agents`에 들어간다.
    """
    from daedalus.model.plugin.agent import Agent

    scene = window._fsm_scene
    comp = create_and_place(scene, window, kind, "k", 0.0, 0.0)

    bucket = (
        window._project.agents if isinstance(comp, Agent) else window._project.skills
    )
    assert comp in bucket
    assert _placements(window) == []
    assert window._project_vm.reference_vms == []


def test_no_place_kinds_match_canvas_placeable(window):
    """배치 역할 선언과 양성 판정이 어긋나지 않는다(원칙 1) — **양방향**."""
    from daedalus.model.plugin.kinds import config_kinds_in
    from daedalus.model.plugin.placement import is_canvas_placeable
    from daedalus.model.plugin.roles import Bucket

    non_canvas = _non_canvas_kinds()
    assert non_canvas == ["declarative", "transfer", "fork_agent"] or set(
        non_canvas
    ) == {"declarative", "transfer", "fork_agent"}
    for kind in non_canvas:
        comp = make_component(window, kind, f"probe-{kind}")
        assert comp is not None
        assert not is_canvas_placeable(comp)
    # 반대 방향 — 선언이 STATE/REFERENCE인 종류는 전부 캔버스에 놓인다.
    for kind in (*config_kinds_in(Bucket.SKILLS), *config_kinds_in(Bucket.AGENTS)):
        if kind in non_canvas:
            continue
        comp = make_component(window, kind, f"ok-{kind}")
        assert comp is not None
        assert is_canvas_placeable(comp)


def test_creation_is_one_undo_unit(window):
    scene = window._fsm_scene
    comp = create_and_place(scene, window, "procedural", "alpha", 10.0, 20.0)
    assert len(window._project_vm.command_stack.history) == 1

    window._project_vm.command_stack.undo()
    assert comp not in window._project.skills
    assert _placements(window) == []


def test_redo_recreates_both(window):
    scene = window._fsm_scene
    create_and_place(scene, window, "procedural", "alpha", 10.0, 20.0)
    window._project_vm.command_stack.undo()
    window._project_vm.command_stack.redo()

    assert [s.name for s in window._project.skills] == ["alpha"]
    assert _placements(window) == ["alpha"]


def test_reference_creation_undo(window):
    scene = window._fsm_scene
    create_and_place(scene, window, "reference", "doc", 0.0, 0.0)
    window._project_vm.command_stack.undo()

    assert window._project.skills == []
    assert window._project_vm.reference_vms == []


def test_no_project_is_safe(qapp):
    win = MainWindow()
    assert create_and_place(win._fsm_scene, win, "procedural", "x", 0.0, 0.0) is None
    win.close()


# --- 캔버스 메뉴 호출부 (퇴역) ---
# "여기에 만들기" 빈 캔버스 서브메뉴는 사용자 확정으로 제거됐다 — 이름을
# 정확히 타이핑해야 해서 쓰기 어려웠다. create_and_place는 MCP 경로가 계속
# 쓰므로 위 테스트가 유지된다.


def test_canvas_creation_menu_is_retired():
    from daedalus.view.canvas import context_menus

    assert not hasattr(context_menus, "add_canvas_creation_menu")
    assert not hasattr(context_menus, "create_component_at")


# --- create_wrapped_skill 배치 (WP-WR) ---


def test_create_wrapped_with_position_places_node(window):
    """x/y까지 주면 생성+선언+배치가 MacroCommand 1 undo (드롭·MCP 공유 경로)."""
    from daedalus.view.actions.creation import create_wrapped_skill

    comp = create_wrapped_skill(window, "alpha@mkt:review", x=30.0, y=40.0)
    assert comp in window._project.skills
    assert window._project.external_plugins == ["alpha@mkt"]
    vm = next(v for v in window._project_vm.state_vms if v.model.name == "review")
    assert (vm.x, vm.y) == (30.0, 40.0)
    assert len(window._project_vm.command_stack.history) == 1

    window._project_vm.command_stack.undo()
    assert window._project.skills == []
    assert window._project.external_plugins == []
    assert _placements(window) == []


# --- D1: 배치 판정은 `is_reference_usage` 하나다 (WP-1) ---


def test_create_and_place_uses_reference_usage_predicate(window, monkeypatch):
    """참조 **용도**의 컴포넌트는 상태 노드가 아니라 참조 노드로 놓인다.

    D1(카탈로그 F11): 여기만 `isinstance(component, ReferenceSkill)`로 물어
    참조 용도 WrappedSkill이 state 노드로 놓였다. 다른 모든 배치 지점
    (캔버스 드롭·`create_wrapped_skill`·`is_canvas_placeable`)은
    `is_reference_usage`를 쓴다 — 판정의 실체는 하나여야 한다(원칙 1).
    """
    from daedalus.model.plugin.skill import WrappedSkill, is_reference_usage
    from daedalus.view.actions import creation

    made = make_component(window, "wrapped", "ref-wrap")
    made.config.source = "alpha@mkt:review"
    made.config.usage = "reference"
    assert isinstance(made, WrappedSkill) and is_reference_usage(made)
    monkeypatch.setattr(creation, "make_component", lambda *a, **k: made)

    comp = create_and_place(
        window._fsm_scene, window, "wrapped", "ref-wrap", 10.0, 20.0
    )

    assert comp is made
    assert _placements(window) == []
    assert [r.model.name for r in window._project_vm.reference_vms] == ["ref-wrap"]
