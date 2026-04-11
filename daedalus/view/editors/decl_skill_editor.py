from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from daedalus.model.plugin.skill import DeclarativeSkill


class DeclSkillEditor(QWidget):
    """DeclarativeSkill 폼 에디터 — A단계 placeholder."""

    def __init__(self, skill: DeclarativeSkill, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch()
        label = QLabel(f"{skill.name}\n\n편집 기능 준비 중")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(label)
        layout.addStretch()
