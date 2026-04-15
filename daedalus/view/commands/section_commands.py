# daedalus/view/commands/section_commands.py
from __future__ import annotations

from daedalus.model.fsm.section import Section
from daedalus.view.commands.base import Command


class AddSectionCmd(Command):
    """섹션 리스트에 Section 추가 (undo: 제거)."""

    def __init__(self, sections: list[Section], section: Section) -> None:
        self._sections = sections
        self._section = section

    @property
    def description(self) -> str:
        return f"섹션 '{self._section.title}' 추가"

    @property
    def script_repr(self) -> str:
        return f'add_section("{self._section.title}")'

    def execute(self) -> None:
        if self._section not in self._sections:
            self._sections.append(self._section)

    def undo(self) -> None:
        if self._section in self._sections:
            self._sections.remove(self._section)


class RemoveSectionCmd(Command):
    """섹션 리스트에서 Section 제거 (undo: 원래 위치에 복원)."""

    def __init__(self, sections: list[Section], section: Section) -> None:
        self._sections = sections
        self._section = section
        self._index: int = -1

    @property
    def description(self) -> str:
        return f"섹션 '{self._section.title}' 제거"

    @property
    def script_repr(self) -> str:
        return f'remove_section("{self._section.title}")'

    def execute(self) -> None:
        if self._section in self._sections:
            self._index = self._sections.index(self._section)
            self._sections.remove(self._section)

    def undo(self) -> None:
        if self._section not in self._sections:
            pos = self._index if 0 <= self._index <= len(self._sections) else len(self._sections)
            self._sections.insert(pos, self._section)
