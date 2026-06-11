# daedalus/view/widgets/combo_widgets.py
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell


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
