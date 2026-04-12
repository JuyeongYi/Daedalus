from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.view.commands.base import Command, CommandStack


class ScriptListenerPanel(QWidget):
    """마야 스크립트 리스너처럼 실행된 커맨드를 Python 표현으로 출력."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stack: CommandStack | None = None
        self._listener: Callable[[Command], None] = self._on_command_executed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Consolas", 9))
        self._output.setStyleSheet(
            "QTextEdit { background: #0d0d1a; color: #88ff88; border: none; }"
        )
        layout.addWidget(self._output)

        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(4, 4, 4, 4)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(22)
        clear_btn.clicked.connect(self._output.clear)
        btn_bar.addStretch()
        btn_bar.addWidget(clear_btn)
        layout.addLayout(btn_bar)

    def set_stack(self, stack: CommandStack) -> None:
        """활성 탭이 바뀔 때 추적할 CommandStack을 교체."""
        if self._stack is not None:
            self._stack.remove_execute_listener(self._listener)
        self._stack = stack
        self._stack.add_execute_listener(self._listener)

    def _on_command_executed(self, cmd: Command) -> None:
        self._output.append(cmd.script_repr)
        sb = self._output.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())
