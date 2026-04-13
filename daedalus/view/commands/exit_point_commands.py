from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ExitPoint
from daedalus.view.commands.base import Command


class AddExitPointCmd(Command):
    """ExitPoint을 FSM에 추가하는 커맨드."""

    def __init__(self, fsm: StateMachine, exit_point: ExitPoint) -> None:
        self._fsm = fsm
        self._ep = exit_point

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 추가"

    @property
    def script_repr(self) -> str:
        return f'add_exit_point("{self._ep.name}")'

    def execute(self) -> None:
        self._fsm.states.append(self._ep)
        self._fsm.final_states.append(self._ep)

    def undo(self) -> None:
        if self._ep in self._fsm.states:
            self._fsm.states.remove(self._ep)
        if self._ep in self._fsm.final_states:
            self._fsm.final_states.remove(self._ep)


class DeleteExitPointCmd(Command):
    """ExitPoint을 FSM에서 삭제하는 커맨드."""

    def __init__(self, fsm: StateMachine, exit_point: ExitPoint) -> None:
        self._fsm = fsm
        self._ep = exit_point
        self._state_idx: int = -1
        self._final_idx: int = -1

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 삭제"

    @property
    def script_repr(self) -> str:
        return f'delete_exit_point("{self._ep.name}")'

    def execute(self) -> None:
        if self._ep in self._fsm.states:
            self._state_idx = self._fsm.states.index(self._ep)
            self._fsm.states.remove(self._ep)
        if self._ep in self._fsm.final_states:
            self._final_idx = self._fsm.final_states.index(self._ep)
            self._fsm.final_states.remove(self._ep)

    def undo(self) -> None:
        if self._state_idx >= 0:
            self._fsm.states.insert(self._state_idx, self._ep)
        if self._final_idx >= 0:
            self._fsm.final_states.insert(self._final_idx, self._ep)


class RenameExitPointCmd(Command):
    """ExitPoint의 이름을 변경하는 커맨드."""

    def __init__(self, exit_point: ExitPoint, old_name: str, new_name: str) -> None:
        self._ep = exit_point
        self._old_name = old_name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return f"ExitPoint 이름 변경: '{self._old_name}' → '{self._new_name}'"

    @property
    def script_repr(self) -> str:
        return f'rename_exit_point("{self._old_name}", "{self._new_name}")'

    def execute(self) -> None:
        self._ep.name = self._new_name

    def undo(self) -> None:
        self._ep.name = self._old_name


class ChangeExitPointColorCmd(Command):
    """ExitPoint의 색상을 변경하는 커맨드."""

    def __init__(self, exit_point: ExitPoint, old_color: str, new_color: str) -> None:
        self._ep = exit_point
        self._old_color = old_color
        self._new_color = new_color

    @property
    def description(self) -> str:
        return f"ExitPoint '{self._ep.name}' 색상 변경"

    @property
    def script_repr(self) -> str:
        return f'change_exit_point_color("{self._ep.name}", "{self._new_color}")'

    def execute(self) -> None:
        self._ep.color = self._new_color

    def undo(self) -> None:
        self._ep.color = self._old_color
