from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import TransitionViewModel

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class CreateTransitionCmd(Command):
    def __init__(
        self, project_vm: ProjectViewModel, transition_vm: TransitionViewModel
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm

    @property
    def description(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f"전이 '{src}→{tgt}' 생성"

    @property
    def script_repr(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f'create_transition("{src}", "{tgt}")'

    def execute(self) -> None:
        self._project_vm.add_transition_vm(self._transition_vm)

    def undo(self) -> None:
        self._project_vm.remove_transition_vm(self._transition_vm)


class DeleteTransitionCmd(Command):
    def __init__(
        self, project_vm: ProjectViewModel, transition_vm: TransitionViewModel
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm

    @property
    def description(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f"전이 '{src}→{tgt}' 삭제"

    @property
    def script_repr(self) -> str:
        src = self._transition_vm.source_vm.model.name
        tgt = self._transition_vm.target_vm.model.name
        return f'delete_transition("{src}", "{tgt}")'

    def execute(self) -> None:
        self._project_vm.remove_transition_vm(self._transition_vm)

    def undo(self) -> None:
        self._project_vm.add_transition_vm(self._transition_vm)
