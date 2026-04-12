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
