# daedalus/view/panels/validation_panel.py
"""ValidationPanel — 프로젝트 검증 결과를 표시하는 도킹 패널."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.validation import ValidationError

_COLOR_ERROR = QColor("#ff5555")
_COLOR_WARNING = QColor("#ffaa33")

_ICON_ERROR = "✖"
_ICON_WARNING = "⚠"

# 열 인덱스
_COL_SEVERITY = 0
_COL_RULE = 1
_COL_MESSAGE = 2
_COL_PATH = 3
_COL_COUNT = 4


class ValidationPanel(QWidget):
    """검증 오류/경고 목록 패널.

    - 에러를 경고보다 먼저 표시.
    - 행 더블클릭 시 ``on_item_activated`` 콜백에 ``ValidationError`` 전달.
    """

    def __init__(
        self,
        on_item_activated: Callable[[ValidationError], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_item_activated = on_item_activated
        self._errors: list[ValidationError] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._summary_label = QLabel("검증을 실행하려면 F7을 누르세요.")
        self._summary_label.setStyleSheet("padding: 4px; color: #aaa;")
        layout.addWidget(self._summary_label)

        self._table = QTableWidget(0, _COL_COUNT)
        self._table.setHorizontalHeaderLabels(["심각도", "규칙", "메시지", "경로"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def set_errors(self, errors: list[ValidationError]) -> None:
        """검증 결과를 설정하고 테이블을 갱신한다.

        에러를 경고보다 먼저 표시(에러=False < 경고=True 순으로 정렬).
        """
        self._errors = list(errors)
        # 에러 먼저, 그 다음 경고
        sorted_errors = sorted(self._errors, key=lambda e: e.is_warning)

        self._table.setRowCount(0)
        for row_idx, err in enumerate(sorted_errors):
            self._table.insertRow(row_idx)
            self._set_row(row_idx, err)

        error_count = sum(1 for e in self._errors if not e.is_warning)
        warning_count = sum(1 for e in self._errors if e.is_warning)

        if not self._errors:
            self._summary_label.setText("문제 없음")
            self._summary_label.setStyleSheet("padding: 4px; color: #88cc88;")
        else:
            self._summary_label.setText(
                f"검증: 오류 {error_count} / 경고 {warning_count}"
            )
            color = "#ff5555" if error_count > 0 else "#ffaa33"
            self._summary_label.setStyleSheet(f"padding: 4px; color: {color};")

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _set_row(self, row: int, err: ValidationError) -> None:
        is_warn = err.is_warning
        icon = _ICON_WARNING if is_warn else _ICON_ERROR
        fg = _COLOR_WARNING if is_warn else _COLOR_ERROR

        sev_item = QTableWidgetItem(icon)
        sev_item.setForeground(fg)
        sev_item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
        sev_item.setData(Qt.ItemDataRole.UserRole, err)
        self._table.setItem(row, _COL_SEVERITY, sev_item)

        rule_item = QTableWidgetItem(err.rule)
        rule_item.setForeground(fg)
        self._table.setItem(row, _COL_RULE, rule_item)

        msg_item = QTableWidgetItem(err.message)
        self._table.setItem(row, _COL_MESSAGE, msg_item)

        path_str = " > ".join(err.path) if err.path else ""
        path_item = QTableWidgetItem(path_str)
        path_item.setForeground(QColor("#888"))
        self._table.setItem(row, _COL_PATH, path_item)

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        sev_item = self._table.item(row, _COL_SEVERITY)
        if sev_item is None:
            return
        err: ValidationError | None = sev_item.data(Qt.ItemDataRole.UserRole)
        if err is not None and self._on_item_activated is not None:
            self._on_item_activated(err)
