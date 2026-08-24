"""캔버스에서 컴포넌트 생성 + 배치 (A9-9) — 공유 함수 + 호출부."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QInputDialog, QMenu

from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
)
from daedalus.model.project import PluginProject
from daedalus.view.actions.creation import (
    CREATABLE_KINDS,
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


# --- 캔버스 메뉴 호출부 ---


def test_menu_lists_creatable_kinds(window):
    from daedalus.view.canvas import context_menus

    menu = QMenu()
    mapping = context_menus.add_canvas_creation_menu(
        window._fsm_scene, menu, QPointF(0, 0)
    )
    assert len(mapping) == len(CREATABLE_KINDS)
    sub = next(m for m in menu.findChildren(QMenu) if m.title() == "여기에 만들기")
    assert [a.text() for a in sub.actions()] == [
        f"{label}…" for _kind, label in CREATABLE_KINDS
    ]
    menu.deleteLater()


def test_menu_absent_without_project(qapp):
    from daedalus.view.canvas import context_menus

    win = MainWindow()
    menu = QMenu()
    assert context_menus.add_canvas_creation_menu(
        win._fsm_scene, menu, QPointF(0, 0)
    ) == {}
    menu.deleteLater()
    win.close()


def test_menu_action_creates_at_the_click_position(window, monkeypatch):
    from daedalus.view.canvas import context_menus

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("beta", True))
    )
    menu = QMenu()
    mapping = context_menus.add_canvas_creation_menu(
        window._fsm_scene, menu, QPointF(300, 400)
    )
    sub = next(m for m in menu.findChildren(QMenu) if m.title() == "여기에 만들기")
    act = next(a for a in sub.actions() if a.text().startswith("Procedural"))

    mapping[act]()
    vm = next(v for v in window._project_vm.state_vms if v.model.name == "beta")
    assert (vm.x, vm.y) == (300.0, 400.0)
    menu.deleteLater()


def test_menu_action_cancelled_creates_nothing(window, monkeypatch):
    from daedalus.view.canvas import context_menus

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False))
    )
    menu = QMenu()
    mapping = context_menus.add_canvas_creation_menu(
        window._fsm_scene, menu, QPointF(0, 0)
    )
    act = next(iter(mapping))
    mapping[act]()

    assert window._project.skills == []
    assert window._project_vm.command_stack.history == []
    menu.deleteLater()


def test_menu_rejects_duplicate_name(window, monkeypatch):
    """이름 중복 검사는 레지스트리 생성과 같은 창 헬퍼(_ask_unique_name)를 쓴다."""
    from daedalus.view.canvas import context_menus

    create_and_place(window._fsm_scene, window, "procedural", "alpha", 0.0, 0.0)

    prompts: list = []
    monkeypatch.setattr(
        QInputDialog, "getText",
        staticmethod(lambda *a, **k: prompts.append(1) or ("alpha", False)),
    )
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    assert context_menus.create_component_at(
        window._fsm_scene, "procedural", QPointF(0, 0)
    ) is None
    assert [s.name for s in window._project.skills] == ["alpha"]
