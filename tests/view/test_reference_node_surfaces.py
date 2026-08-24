"""참조 노드 액션의 두 호출부 — 캔버스 우클릭 / 참조 스킬 에디터 (A9-6,7).

로직은 tests/view/actions/test_references.py가 검사한다.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject, ReferencePlacement
from daedalus.view.app import MainWindow


def _submenu(menu: QMenu, title: str) -> QMenu:
    return next(m for m in menu.findChildren(QMenu) if m.title() == title)


def _proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


@pytest.fixture
def window(qapp):
    a, b = _proc("alpha"), _proc("beta")
    doc = ReferenceSkill(name="doc", description="d")
    project = PluginProject(name="p", skills=[a, b, doc])
    project.graph.states.append(SimpleState(name="alpha", skill_ref=a))
    project.graph.states.append(SimpleState(name="beta", skill_ref=b))
    project.reference_placements.append(
        ReferencePlacement(skill_name="doc", x=0.0, y=0.0, connected_states=["alpha"])
    )

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


def _ref_vm(window):
    return window._project_vm.reference_vms[0]


# --- 캔버스 메뉴 ---


def test_menu_shows_link_count(window):
    menu = QMenu()
    window._fsm_scene._add_reference_actions_menu(menu, _ref_vm(window))
    labels = [a.text() for a in menu.actions()]
    assert any("링크된 노드 하이라이트 (1)" in x for x in labels)
    menu.deleteLater()


def test_highlight_disabled_without_links(window):
    window._project_vm.reference_links.clear()
    menu = QMenu()
    window._fsm_scene._add_reference_actions_menu(menu, _ref_vm(window))
    act = next(a for a in menu.actions() if "하이라이트" in a.text())
    assert act.isEnabled() is False
    menu.deleteLater()


def test_highlight_selects_linked_nodes(window):
    scene = window._fsm_scene
    targets = scene.highlight_reference_links(_ref_vm(window))
    assert [t.model.name for t in targets] == ["alpha"]

    selected = [
        svm.model.name for svm, item in scene._node_items.items() if item.isSelected()
    ]
    assert selected == ["alpha"]


def test_highlight_clears_previous_selection(window):
    scene = window._fsm_scene
    beta_item = next(
        item for svm, item in scene._node_items.items() if svm.model.name == "beta"
    )
    beta_item.setSelected(True)
    scene.highlight_reference_links(_ref_vm(window))
    assert beta_item.isSelected() is False


def test_clear_highlight_survives_dead_scene(window):
    """2초 뒤에 도는 타이머라 그 사이 씬이 파괴될 수 있다."""
    from daedalus.view.canvas import context_menus

    scene = window._fsm_scene

    class _Dead:
        def clearSelection(self):
            raise RuntimeError("Internal C++ object already deleted")

    context_menus.clear_highlight(_Dead())  # 예외가 새면 안 된다
    context_menus.clear_highlight(scene)


def test_add_link_submenu_lists_only_candidates(window):
    menu = QMenu()
    window._fsm_scene._add_reference_actions_menu(menu, _ref_vm(window))
    add_menu = _submenu(menu, "링크 추가")
    # alpha는 이미 연결됨 → beta만 후보
    assert [a.text() for a in add_menu.actions()] == ["beta"]
    menu.deleteLater()


def test_add_link_submenu_placeholder_when_full(window):
    from daedalus.view.viewmodel.state_vm import ReferenceLinkViewModel

    vm = window._project_vm
    beta = next(s for s in vm.state_vms if s.model.name == "beta")
    vm.reference_links.append(
        ReferenceLinkViewModel(state_vm=beta, reference_vm=_ref_vm(window))
    )
    menu = QMenu()
    window._fsm_scene._add_reference_actions_menu(menu, _ref_vm(window))
    add_menu = _submenu(menu, "링크 추가")
    (act,) = add_menu.actions()
    assert act.text() == "(연결할 노드 없음)"
    assert act.isEnabled() is False
    menu.deleteLater()


def test_add_link_uses_the_drag_command_path(window):
    """드래그와 같은 커맨드 경로 — 그래서 undo되고 모델도 함께 동기화된다."""
    menu = QMenu()
    dispatch = window._fsm_scene._add_reference_actions_menu(menu, _ref_vm(window))
    add_menu = _submenu(menu, "링크 추가")
    beta_act = next(a for a in add_menu.actions() if a.text() == "beta")

    dispatch[beta_act]()
    assert len(window._project_vm.reference_links) == 2
    connected = window._project.reference_placements[0].connected_states
    assert sorted(connected) == ["alpha", "beta"]

    window._project_vm.command_stack.undo()
    assert len(window._project_vm.reference_links) == 1
    menu.deleteLater()


# --- 참조 스킬 에디터 ---


def _open_ref_editor(window):
    doc = next(s for s in window._project.skills if s.name == "doc")
    window._open_component(doc)
    return doc, window._tabs.widget(window._open_tabs[doc.id])


def test_editor_has_link_panel(window):
    from daedalus.view.editors.skill_editor import _ReferenceLinkPanel

    _doc, editor = _open_ref_editor(window)
    panel = editor.findChild(_ReferenceLinkPanel)
    assert panel is not None
    assert panel._list.count() == 1
    assert panel._list.item(0).text() == "alpha"


def test_editor_panel_absent_for_non_reference(window):
    from daedalus.view.editors.skill_editor import SkillEditor, _ReferenceLinkPanel

    editor = SkillEditor(window._project.skills[0], project_vm=window._project_vm)
    assert editor.findChild(_ReferenceLinkPanel) is None
    editor.close()


def test_editor_add_link_calls_shared_action(window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from daedalus.view.editors.skill_editor import _ReferenceLinkPanel

    _doc, editor = _open_ref_editor(window)
    panel = editor.findChild(_ReferenceLinkPanel)
    monkeypatch.setattr(
        QInputDialog, "getItem", staticmethod(lambda *a, **k: ("beta", True))
    )

    calls: list = []
    import daedalus.view.actions.references as refs

    monkeypatch.setattr(
        refs, "add_reference_link",
        lambda scene, ref_vm, state_vm: calls.append((ref_vm, state_vm.model.name)),
    )
    panel._add_btn.click()
    assert len(calls) == 1
    assert calls[0][1] == "beta"


def test_editor_add_link_actually_links(window, monkeypatch):
    """몽키패치 없이 한 번 — 공유 함수가 실제로 배선돼 있는지."""
    from PySide6.QtWidgets import QInputDialog

    from daedalus.view.editors.skill_editor import _ReferenceLinkPanel

    _doc, editor = _open_ref_editor(window)
    panel = editor.findChild(_ReferenceLinkPanel)
    monkeypatch.setattr(
        QInputDialog, "getItem", staticmethod(lambda *a, **k: ("beta", True))
    )
    panel._add_btn.click()

    assert len(window._project_vm.reference_links) == 2
    assert panel._list.count() == 2


def test_editor_add_button_disabled_when_unplaced(window):
    from daedalus.view.editors.skill_editor import SkillEditor, _ReferenceLinkPanel

    unplaced = ReferenceSkill(name="unplaced", description="d")
    window._project.skills.append(unplaced)
    editor = SkillEditor(unplaced, project_vm=window._project_vm)
    panel = editor.findChild(_ReferenceLinkPanel)
    assert panel._add_btn.isEnabled() is False
    assert panel._note.isVisible() or not panel.isVisible()
    editor.close()
