from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import TransitionViewModel

if TYPE_CHECKING:
    from daedalus.model.project import PluginProject
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


class SetTransitionSkillRefCmd(Command):
    """Transition.skill_ref 설정/해제 — undo 가능."""

    def __init__(
        self,
        transition_vm: TransitionViewModel,
        new_skill: object | None,
    ) -> None:
        self._transition_vm = transition_vm
        self._new_skill = new_skill
        self._old_skill = transition_vm.model.skill_ref

    @property
    def description(self) -> str:
        if self._new_skill is None:
            name = getattr(self._old_skill, "name", "?")
            return f"Transfer Skill '{name}' 해제"
        return f"Transfer Skill '{getattr(self._new_skill, 'name', '?')}' 설정"

    @property
    def script_repr(self) -> str:
        if self._new_skill is None:
            return f'unset_transition_skill("{self._transition_vm.model.trigger.name}")'
        return f'set_transition_skill("{self._transition_vm.model.trigger.name}", "{getattr(self._new_skill, "name", "?")}")'

    def execute(self) -> None:
        self._transition_vm.model.skill_ref = self._new_skill

    def undo(self) -> None:
        self._transition_vm.model.skill_ref = self._old_skill


class AddSkillToProjectCmd(Command):
    """TransferSkill을 PluginProject.skills에 추가 (undo: 제거)."""

    def __init__(self, project: PluginProject, skill: object) -> None:
        self._project = project
        self._skill = skill

    @property
    def description(self) -> str:
        return f"Transfer Skill '{getattr(self._skill, 'name', '?')}' 추가"

    @property
    def script_repr(self) -> str:
        return f'add_transfer_skill("{getattr(self._skill, "name", "?")}")'

    def execute(self) -> None:
        if self._skill not in self._project.skills:
            self._project.skills.append(self._skill)

    def undo(self) -> None:
        if self._skill in self._project.skills:
            self._project.skills.remove(self._skill)
