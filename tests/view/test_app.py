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


def test_agent_tab_undo_targets_project_stack(qapp):
    """WP-AF — AgentEditor는 별도 그래프 VM이 없다. 에이전트 탭이 활성이어도
    undo/redo는 프로젝트 스택을 따른다 (SkillEditor와 동일)."""
    window = MainWindow()
    agent = _make_agent()
    project = PluginProject(name="p")
    project.agents.append(agent)
    window.set_project(project)

    window._open_component(agent)
    from daedalus.view.editors.agent_editor import AgentEditor
    widget = window._tabs.currentWidget()
    assert isinstance(widget, AgentEditor)
    assert window._active_stack is window._project_vm.command_stack

    state = SimpleState(name="x")
    window._project_vm.execute(
        CreateStateCmd(window._project_vm, StateViewModel(model=state, x=0, y=0))
    )
    window._update_undo_redo()
    assert window._undo_action.isEnabled()
    window._undo()
    assert not window._project_vm.command_stack.can_undo
    window.close()
