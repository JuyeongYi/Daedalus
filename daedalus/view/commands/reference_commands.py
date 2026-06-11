from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from daedalus.view.commands.base import Command

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel
    from daedalus.view.viewmodel.state_vm import (
        ReferenceLinkViewModel,
        ReferenceViewModel,
    )


class CreateRefCmd(Command):
    """참조 노드 생성 — undo 가능."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        ref_vm: ReferenceViewModel,
        sync_fn: Callable[[], None],
    ) -> None:
        self._project_vm = project_vm
        self._ref_vm = ref_vm
        self._sync_fn = sync_fn

    @property
    def description(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f"참조 노드 '{name}' 생성"

    @property
    def script_repr(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f'create_ref_node("{name}", x={self._ref_vm.x:.0f}, y={self._ref_vm.y:.0f})'

    def execute(self) -> None:
        if self._ref_vm not in self._project_vm.reference_vms:
            self._project_vm.reference_vms.append(self._ref_vm)
        self._sync_fn()

    def undo(self) -> None:
        # 이 노드에 연결된 링크도 제거
        self._project_vm.reference_links = [
            l for l in self._project_vm.reference_links
            if l.reference_vm is not self._ref_vm
        ]
        if self._ref_vm in self._project_vm.reference_vms:
            self._project_vm.reference_vms.remove(self._ref_vm)
        self._sync_fn()


class DeleteRefCmd(Command):
    """참조 노드 + 연결 링크 삭제 — undo 가능."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        ref_vm: ReferenceViewModel,
        sync_fn: Callable[[], None],
    ) -> None:
        self._project_vm = project_vm
        self._ref_vm = ref_vm
        self._sync_fn = sync_fn
        self._removed_links: list[ReferenceLinkViewModel] = []

    @property
    def description(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f"참조 노드 '{name}' 삭제"

    @property
    def script_repr(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f'delete_ref_node("{name}")'

    def execute(self) -> None:
        self._removed_links = [
            l for l in self._project_vm.reference_links
            if l.reference_vm is self._ref_vm
        ]
        self._project_vm.reference_links = [
            l for l in self._project_vm.reference_links
            if l.reference_vm is not self._ref_vm
        ]
        if self._ref_vm in self._project_vm.reference_vms:
            self._project_vm.reference_vms.remove(self._ref_vm)
        self._sync_fn()

    def undo(self) -> None:
        if self._ref_vm not in self._project_vm.reference_vms:
            self._project_vm.reference_vms.append(self._ref_vm)
        for lvm in self._removed_links:
            if lvm not in self._project_vm.reference_links:
                self._project_vm.reference_links.append(lvm)
        self._sync_fn()


class MoveRefCmd(Command):
    """참조 노드 이동 — undo 가능. sync_fn으로 모델 좌표 동기화."""

    def __init__(
        self,
        ref_vm: ReferenceViewModel,
        old_x: float,
        old_y: float,
        new_x: float,
        new_y: float,
        sync_fn: Callable[[], None],
    ) -> None:
        self._ref_vm = ref_vm
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y
        self._sync_fn = sync_fn

    @property
    def description(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f"참조 노드 '{name}' 이동"

    @property
    def script_repr(self) -> str:
        name = getattr(self._ref_vm.model, "name", "?")
        return f'move_ref_node("{name}", x={self._new_x:.0f}, y={self._new_y:.0f})'

    def execute(self) -> None:
        self._ref_vm.x = self._new_x
        self._ref_vm.y = self._new_y
        self._sync_fn()

    def undo(self) -> None:
        self._ref_vm.x = self._old_x
        self._ref_vm.y = self._old_y
        self._sync_fn()


class CreateRefLinkCmd(Command):
    """참조 링크(상태 → 참조 노드) 생성 — undo 가능."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        link_vm: ReferenceLinkViewModel,
        sync_fn: Callable[[], None],
    ) -> None:
        self._project_vm = project_vm
        self._link_vm = link_vm
        self._sync_fn = sync_fn

    @property
    def description(self) -> str:
        state_name = self._link_vm.state_vm.model.name
        ref_name = getattr(self._link_vm.reference_vm.model, "name", "?")
        return f"참조 링크 '{state_name}→{ref_name}' 생성"

    @property
    def script_repr(self) -> str:
        state_name = self._link_vm.state_vm.model.name
        ref_name = getattr(self._link_vm.reference_vm.model, "name", "?")
        return f'create_ref_link("{state_name}", "{ref_name}")'

    def execute(self) -> None:
        if self._link_vm not in self._project_vm.reference_links:
            self._project_vm.reference_links.append(self._link_vm)
        self._sync_fn()

    def undo(self) -> None:
        if self._link_vm in self._project_vm.reference_links:
            self._project_vm.reference_links.remove(self._link_vm)
        self._sync_fn()


class DeleteRefLinkCmd(Command):
    """참조 링크 삭제 — undo 가능."""

    def __init__(
        self,
        project_vm: ProjectViewModel,
        link_vm: ReferenceLinkViewModel,
        sync_fn: Callable[[], None],
    ) -> None:
        self._project_vm = project_vm
        self._link_vm = link_vm
        self._sync_fn = sync_fn

    @property
    def description(self) -> str:
        state_name = self._link_vm.state_vm.model.name
        ref_name = getattr(self._link_vm.reference_vm.model, "name", "?")
        return f"참조 링크 '{state_name}→{ref_name}' 삭제"

    @property
    def script_repr(self) -> str:
        state_name = self._link_vm.state_vm.model.name
        ref_name = getattr(self._link_vm.reference_vm.model, "name", "?")
        return f'delete_ref_link("{state_name}", "{ref_name}")'

    def execute(self) -> None:
        if self._link_vm in self._project_vm.reference_links:
            self._project_vm.reference_links.remove(self._link_vm)
        self._sync_fn()

    def undo(self) -> None:
        if self._link_vm not in self._project_vm.reference_links:
            self._project_vm.reference_links.append(self._link_vm)
        self._sync_fn()
