from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Command(ABC):
    """모든 편집 동작의 기반."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Undo/Redo 메뉴 및 히스토리 패널에 표시될 설명."""

    @property
    def script_repr(self) -> str:
        """스크립트 리스너에 출력할 Python 표현. 서브클래스에서 오버라이드."""
        return f"# {self.description}"

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
    def script_repr(self) -> str:
        lines = [f"# {self._description}"]
        lines.extend(f"  {c.script_repr}" for c in self._children)
        return "\n".join(lines)

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
        self._execute_listeners: list[Callable[[Command], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        """등록된 리스너를 제거. 없으면 무시."""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def add_execute_listener(self, listener: Callable[[Command], None]) -> None:
        """커맨드 실행 시 해당 커맨드를 인수로 받는 리스너 등록."""
        self._execute_listeners.append(listener)

    def remove_execute_listener(self, listener: Callable[[Command], None]) -> None:
        """execute 리스너를 제거. 없으면 무시."""
        try:
            self._execute_listeners.remove(listener)
        except ValueError:
            pass

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def execute(self, cmd: Command) -> None:
        cmd.execute()
        self._undo_stack.append(cmd)
        self._redo_stack.clear()
        for listener in self._execute_listeners:
            listener(cmd)
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
