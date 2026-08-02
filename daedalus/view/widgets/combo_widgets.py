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
    """필드 타입 콤보박스.

    members가 주어지면 그 부분집합만 노출한다 — 블랙보드 필드는 스칼라 원소
    타입만 허용(BLACKBOARD_FIELD_TYPES, 컨테이너 형상은 CollectionType 전담 —
    type=list × collection=list 같은 무의미 조합 차단).
    `ensure_member(t)`는 목록에 없는 기존 값(구버전 파일의 legacy 타입)을
    "(legacy)" 표기로 임시 추가해, 다른 칸 편집이 타입을 몰래 바꾸지 않게 한다.
    """

    def __init__(self, parent=None, members: tuple[FieldType, ...] | None = None) -> None:
        super().__init__(parent)
        for t in (members if members is not None else tuple(FieldType)):
            self.addItem(t.value, t)

    def ensure_member(self, t: FieldType) -> None:
        for i in range(self.count()):
            if self.itemData(i) is t:
                return
        self.addItem(f"{t.value} (legacy)", t)


class CollectionTypeComboBox(QComboBox):
    """블랙보드 필드 컬렉션 콤보박스 — none/list/set."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for c in CollectionType:
            self.addItem(c.value, c)
