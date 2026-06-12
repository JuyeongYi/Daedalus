from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill


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
    assert len(sections) == 4  # Procedural + Transfer + Reference + Delegation


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


def _make_agent_with_skill() -> tuple[AgentDefinition, ProceduralSkill]:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="a_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )
    agent = AgentDefinition(fsm=fsm, name="a", description="")
    s = SimpleState(name="start")
    skill = ProceduralSkill(
        fsm=StateMachine(name="p_fsm", states=[s], initial_state=s),
        name="proc", description="",
    )
    agent.skills.append(skill)
    return agent, skill


def test_canvas_skill_node_survives_reopen(qapp):
    """drop_skill로 만든 노드가 에디터 재생성(탭 재오픈) 후 복원된다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent, skill = _make_agent_with_skill()
    editor1 = AgentEditor(agent)
    editor1._graph_scene.drop_skill("proc", QPointF(120, 80))
    assert any(
        getattr(s, "skill_ref", None) is skill for s in agent.fsm.states
    ), "드롭한 스킬 노드가 agent.fsm.states에 있어야 한다"
    editor1._graph_scene.close()

    editor2 = AgentEditor(agent)
    names = [vm.model.name for vm in editor2._graph_vm.state_vms]
    assert "proc" in names, "재오픈 시 캔버스 상태가 복원되어야 한다"
    editor2._graph_scene.close()


def test_deleted_default_transition_stays_deleted(qapp):
    """기본 entry→done 전이를 지우면 재오픈 시 부활하지 않는다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent, _skill = _make_agent_with_skill()
    editor1 = AgentEditor(agent)
    editor1._graph_scene.drop_skill("proc", QPointF(120, 80))
    # _migrate_fsm이 만든 기본 entry→done 전이 삭제
    assert len(editor1._graph_vm.transition_vms) == 1  # 마이그레이션 기본 전이 1개 전제
    default_tvm = editor1._graph_vm.transition_vms[0]
    editor1._graph_scene._delete_transition(default_tvm)
    assert agent.fsm.transitions == []
    editor1._graph_scene.close()

    editor2 = AgentEditor(agent)
    assert agent.fsm.transitions == [], (
        "일반 상태가 존재하면 빈 전이 목록을 마이그레이션이 덮어쓰면 안 된다"
    )
    editor2._graph_scene.close()


def test_migrate_fsm_removes_orphan_from_final_states(qapp):
    """_migrate_fsm: skill_ref 없는 SimpleState가 final_states에 있어도 제거된다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.view.editors.agent_editor import AgentEditor

    entry = EntryPoint(name="entry")
    orphan = SimpleState(name="orphan")  # skill_ref=None — 구버전 잔재
    exit_done = ExitPoint(name="done")
    fsm = StateMachine(
        name="test_fsm",
        states=[entry, orphan, exit_done],
        initial_state=entry,
        final_states=[orphan, exit_done],  # orphan이 final_states에 포함된 상황
    )
    agent = AgentDefinition(fsm=fsm, name="test-agent", description="")

    editor = AgentEditor(agent)  # _migrate_fsm 내부에서 호출됨

    assert orphan not in fsm.states, "orphan이 states에서 제거되어야 한다"
    assert orphan not in fsm.final_states, "orphan이 final_states에서도 제거되어야 한다"
    assert exit_done in fsm.final_states, "exit_done은 final_states에 남아있어야 한다"


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
