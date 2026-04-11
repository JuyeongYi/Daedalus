from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Command(ABC):
    """모든 편집 동작의 기반."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Undo/Redo 메뉴 및 히스토리 패널에 표시될 설명."""

    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...


class MacroCommand(Command):
    """여러 커맨드를 하나의 Undo 단위로 묶음."""

    def __init__(self, children: list[Command], description: str) -> None:
        self._children = list(children)
        self._description = description

    @property
    def description(self) -> str:
        return self._description

    @property
    def children(self) -> list[Command]:
        return list(self._children)

    def execute(self) -> None:
        for cmd in self._children:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self._children):
            cmd.undo()


class CommandStack:
    """Undo/Redo 스택. 모든 편집의 관문."""

    def __init__(self) -> None:
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        """등록된 리스너를 제거. 없으면 무시."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def execute(self, cmd: Command) -> None:
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        self._notify()

    def undo(self) -> None:
        if not self.can_undo:
            return
        cmd = self._undo_stack.pop()
        cmd.undo()
        self._redo_stack.append(cmd)
        self._notify()

    def redo(self) -> None:
        if not self.can_redo:
            return
        cmd = self._redo_stack.pop()
        cmd.execute()
        self._undo_stack.append(cmd)
        self._notify()

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def history(self) -> list[Command]:
        return list(self._undo_stack)

    @property
    def redo_history(self) -> list[Command]:
        """Redo 가능한 커맨드 목록 (다음 redo 대상이 [0])."""
        return list(reversed(self._redo_stack))

    @property
    def current_index(self) -> int:
        return len(self._undo_stack) - 1

    def goto(self, index: int) -> None:
        """히스토리 특정 지점으로 점프."""
        while self.current_index > index:
            self.undo()
        while self.current_index < index:
            self.redo()
