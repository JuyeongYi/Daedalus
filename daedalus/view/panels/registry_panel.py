# daedalus/view/panels/registry_panel.py
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.plugin.kinds import config_kinds_in, spec_for
from daedalus.model.plugin.roles import Bucket
from daedalus.model.project import PluginProject
from daedalus.view.kind_ui import ui_by_config_kind, ui_for

_ROLE_COMPONENT = Qt.ItemDataRole.UserRole + 1
_ROLE_PLACED = Qt.ItemDataRole.UserRole + 2
_COLOR_PLACED = QColor("#445544")
_COLOR_NO_PLACE = QColor("#666644")

#: 섹션 키 = config `kind` 어휘. **선언 순서**가 곧 탭 순서다(결정성) — 새 종류는
#: 모델 레지스트리 한 줄 + `KIND_UI` 한 행이면 팔레트에 나타난다(V1~V4 소멸).
_SECTION_KINDS: tuple[str, ...] = (
    config_kinds_in(Bucket.SKILLS) + config_kinds_in(Bucket.AGENTS)
)


class _DraggableList(QListWidget):
    """배치된 항목은 드래그 불가인 목록 위젯."""

    def startDrag(self, supported_actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None or item.data(_ROLE_PLACED):
            return
        component = item.data(_ROLE_COMPONENT)
        if component is None:
            return
        drag_text = component.name
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(drag_text)
        drag.setMimeData(mime)
        _run_drag = getattr(drag, "exec")
        _run_drag(Qt.DropAction.CopyAction)


class _RegistrySection(QWidget):
    """레이블 + 리스트 + "+" 버튼을 묶은 레지스트리 섹션."""

    add_requested = Signal()
    item_double_clicked = Signal(object)
    delete_requested = Signal(object)  # component
    preview_requested = Signal(object)  # component — 컴파일 미리보기 (A9-1)

    def __init__(
        self,
        label: str,
        color: QColor,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self.label_text = label  # RegistryPanel이 탭 툴팁으로 재사용

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(2)
        hdr.addWidget(QLabel(label))
        hdr.addStretch()
        btn = QPushButton("+")
        btn.setFixedSize(20, 20)
        btn.clicked.connect(self.add_requested)
        hdr.addWidget(btn)
        lay.addLayout(hdr)

        self._list = _DraggableList()
        self._list.setDragEnabled(True)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._list.setMinimumHeight(30)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.doubleClicked.connect(self._on_double_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self._list)

    def clear(self) -> None:
        self._list.clear()

    def add_item(self, component: object, placed: bool) -> None:
        from daedalus.model.plugin.placement import is_canvas_placeable

        icon = ui_for(component).icon
        name = getattr(component, "name", str(component))
        # 캔버스에 놓이는가는 **항목마다** 묻는다(양성 판정 단일 진실) — 섹션
        # 단위 플래그를 따로 두면 같은 사실의 출처가 둘이 된다(스멜 ②).
        no_place = not is_canvas_placeable(component)

        label = f"{icon} {name}"
        item = QListWidgetItem(label)
        item.setData(_ROLE_COMPONENT, component)
        item.setData(_ROLE_PLACED, placed)

        if no_place:
            item.setForeground(_COLOR_NO_PLACE)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        elif placed:
            item.setForeground(_COLOR_PLACED)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
        else:
            item.setForeground(self._color)
        self._list.addItem(item)

    def _on_double_click(self, index) -> None:
        item = self._list.itemFromIndex(index)
        if item:
            comp = item.data(_ROLE_COMPONENT)
            if comp is not None:
                self.item_double_clicked.emit(comp)

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        comp = item.data(_ROLE_COMPONENT)
        if comp is None:
            return
        menu = QMenu(self)
        # 트랜스퍼 스킬은 캔버스 노드가 아니라 엣지에 붙어 placement 우클릭
        # 메뉴가 닿지 않는다(사용자 보고) — 레지스트리가 전 컴포넌트 공통의
        # 미리보기 진입점이다.
        preview_action = menu.addAction("컴파일 미리보기…")
        if preview_action is not None:
            from daedalus.compiler.preview import can_preview

            # 산출 자리가 없는 종류만 비활성(compiler/preview.py).
            preview_action.setEnabled(can_preview(comp))
            if not can_preview(comp):
                preview_action.setToolTip(
                    "이 종류는 산출 파일이 없어 미리볼 것이 없습니다."
                )
            preview_action.triggered.connect(lambda: self.preview_requested.emit(comp))
        delete_action = menu.addAction("삭제")
        if delete_action is not None:
            delete_action.triggered.connect(
                lambda: self.delete_requested.emit(comp)
            )
        menu.exec(self._list.mapToGlobal(pos))


class RegistryPanel(QWidget):
    """스킬/에이전트 레지스트리 팔레트."""

    component_double_clicked = Signal(object)
    new_component_requested = Signal(str)  # kind: "procedural"|"declarative"|"transfer"|"agent"
    component_delete_requested = Signal(object)  # component
    component_preview_requested = Signal(object)  # component — 컴파일 미리보기

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project: PluginProject | None = None
        self._placed_ids: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._sections: dict[str, _RegistrySection] = {
            kind: _RegistrySection(
                ui_by_config_kind(kind).section_label,
                ui_by_config_kind(kind).section_color,
            )
            for kind in _SECTION_KINDS
        }
        # 종류별 세로 스택 대신 **탭**으로 담는다 (사용자 확정 — 좌측 열을
        # 컴팩트하게 만들어 파일 독을 아래에 두고 에디터가 공간을 가져간다).
        # 탭 라벨은 짧게, 전체 이름은 툴팁으로.
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        for kind, section in self._sections.items():
            section.add_requested.connect(lambda k=kind: self.new_component_requested.emit(k))
            section.item_double_clicked.connect(self.component_double_clicked)
            section.delete_requested.connect(self.component_delete_requested)
            section.preview_requested.connect(self.component_preview_requested)
            idx = self._tabs.addTab(section, ui_by_config_kind(kind).tab_label)
            self._tabs.setTabToolTip(idx, section.label_text)
        layout.addWidget(self._tabs)

    def set_project(self, project: PluginProject) -> None:
        self._project = project
        self._rebuild()

    def set_placed_ids(self, placed_ids: set[int]) -> None:
        self._placed_ids = placed_ids
        self._rebuild()

    def _rebuild(self) -> None:
        for section in self._sections.values():
            section.clear()
        if self._project is None:
            return
        # **순서 민감한 isinstance 사다리가 있던 자리다**(V4) — 서브클래스가 먼저
        # 매치돼야 해서 AsyncForkSkill을 앞에 두어야 했고, 새 종류는
        # 어느 분기에도 걸리지 않아 **조용히 레지스트리에서 사라졌다**. 이제
        # 종류 선언이 자기 섹션을 답한다(`spec_for(c).config_kind`).
        # 배치 여부는 항목마다 묻는다 — 캔버스에 놓이지 않는 종류는 애초에
        # `_placed_ids`(상태 노드의 skill_ref)에 들어가지 않는다.
        for component in list(self._project.skills) + list(self._project.agents):
            key = spec_for(component).config_kind
            self._sections[key].add_item(
                component, id(component) in self._placed_ids
            )
