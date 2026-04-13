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


def test_agent_editor_has_two_tabs(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert tabs.count() == 2


def test_agent_editor_tab_names(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    editor = AgentEditor(_make_agent())
    tabs = editor.findChild(QTabWidget)
    assert tabs is not None
    assert "Graph" in tabs.tabText(0)
    assert "Content" in tabs.tabText(1)


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


def test_agent_editor_has_proc_and_transfer_sections(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    from daedalus.view.panels.registry_panel import _RegistrySection
    editor = AgentEditor(_make_agent())
    graph_tab = editor._tabs.widget(0)
    sections = graph_tab.findChildren(_RegistrySection)
    assert len(sections) == 2  # Procedural + Transfer


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


def test_agent_editor_content_tab_has_frontmatter_panel(qapp):
    """Content 탭에 FrontmatterPanel이 포함되어 있어야 한다 (SkillEditor UX 일치)."""
    from daedalus.view.editors.agent_editor import AgentEditor
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    editor = AgentEditor(_make_agent())
    content_tab = editor._tabs.widget(1)
    panel = content_tab.findChild(_FrontmatterPanel)
    assert panel is not None


def test_agent_fsm_scene_delete_state_guard_blocks_entry_point(qapp):
    """AgentFsmScene._delete_state를 직접 호출해도 EntryPoint는 삭제되지 않아야 한다."""
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.view.canvas.scene import AgentFsmScene
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    from daedalus.view.viewmodel.state_vm import StateViewModel

    entry = EntryPoint(name="entry")
    exit_done = ExitPoint(name="done")
    fsm = StateMachine(
        name="f", states=[entry, exit_done],
        initial_state=entry, final_states=[exit_done],
    )

    vm = ProjectViewModel()
    entry_vm = StateViewModel(model=entry, x=0.0, y=0.0)
    vm.state_vms.append(entry_vm)
    exit_vm = StateViewModel(model=exit_done, x=200.0, y=0.0)
    vm.state_vms.append(exit_vm)

    scene = AgentFsmScene(vm, agent_fsm=fsm)

    # 직접 _delete_state 호출 — guard가 막아야 함
    scene._delete_state(entry_vm)

    assert entry_vm in vm.state_vms  # 삭제되지 않아야 함


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


def test_agent_fsm_scene_delete_key_preserves_last_exit_point_in_multi_select(qapp):
    """두 개 ExitPoint를 모두 선택해 Delete해도 마지막 하나는 살아남아야 한다."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent
    from daedalus.model.fsm.pseudo import EntryPoint
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.view.canvas.scene import AgentFsmScene
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    from daedalus.view.viewmodel.state_vm import StateViewModel
    from daedalus.view.canvas.node_item import StateNodeItem

    entry = EntryPoint(name="entry")
    exit_a = ExitPoint(name="done")
    exit_b = ExitPoint(name="error")
    fsm = StateMachine(
        name="f", states=[entry, exit_a, exit_b],
        initial_state=entry, final_states=[exit_a, exit_b],
    )

    vm = ProjectViewModel()
    vm.state_vms.extend([
        StateViewModel(model=entry, x=0.0, y=0.0),
        StateViewModel(model=exit_a, x=200.0, y=0.0),
        StateViewModel(model=exit_b, x=400.0, y=0.0),
    ])

    scene = AgentFsmScene(vm, agent_fsm=fsm)
    vm.notify()

    # 두 ExitPoint 노드를 모두 선택
    for item in scene.items():
        if isinstance(item, StateNodeItem) and isinstance(item.state_vm.model, ExitPoint):
            item.setSelected(True)

    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    scene.keyPressEvent(key_event)

    # 적어도 하나의 ExitPoint는 남아있어야 함
    remaining_exits = [s for s in fsm.states if isinstance(s, ExitPoint)]
    assert len(remaining_exits) >= 1
