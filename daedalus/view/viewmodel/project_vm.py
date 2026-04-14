from __future__ import annotations

from typing import Callable

from daedalus.view.commands.base import Command, CommandStack
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
    TransitionViewModel,
)


class ProjectViewModel:
    """전체 편집 세션의 상태를 관리. 단일 진실 공급원."""

    def __init__(self) -> None:
        self.state_vms: list[StateViewModel] = []
        self.transition_vms: list[TransitionViewModel] = []
        self.reference_vms: list[ReferenceViewModel] = []
        self.reference_links: list[ReferenceLinkViewModel] = []
        self.command_stack = CommandStack()
        self._listeners: list[Callable[[], None]] = []

    # --- 커맨드 실행 ---

    def execute(self, cmd: Command) -> None:
        """커맨드 실행 후 리스너에 알림."""
        self.command_stack.execute(cmd)
        self.notify()

    # --- 조회 ---

    def get_state_vm(self, name: str) -> StateViewModel | None:
        for vm in self.state_vms:
            if vm.model.name == name:
                return vm
        return None

    def get_transitions_for(
        self, state_vm: StateViewModel
    ) -> list[TransitionViewModel]:
        return [
            t
            for t in self.transition_vms
            if t.source_vm is state_vm or t.target_vm is state_vm
        ]

    # --- 직접 변이 (커맨드 내부에서만 호출) ---

    def add_state_vm(self, vm: StateViewModel) -> None:
        self.state_vms.append(vm)

    def remove_state_vm(self, vm: StateViewModel) -> None:
        if vm in self.state_vms:
            self.state_vms.remove(vm)

    def add_transition_vm(self, vm: TransitionViewModel) -> None:
        self.transition_vms.append(vm)

    def remove_transition_vm(self, vm: TransitionViewModel) -> None:
        if vm in self.transition_vms:
            self.transition_vms.remove(vm)

    # --- 옵저버 ---

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        """등록된 리스너를 제거. 없으면 무시."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def notify(self) -> None:
        for listener in self._listeners:
            listener()
