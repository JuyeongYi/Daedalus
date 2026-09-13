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


class ForkAgentComboBox(QComboBox):
    """fork 에이전트 — 내장 / 사용 선언 외부 / 캔버스 미배치 프로젝트 에이전트.

    후보는 생성 시점에 제공자(`tag_input.get_fork_agent_choices`)에서 읽는다 —
    값 적용이 후보 연결보다 먼저라 생성자에서 채워야 저장된 값이 선택된다.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import Qt

        from daedalus.view.widgets.tag_input import get_fork_agent_choices

        for value, note in get_fork_agent_choices():
            self.addItem(value)
            self.setItemData(self.count() - 1, note, Qt.ItemDataRole.ToolTipRole)

    def add_unlisted(self, value: str) -> int:
        """후보에 없는 저장값을 보이게 하고 그 인덱스를 돌려준다 — 안 보이면 무엇이
        걸려 있는지 모른다."""
        from PySide6.QtCore import Qt

        self.addItem(value)
        index = self.count() - 1
        self.setItemData(
            index, "고를 수 있는 목록에 없음 — 검증 결과를 확인하세요",
            Qt.ItemDataRole.ToolTipRole,
        )
        return index


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
