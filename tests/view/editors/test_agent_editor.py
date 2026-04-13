from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition


def _make_agent():
    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    fsm = StateMachine(
        name="test_fsm", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )
    return AgentDefinition(fsm=fsm, name="test-agent", description="테스트")


def test_agent_editor_smoke(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())


def test_agent_editor_has_three_tabs(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 3


def test_agent_editor_tab_names(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert "Graph" in tabs.tabText(0)
    assert "Content" in tabs.tabText(1)
    assert "Config" in tabs.tabText(2)


def test_agent_editor_changed_signal(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    assert hasattr(editor, "agent_changed")


def test_agent_editor_on_notify_fn_called(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    called = []
    editor = AgentEditor(_make_agent(), on_notify_fn=lambda: called.append(1))
    before = len(called)
    editor._on_model_changed()
    assert len(called) == before + 1


def test_agent_editor_graph_loads_fsm_states(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    editor = AgentEditor(agent)
    # FSM에 2개 상태(entry, done)가 있으므로 graph_vm에도 2개가 로드되어야 함
    assert len(editor._graph_vm.state_vms) == 2


def test_agent_editor_mini_registry_is_left(qapp):
    from PyQt6.QtWidgets import QSplitter
    from daedalus.view.editors.agent_editor import AgentEditor, _MiniRegistry
    from daedalus.view.canvas.canvas_view import FsmCanvasView
    editor = AgentEditor(_make_agent())
    graph_tab = editor._tabs.widget(0)
    splitter = graph_tab.findChild(QSplitter)
    assert splitter is not None
    assert isinstance(splitter.widget(0), _MiniRegistry)
    assert isinstance(splitter.widget(1), FsmCanvasView)
