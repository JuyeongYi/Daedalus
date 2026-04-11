from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.commands.base import CommandStack
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _make_state_vm(name: str = "S") -> StateViewModel:
    return StateViewModel(model=SimpleState(name=name))


def _make_transition_vm(
    src: StateViewModel, tgt: StateViewModel
) -> TransitionViewModel:
    return TransitionViewModel(
        model=Transition(source=src.model, target=tgt.model),
        source_vm=src,
        target_vm=tgt,
    )


class TestProjectViewModel:
    def test_initially_empty(self):
        pvm = ProjectViewModel()
        assert pvm.state_vms == []
        assert pvm.transition_vms == []

    def test_has_command_stack(self):
        pvm = ProjectViewModel()
        assert isinstance(pvm.command_stack, CommandStack)

    def test_add_and_remove_state_vm(self):
        pvm = ProjectViewModel()
        vm = _make_state_vm("A")
        pvm.add_state_vm(vm)
        assert vm in pvm.state_vms
        pvm.remove_state_vm(vm)
        assert vm not in pvm.state_vms

    def test_add_and_remove_transition_vm(self):
        pvm = ProjectViewModel()
        a = _make_state_vm("A")
        b = _make_state_vm("B")
        tvm = _make_transition_vm(a, b)
        pvm.add_transition_vm(tvm)
        assert tvm in pvm.transition_vms
        pvm.remove_transition_vm(tvm)
        assert tvm not in pvm.transition_vms

    def test_get_state_vm_found(self):
        pvm = ProjectViewModel()
        vm = _make_state_vm("X")
        pvm.add_state_vm(vm)
        assert pvm.get_state_vm("X") is vm

    def test_get_state_vm_not_found(self):
        pvm = ProjectViewModel()
        assert pvm.get_state_vm("missing") is None

    def test_get_transitions_for(self):
        pvm = ProjectViewModel()
        a = _make_state_vm("A")
        b = _make_state_vm("B")
        c = _make_state_vm("C")
        t_ab = _make_transition_vm(a, b)
        t_bc = _make_transition_vm(b, c)
        pvm.add_transition_vm(t_ab)
        pvm.add_transition_vm(t_bc)
        assert pvm.get_transitions_for(b) == [t_ab, t_bc]
        assert pvm.get_transitions_for(a) == [t_ab]
        assert pvm.get_transitions_for(c) == [t_bc]

    def test_listener_notified(self):
        calls: list[str] = []
        pvm = ProjectViewModel()
        pvm.add_listener(lambda: calls.append("changed"))
        pvm.notify()
        assert calls == ["changed"]

    def test_remove_listener_stops_notifications(self):
        calls: list[str] = []
        pvm = ProjectViewModel()
        listener = lambda: calls.append("changed")
        pvm.add_listener(listener)
        pvm.notify()
        assert calls == ["changed"]
        pvm.remove_listener(listener)
        pvm.notify()
        assert calls == ["changed"]  # no new call after removal

    def test_remove_listener_missing_does_not_raise(self):
        pvm = ProjectViewModel()
        pvm.remove_listener(lambda: None)  # should not raise

    def test_execute_delegates_to_command_stack(self):
        from daedalus.view.commands.base import Command

        class NoopCmd(Command):
            def __init__(self) -> None:
                self.executed = False

            @property
            def description(self) -> str:
                return "noop"

            def execute(self) -> None:
                self.executed = True

            def undo(self) -> None:
                self.executed = False

        pvm = ProjectViewModel()
        calls: list[str] = []
        pvm.add_listener(lambda: calls.append("fired"))
        cmd = NoopCmd()
        pvm.execute(cmd)
        assert cmd.executed
        assert pvm.command_stack.current_index == 0
        assert calls == ["fired"]
