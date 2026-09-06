"""캔버스에서 컴포넌트 생성 + 배치 (A9-9) — 공유 함수 + 호출부."""
from __future__ import annotations

import pytest
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
)
from daedalus.model.project import PluginProject
from daedalus.view.actions.creation import (
    NO_PLACE_KINDS,
    create_and_place,
    make_component,
)
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
        ("declarative", DeclarativeSkill),
        ("reference", ReferenceSkill),
        ("agent", AgentDefinition),
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


@pytest.mark.parametrize("kind", sorted(NO_PLACE_KINDS))
def test_no_place_kinds_are_created_only(window, kind):
    """declarative/transfer는 워크플로 노드가 아니다 — 레지스트리와 같은 규칙."""
    scene = window._fsm_scene
    comp = create_and_place(scene, window, kind, "k", 0.0, 0.0)

    assert comp in window._project.skills
    assert _placements(window) == []
    assert window._project_vm.reference_vms == []


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
