from __future__ import annotations

from typing import TYPE_CHECKING

from daedalus.view.commands.base import Command
from daedalus.view.viewmodel.state_vm import TransitionViewModel

if TYPE_CHECKING:
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.project import PluginProject
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


class CreateTransitionCmd(Command):
    def __init__(
        self,
        project_vm: ProjectViewModel,
        transition_vm: TransitionViewModel,
        fsm: StateMachine | None = None,
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm
        self._fsm = fsm

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
        if self._fsm is not None and self._transition_vm.model not in self._fsm.transitions:
            self._fsm.transitions.append(self._transition_vm.model)

    def undo(self) -> None:
        self._project_vm.remove_transition_vm(self._transition_vm)
        if self._fsm is not None and self._transition_vm.model in self._fsm.transitions:
            self._fsm.transitions.remove(self._transition_vm.model)


class DeleteTransitionCmd(Command):
    def __init__(
        self,
        project_vm: ProjectViewModel,
        transition_vm: TransitionViewModel,
        fsm: StateMachine | None = None,
    ) -> None:
        self._project_vm = project_vm
        self._transition_vm = transition_vm
        self._fsm = fsm

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
        if self._fsm is not None and self._transition_vm.model in self._fsm.transitions:
            self._fsm.transitions.remove(self._transition_vm.model)

    def undo(self) -> None:
        self._project_vm.add_transition_vm(self._transition_vm)
        if self._fsm is not None and self._transition_vm.model not in self._fsm.transitions:
            self._fsm.transitions.append(self._transition_vm.model)


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


class AddSkillToListCmd(Command):
    """스킬을 임의 리스트에 추가 (undo: identity 기준 제거).

    plugin 레이어 스킬은 값 동등성 dataclass이므로 list.remove()가
    같은 값의 다른 인스턴스를 제거할 수 있다 — identity로 판단한다.
    """

    def __init__(self, skill_list: list, skill: object) -> None:
        self._skill_list = skill_list
        self._skill = skill

    @property
    def description(self) -> str:
        return f"스킬 '{getattr(self._skill, 'name', '?')}' 추가"

    @property
    def script_repr(self) -> str:
        return f'add_skill_to_list("{getattr(self._skill, "name", "?")}")'

    def execute(self) -> None:
        if not any(s is self._skill for s in self._skill_list):
            self._skill_list.append(self._skill)

    def undo(self) -> None:
        # identity 기준 제거 — 값 동등성 dataclass에서 remove() 오작동 방지
        for i, s in enumerate(self._skill_list):
            if s is self._skill:
                del self._skill_list[i]
                break
