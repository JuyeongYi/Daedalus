# daedalus/view/widgets/combo_widgets.py
from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from daedalus.model.fsm.blackboard import CollectionType
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillShell,
)


class ModelComboBox(QComboBox):
    """모델 선택 콤보박스 — inherit/sonnet/opus/haiku.

    INHERIT 항목을 포함한다 — config의 단일 진실 기본값(ModelType.INHERIT)과
    콤보 항목 집합을 일치시켜, 모델이 INHERIT인데 위젯엔 항목이 없어 'sonnet'으로
    표시되던 로드 괴리를 해소한다.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for m in ModelType:
            self.addItem(m.value)
        self.setCurrentText(ModelType.INHERIT.value)


class EffortComboBox(QComboBox):
    """Effort 레벨 콤보박스 — low/medium/high/max."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for e in EffortLevel:
            self.addItem(e.value)


class ContextComboBox(QComboBox):
    """실행 컨텍스트 콤보박스 — inline/fork."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for c in SkillContext:
            self.addItem(c.value)


class ShellComboBox(QComboBox):
    """셸 선택 콤보박스 — bash/powershell."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for s in SkillShell:
            self.addItem(s.value)


class PermissionModeComboBox(QComboBox):
    """권한 모드 콤보박스 — default/acceptEdits/auto/dontAsk/bypassPermissions/plan."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for p in PermissionMode:
            self.addItem(p.value)
        self.setCurrentText(PermissionMode.DEFAULT.value)


class MemoryScopeComboBox(QComboBox):
    """메모리 스코프 콤보박스 — user/project/local."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for m in MemoryScope:
            self.addItem(m.value)


class AgentIsolationComboBox(QComboBox):
    """에이전트 격리 모드 콤보박스 — none/worktree."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for i in AgentIsolation:
            self.addItem(i.value)
        self.setCurrentText(AgentIsolation.NONE.value)


class AgentColorComboBox(QComboBox):
    """에이전트 색상 콤보박스 — red/blue/green/yellow/purple/orange/pink/cyan."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for c in AgentColor:
            self.addItem(c.value)


class FieldTypeComboBox(QComboBox):
    """블랙보드 필드 타입 콤보박스 — string/int/float/number/bool/list/json/any."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for t in FieldType:
            self.addItem(t.value, t)


class CollectionTypeComboBox(QComboBox):
    """블랙보드 필드 컬렉션 콤보박스 — none/list/set."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for c in CollectionType:
            self.addItem(c.value, c)
