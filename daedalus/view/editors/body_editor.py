"""공용 섹션 편집 위젯 — SectionTree, BreadcrumbNav, SectionContentPanel, VariablePopup."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLabel,
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
