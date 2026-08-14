"""MainWindow의 활성 스택 기반 undo/redo 검증."""
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.commands.state_commands import CreateStateCmd
from daedalus.view.viewmodel.state_vm import StateViewModel
# 고정 상주 탭 개수(Project FSM / 블랙보드 / 훅) — 탭이 늘어도 테스트가 따라간다
from daedalus.view.app import _FIXED_TAB_INDEXES
_FIXED_TAB_COUNT = len(_FIXED_TAB_INDEXES)


def _make_agent() -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="a_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )
    return AgentDefinition(fsm=fsm, name="my_agent", description="")


def test_undo_targets_active_agent_stack(qapp):
    """에이전트 탭이 활성일 때 _undo는 에이전트 그래프 스택을 되돌린다."""
    window = MainWindow()
    agent = _make_agent()
    project = PluginProject(name="p")
    project.agents.append(agent)
    window.set_project(project)

    window._open_component(agent)  # 에이전트 탭 열림 + setCurrentIndex로 활성화
    from daedalus.view.editors.agent_editor import AgentEditor
    widget = window._tabs.currentWidget()
    assert isinstance(widget, AgentEditor)

    graph_vm = widget._graph_vm
    state = SimpleState(name="x")
    graph_vm.execute(CreateStateCmd(graph_vm, StateViewModel(model=state, x=0, y=0)))
    assert graph_vm.command_stack.can_undo

    window._undo()
    assert not graph_vm.command_stack.can_undo, "에이전트 스택이 undo되어야 한다"
    assert graph_vm.command_stack.can_redo
    assert not window._project_vm.command_stack.can_redo, "프로젝트 스택은 건드리면 안 된다"

    window._redo()
    assert graph_vm.command_stack.can_undo
    window.close()


def test_undo_action_state_follows_active_stack(qapp):
    """Undo 액션 활성화 여부가 활성 탭 스택을 따른다."""
    window = MainWindow()
    agent = _make_agent()
    project = PluginProject(name="p")
    project.agents.append(agent)
    window.set_project(project)

    window._open_component(agent)
    widget = window._tabs.currentWidget()
    graph_vm = widget._graph_vm
    state = SimpleState(name="x")
    graph_vm.execute(CreateStateCmd(graph_vm, StateViewModel(model=state, x=0, y=0)))

    window._update_undo_redo()
    assert window._undo_action.isEnabled(), (
        "에이전트 스택에 커맨드가 있으면 Undo 액션이 활성화되어야 한다"
    )
    window.close()


def test_close_tab_triggers_close_event_cleanup(qapp):
    """_close_tab 경유 시 AgentEditor.closeEvent → scene.close()가 호출된다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    window = MainWindow()
    agent = _make_agent()
    project = PluginProject(name="p")
    project.agents.append(agent)
    window.set_project(project)

    window._open_component(agent)
    widget = window._tabs.currentWidget()
    assert isinstance(widget, AgentEditor)
    tab_index = window._tabs.currentIndex()

    close_called: list[bool] = []
    original_close = widget._graph_scene.close

    def _tracking_close() -> None:
        close_called.append(True)
        original_close()

    widget._graph_scene.close = _tracking_close  # type: ignore[method-assign]

    window._close_tab(tab_index)

    assert close_called, (
        "_close_tab이 widget.close()를 호출해 AgentEditor.closeEvent → "
        "scene.close()(씬 리스너 해제)가 실행되어야 한다"
    )
    # 탭이 실제로 제거되었는지 확인
    assert window._tabs.count() == _FIXED_TAB_COUNT  # 고정 탭만 남음
    assert "my_agent" not in window._open_tabs
    window.close()
