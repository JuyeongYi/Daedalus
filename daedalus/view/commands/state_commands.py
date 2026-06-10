from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import StateViewModel

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class CreateStateCmd(Command):
    def __init__(
        self,
        project_vm: ProjectViewModel,
        state_vm: StateViewModel,
        fsm: StateMachine | None = None,
    ) -> None:
        self._project_vm = project_vm
        self._state_vm = state_vm
        self._fsm = fsm

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 생성"

    @property
    def script_repr(self) -> str:
        vm = self._state_vm
        return f'create_state("{vm.model.name}", x={vm.x:.0f}, y={vm.y:.0f})'

    def execute(self) -> None:
        self._project_vm.add_state_vm(self._state_vm)
        if self._fsm is not None and self._state_vm.model not in self._fsm.states:
            self._fsm.states.append(self._state_vm.model)

    def undo(self) -> None:
        self._project_vm.remove_state_vm(self._state_vm)
        if self._fsm is not None and self._state_vm.model in self._fsm.states:
            self._fsm.states.remove(self._state_vm.model)


class DeleteStateCmd(Command):
    def __init__(
        self,
        project_vm: ProjectViewModel,
        state_vm: StateViewModel,
        fsm: StateMachine | None = None,
    ) -> None:
        self._project_vm = project_vm
        self._state_vm = state_vm
        self._fsm = fsm

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 삭제"

    @property
    def script_repr(self) -> str:
        return f'delete_state("{self._state_vm.model.name}")'

    def execute(self) -> None:
        self._project_vm.remove_state_vm(self._state_vm)
        if self._fsm is not None and self._state_vm.model in self._fsm.states:
            self._fsm.states.remove(self._state_vm.model)

    def undo(self) -> None:
        self._project_vm.add_state_vm(self._state_vm)
        if self._fsm is not None and self._state_vm.model not in self._fsm.states:
            self._fsm.states.append(self._state_vm.model)


class MoveStateCmd(Command):
    def __init__(
        self,
        state_vm: StateViewModel,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
    ) -> None:
        self._state_vm = state_vm
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y

    @property
    def description(self) -> str:
        return f"상태 '{self._state_vm.model.name}' 이동"

    @property
    def script_repr(self) -> str:
        return f'move_state("{self._state_vm.model.name}", x={self._new_x:.0f}, y={self._new_y:.0f})'

    def execute(self) -> None:
        self._state_vm.x = self._new_x
        self._state_vm.y = self._new_y

    def undo(self) -> None:
        self._state_vm.x = self._old_x
        self._state_vm.y = self._old_y


class RenameStateCmd(Command):
    def __init__(
        self, state_vm: StateViewModel, old_name: str, new_name: str
    ) -> None:
        self._state_vm = state_vm
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"상태 이름 변경: '{self._old_name}' → '{self._new_name}'"

    @property
    def script_repr(self) -> str:
        return f'rename_state("{self._old_name}", "{self._new_name}")'

    def execute(self) -> None:
        self._state_vm.model.name = self._new_name

    def undo(self) -> None:
        self._state_vm.model.name = self._old_name
