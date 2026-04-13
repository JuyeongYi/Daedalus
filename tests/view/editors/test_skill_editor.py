# tests/view/editors/test_skill_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QFrame, QScrollArea, QWidget

from daedalus.model.fsm.section import Section


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
    assert panel.minimumWidth() >= 170


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


def test_transfer_on_panel_procedural(qapp):
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    from daedalus.model.fsm.section import EventDef
    events = [EventDef("done"), EventDef("error", color="#cc3333")]
    panel = _TransferOnPanel(events)
    assert isinstance(panel, QWidget)


def test_event_card_renders(qapp):
    from daedalus.view.editors.skill_editor import _EventCard
    from daedalus.model.fsm.section import EventDef
    e = EventDef("done", color="#4488ff")
    card = _EventCard(e, can_delete=False)
    assert isinstance(card, QFrame)


def test_skill_editor_procedural_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_declarative_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_declarative()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_agent_smoke(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_agent()
    editor = SkillEditor(comp)
    assert isinstance(editor, QWidget)


def test_skill_editor_changed_signal_exists(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    comp = _make_procedural()
    editor = SkillEditor(comp)
    assert hasattr(editor, "skill_changed")


def test_skill_editor_has_splitter(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from PyQt6.QtWidgets import QSplitter
    comp = _make_procedural()
    editor = SkillEditor(comp)
    splitter = editor.findChild(QSplitter)
    assert splitter is not None


def test_skill_editor_has_breadcrumb(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from daedalus.view.editors.body_editor import BreadcrumbNav
    comp = _make_procedural()
    comp.sections = [Section("S1"), Section("S2")]
    editor = SkillEditor(comp)
    nav = editor.findChild(BreadcrumbNav)
    assert nav is not None


def test_skill_editor_has_section_tree(qapp):
    from daedalus.view.editors.skill_editor import SkillEditor
    from daedalus.view.editors.body_editor import SectionTree
    comp = _make_procedural()
    editor = SkillEditor(comp)
    tree = editor.findChild(SectionTree)
    assert tree is not None


def test_frontmatter_panel_transfer(qapp):
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import TransferSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    comp = TransferSkill(fsm=fsm, name="Validate", description="검증")
    panel = _FrontmatterPanel(comp)
    assert isinstance(panel, QScrollArea)


def test_node_item_port_color_from_event_def(qapp):
    """EventDef.color가 StateNodeItem 포트 색상에 반영되는지 확인."""
    from PyQt6.QtGui import QColor
    from daedalus.model.fsm.section import EventDef
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem

    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    skill = ProceduralSkill(
        fsm=fsm, name="ColorSkill", description="d",
        transfer_on=[EventDef("done", color="#aa44cc"), EventDef("error", color="#cc3333")],
    )
    state = SimpleState(name="node", skill_ref=skill)
    vm = StateViewModel(model=state)
    item = StateNodeItem(vm)

    defs = item._event_defs()
    assert len(defs) == 2
    assert defs[0].color == "#aa44cc"
    assert defs[1].color == "#cc3333"
    assert QColor(defs[0].color).isValid()
    assert QColor(defs[1].color).isValid()
    assert item._output_events() == ["done", "error"]
