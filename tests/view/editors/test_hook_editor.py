# tests/view/editors/test_hook_editor.py
"""WP-HOOK: HookLibraryDialog 빌더 폼 + PresetPicker 동적 연결."""
from __future__ import annotations

import pytest

from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject


def _make_project() -> PluginProject:
    return PluginProject(name="p", hook_library=[
        HookDef(name="fmt", description="d", event=HookEvent.POST_TOOL_USE,
                matcher="Edit", command="c"),
    ])


def test_form_loads_selected_hook(qapp):
    from daedalus.view.editors.hook_editor import HookLibraryDialog

    proj = _make_project()
    dlg = HookLibraryDialog(proj)
    # 첫 행 자동 선택 → 폼에 로드
    assert dlg._form._name_edit.text() == "fmt"
    assert dlg._form._command_edit.toPlainText() == "c"
    assert dlg._form._matcher_edit.text() == "Edit"


def test_form_event_combo_toggles_matcher(qapp):
    """이벤트 콤보를 STOP으로 바꾸면 matcher가 비활성화된다."""
    from daedalus.view.editors.hook_editor import HookLibraryDialog

    proj = _make_project()
    dlg = HookLibraryDialog(proj)
    form = dlg._form
    assert form._matcher_edit.isEnabled()  # POST_TOOL_USE → 활성

    # STOP으로 전환
    for i in range(form._event_combo.count()):
        if form._event_combo.itemData(i) is HookEvent.STOP:
            form._event_combo.setCurrentIndex(i)
            break
    assert not form._matcher_edit.isEnabled()
    assert proj.hook_library[0].event is HookEvent.STOP


def test_form_writeback_to_model(qapp):
    from daedalus.view.editors.hook_editor import HookLibraryDialog

    proj = _make_project()
    notified = []
    dlg = HookLibraryDialog(proj, on_notify_fn=lambda: notified.append(1))
    dlg._form._command_edit.setPlainText("new-cmd")
    assert proj.hook_library[0].command == "new-cmd"
    assert notified  # notify 호출됨


def test_add_and_delete_hook(qapp):
    from daedalus.view.editors.hook_editor import HookLibraryDialog

    proj = _make_project()
    dlg = HookLibraryDialog(proj)
    n0 = len(proj.hook_library)
    dlg._add_hook()
    assert len(proj.hook_library) == n0 + 1
    # 새 항목이 선택됨
    assert dlg._list.currentRow() == n0

    dlg._delete_hook()
    assert len(proj.hook_library) == n0


def test_add_from_preset(qapp, monkeypatch):
    from daedalus.view.editors import hook_editor
    from daedalus.view.editors.hook_editor import HookLibraryDialog

    proj = PluginProject(name="p")
    dlg = HookLibraryDialog(proj)

    # QInputDialog.getItem을 첫 프리셋 선택으로 스텁
    from daedalus.model.plugin.hook_presets import BUILTIN_HOOK_PRESETS
    target = BUILTIN_HOOK_PRESETS[0].name
    monkeypatch.setattr(
        hook_editor.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (target, True)),
    )
    dlg._add_from_preset()
    assert len(proj.hook_library) == 1
    added = proj.hook_library[0]
    assert added.name == target
    # 사본이므로 원본과 다른 id
    assert added.id != BUILTIN_HOOK_PRESETS[0].id


def test_hook_preset_picker_shows_library_names(qapp):
    """HookPresetPicker가 등록된 hook_library 이름을 표시한다."""
    from daedalus.view.widgets.preset_picker import (
        HookPresetPicker,
        set_hook_name_provider,
    )

    proj = _make_project()
    set_hook_name_provider(lambda: [h.name for h in proj.hook_library])
    try:
        picker = HookPresetPicker()
        assert "fmt" in picker.get_available()
    finally:
        set_hook_name_provider(None)


def test_hook_preset_picker_refresh_picks_up_new_names(qapp):
    from daedalus.view.widgets.preset_picker import (
        HookPresetPicker,
        set_hook_name_provider,
    )

    proj = PluginProject(name="p")
    set_hook_name_provider(lambda: [h.name for h in proj.hook_library])
    try:
        picker = HookPresetPicker()
        assert picker.get_available() == []
        proj.hook_library.append(HookDef(name="added", description="d", command="c"))
        picker.refresh()
        assert "added" in picker.get_available()
    finally:
        set_hook_name_provider(None)
