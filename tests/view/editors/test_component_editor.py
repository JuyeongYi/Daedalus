# tests/view/editors/test_component_editor.py
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QSplitter, QWidget


def _make_procedural():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.skill import ProceduralSkill
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return ProceduralSkill(fsm=fsm, name="TestSkill", description="d")


def _make_declarative():
    from daedalus.model.plugin.skill import DeclarativeSkill
    return DeclarativeSkill(name="K", description="d")


def _make_agent():
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.plugin.agent import AgentDefinition
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    return AgentDefinition(fsm=fsm, name="TestAgent", description="d")


def test_two_column_no_right_widgets(qapp):
    """right_widgets가 없으면 2컬럼(좌측+중앙)만 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 2  # left + center


def test_three_column_with_right_widgets(qapp):
    """right_widgets가 있으면 3컬럼(좌측+중앙+우측)."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_procedural()
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    rw = [_TransferOnPanel(comp.transfer_on)]
    editor = ComponentEditor(comp, right_widgets=rw)
    root_splitter = editor.findChild(QSplitter)
    assert root_splitter is not None
    assert root_splitter.count() == 3  # left + center + right


def test_left_splitter_has_tree_and_frontmatter(qapp):
    """좌측 수직 스플리터에 SectionTree + FrontmatterPanel."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.body_editor import SectionTree
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    tree = editor.findChild(SectionTree)
    fm = editor.findChild(_FrontmatterPanel)
    assert tree is not None
    assert fm is not None


def test_center_has_breadcrumb_and_content(qapp):
    """중앙에 BreadcrumbNav + SectionContentPanel."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.body_editor import BreadcrumbNav, SectionContentPanel
    comp = _make_procedural()
    editor = ComponentEditor(comp)
    nav = editor.findChild(BreadcrumbNav)
    cp = editor.findChild(SectionContentPanel)
    assert nav is not None
    assert cp is not None


def test_changed_signal(qapp):
    """changed 시그널이 존재."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    editor = ComponentEditor(comp)
    assert hasattr(editor, "changed")


def test_right_widgets_in_vertical_splitter(qapp):
    """우측 위젯이 수직 스플리터에 배치."""
    from daedalus.view.editors.component_editor import ComponentEditor
    from daedalus.view.editors.skill_editor import _TransferOnPanel
    comp = _make_procedural()
    t1 = _TransferOnPanel(comp.transfer_on)
    t2 = _TransferOnPanel(comp.call_agents, default_color="#8a4a4a", multiline_desc=True)
    editor = ComponentEditor(comp, right_widgets=[t1, t2])
    splitters = editor.findChildren(QSplitter)
    assert len(splitters) >= 3


def test_on_notify_callback(qapp):
    """on_notify_fn이 모델 변경 시 호출."""
    from daedalus.view.editors.component_editor import ComponentEditor
    comp = _make_declarative()
    called = []
    editor = ComponentEditor(comp, on_notify_fn=lambda: called.append(1))
    editor._on_model_changed()
    assert len(called) == 1
