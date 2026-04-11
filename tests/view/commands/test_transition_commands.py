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
