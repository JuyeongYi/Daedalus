from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.commands.transition_commands import (
    CreateTransitionCmd,
    DeleteTransitionCmd,
)


def _make_transition_vm() -> tuple[ProjectViewModel, TransitionViewModel]:
    s1 = SimpleState(name="A")
    s2 = SimpleState(name="B")
    pvm = ProjectViewModel()
    vm_a = StateViewModel(model=s1)
    vm_b = StateViewModel(model=s2)
    tvm = TransitionViewModel(
        model=Transition(source=s1, target=s2),
        source_vm=vm_a,
        target_vm=vm_b,
    )
    return pvm, tvm


class TestCreateTransitionCmd:
    def test_execute_adds_transition(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        cmd.execute()
        assert tvm in pvm.transition_vms

    def test_undo_removes_transition(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        cmd.execute()
        cmd.undo()
        assert tvm not in pvm.transition_vms

    def test_description(self):
        pvm, tvm = _make_transition_vm()
        cmd = CreateTransitionCmd(pvm, tvm)
        assert "A" in cmd.description and "B" in cmd.description


class TestDeleteTransitionCmd:
    def test_execute_removes_transition(self):
        pvm, tvm = _make_transition_vm()
        pvm.add_transition_vm(tvm)
        cmd = DeleteTransitionCmd(pvm, tvm)
        cmd.execute()
        assert tvm not in pvm.transition_vms

    def test_undo_restores_transition(self):
        pvm, tvm = _make_transition_vm()
        pvm.add_transition_vm(tvm)
        cmd = DeleteTransitionCmd(pvm, tvm)
        cmd.execute()
        cmd.undo()
        assert tvm in pvm.transition_vms

    def test_description(self):
        pvm, tvm = _make_transition_vm()
        cmd = DeleteTransitionCmd(pvm, tvm)
        assert "A" in cmd.description and "B" in cmd.description


def _make_transition_fixture():
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm = StateMachine(name="fsm", states=[a, b], initial_state=a)
    vm = ProjectViewModel()
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=100, y=0)
    vm.state_vms.extend([avm, bvm])
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    return vm, fsm, model, tvm


def test_create_transition_cmd_syncs_fsm():
    vm, fsm, model, tvm = _make_transition_fixture()
    cmd = CreateTransitionCmd(vm, tvm, fsm=fsm)

    cmd.execute()
    assert model in fsm.transitions
    assert tvm in vm.transition_vms

    cmd.undo()
    assert model not in fsm.transitions
    assert tvm not in vm.transition_vms


def test_delete_transition_cmd_syncs_fsm():
    vm, fsm, model, tvm = _make_transition_fixture()
    fsm.transitions.append(model)
    vm.transition_vms.append(tvm)
    cmd = DeleteTransitionCmd(vm, tvm, fsm=fsm)

    cmd.execute()
    assert model not in fsm.transitions
    assert tvm not in vm.transition_vms

    cmd.undo()
    assert model in fsm.transitions
    assert tvm in vm.transition_vms


def test_create_transition_cmd_without_fsm_keeps_legacy_behavior():
    vm, _fsm, _model, tvm = _make_transition_fixture()
    cmd = CreateTransitionCmd(vm, tvm)
    cmd.execute()
    assert tvm in vm.transition_vms
    cmd.undo()
    assert tvm not in vm.transition_vms
