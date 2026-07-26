# tests/view/test_project_properties.py
"""WP-T Part C: ProjectPropertiesDialog + 새 프로젝트 기본 이름."""
from __future__ import annotations

from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.editors.project_properties import ProjectPropertiesDialog


def test_dialog_initial_values_match_project(qapp):
    project = PluginProject(name="my-plugin", description="desc", version="1.0.0")
    dialog = ProjectPropertiesDialog(project)
    assert dialog._name_edit.text() == "my-plugin"
    assert dialog._description_edit.text() == "desc"
    assert dialog._version_edit.text() == "1.0.0"


def test_apply_to_updates_project(qapp):
    project = PluginProject(name="old-name", description="old desc", version="0.1.0")
    dialog = ProjectPropertiesDialog(project)
    dialog._name_edit.setText("new-name")
    dialog._description_edit.setText("new desc")
    dialog._version_edit.setText("2.0.0")

    dialog.apply_to(project)

    assert project.name == "new-name"
    assert project.description == "new desc"
    assert project.version == "2.0.0"


def test_apply_to_does_not_enforce_name_convention(qapp):
    """이름 규약 검사는 다이얼로그에서 막지 않는다 — 편집 중 자유."""
    project = PluginProject(name="old-name")
    dialog = ProjectPropertiesDialog(project)
    dialog._name_edit.setText("Bad Name With Spaces")
    dialog.apply_to(project)
    assert project.name == "Bad Name With Spaces"


def test_new_project_default_name_is_new_plugin(qapp):
    window = MainWindow()
    window._new_project()
    assert window._project is not None
    assert window._project.name == "new-plugin"
    window.close()
