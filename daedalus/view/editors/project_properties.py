# daedalus/view/editors/project_properties.py
"""프로젝트 속성(이름/설명/버전) 편집 다이얼로그.

파일 메뉴 "프로젝트 속성…"에서 연다. 이름 규약 검사는 여기서 막지 않는다 —
편집 중에는 자유, F7 경고 / 컴파일 게이트가 잡는다(WP-T A-5).

테스트 편의를 위해 QDialog.exec 없이도 위젯 값 → apply_to(project) 경로를
직접 검증할 수 있도록, 위젯 초기값 세팅과 대입 로직을 각각 별도 메서드로 둔다.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.project import PluginProject


class ProjectPropertiesDialog(QDialog):
    """프로젝트 name/description/version 편집 다이얼로그."""

    def __init__(
        self,
        project: PluginProject,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("프로젝트 속성")

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self._name_edit = QLineEdit(project.name)
        form.addRow("이름:", self._name_edit)

        self._description_edit = QLineEdit(project.description)
        form.addRow("설명:", self._description_edit)

        self._version_edit = QLineEdit(project.version)
        form.addRow("버전:", self._version_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def apply_to(self, project: PluginProject) -> None:
        """현재 위젯 값을 project에 대입한다 (이름 규약 검사 없음 — 편집 중 자유)."""
        project.name = self._name_edit.text()
        project.description = self._description_edit.text()
        project.version = self._version_edit.text()
