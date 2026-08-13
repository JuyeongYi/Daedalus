"""범용 속성/리스트 편집 커맨드 (WP-CE).

폼 편집(프론트매터 필드, transfer_on, entry_paths, 전이 트리거, 상태 reads/writes,
블랙보드 클래스…)은 지금까지 모델에 직접 쓰여서 Ctrl+Z가 듣지 않았고, 그래서 MCP
표면에도 올릴 수 없었다(AI 편집만 되돌릴 수 없는 비대칭이 생긴다).

편집 대상이 워낙 다양해서 편집마다 커맨드 클래스를 만드는 대신, **속성 하나를
바꾸는 것**과 **리스트에 넣고 빼는 것** 두 가지로 환원한다. 대부분의 폼 편집이
이 둘로 표현된다.

값은 얕은 복사조차 하지 않는다 — 호출자가 새 객체를 만들어 넘기는 것을 전제로
한다(리스트를 제자리에서 바꿔치기하면 old/new가 같은 객체가 되어 undo가 죽는다).
"""
from __future__ import annotations

from typing import Any

from daedalus.view.commands.base import Command

_UNSET = object()


class SetAttrCmd(Command):
    """객체의 속성 하나를 바꾼다.

    ``label``은 히스토리 패널에 보일 문구다 — 무엇이 바뀌었는지 사람이 읽고
    알아볼 수 있어야 하므로 호출자가 대상 이름을 담아 넘긴다.
    """

    def __init__(
        self,
        target: Any,
        attr: str,
        new_value: Any,
        label: str = "",
        script: str = "",
    ) -> None:
        self._target = target
        self._attr = attr
        self._new = new_value
        self._old: Any = _UNSET
        self._label = label or f"{attr} 변경"
        self._script = script

    @property
    def description(self) -> str:
        return self._label

    @property
    def script_repr(self) -> str:
        return self._script or f"set_attr({self._attr!r}, ...)"

    def execute(self) -> None:
        # 최초 실행 때만 이전 값을 잡는다 — redo가 old를 덮어쓰면 undo가 깨진다.
        if self._old is _UNSET:
            self._old = getattr(self._target, self._attr, None)
        setattr(self._target, self._attr, self._new)

    def undo(self) -> None:
        if self._old is not _UNSET:
            setattr(self._target, self._attr, self._old)


class AppendToListCmd(Command):
    """리스트 끝에 항목을 추가한다(블랙보드 클래스, 훅 정의 등)."""

    def __init__(self, container: list, item: Any, label: str = "", script: str = "") -> None:
        self._container = container
        self._item = item
        self._label = label or "항목 추가"
        self._script = script

    @property
    def description(self) -> str:
        return self._label

    @property
    def script_repr(self) -> str:
        return self._script or "append(...)"

    def execute(self) -> None:
        if not any(x is self._item for x in self._container):
            self._container.append(self._item)

    def undo(self) -> None:
        for i, existing in enumerate(self._container):
            if existing is self._item:
                del self._container[i]
                break


class RemoveFromListCmd(Command):
    """리스트에서 항목을 뺀다 — undo 시 **원래 위치로** 되돌린다."""

    def __init__(self, container: list, item: Any, label: str = "", script: str = "") -> None:
        self._container = container
        self._item = item
        self._index = -1
        self._label = label or "항목 제거"
        self._script = script

    @property
    def description(self) -> str:
        return self._label

    @property
    def script_repr(self) -> str:
        return self._script or "remove(...)"

    def execute(self) -> None:
        for i, existing in enumerate(self._container):
            if existing is self._item:
                self._index = i
                del self._container[i]
                break

    def undo(self) -> None:
        if self._index < 0:
            return
        index = min(self._index, len(self._container))
        self._container.insert(index, self._item)
