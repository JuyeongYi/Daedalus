# daedalus/view/commands/surface_commands.py
"""모델을 바꾸지 않고 **화면만** 현재 사실에 맞추는 커맨드 (2026-09-18).

종류 전환(`actions/fork_skill.convert_skill_kind`)처럼 `__class__`와 config를
통째로 바꾸는 편집은 열린 편집 탭의 프론트매터 폼과 레지스트리를 스테일로
만든다. 그 재동기를 **액션 함수**에 두면 undo에는 걸리지 않는다 — 되돌린
뒤에도 폼은 전환 후의 표로 남고, 그 폼의 write-back은 스테일 가드가 조용히
버린다(버튼은 "Ctrl+Z로 되돌릴 수 있습니다"라고 말해 놓고). 그래서 재동기도
커맨드 스택을 탄다.
"""
from __future__ import annotations

from daedalus.view.commands.base import Command


class ResyncSurfacesCmd(Command):
    """열린 편집 탭의 프론트매터 폼 + 레지스트리를 컴포넌트의 **현재** 종류로 다시 그린다.

    모델을 건드리지 않으므로 execute/undo가 같은 일을 한다. 방향 플래그가 있는
    이유는 `MacroCommand`가 execute를 앞→뒤로, undo를 뒤→앞으로 돌리기
    때문이다 — 한쪽 끝에만 두면 한 방향은 상태가 확정되기 **전에** 그린다.
    `resync_bracket()`이 만드는 두 개를 매크로의 양 끝에 두면 어느 방향이든
    마지막 한 번이 확정된 상태를 본다.
    """

    def __init__(
        self, window, component, *, on_execute: bool = True, on_undo: bool = True,
    ) -> None:
        self._window = window
        self._component = component
        self._on_execute = on_execute
        self._on_undo = on_undo

    @property
    def description(self) -> str:
        return f"'{getattr(self._component, 'name', '?')}' 편집 표면 재동기"

    def execute(self) -> None:
        if self._on_execute:
            self._resync()

    def undo(self) -> None:
        if self._on_undo:
            self._resync()

    def _resync(self) -> None:
        window = self._window
        panel = getattr(window, "_registry_panel", None)
        project = getattr(window, "_project", None)
        if panel is not None and project is not None:
            panel.set_project(project)
        rebuild = getattr(window, "rebuild_component_frontmatter", None)
        if callable(rebuild):
            rebuild(self._component)


def resync_bracket(window, component) -> tuple[Command, Command]:
    """매크로의 (맨 앞, 맨 뒤)에 넣을 재동기 커맨드 한 쌍.

    맨 앞은 undo에서만(= undo의 마지막 단계), 맨 뒤는 execute/redo에서만
    (= execute의 마지막 단계) 그린다 — 쓸데없는 재생성이 없다.
    """
    head = ResyncSurfacesCmd(window, component, on_execute=False)
    tail = ResyncSurfacesCmd(window, component, on_undo=False)
    return head, tail
