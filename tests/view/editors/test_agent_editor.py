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


def test_agent_editor_graph_tab_has_canvas(qapp):
    from daedalus.view.canvas.canvas_view import FsmCanvasView
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    graph_tab = editor._tabs.widget(0)
    canvas = graph_tab.findChild(FsmCanvasView)
    assert canvas is not None


def test_agent_editor_uses_agent_fsm_scene(qapp):
    from daedalus.view.canvas.scene import AgentFsmScene
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    assert isinstance(editor._graph_scene, AgentFsmScene)


def test_agent_fsm_scene_delete_key_does_not_remove_entry_point(qapp):
    """Delete 키를 눌러도 EntryPoint는 삭제되지 않아야 한다."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.view.canvas.scene import AgentFsmScene
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem

    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    from daedalus.model.fsm.machine import StateMachine
    fsm = StateMachine(name="f", states=[entry, exit_done], initial_state=entry, final_states=[exit_done])

    vm = ProjectViewModel()
    entry_vm = StateViewModel(model=entry, x=0.0, y=0.0)
    exit_vm = StateViewModel(model=exit_done, x=200.0, y=0.0)
    vm.state_vms.extend([entry_vm, exit_vm])

    scene = AgentFsmScene(vm, agent_fsm=fsm)
    vm.notify()  # 씬 등록 후 notify해야 아이템이 씬에 추가됨

    # EntryPoint 노드를 찾아 선택
    entry_item = next(
        item for item in scene.items()
        if isinstance(item, StateNodeItem) and isinstance(item.state_vm.model, EntryPoint)
    )
    entry_item.setSelected(True)
    before_count = len(fsm.states)

    # Delete 키 이벤트 생성 및 전달
    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    scene.keyPressEvent(key_event)

    # EntryPoint는 삭제되지 않아야 함
    assert len(fsm.states) == before_count
    assert entry in fsm.states
