# daedalus/view/editors/new_project_dialog.py
"""새 프로젝트 통합 다이얼로그 — 출발점(빈 프로젝트|템플릿) + 빌드 타깃 (사용자 확정).

Ctrl+N 한 흐름에서 두 가지를 **같이** 고른다. 시작 템플릿의 초기 구현은 그것을 File
메뉴 별도 항목으로 뒀지만("템플릿은 자기 타깃을 선언하므로 충돌"), 사용자
확정으로 통합됐다 — 충돌은 규칙 하나로 푼다: **생성 시 고른 타깃이 템플릿에
저장된 타깃을 항상 이긴다**(템플릿 내용은 타깃 중립, 타깃은 사용자 소유).
취소는 한 겹이고 의미는 기존 그대로다 — 취소 = 생성 취소.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.enums import BuildTarget
from daedalus.view.editors.project_properties import BUILD_TARGET_LABELS

_EMPTY_LABEL = "빈 프로젝트 — 빈 캔버스에서 시작"


class NewProjectDialog(QDialog):
    """출발점 목록(0행=빈 프로젝트, 이후 템플릿) + 빌드 타깃 콤보."""

    def __init__(self, parent: QWidget | None = None, catalogue=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("새 프로젝트")
        self.setMinimumWidth(460)

        if catalogue is None:
            from daedalus.model import templates

            catalogue = templates.list_templates()
        self._catalogue = list(catalogue)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("출발점:"))
        self._list = QListWidget()
        self._list.addItem(QListWidgetItem(_EMPTY_LABEL))
        for t in self._catalogue:
            self._list.addItem(QListWidgetItem(f"{t.title} — {t.summary}"))
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        lay.addWidget(self._list, 1)

        lay.addWidget(QLabel("빌드 타깃:"))
        self._target = QComboBox()
        for _t, label in BUILD_TARGET_LABELS:
            self._target.addItem(label)
        self._target.setToolTip(
            "템플릿을 골라도 타깃은 여기서 정한 값이 적용됩니다 — "
            "템플릿에 저장된 타깃보다 우선합니다."
        )
        lay.addWidget(self._target)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def template_id(self) -> str | None:
        """선택한 템플릿 id — 빈 프로젝트면 None."""
        row = self._list.currentRow()
        if row <= 0:
            return None
        return self._catalogue[row - 1].id

    def build_target(self) -> BuildTarget:
        index = self._target.currentIndex()
        if 0 <= index < len(BUILD_TARGET_LABELS):
            return BUILD_TARGET_LABELS[index][0]
        return BuildTarget.MARKETPLACE
