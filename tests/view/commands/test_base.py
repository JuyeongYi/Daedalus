from __future__ import annotations

from daedalus.view.commands.base import Command, CommandStack, MacroCommand


class AppendCmd(Command):
    """테스트용: 리스트에 값 추가/제거."""

    def __init__(self, target: list[int], value: int) -> None:
        self._target = target
        self._value = value

    @property
    def description(self) -> str:
        return f"Append {self._value}"

    def execute(self) -> None:
        self._target.append(self._value)

    def undo(self) -> None:
        self._target.remove(self._value)


class TestCommandStack:
    def test_execute_runs_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        assert data == [1]

    def test_undo_reverses_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        assert data == []

    def test_redo_reapplies_command(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        stack.redo()
        assert data == [1]

    def test_execute_clears_redo_stack(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.undo()
        stack.execute(AppendCmd(data, 2))
        assert not stack.can_redo

    def test_can_undo_empty(self):
        assert not CommandStack().can_undo

    def test_can_redo_empty(self):
        assert not CommandStack().can_redo

    def test_history_returns_undo_stack(self):
        stack = CommandStack()
        cmd1 = AppendCmd([], 1)
        cmd2 = AppendCmd([], 2)
        stack.execute(cmd1)
        stack.execute(cmd2)
        assert stack.history == [cmd1, cmd2]

    def test_current_index(self):
        stack = CommandStack()
        stack.execute(AppendCmd([], 1))
        stack.execute(AppendCmd([], 2))
        assert stack.current_index == 1
        stack.undo()
        assert stack.current_index == 0

    def test_current_index_empty(self):
        assert CommandStack().current_index == -1

    def test_goto_backward(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.execute(AppendCmd(data, 2))
        stack.execute(AppendCmd(data, 3))
        stack.goto(0)
        assert data == [1]
        assert stack.current_index == 0

    def test_goto_forward(self):
        data: list[int] = []
        stack = CommandStack()
        stack.execute(AppendCmd(data, 1))
        stack.execute(AppendCmd(data, 2))
        stack.execute(AppendCmd(data, 3))
        stack.goto(0)
        stack.goto(2)
        assert data == [1, 2, 3]

    def test_listener_notified_on_execute(self):
        calls: list[str] = []
        stack = CommandStack()
        stack.add_listener(lambda: calls.append("changed"))
        stack.execute(AppendCmd([], 1))
        assert calls == ["changed"]

    def test_listener_notified_on_undo(self):
        calls: list[str] = []
        stack = CommandStack()
        stack.execute(AppendCmd([], 1))
        stack.add_listener(lambda: calls.append("changed"))
        stack.undo()
        assert calls == ["changed"]


class TestMacroCommand:
    def test_execute_runs_all_children(self):
        data: list[int] = []
        macro = MacroCommand(
            children=[AppendCmd(data, 1), AppendCmd(data, 2)],
            description="Append 1 and 2",
        )
        macro.execute()
        assert data == [1, 2]

    def test_undo_reverses_in_reverse_order(self):
        data: list[int] = []
        macro = MacroCommand(
            children=[AppendCmd(data, 1), AppendCmd(data, 2)],
            description="Append 1 and 2",
        )
        macro.execute()
        macro.undo()
        assert data == []

    def test_description(self):
        macro = MacroCommand(children=[], description="Test macro")
        assert macro.description == "Test macro"

    def test_children_returns_copy(self):
        cmd = AppendCmd([], 1)
        macro = MacroCommand(children=[cmd], description="x")
        macro.children.append(AppendCmd([], 2))
        assert len(macro.children) == 1  # 원본 불변
