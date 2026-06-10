"""AgentFsmScene이 agent.fsm 모델을 동기화하는지 검증."""
from PyQt6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.canvas.scene import AgentFsmScene, FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_agent_fsm() -> StateMachine:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm",
        states=[entry, done],
        initial_state=entry,
        final_states=[done],
    )


def _make_scene(qapp):
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    return vm, fsm, scene


def test_create_state_syncs_to_agent_fsm(qapp):
    vm, fsm, scene = _make_scene(qapp)
    scene._create_state(QPointF(50, 60))

    created = [s for s in fsm.states if s.name == "State_1"]
    assert len(created) == 1, "캔버스에서 만든 상태가 agent.fsm.states에 있어야 한다"

    vm.command_stack.undo()
    assert not any(s.name == "State_1" for s in fsm.states)


def test_delete_state_syncs_to_agent_fsm(qapp):
    vm, fsm, scene = _make_scene(qapp)
    state = SimpleState(name="victim")
    fsm.states.append(state)
    svm = StateViewModel(model=state, x=0, y=0)
    vm.state_vms.append(svm)

    scene._delete_state(svm)
    assert state not in fsm.states

    vm.command_stack.undo()
    assert state in fsm.states


def test_delete_transition_syncs_to_agent_fsm(qapp):
    vm, fsm, scene = _make_scene(qapp)
    a, b = fsm.states[0], fsm.states[1]
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    fsm.transitions.append(model)
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=100, y=0)
    vm.state_vms.extend([avm, bvm])
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    vm.transition_vms.append(tvm)

    scene._delete_transition(tvm)
    assert model not in fsm.transitions

    vm.command_stack.undo()
    assert model in fsm.transitions


def test_delete_exit_point_does_not_double_remove(qapp):
    """ExitPoint 삭제는 DeleteExitPointCmd가 fsm을 처리 — 이중 제거/이중 복원 금지."""
    vm, fsm, scene = _make_scene(qapp)
    extra = ExitPoint(name="alt_exit")
    fsm.states.append(extra)
    fsm.final_states.append(extra)
    svm = StateViewModel(model=extra, x=0, y=0)
    vm.state_vms.append(svm)

    scene._delete_exit_point(svm, extra)
    assert extra not in fsm.states
    assert extra not in fsm.final_states

    vm.command_stack.undo()
    assert sum(1 for s in fsm.states if s is extra) == 1, "undo 후 정확히 1개여야 한다"
    assert sum(1 for s in fsm.final_states if s is extra) == 1


def test_project_scene_does_not_touch_fsm(qapp):
    """프로젝트 캔버스(FsmScene)는 _target_fsm=None — 기존 동작 유지."""
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene._create_state(QPointF(0, 0))
    assert len(vm.state_vms) == 1  # VM에만 추가, 크래시 없음
