# tests/view/widgets/test_combo_widgets.py
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox


def test_model_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ModelComboBox
    w = ModelComboBox()
    assert isinstance(w, QComboBox)
    items = [w.itemText(i) for i in range(w.count())]
    assert "sonnet" in items
    assert "opus" in items
    assert "haiku" in items
    assert w.currentText() == "sonnet"


def test_effort_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import EffortComboBox
    w = EffortComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "low" in items
    assert "max" in items


def test_context_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ContextComboBox
    w = ContextComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "inline" in items
    assert "fork" in items


def test_shell_combo_has_choices(qapp):
    from daedalus.view.widgets.combo_widgets import ShellComboBox
    w = ShellComboBox()
    items = [w.itemText(i) for i in range(w.count())]
    assert "bash" in items
    assert "powershell" in items
