# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill

_INPUT_STYLE = (
    "background: #1a1a2e; border: 1px solid #446; color: #aac; "
    "padding: 3px 5px; border-radius: 3px; font-size: 9px;"
)
_DARK_BG = "#111120"

# QTreeWidgetItem 커스텀 데이터 롤
_ROLE_SECTION = Qt.ItemDataRole.UserRole
_ROLE_IS_TRANSFER_ON = Qt.ItemDataRole.UserRole + 1  # reserved — TransferOn is a QPushButton, not a tree item

_COLOR_PRESETS = [
    "#4488ff", "#cc3333", "#cc8800", "#44aa44",
    "#aa44cc", "#ccaa00", "#44aacc", "#888888",
]


class _OptionalRow(QWidget):
    """체크박스 ON/OFF로 선택적 프론트매터 필드를 표시/비활성화."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        label: str,
        widget: QWidget,
        initially_enabled: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(3)

        self._cb = QCheckBox()
        self._cb.setChecked(initially_enabled)
        self._cb.setStyleSheet("QCheckBox::indicator { width: 10px; height: 10px; }")
        layout.addWidget(self._cb)

        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 8px; color: #88aaff; min-width: 58px;")
        layout.addWidget(lbl)

        self._widget = widget
        widget.setStyleSheet(_INPUT_STYLE)
        layout.addWidget(widget, 1)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._cb.toggled.connect(self._update_state)
        self._update_state(initially_enabled)

    def _update_state(self, checked: bool) -> None:
        self._widget.setEnabled(checked)
        self._opacity.setOpacity(1.0 if checked else 0.4)
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, checked: bool) -> None:
        self._cb.setChecked(checked)


class _FrontmatterPanel(QScrollArea):
    """좌측 170px 고정 패널 — name/description(필수) + 선택 필드 체크박스."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setFixedWidth(170)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            f"QScrollArea {{ background: {_DARK_BG}; border: none; "
            f"border-right: 1px solid #1a1a33; }}"
        )

        inner = QWidget()
        inner.setStyleSheet(f"background: {_DARK_BG};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        hdr = QLabel("Frontmatter")
        hdr.setStyleSheet(
            "font-size: 8px; color: #446; text-transform: uppercase; "
            "letter-spacing: 1px; margin-bottom: 4px;"
        )
        lay.addWidget(hdr)

        # --- 필수 필드 ---
        lay.addWidget(self._lbl("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.setStyleSheet(_INPUT_STYLE)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        lay.addWidget(self._lbl("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # --- 선택 필드 구분선 ---
        sep = QLabel("선택 필드")
        sep.setStyleSheet(
            "font-size: 8px; color: #446; margin-top: 6px; margin-bottom: 2px;"
        )
        lay.addWidget(sep)

        config = getattr(component, "config", None)

        # model
        self._w_model = QComboBox()
        for e in ModelType:
            self._w_model.addItem(e.value)
        if config is not None:
            mv = config.model.value if isinstance(config.model, ModelType) else str(config.model)
            idx = self._w_model.findText(mv)
            if idx >= 0:
                self._w_model.setCurrentIndex(idx)
        self._row_model = _OptionalRow(
            "model", self._w_model,
            initially_enabled=(config is not None and config.model != ModelType.INHERIT),
        )
        lay.addWidget(self._row_model)

        # effort
        self._w_effort = QComboBox()
        for e in EffortLevel:
            self._w_effort.addItem(e.value)
        if config is not None and config.effort is not None:
            idx = self._w_effort.findText(config.effort.value)
            if idx >= 0:
                self._w_effort.setCurrentIndex(idx)
        self._row_effort = _OptionalRow(
            "effort", self._w_effort,
            initially_enabled=(config is not None and config.effort is not None),
        )
        lay.addWidget(self._row_effort)

        # allowed-tools (SkillConfig 계열)
        if config is not None and hasattr(config, "allowed_tools"):
            self._w_tools = QLineEdit(" ".join(config.allowed_tools))
            self._w_tools.setPlaceholderText("Read Grep WebSearch")
            self._row_tools = _OptionalRow(
                "allowed-tools", self._w_tools,
                initially_enabled=bool(config.allowed_tools),
            )
            lay.addWidget(self._row_tools)

        # ProceduralSkill 전용 필드
        if isinstance(config, ProceduralSkillConfig):
            self._w_context = QComboBox()
            for e in SkillContext:
                self._w_context.addItem(e.value)
            idx = self._w_context.findText(config.context.value)
            if idx >= 0:
                self._w_context.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("context", self._w_context, initially_enabled=True))

            self._w_paths = QLineEdit(" ".join(config.paths) if config.paths else "")
            self._w_paths.setPlaceholderText("src/**/*.py")
            lay.addWidget(
                _OptionalRow(
                    "paths", self._w_paths,
                    initially_enabled=bool(config.paths),
                )
            )

            self._w_shell = QComboBox()
            for e in SkillShell:
                self._w_shell.addItem(e.value)
            idx = self._w_shell.findText(config.shell.value)
            if idx >= 0:
                self._w_shell.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("shell", self._w_shell, initially_enabled=True))

            self._w_disable_model = QCheckBox("disable-model-invocation")
            self._w_disable_model.setChecked(config.disable_model_invocation)
            self._w_disable_model.setStyleSheet("color: #88aaff; font-size: 8px;")
            lay.addWidget(self._w_disable_model)

            self._w_user_invocable = QCheckBox("user-invocable")
            self._w_user_invocable.setChecked(config.user_invocable)
            self._w_user_invocable.setStyleSheet("color: #88aaff; font-size: 8px;")
            lay.addWidget(self._w_user_invocable)

        # argument-hint (ProceduralSkill + DeclarativeSkill)
        if config is not None and hasattr(config, "argument_hint"):
            self._w_hint = QLineEdit(config.argument_hint or "")
            self._w_hint.setPlaceholderText("[topic]")
            self._row_hint = _OptionalRow(
                "argument-hint", self._w_hint,
                initially_enabled=bool(config.argument_hint),
            )
            lay.addWidget(self._row_hint)

        lay.addStretch()
        self.setWidget(inner)

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 8px; color: #88aaff;")
        return lbl

    def _save_name(self) -> None:
        self._component.name = self._w_name.text().strip()
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        self.changed.emit()


def _section_depth(item: QTreeWidgetItem) -> int:
    """QTreeWidgetItem의 트리 깊이 (루트=0)."""
    depth = 0
    parent = item.parent()
    while parent is not None:
        depth += 1
        parent = parent.parent()
    return depth


def _build_path(item: QTreeWidgetItem) -> list[str]:
    """루트 → 현재 아이템까지 타이틀 경로."""
    path: list[str] = []
    current: QTreeWidgetItem | None = item
    while current is not None:
        path.insert(0, current.text(0))
        current = current.parent()
    return path


class _TreeSidebar(QWidget):
    """중앙 145px 패널 — 섹션 트리 + TransferOn 고정 항목."""

    section_selected = pyqtSignal(object, list)   # (Section, path: list[str])
    transfer_on_selected = pyqtSignal()
    structure_changed = pyqtSignal()              # 섹션 추가/삭제 시

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setFixedWidth(145)
        self.setStyleSheet(
            "background: #0f0f22; border-right: 1px solid #1a1a33;"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(4)

        hdr = QLabel("Sections")
        hdr.setStyleSheet(
            "font-size: 8px; color: #446; text-transform: uppercase; letter-spacing: 1px;"
        )
        lay.addWidget(hdr)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { background: #0f0f22; border: none; color: #aaa; font-size: 9px; }"
            "QTreeWidget::item:selected { background: #1a1a3a; color: #88aaff; }"
            "QTreeWidget::item { padding: 2px 0; }"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        lay.addWidget(self._tree, 1)

        btn_add = QPushButton("＋ 섹션 추가")
        btn_add.setStyleSheet(
            "border: 1px dashed #2a2a44; border-radius: 3px; color: #446; "
            "font-size: 9px; padding: 3px; background: transparent;"
        )
        btn_add.clicked.connect(self._on_add_section)
        lay.addWidget(btn_add)

        # TransferOn — ProceduralSkill / AgentDefinition 전용 고정 하단 항목
        self._has_transfer_on = not isinstance(component, DeclarativeSkill)
        if self._has_transfer_on:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #2a4a2a;")
            lay.addWidget(sep)
            self._transfer_on_btn = QPushButton("⇄ TransferOn")
            self._transfer_on_btn.setStyleSheet(
                "background: #132013; border: 1px solid #2a4a2a; border-radius: 3px; "
                "color: #88cc88; font-size: 9px; padding: 3px 6px; text-align: left;"
            )
            self._transfer_on_btn.clicked.connect(self.transfer_on_selected)
            lay.addWidget(self._transfer_on_btn)

        self._rebuild()

    def tree_widget(self) -> QTreeWidget:
        return self._tree

    def _rebuild(self) -> None:
        self._tree.clear()
        for section in self._component.sections:
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
        path = _build_path(item)
        self.section_selected.emit(section, path)

    def _on_add_section(self) -> None:
        selected = self._tree.currentItem()
        new_section = Section(title="새 섹션")
        if selected is None:
            # 최상위 H1 추가
            self._component.sections.append(new_section)
        else:
            section = selected.data(0, _ROLE_SECTION)
            if section is None:
                self._component.sections.append(new_section)
            else:
                # 선택 항목과 같은 레벨 (형제) 추가
                parent_item = selected.parent()
                if parent_item is None:
                    # 루트 레벨
                    idx = self._component.sections.index(section)
                    self._component.sections.insert(idx + 1, new_section)
                else:
                    parent_section: Section = parent_item.data(0, _ROLE_SECTION)
                    idx = parent_section.children.index(section)
                    parent_section.children.insert(idx + 1, new_section)
        self._rebuild()
        self.structure_changed.emit()

    def add_child_to_current(self) -> None:
        """ContentPanel의 '+ 하위 섹션' 버튼이 호출."""
        selected = self._tree.currentItem()
        if selected is None:
            return
        depth = _section_depth(selected)
        if depth >= 5:  # H6 이상 불가
            return
        section: Section = selected.data(0, _ROLE_SECTION)
        if section is None:
            return
        child = Section(title="새 하위 섹션")
        section.children.append(child)
        self._rebuild()
        self.structure_changed.emit()

    def delete_current(self) -> None:
        """ContentPanel의 '삭제' 버튼이 호출."""
        selected = self._tree.currentItem()
        if selected is None:
            return
        section: Section = selected.data(0, _ROLE_SECTION)
        if section is None:
            return
        parent_item = selected.parent()
        if parent_item is None:
            if section in self._component.sections:
                self._component.sections.remove(section)
        else:
            parent_section: Section = parent_item.data(0, _ROLE_SECTION)
            if section in parent_section.children:
                parent_section.children.remove(section)
        self._rebuild()
        self.structure_changed.emit()

    def current_depth(self) -> int:
        """현재 선택 아이템의 깊이 (없으면 -1)."""
        item = self._tree.currentItem()
        return _section_depth(item) if item is not None else -1


class _ColorPickerPopup(QFrame):
    """8색 프리셋 팔레트 팝업 (모달 아님)."""

    color_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1a1a2e; border: 1px solid #3a4a6a; border-radius: 5px; }"
        )
        self.setWindowFlags(Qt.WindowType.Popup)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        for hex_color in _COLOR_PRESETS:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setStyleSheet(
                f"background: {hex_color}; border: 2px solid #333; border-radius: 9px;"
            )
            btn.clicked.connect(lambda _checked, c=hex_color: self._emit(c))
            lay.addWidget(btn)

    def _emit(self, color: str) -> None:
        self.color_selected.emit(color)
        self.hide()


class _EventCard(QFrame):
    """TransferOn 패널의 이벤트 한 항목 카드."""

    delete_requested = pyqtSignal(object)   # EventDef
    changed = pyqtSignal()

    def __init__(
        self,
        event_def: EventDef,
        can_delete: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event_def
        self._popup = _ColorPickerPopup()
        self._popup.color_selected.connect(self._on_color_picked)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._update_border()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # 색상 원 버튼
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(14, 14)
        self._color_btn.setStyleSheet(
            f"background: {event_def.color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._color_btn.clicked.connect(self._show_color_popup)
        lay.addWidget(self._color_btn)

        # 이름 + 설명 컬럼
        col = QVBoxLayout()
        col.setSpacing(3)

        name_row = QHBoxLayout()
        self._w_name = QLineEdit(event_def.name)
        self._w_name.setStyleSheet(
            "background: transparent; border: none; border-bottom: 1px solid #335; "
            "color: #88aaff; font-size: 11px; font-weight: bold;"
        )
        self._w_name.setFixedWidth(100)
        self._w_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._w_name)
        name_lbl = QLabel("이벤트 이름")
        name_lbl.setStyleSheet("font-size: 8px; color: #335;")
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        col.addLayout(name_row)

        self._w_desc = QLineEdit(event_def.description)
        self._w_desc.setPlaceholderText("간략한 설명 (선택)")
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.editingFinished.connect(self._on_desc_changed)
        col.addWidget(self._w_desc)

        lay.addLayout(col, 1)

        # 삭제 버튼
        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setEnabled(can_delete)
        self._del_btn.setStyleSheet(
            "color: #335; background: transparent; border: none; font-size: 11px;"
        )
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._event))
        lay.addWidget(self._del_btn)

    def _update_border(self) -> None:
        c = QColor(self._event.color)
        border = c.name()
        bg = c.darker(300).name()
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 5px; }}"
        )

    def _show_color_popup(self) -> None:
        pos = self._color_btn.mapToGlobal(self._color_btn.rect().bottomLeft())
        self._popup.move(pos)
        self._popup.show()

    def _on_color_picked(self, color: str) -> None:
        self._event.color = color
        self._color_btn.setStyleSheet(
            f"background: {color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._update_border()
        self.changed.emit()

    def _on_name_changed(self) -> None:
        self._event.name = self._w_name.text().strip() or self._event.name
        self._w_name.setText(self._event.name)
        self.changed.emit()

    def _on_desc_changed(self) -> None:
        self._event.description = self._w_desc.text()
        self.changed.emit()


class _TransferOnPanel(QWidget):
    """TransferOn 선택 시 우측에 표시되는 이벤트 카드 목록."""

    transfer_on_changed = pyqtSignal()

    def __init__(
        self,
        transfer_on: list[EventDef],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_on = transfer_on
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hdr = QLabel("출력 이벤트 정의 — 노드 포트로 자동 반영")
        hdr.setStyleSheet("font-size: 9px; color: #446; margin-bottom: 4px;")
        lay.addWidget(hdr)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        lay.addWidget(self._cards_widget)

        btn_add = QPushButton("＋ 이벤트 추가")
        btn_add.setStyleSheet(
            "border: 1px dashed #2a4a2a; border-radius: 5px; color: #446; "
            "font-size: 9px; padding: 7px; background: transparent;"
        )
        btn_add.clicked.connect(self._on_add_event)
        lay.addWidget(btn_add)

        hint = QLabel("색상 원 클릭 → 색상 팔레트 선택. 변경 즉시 캔버스 노드에 반영.")
        hint.setStyleSheet("font-size: 8px; color: #335;")
        lay.addWidget(hint)

        lay.addStretch()
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for event_def in self._transfer_on:
            can_delete = len(self._transfer_on) > 1
            card = _EventCard(event_def, can_delete=can_delete)
            card.changed.connect(self.transfer_on_changed)
            card.delete_requested.connect(self._on_delete_event)
            self._cards_layout.addWidget(card)

    def _on_add_event(self) -> None:
        self._transfer_on.append(EventDef("new_event"))
        self._rebuild_cards()
        self.transfer_on_changed.emit()

    def _on_delete_event(self, event_def: EventDef) -> None:
        if len(self._transfer_on) <= 1:
            return
        self._transfer_on.remove(event_def)
        self._rebuild_cards()
        self.transfer_on_changed.emit()


class _ContentPanel(QWidget):
    """우측 패널 — 브레드크럼 툴바 + 타이틀 인라인 편집 + QTextEdit."""

    add_child_requested = pyqtSignal()
    delete_requested = pyqtSignal()
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
        toolbar.setStyleSheet("background: #111120; border-bottom: 1px solid #1a1a33;")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(10, 5, 10, 5)
        tb_lay.setSpacing(6)

        self._breadcrumb = QLabel("")
        self._breadcrumb.setStyleSheet("font-size: 9px; color: #446;")
        tb_lay.addWidget(self._breadcrumb)
        tb_lay.addStretch()

        self._btn_variable = QPushButton("{ } 변수 삽입")
        self._btn_variable.setStyleSheet(
            "background: #1a2a1a; border: 1px solid #3a7a3a; border-radius: 3px; "
            "padding: 2px 8px; font-size: 9px; color: #88cc88;"
        )
        self._btn_variable.clicked.connect(self.variable_insert_requested)
        tb_lay.addWidget(self._btn_variable)

        self._btn_add_child = QPushButton("＋ 하위 섹션")
        self._btn_add_child.setStyleSheet(
            "background: #1a1a2e; border: 1px solid #333; border-radius: 3px; "
            "padding: 2px 7px; font-size: 9px; color: #668;"
        )
        self._btn_add_child.clicked.connect(self.add_child_requested)
        tb_lay.addWidget(self._btn_add_child)

        self._btn_delete = QPushButton("삭제")
        self._btn_delete.setStyleSheet(
            "background: #2a1a1a; border: 1px solid #443; border-radius: 3px; "
            "padding: 2px 7px; font-size: 9px; color: #885;"
        )
        self._btn_delete.clicked.connect(self.delete_requested)
        tb_lay.addWidget(self._btn_delete)

        lay.addWidget(toolbar)

        # --- 타이틀 인라인 편집 ---
        title_area = QWidget()
        title_area.setStyleSheet(f"background: {_DARK_BG};")
        ta_lay = QVBoxLayout(title_area)
        ta_lay.setContentsMargins(12, 8, 12, 4)
        self._w_title = QLineEdit()
        self._w_title.setPlaceholderText("섹션 타이틀")
        self._w_title.setStyleSheet(
            "background: transparent; border: none; border-bottom: 1px solid #333; "
            "color: #ccc; font-size: 14px; font-weight: bold;"
        )
        self._w_title.editingFinished.connect(self._save_title)
        ta_lay.addWidget(self._w_title)
        lay.addWidget(title_area)

        # --- 본문 텍스트 ---
        self._w_content = QTextEdit()
        self._w_content.setStyleSheet(
            f"background: {_DARK_BG}; color: #aaa; border: none; "
            "font-family: Consolas, monospace; font-size: 10px; padding: 4px 12px;"
        )
        self._w_content.textChanged.connect(self._save_content)
        lay.addWidget(self._w_content, 1)

    def current_section(self) -> Section | None:
        return self._section

    def show_section(self, section: Section, path: list[str]) -> None:
        self._section = section
        crumb = " › ".join(path)
        self._breadcrumb.setText(crumb)
        self._w_title.setText(section.title)
        self._w_content.blockSignals(True)
        self._w_content.setPlainText(section.content)
        self._w_content.blockSignals(False)

    def set_add_child_enabled(self, enabled: bool) -> None:
        self._btn_add_child.setEnabled(enabled)

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
