# daedalus/view/widgets/combo_widgets.py
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell


class ModelComboBox(QComboBox):
    """모델 선택 콤보박스 — sonnet/opus/haiku."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        for m in ModelType:
            if m != ModelType.INHERIT:
                self.addItem(m.value)
        self.setCurrentText("sonnet")


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
