"""공용 섹션 편집 위젯 — SectionTree, BreadcrumbNav, SectionContentPanel, VariablePopup."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import Section

MAX_DEPTH = 3  # 0-indexed; 4 levels total (H1–H4)


def find_path(target: Section, roots: list[Section]) -> list[Section] | None:
    """루트부터 target까지의 조상 경로를 반환. 못 찾으면 None."""
    for root in roots:
        result = _search(target, root, [])
        if result is not None:
            return result
    return None


def _search(
    target: Section, current: Section, ancestors: list[Section],
) -> list[Section] | None:
    path = ancestors + [current]
    if current is target:
        return path
    for child in current.children:
        result = _search(target, child, path)
        if result is not None:
            return result
    return None


def section_depth(target: Section, roots: list[Section]) -> int:
    """target의 깊이 (루트=0). 못 찾으면 -1."""
    path = find_path(target, roots)
    return len(path) - 1 if path is not None else -1


_ROLE_SECTION = Qt.ItemDataRole.UserRole


class SectionTree(QWidget):
    """섹션 트리 — 전체 구조를 한눈에 보여주는 사이드바 위젯."""

    section_selected = pyqtSignal(object, list)  # (Section, path: list[str])
    structure_changed = pyqtSignal()
    add_root_requested = pyqtSignal()

    def __init__(self, sections: list[Section], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sections = sections
        self.setMinimumWidth(100)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(4)

        hdr = QLabel("Sections")
        lay.addWidget(hdr)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._tree, 1)

        add_btn = QPushButton("＋ 섹션 추가")
        add_btn.clicked.connect(self.add_root_requested.emit)
        lay.addWidget(add_btn)

        self._rebuild()

    def tree_widget(self) -> QTreeWidget:
        return self._tree

    def set_sections(self, sections: list[Section]) -> None:
        self._sections = sections
        self._rebuild()

    def select_section(self, target: Section) -> None:
        item = self._find_item(target)
        if item is not None:
            self._tree.setCurrentItem(item)

    def add_sibling(self, after: Section) -> None:
        path = find_path(after, self._sections)
        if path is None:
            return
        new = Section(title="새 섹션")
        if len(path) == 1:
            idx = self._sections.index(after)
            self._sections.insert(idx + 1, new)
        else:
            parent = path[-2]
            idx = parent.children.index(after)
            parent.children.insert(idx + 1, new)
        self._rebuild()
        self.structure_changed.emit()

    def add_child(self, parent: Section) -> None:
        depth = section_depth(parent, self._sections)
        if depth < 0 or depth >= MAX_DEPTH:
            return
        child = Section(title="새 하위 섹션")
        parent.children.append(child)
        self._rebuild()
        self.structure_changed.emit()

    def delete_section(self, target: Section) -> None:
        path = find_path(target, self._sections)
        if path is None:
            return
        if len(path) == 1:
            if target in self._sections:
                self._sections.remove(target)
        else:
            parent = path[-2]
            if target in parent.children:
                parent.children.remove(target)
        self._rebuild()
        self.structure_changed.emit()

    def _rebuild(self) -> None:
        self._tree.clear()
        for section in self._sections:
            item = self._make_item(section)
            self._tree.addTopLevelItem(item)
            self._populate_children(item, section)
        self._tree.expandAll()

    def _make_item(self, section: Section) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, section.title)
        item.setData(0, _ROLE_SECTION, section)
        return item

    def _populate_children(self, parent_item: QTreeWidgetItem, section: Section) -> None:
        for child in section.children:
            child_item = self._make_item(child)
            parent_item.addChild(child_item)
            self._populate_children(child_item, child)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        section: Section | None = item.data(0, _ROLE_SECTION)
        if section is None:
            return
        path = find_path(section, self._sections)
        if path is not None:
            self.section_selected.emit(section, [s.title for s in path])

    def _find_item(
        self, target: Section, parent: QTreeWidgetItem | None = None
    ) -> QTreeWidgetItem | None:
        if parent is None:
            for i in range(self._tree.topLevelItemCount()):
                result = self._find_item(target, self._tree.topLevelItem(i))
                if result is not None:
                    return result
            return None
        if parent.data(0, _ROLE_SECTION) is target:
            return parent
        for i in range(parent.childCount()):
            result = self._find_item(target, parent.child(i))
            if result is not None:
                return result
        return None


class SectionContentPanel(QWidget):
    """섹션 타이틀 + 본문 편집 패널."""

    variable_insert_requested = pyqtSignal()
    content_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section: Section | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- 툴바 ---
        toolbar = QWidget()
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 5, 10, 5)
        tb_lay.setSpacing(6)

        tb_lay.addStretch()
        self._btn_variable = QPushButton("{ } 변수 삽입")
        self._btn_variable.clicked.connect(self.variable_insert_requested)
        tb_lay.addWidget(self._btn_variable)

        lay.addWidget(toolbar)

        # --- 타이틀 인라인 편집 ---
        title_area = QWidget()
        ta_lay = QVBoxLayout(title_area)
        ta_lay.setContentsMargins(12, 8, 12, 4)
        self._w_title = QLineEdit()
        self._w_title.setPlaceholderText("섹션 타이틀")
        self._w_title.editingFinished.connect(self._save_title)
        ta_lay.addWidget(self._w_title)
        lay.addWidget(title_area)

        # --- 본문 텍스트 ---
        self._w_content = QTextEdit()
        self._w_content.textChanged.connect(self._save_content)
        lay.addWidget(self._w_content, 1)

    def current_section(self) -> Section | None:
        return self._section

    def show_section(self, section: Section, path: list[str]) -> None:
        self._section = section
        self._w_title.setText(section.title)
        self._w_content.blockSignals(True)
        self._w_content.setPlainText(section.content)
        self._w_content.blockSignals(False)

    def insert_variable(self, var_name: str) -> None:
        self._w_content.insertPlainText(var_name)

    def _save_title(self) -> None:
        if self._section is not None:
            self._section.title = self._w_title.text().strip() or self._section.title
            self.content_changed.emit()

    def _save_content(self) -> None:
        if self._section is not None:
            self._section.content = self._w_content.toPlainText()
            self.content_changed.emit()


class VariablePopup(QFrame):
    """변수 선택 팝업 — 클릭 시 variable_selected 시그널 방출."""

    variable_selected = pyqtSignal(str)

    def __init__(
        self,
        entries: list,  # list[VariableEntry]
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(300)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(8, 5, 8, 5)
        hdr_lbl = QLabel("변수 선택 — 클릭 시 커서 위치에 삽입")
        hdr_row.addWidget(hdr_lbl)
        hdr_row.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self.hide)
        hdr_row.addWidget(close_btn)
        hdr_widget = QWidget()
        hdr_widget.setLayout(hdr_row)
        lay.addWidget(hdr_widget)

        _SOURCE_LABELS = {
            "builtin": ("기본 제공", "#4477aa"),
            "global":  ("글로벌 (~/.daedalus/variables.yaml)", "#4a7a4a"),
            "project": ("프로젝트 (.daedalus/variables.yaml)", "#7a7a4a"),
        }
        current_source: str | None = None
        for entry in entries:
            if entry.source != current_source:
                current_source = entry.source
                label_text, label_color = _SOURCE_LABELS.get(
                    entry.source, (entry.source, "#446"),
                )
                grp = QLabel(label_text)
                lay.addWidget(grp)
            row = QPushButton()
            row.setText(f"{entry.name}   {entry.description}")
            row.clicked.connect(lambda _c, n=entry.name: self._emit(n))
            lay.addWidget(row)

    def _emit(self, name: str) -> None:
        self.variable_selected.emit(name)
        self.hide()


class BreadcrumbNav(QWidget):
    """브레드크럼브 칩 네비게이션 — 레벨별 형제 섹션을 칩으로 나열."""

    section_selected = pyqtSignal(object, list)        # (Section, path_titles)
    section_add_requested = pyqtSignal(object, int)    # (parent_or_None, depth)
    structure_changed = pyqtSignal()

    def __init__(
        self,
        sections: list[Section],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sections = sections
        self._current: Section | None = None
        self._level_rows: list[QWidget] = []

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 0)
        self._layout.setSpacing(2)

    def set_sections(self, sections: list[Section]) -> None:
        self._sections = sections
        if self._current is not None:
            path = find_path(self._current, self._sections)
            if path is None:
                self._current = None
        self._rebuild()

    def set_current(self, section: Section | None) -> None:
        self._current = section
        self._rebuild()

    def level_count(self) -> int:
        return len(self._level_rows)

    def chip_count(self, level: int) -> int:
        """level번째 행의 섹션 칩 수 (+ 버튼 제외)."""
        if level < 0 or level >= len(self._level_rows):
            return 0
        row = self._level_rows[level]
        return row.property("chip_count") or 0

    def _rebuild(self) -> None:
        for row in self._level_rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._level_rows.clear()

        if self._current is None or not self._sections:
            return

        path = find_path(self._current, self._sections)
        if path is None:
            return

        # Build level info: (siblings_list, parent_section_or_None, depth)
        siblings_at_level: list[tuple[list[Section], Section | None, int]] = []
        # Level 0: root siblings
        siblings_at_level.append((self._sections, None, 0))
        # Level 1..N: children of each ancestor
        for i, node in enumerate(path[:-1]):
            siblings_at_level.append((node.children, node, i + 1))

        for siblings, parent_section, depth in siblings_at_level:
            selected = path[depth] if depth < len(path) else None
            row = self._make_row(siblings, selected, parent_section, depth)
            self._layout.addWidget(row)
            self._level_rows.append(row)

    def _make_row(
        self,
        siblings: list[Section],
        selected: Section | None,
        parent_section: Section | None,
        depth: int,
    ) -> QWidget:
        row = QWidget()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(depth * 12, 0, 0, 0)
        row_lay.setSpacing(4)

        chip_count = 0
        for section in siblings:
            is_selected = section is selected
            has_children = bool(section.children)
            label = section.title
            if is_selected and has_children:
                label += " ▼"

            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(is_selected)
            btn.clicked.connect(
                lambda _c, s=section: self._on_chip_clicked(s),
            )
            row_lay.addWidget(btn)
            chip_count += 1

        row_lay.addStretch()

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.clicked.connect(
            lambda: self.section_add_requested.emit(parent_section, depth),
        )
        row_lay.addWidget(add_btn)

        row.setProperty("chip_count", chip_count)
        return row

    def _on_chip_clicked(self, section: Section) -> None:
        self._current = section
        path = find_path(section, self._sections)
        if path is not None:
            self.section_selected.emit(section, [s.title for s in path])
        self._rebuild()
