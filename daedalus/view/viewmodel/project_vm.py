from __future__ import annotations

from typing import Callable, Literal

from daedalus.view.commands.base import Command, CommandStack
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
    TransitionViewModel,
)

# notify 채널 규약:
#   "structure" — 상태/전이/참조의 추가·삭제·이동 등 구조 변경.
#                 레지스트리/트리/캔버스 재구성 같은 무거운 리스너가 구독한다 (기본값).
#   "content"   — 섹션 content/description/when_to_use 등 텍스트 키스트로크.
#                 가벼운 갱신만 필요한 경로로, structure 리스너는 호출되지 않는다.
# structure 리스너는 양쪽 채널을 모두 수신한다(상위 호환). content 리스너는 content만 수신.
NotifyScope = Literal["structure", "content"]


def _accepts_scope(fn: Callable[..., None]) -> bool:
    """콜백이 scope 키워드 인자를 받는지 시그니처로 판별한다."""
    import inspect
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return False
    params = sig.parameters
    if "scope" in params:
        return True
    return any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def call_notify(fn: Callable[..., None] | None, scope: NotifyScope = "structure") -> None:
    """on_notify_fn 콜백을 채널 인지하여 호출한다.

    콜백이 scope 키워드를 받으면(ProjectViewModel.notify 등) 채널을 전달하고,
    받지 않는 단순 콜백이면 인자 없이 호출한다(상위 호환). 에디터가 임의의
    Callable[[], None]을 받는 기존 계약을 깨지 않으면서 채널 분리를 가능케 한다.
    시그니처를 검사해 콜백 내부의 TypeError를 삼키지 않는다.
    """
    if fn is None:
        return
    if _accepts_scope(fn):
        fn(scope=scope)
    else:
        fn()


class ProjectViewModel:
    """전체 편집 세션의 상태를 관리. 단일 진실 공급원."""

    def __init__(self) -> None:
        self.state_vms: list[StateViewModel] = []
        self.transition_vms: list[TransitionViewModel] = []
        self.reference_vms: list[ReferenceViewModel] = []
        self.reference_links: list[ReferenceLinkViewModel] = []
        self.command_stack = CommandStack()
        self._listeners: list[Callable[[], None]] = []          # structure 채널
        self._content_listeners: list[Callable[[], None]] = []  # content 채널

    # --- 커맨드 실행 ---

    def execute(self, cmd: Command) -> None:
        """커맨드 실행 후 리스너에 알림 (구조 변경)."""
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
        # identity 기준 중복 가드 — undo 시 중복 복원 방지
        if not any(v is vm for v in self.transition_vms):
            self.transition_vms.append(vm)

    def remove_transition_vm(self, vm: TransitionViewModel) -> None:
        if vm in self.transition_vms:
            self.transition_vms.remove(vm)

    # --- 옵저버 ---

    def add_listener(
        self, listener: Callable[[], None], scope: NotifyScope = "structure"
    ) -> None:
        """리스너를 채널에 등록한다. 기본은 structure(상위 호환)."""
        if scope == "content":
            self._content_listeners.append(listener)
        else:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        """등록된 리스너를 양쪽 채널에서 제거. 없으면 무시."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass
        try:
            self._content_listeners.remove(listener)
        except ValueError:
            pass

    def notify(self, scope: NotifyScope = "structure") -> None:
        """채널 리스너에 알림.

        - structure: structure 리스너만 호출 (구조 변경 — 무거운 재구성 포함).
        - content:   content 리스너만 호출 (텍스트 키스트로크 — 가벼운 갱신).
        """
        if scope == "content":
            for listener in self._content_listeners:
                listener()
        else:
            for listener in self._listeners:
                listener()
