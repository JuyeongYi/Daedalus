from daedalus.model.fsm.state import SimpleState
from daedalus.view.viewmodel.state_vm import StateViewModel
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.commands.state_commands import (
    CreateStateCmd,
    DeleteStateCmd,
    MoveStateCmd,
    RenameStateCmd,
)


def _make_pvm_with_state(name: str = "S") -> tuple[ProjectViewModel, StateViewModel]:
    pvm = ProjectViewModel()
    vm = StateViewModel(model=SimpleState(name=name))
    pvm.add_state_vm(vm)
    return pvm, vm


class TestCreateStateCmd:
    def test_execute_adds_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        assert vm in pvm.state_vms

    def test_undo_removes_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm not in pvm.state_vms

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = CreateStateCmd(ProjectViewModel(), vm)
        assert "Idle" in cmd.description


class TestDeleteStateCmd:
    def test_execute_removes_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        assert vm not in pvm.state_vms

    def test_undo_restores_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm in pvm.state_vms

    def test_description(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        assert "X" in cmd.description


class TestMoveStateCmd:
    def test_execute_updates_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        assert vm.x == 100.0
        assert vm.y == 200.0

    def test_undo_restores_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        cmd.undo()
        assert vm.x == 0.0
        assert vm.y == 0.0

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = MoveStateCmd(vm, 0, 0, 1, 1)
        assert "Idle" in cmd.description


class TestRenameStateCmd:
    def test_execute_changes_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        assert vm.model.name == "New"

    def test_undo_restores_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        cmd.undo()
        assert vm.model.name == "Old"

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, "Old", "New")
        assert "Old" in cmd.description and "New" in cmd.description
