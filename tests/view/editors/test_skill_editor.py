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
