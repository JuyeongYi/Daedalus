# daedalus/view/editors/blackboard_editor.py
"""블랙보드(BlackboardPanel) 편집 탭 — 프로젝트 최상위 블랙보드 class_definitions 편집.

진입점: MainWindow 상주 탭(인덱스 1, 항상 존재 — 닫기 불가).
편집 결과는 모델(project.blackboard.class_definitions)에 직접 기록 + notify
(undo 커맨드화 범위 외 — hook_panel.HookLibraryPanel 폼 정책과 동일).
편집 중 위젯 파괴 금지 — 리스트/테이블 재구성은 구조 변경(클래스·필드 추가/삭제)
시에만 일어나고, 텍스트 키스트로크는 in-place 반영이다.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.blackboard import (
    BLACKBOARD_FIELD_TYPES,
    CollectionType,
    DynamicClass,
    DynamicField,
)
from daedalus.model.fsm.variable import FieldType
from daedalus.model.project import PluginProject, blackboard_rename_ref_updates
from daedalus.view.widgets.combo_widgets import CollectionTypeComboBox, FieldTypeComboBox

_FIELD_COLS = ("이름", "타입", "컬렉션", "필수", "기본값")


def blackboard_candidate_strings(project: PluginProject | None) -> list[str]:
    """프로젝트 최상위 블랙보드에서 "클래스" + "클래스.필드" 후보 문자열 전체를 만든다
    (WP-BB Part C-1 — 상태 reads/writes TagInput 자동완성 후보)."""
    if project is None:
        return []
    result: list[str] = []
    for cls in project.blackboard.class_definitions:
        result.append(cls.name)
        for fld in cls.fields:
            result.append(f"{cls.name}.{fld.name}")
    return result


class BlackboardPanel(QWidget):
    """프로젝트 최상위 블랙보드(class_definitions) 편집 상주 탭.

    좌: 클래스 목록(＋/삭제, 더블클릭 이름 변경). 우: 선택 클래스의 description +
    필드 테이블(name/FieldType/CollectionType/required/default, ＋필드/필드 삭제).
    """

    def __init__(
        self,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._on_notify_fn = on_notify_fn
        self._loading = False

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        # ── 좌측: 클래스 목록 + 버튼 ──
        left = QVBoxLayout()
        left.addWidget(QLabel("블랙보드 클래스:"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_rename_class)
        left.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ 클래스")
        add_btn.clicked.connect(self._add_class)
        del_btn = QPushButton("✕ 삭제")
        del_btn.clicked.connect(self._delete_class)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)
        body.addLayout(left, 1)

        # ── 우측: 선택 클래스 편집 ──
        right = QVBoxLayout()
        right.addWidget(QLabel("설명:"))
        self._desc_edit = QLineEdit()
        self._desc_edit.textChanged.connect(self._on_desc_changed)
        right.addWidget(self._desc_edit)

        right.addWidget(QLabel("필드:"))
        self._table = QTableWidget(0, len(_FIELD_COLS))
        self._table.setHorizontalHeaderLabels(_FIELD_COLS)
        header = self._table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
        self._table.itemChanged.connect(self._on_table_item_changed)
        right.addWidget(self._table, 1)

        field_btn_row = QHBoxLayout()
        add_field_btn = QPushButton("＋ 필드")
        add_field_btn.clicked.connect(self._add_field)
        del_field_btn = QPushButton("필드 삭제")
        del_field_btn.clicked.connect(self._delete_field)
        field_btn_row.addWidget(add_field_btn)
        field_btn_row.addWidget(del_field_btn)
        right.addLayout(field_btn_row)

        body.addLayout(right, 2)

        self.setEnabled(False)

    # ── 프로젝트 배선 ──

    def set_project(self, project: PluginProject | None) -> None:
        """프로젝트 교체 시 재바인딩 — 클래스 목록을 새로 로드한다."""
        self._project = project
        self.setEnabled(project is not None)
        self._reload_list()

    # ── 클래스 목록 ──

    def _classes(self) -> list[DynamicClass]:
        if self._project is None:
            return []
        return self._project.blackboard.class_definitions

    def _reload_list(self, select_index: int | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for cls in self._classes():
            self._list.addItem(QListWidgetItem(cls.name or "(이름 없음)"))
        self._list.blockSignals(False)
        if select_index is not None and 0 <= select_index < self._list.count():
            self._list.setCurrentRow(select_index)
        elif self._list.count() and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)
        else:
            self._on_row_changed(self._list.currentRow())

    def _current_class(self) -> DynamicClass | None:
        row = self._list.currentRow()
        classes = self._classes()
        if 0 <= row < len(classes):
            return classes[row]
        return None

    def _on_row_changed(self, row: int) -> None:
        cls = self._current_class()
        self._loading = True
        try:
            self._desc_edit.setEnabled(cls is not None)
            desc = cls.description if cls is not None else ""
            # 같은 값이어도 setText는 커서를 처음으로 되돌린다 — 외부 notify가
            # 이 경로를 타고 들어올 수 있으므로 달라졌을 때만 쓴다.
            if self._desc_edit.text() != desc:
                self._desc_edit.setText(desc)
        finally:
            self._loading = False
        self._reload_table()

    def _add_class(self) -> None:
        if self._project is None:
            return
        classes = self._classes()
        base = "NewClass"
        name = base
        counter = 2
        existing = {c.name for c in classes}
        while name in existing:
            name = f"{base}{counter}"
            counter += 1
        classes.append(DynamicClass(name=name, description=""))
        self._reload_list(select_index=len(classes) - 1)
        self._notify()

    def _delete_class(self) -> None:
        row = self._list.currentRow()
        classes = self._classes()
        if 0 <= row < len(classes):
            classes.pop(row)
            self._reload_list(select_index=min(row, len(classes) - 1) if classes else None)
            self._notify()

    def _on_rename_class(self, item: QListWidgetItem) -> None:
        cls = self._current_class()
        if cls is None or self._project is None:
            return
        name, ok = QInputDialog.getText(self, "클래스 이름 변경", "이름:", text=cls.name)
        if not ok or not name.strip():
            return
        old_name = cls.name
        new_name = name.strip()
        # 개명은 참조를 따라간다 — 계산은 모델(blackboard_rename_ref_updates)이
        # 하고 여기서는 대입만 한다(MCP update_blackboard_class와 같은 판정).
        updates = blackboard_rename_ref_updates(self._project, old_name, new_name)
        cls.name = new_name
        for state, attr, renamed in updates:
            setattr(state, attr, renamed)
        self._reload_list(select_index=self._list.currentRow())
        self._notify()

    def _on_desc_changed(self, text: str) -> None:
        if self._loading:
            return
        cls = self._current_class()
        if cls is None:
            return
        cls.description = text
        self._notify()

    # ── 필드 테이블 ──

    def _reload_table(self) -> None:
        cls = self._current_class()
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        if cls is not None:
            for fld in cls.fields:
                self._append_field_row(fld)
        self._table.blockSignals(False)
        self._table.setEnabled(cls is not None)

    def _append_field_row(self, fld: DynamicField) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        name_item = QTableWidgetItem(fld.name)
        self._table.setItem(row, 0, name_item)

        # 블랙보드 필드는 스칼라 원소 타입만 (WP-BT) — 컨테이너 형상은 컬렉션
        # 콤보가 전담. 구버전 파일의 legacy 타입은 "(legacy)" 항목으로 표시 유지.
        type_combo = FieldTypeComboBox(members=BLACKBOARD_FIELD_TYPES)
        type_combo.ensure_member(fld.field_type)
        idx = type_combo.findData(fld.field_type)
        if idx >= 0:
            type_combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, 1, type_combo)

        coll_combo = CollectionTypeComboBox()
        idx = coll_combo.findData(fld.collection)
        if idx >= 0:
            coll_combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, 2, coll_combo)

        req_check = QCheckBox()
        req_check.setChecked(fld.required)
        self._table.setCellWidget(row, 3, req_check)

        default_item = QTableWidgetItem("" if fld.default is None else str(fld.default))
        self._table.setItem(row, 4, default_item)

        type_combo.currentIndexChanged.connect(lambda _i, r=row: self._write_field_widgets(r))
        coll_combo.currentIndexChanged.connect(lambda _i, r=row: self._write_field_widgets(r))
        req_check.toggled.connect(lambda _c, r=row: self._write_field_widgets(r))

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """name/default 셀(QTableWidgetItem) 텍스트 편집 — 테이블 재구성 시에는
        blockSignals로 억제되므로 실제 사용자 입력에서만 호출된다."""
        self._write_field_widgets(item.row())

    def _write_field_widgets(self, row: int) -> None:
        cls = self._current_class()
        if cls is None or not (0 <= row < len(cls.fields)):
            return
        fld = cls.fields[row]
        name_item = self._table.item(row, 0)
        default_item = self._table.item(row, 4)
        type_combo = self._table.cellWidget(row, 1)
        coll_combo = self._table.cellWidget(row, 2)
        req_check = self._table.cellWidget(row, 3)

        if name_item is not None:
            fld.name = name_item.text().strip()
        if isinstance(type_combo, FieldTypeComboBox):
            data = type_combo.currentData()
            if isinstance(data, FieldType):
                fld.field_type = data
        if isinstance(coll_combo, CollectionTypeComboBox):
            data = coll_combo.currentData()
            if isinstance(data, CollectionType):
                fld.collection = data
        if isinstance(req_check, QCheckBox):
            fld.required = req_check.isChecked()
        if default_item is not None:
            text = default_item.text()
            fld.default = text if text != "" else None
        self._notify()

    def _add_field(self) -> None:
        cls = self._current_class()
        if cls is None:
            return
        base = "field"
        name = base
        counter = 2
        existing = {f.name for f in cls.fields}
        while name in existing:
            name = f"{base}{counter}"
            counter += 1
        cls.fields.append(DynamicField(name=name, field_type=FieldType.STRING))
        self._reload_table()
        self._notify()

    def _delete_field(self) -> None:
        cls = self._current_class()
        if cls is None:
            return
        row = self._table.currentRow()
        if 0 <= row < len(cls.fields):
            cls.fields.pop(row)
            self._reload_table()
            self._notify()

    # ── notify ──

    def _notify(self) -> None:
        if self._on_notify_fn is not None:
            self._self_notify = True
            try:
                self._on_notify_fn()
            finally:
                self._self_notify = False

    def refresh_external(self) -> None:
        """바깥(MCP 블랙보드 도구 등)의 변경을 목록·설명·필드 테이블에 반영한다.

        hook_panel.refresh_external과 같은 패턴 — 자기 편집이 발화한 notify가
        되돌아온 경우는 건너뛴다(타이핑 중인 폼의 선택 리셋 방지).

        **목록만 다시 그리면 부족하다**: 같은 행이 계속 선택돼 있으면
        `setCurrentRow`가 시그널을 내지 않아 `_on_row_changed`가 돌지 않고,
        MCP가 고친 설명·필드가 화면에 반영되지 않는다. 그래서 목록을 새로 그린
        뒤 현재 행을 명시적으로 다시 로드한다.
        """
        if getattr(self, "_self_notify", False):
            return
        current = self._list.currentRow()
        self._reload_list(select_index=current if current >= 0 else None)
        self._on_row_changed(self._list.currentRow())
