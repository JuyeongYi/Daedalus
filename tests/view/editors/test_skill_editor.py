# tests/view/editors/test_skill_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QScrollArea, QWidget

# qapp 픽스처는 tests/view/conftest.py에서 상속됨


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="테스트")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="Knowledge", description="배경지식")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="에이전트")


def test_frontmatter_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)
    assert panel.width() == 170 or panel.maximumWidth() == 170


def test_frontmatter_panel_declarative(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_declarative()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_frontmatter_panel_agent(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_agent()
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_tree_sidebar_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TreeSidebar
    from daedalus.model.fsm.section import Section
    from PyQt6.QtCore import Qt
    comp = _make_procedural()
    comp.sections = [
        Section("Persona", children=[Section("Role"), Section("Background")]),
        Section("Style"),
    ]
    sidebar = _TreeSidebar(comp)
    assert sidebar.tree_widget().topLevelItemCount() >= 2  # 2 sections (Persona, Style)


def test_tree_sidebar_declarative_no_transfer_on(qapp):
    from daedalus.view.editors.skill_editor import _TreeSidebar
    comp = _make_declarative()
    sidebar = _TreeSidebar(comp)
    # DeclarativeSkill은 TransferOn QPushButton 없음
    assert not hasattr(sidebar, "_transfer_on_btn")


def test_content_panel_show_section(qapp):
    from daedalus.model.fsm.section import Section
    from daedalus.view.editors.skill_editor import _ContentPanel
    panel = _ContentPanel()
    section = Section(title="Role", content="You are a writer.")
    panel.show_section(section, ["Persona", "Role"])
    assert panel.current_section() is section


def test_transfer_on_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    from daedalus.model.fsm.section import EventDef
    from PyQt6.QtWidgets import QWidget
    events = [EventDef("done"), EventDef("error", color="#cc3333")]
    panel = _TransferOnPanel(events)
    assert isinstance(panel, QWidget)


def test_event_card_renders(qapp):
    from daedalus.view.editors.skill_editor import _EventCard
    from daedalus.model.fsm.section import EventDef
    from PyQt6.QtWidgets import QFrame
    e = EventDef("done", color="#4488ff")
    card = _EventCard(e, can_delete=False)
    assert isinstance(card, QFrame)


def test_variable_popup_shows_builtins(qapp):
    from daedalus.view.editors.skill_editor import _VariablePopup
    from daedalus.view.editors.variable_loader import load_variables
    from PyQt6.QtWidgets import QFrame
    entries = load_variables()
    popup = _VariablePopup(entries)
    assert isinstance(popup, QFrame)


def test_skill_editor_procedural_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from PyQt6.QtWidgets import QWidget
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_declarative_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from PyQt6.QtWidgets import QWidget
    comp = _make_declarative()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_agent_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from PyQt6.QtWidgets import QWidget
    comp = _make_agent()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_changed_signal_exists(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    # skill_changed 시그널이 존재하는지 확인 (기존 API 호환)
    assert hasattr(editor, "skill_changed")
