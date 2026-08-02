# tests/view/editors/test_blackboard_editor.py
"""WP-BB Part B: BlackboardPanel — 클래스/필드 편집 폼."""
from __future__ import annotations

from daedalus.model.fsm.blackboard import Blackboard, CollectionType, DynamicClass, DynamicField
from daedalus.model.fsm.variable import FieldType
from daedalus.model.project import PluginProject


def _make_project() -> PluginProject:
    bb = Blackboard(class_definitions=[
        DynamicClass(
            name="TaskState", description="작업 상태",
            fields=[DynamicField(name="step", field_type=FieldType.INT)],
        ),
    ])
    return PluginProject(name="p", blackboard=bb)


def test_panel_disabled_without_project(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    panel = BlackboardPanel()
    assert not panel.isEnabled()


def test_set_project_loads_class_list(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    panel = BlackboardPanel()
    proj = _make_project()
    panel.set_project(proj)
    assert panel.isEnabled()
    assert panel._list.count() == 1
    assert panel._list.item(0).text() == "TaskState"
    # 첫 클래스 자동 선택 + 필드 테이블 로드
    assert panel._table.rowCount() == 1


def test_add_class_appends_to_model(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    notified = []
    panel = BlackboardPanel(on_notify_fn=lambda: notified.append(1))
    panel.set_project(proj)

    panel._add_class()
    assert len(proj.blackboard.class_definitions) == 2
    assert notified


def test_delete_class_removes_from_model(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    panel._delete_class()
    assert proj.blackboard.class_definitions == []


def test_rename_class_via_dialog(qapp, monkeypatch):
    from daedalus.view.editors import blackboard_editor as be_module
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    monkeypatch.setattr(
        be_module.QInputDialog, "getText",
        staticmethod(lambda *a, **k: ("RenamedClass", True)),
    )
    panel._on_rename_class(panel._list.item(0))
    assert proj.blackboard.class_definitions[0].name == "RenamedClass"
    assert panel._list.item(0).text() == "RenamedClass"


def test_description_edit_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    notified = []
    panel = BlackboardPanel(on_notify_fn=lambda: notified.append(1))
    panel.set_project(proj)

    panel._desc_edit.setText("새 설명")
    assert proj.blackboard.class_definitions[0].description == "새 설명"
    assert notified


def test_add_field_appends_dynamic_field(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    panel._add_field()
    cls = proj.blackboard.class_definitions[0]
    assert len(cls.fields) == 2
    assert panel._table.rowCount() == 2


def test_delete_field_removes_dynamic_field(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)
    panel._table.setCurrentCell(0, 0)

    panel._delete_field()
    cls = proj.blackboard.class_definitions[0]
    assert cls.fields == []
    assert panel._table.rowCount() == 0


def test_field_name_edit_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    notified = []
    panel = BlackboardPanel(on_notify_fn=lambda: notified.append(1))
    panel.set_project(proj)

    panel._table.item(0, 0).setText("renamed_step")
    cls = proj.blackboard.class_definitions[0]
    assert cls.fields[0].name == "renamed_step"
    assert notified


def test_field_type_combo_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel
    from daedalus.view.widgets.combo_widgets import FieldTypeComboBox

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    combo = panel._table.cellWidget(0, 1)
    assert isinstance(combo, FieldTypeComboBox)
    idx = combo.findData(FieldType.BOOL)
    combo.setCurrentIndex(idx)

    cls = proj.blackboard.class_definitions[0]
    assert cls.fields[0].field_type is FieldType.BOOL


def test_field_collection_combo_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel
    from daedalus.view.widgets.combo_widgets import CollectionTypeComboBox

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    combo = panel._table.cellWidget(0, 2)
    assert isinstance(combo, CollectionTypeComboBox)
    idx = combo.findData(CollectionType.LIST)
    combo.setCurrentIndex(idx)

    cls = proj.blackboard.class_definitions[0]
    assert cls.fields[0].collection is CollectionType.LIST


def test_field_required_checkbox_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel
    from PySide6.QtWidgets import QCheckBox

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    check = panel._table.cellWidget(0, 3)
    assert isinstance(check, QCheckBox)
    check.setChecked(True)

    cls = proj.blackboard.class_definitions[0]
    assert cls.fields[0].required is True


def test_field_default_edit_writes_back(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)

    panel._table.item(0, 4).setText("42")
    cls = proj.blackboard.class_definitions[0]
    assert cls.fields[0].default == "42"


def test_set_project_none_disables_panel(qapp):
    from daedalus.view.editors.blackboard_editor import BlackboardPanel

    proj = _make_project()
    panel = BlackboardPanel()
    panel.set_project(proj)
    panel.set_project(None)
    assert not panel.isEnabled()
    assert panel._list.count() == 0
