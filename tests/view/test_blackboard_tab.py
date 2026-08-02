# tests/view/test_blackboard_tab.py
"""WP-BB Part B: MainWindow의 블랙보드 상주 탭 — 항상 존재, 닫기 불가."""
from __future__ import annotations

from daedalus.model.fsm.blackboard import Blackboard, DynamicClass
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.editors.blackboard_editor import BlackboardPanel


def test_blackboard_tab_exists_at_index_1(qapp):
    window = MainWindow()
    assert window._tabs.count() == 2
    assert isinstance(window._tabs.widget(1), BlackboardPanel)
    assert window._tabs.tabText(1) == "🗂 블랙보드"
    window.close()


def test_blackboard_tab_has_no_close_button(qapp):
    window = MainWindow()
    tab_bar = window._tabs.tabBar()
    assert tab_bar is not None
    assert tab_bar.tabButton(1, tab_bar.ButtonPosition.RightSide) is None
    window.close()


def test_close_tab_rejects_blackboard_index(qapp):
    window = MainWindow()
    before = window._tabs.count()
    window._close_tab(1)
    assert window._tabs.count() == before
    window.close()


def test_set_project_binds_blackboard_panel(qapp):
    window = MainWindow()
    bb = Blackboard(class_definitions=[DynamicClass(name="TaskState", description="")])
    project = PluginProject(name="p", blackboard=bb)
    window.set_project(project)

    panel = window._blackboard_panel
    assert panel.isEnabled()
    assert panel._list.count() == 1
    assert panel._list.item(0).text() == "TaskState"
    window.close()


def test_load_project_preserves_blackboard_tab(qapp, tmp_path):
    """open_path(load_project) 이후에도 블랙보드 탭은 살아남는다."""
    from daedalus.model.serialize import serialize_project
    import json

    window = MainWindow()
    project = PluginProject(name="p")
    window.set_project(project)
    path = str(tmp_path / "proj.daedalus.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serialize_project(project), f)

    window.open_path(path)
    assert window._tabs.count() == 2
    assert isinstance(window._tabs.widget(1), BlackboardPanel)
    window.close()


def test_blackboard_edit_notifies_project_vm(qapp):
    """BlackboardPanel 편집이 MainWindow의 project_vm.notify를 발화한다."""
    window = MainWindow()
    project = PluginProject(name="p")
    window.set_project(project)

    notified = []
    window._project_vm.add_listener(lambda: notified.append(1))
    window._blackboard_panel._add_class()

    assert notified
    assert len(project.blackboard.class_definitions) == 1
    window.close()
