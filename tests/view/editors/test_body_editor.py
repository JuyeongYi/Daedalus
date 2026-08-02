from __future__ import annotations


def _make_declarative(body: str = ""):
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="K", description="d", body=body)


def test_section_content_panel_show(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel
    panel = SectionContentPanel()
    comp = _make_declarative("Body text")
    panel.show_body(comp)
    assert panel.current_component() is comp


def test_section_content_panel_loads_body_into_editor(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel
    panel = SectionContentPanel()
    comp = _make_declarative("# Title\n\nHello")
    panel.show_body(comp)
    assert panel._w_content.toPlainText() == "# Title\n\nHello"


def test_section_content_panel_saves_body_on_typing(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel
    panel = SectionContentPanel()
    comp = _make_declarative("old")
    panel.show_body(comp)
    panel._w_content.setPlainText("new")
    assert comp.body == "new"


def test_section_content_panel_emits_content_changed_on_typing(qapp):
    from daedalus.view.editors.body_editor import SectionContentPanel
    panel = SectionContentPanel()
    comp = _make_declarative("")
    panel.show_body(comp)

    fired: list[int] = []
    panel.content_changed.connect(lambda: fired.append(1))
    panel._w_content.setPlainText("typed")
    assert fired == [1]
    assert comp.body == "typed"


def test_section_content_panel_show_body_does_not_emit_content_changed(qapp):
    """show_body 로드 시 blockSignals로 write-back이 억제되어야 한다(편집 시작 시
    본문이 조용히 재기록되는 것을 방지)."""
    from daedalus.view.editors.body_editor import SectionContentPanel
    panel = SectionContentPanel()
    comp = _make_declarative("preset")

    fired: list[int] = []
    panel.content_changed.connect(lambda: fired.append(1))
    panel.show_body(comp)
    assert fired == []
    assert comp.body == "preset"


def test_variable_popup_has_entries(qapp):
    from daedalus.view.editors.body_editor import VariablePopup
    from daedalus.view.editors.variable_loader import load_variables
    from PySide6.QtWidgets import QFrame
    entries = load_variables()
    popup = VariablePopup(entries)
    assert isinstance(popup, QFrame)
