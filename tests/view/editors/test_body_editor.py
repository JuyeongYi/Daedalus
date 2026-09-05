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


# ─────── 변수 팝업 컨텍스트 필터 — 열 때마다 갱신 (사용자 확정 매트릭스) ───────


def _popup_row_texts(popup):
    from PySide6.QtWidgets import QPushButton
    return [
        b.text() for b in popup.findChildren(QPushButton)
        if b.text() not in ("✕",)
    ]


def test_popup_refreshes_from_variables_fn_on_toggle(qapp):
    """variables_fn이 있으면 열 때마다 목록을 다시 만든다 — 빌드 타깃이
    세션 중 바뀌어도 다음 열기부터 반영된다."""
    from daedalus.view.editors.body_editor import (
        SectionContentPanel,
        make_variable_popup,
        toggle_variable_popup,
    )
    from daedalus.view.editors.variable_loader import VariableEntry

    lists = [
        [VariableEntry("$A", "first", "builtin")],
        [VariableEntry("$B", "second", "builtin")],
    ]
    panel = SectionContentPanel()
    popup = make_variable_popup(panel, variables_fn=lambda: lists.pop(0))
    toggle_variable_popup(panel, popup)
    assert any("$A" in t for t in _popup_row_texts(popup))
    popup.hide()
    toggle_variable_popup(panel, popup)
    texts = _popup_row_texts(popup)
    assert any("$B" in t for t in texts)
    assert not any("$A" in t for t in texts)


def test_agent_editor_popup_excludes_skill_only_variables(qapp):
    """에이전트 본문 팝업에는 스킬 전용 변수($ARGUMENTS 등)가 없다."""
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.view.editors.body_editor import toggle_variable_popup
    from daedalus.view.editors.component_editor import ComponentEditor

    entry = EntryPoint(name="start")
    agent = AgentDefinition(
        name="w", description="d",
        fsm=StateMachine(name="m", states=[entry], initial_state=entry),
    )
    editor = ComponentEditor(agent)
    toggle_variable_popup(editor._content_panel, editor._var_popup)
    texts = _popup_row_texts(editor._var_popup)
    assert not any("$ARGUMENTS" in t for t in texts)
    assert not any("CLAUDE_SKILL_DIR" in t for t in texts)
    assert any("CLAUDE_PROJECT_DIR" in t for t in texts)
    editor._var_popup.hide()


def test_workspace_panel_popup_respects_local_build(qapp):
    """로컬 프로젝트의 규칙 편집 팝업에는 ${CLAUDE_PLUGIN_ROOT}가 없다."""
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.model.project import PluginProject
    from daedalus.view.editors.body_editor import toggle_variable_popup
    from daedalus.view.editors.workspace_editor import RulesPanel

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    panel = RulesPanel()
    panel.set_project(project)
    toggle_variable_popup(panel._content, panel._var_popup)
    texts = _popup_row_texts(panel._var_popup)
    assert not any("CLAUDE_PLUGIN_ROOT" in t for t in texts)
    assert any("CLAUDE_PROJECT_DIR" in t for t in texts)
    assert not any("$ARGUMENTS" in t for t in texts)
    panel._var_popup.hide()
