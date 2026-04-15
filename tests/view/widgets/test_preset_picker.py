# tests/view/widgets/test_preset_picker.py
from __future__ import annotations

import os
import tempfile


def test_preset_picker_empty_dir(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        w = PresetPicker(scan_path=d)
        assert w.get_selected() == []


def test_preset_picker_scans_json_files(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        for name in ["hook-a.json", "hook-b.json", "readme.txt"]:
            with open(os.path.join(d, name), "w") as f:
                f.write("{}")
        w = PresetPicker(scan_path=d)
        items = w.get_available()
        assert "hook-a" in items
        assert "hook-b" in items
        assert "readme" not in items


def test_preset_picker_select_and_get(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        for name in ["a.json", "b.json"]:
            with open(os.path.join(d, name), "w") as f:
                f.write("{}")
        w = PresetPicker(scan_path=d)
        w.set_selected(["a"])
        assert w.get_selected() == ["a"]


def test_preset_picker_changed_signal(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "x.json"), "w") as f:
            f.write("{}")
        w = PresetPicker(scan_path=d)
        called = []
        w.selection_changed.connect(lambda: called.append(1))
        w.set_selected(["x"])
        assert len(called) == 1


def test_preset_picker_nonexistent_dir(qapp):
    from daedalus.view.widgets.preset_picker import PresetPicker
    w = PresetPicker(scan_path="/nonexistent/path/12345")
    assert w.get_available() == []
    assert w.get_selected() == []
