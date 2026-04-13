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
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill

from daedalus.view.editors.body_editor import (
    BreadcrumbNav,
    SectionContentPanel,
    SectionTree,
    VariablePopup,
    find_path,
)

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
        layout.addWidget(self._cb)

        lbl = QLabel(label)
        layout.addWidget(lbl)

        self._widget = widget
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

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        hdr = QLabel("Frontmatter")
        lay.addWidget(hdr)

        # --- 필수 필드 ---
        lay.addWidget(self._lbl("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        lay.addWidget(self._lbl("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # --- 선택 필드 구분선 ---
        sep = QLabel("선택 필드")
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
            lay.addWidget(self._w_disable_model)

            self._w_user_invocable = QCheckBox("user-invocable")
            self._w_user_invocable.setChecked(config.user_invocable)
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
        return QLabel(text)

    def _save_name(self) -> None:
        self._component.name = self._w_name.text().strip()
        self.changed.emit()

    def _save_desc(self) -> None:
        self._component.description = self._w_desc.toPlainText().strip()
        self.changed.emit()


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
        self._popup = _ColorPickerPopup(parent=self)
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
        self._w_name.setFixedWidth(100)
        self._w_name.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(self._w_name)
        name_lbl = QLabel("이벤트 이름")
        name_row.addWidget(name_lbl)
        name_row.addStretch()
        col.addLayout(name_row)

        self._w_desc = QLineEdit(event_def.description)
        self._w_desc.setPlaceholderText("간략한 설명 (선택)")
        self._w_desc.editingFinished.connect(self._on_desc_changed)
        col.addWidget(self._w_desc)

        lay.addLayout(col, 1)

        # 삭제 버튼
        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setEnabled(can_delete)
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
        lay.addWidget(hdr)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        lay.addWidget(self._cards_widget)

        btn_add = QPushButton("＋ 이벤트 추가")
        btn_add.clicked.connect(self._on_add_event)
        lay.addWidget(btn_add)

        hint = QLabel("색상 원 클릭 → 색상 팔레트 선택. 변경 즉시 캔버스 노드에 반영.")
        lay.addWidget(hint)

        lay.addStretch()
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
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


class SkillEditor(QWidget):
    """ProceduralSkill / DeclarativeSkill / AgentDefinition 편집기.

    레이아웃 (QSplitter):
      _FrontmatterPanel | SectionTree + TransferOn | BreadcrumbNav + ContentPanel / TransferOnPanel
    """

    skill_changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self._on_notify_fn = on_notify_fn

        from daedalus.view.editors.variable_loader import load_variables
        self._variables = load_variables()

        root_lay = QHBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Frontmatter
        self._fm = _FrontmatterPanel(component)
        self._fm.changed.connect(self._on_model_changed)
        splitter.addWidget(self._fm)

        # Center: SectionTree + TransferOn button
        tree_area = QWidget()
        tree_lay = QVBoxLayout(tree_area)
        tree_lay.setContentsMargins(0, 0, 0, 0)
        tree_lay.setSpacing(4)

        self._section_tree = SectionTree(component.sections)
        self._section_tree.section_selected.connect(self._on_tree_selected)
        self._section_tree.structure_changed.connect(self._on_structure_changed)
        tree_lay.addWidget(self._section_tree, 1)

        if not isinstance(component, DeclarativeSkill):
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            tree_lay.addWidget(sep)
            self._transfer_on_btn = QPushButton("⇄ TransferOn")
            self._transfer_on_btn.clicked.connect(self._on_transfer_on_selected)
            tree_lay.addWidget(self._transfer_on_btn)

        splitter.addWidget(tree_area)

        # Right: BreadcrumbNav + Stack
        right_area = QWidget()
        right_lay = QVBoxLayout(right_area)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self._breadcrumb = BreadcrumbNav(component.sections)
        self._breadcrumb.section_selected.connect(self._on_breadcrumb_selected)
        self._breadcrumb.section_add_requested.connect(self._on_breadcrumb_add)
        right_lay.addWidget(self._breadcrumb)

        self._stack = QStackedWidget()

        self._content_panel = SectionContentPanel()
        self._content_panel.variable_insert_requested.connect(self._on_variable_insert)
        self._content_panel.content_changed.connect(self._on_content_changed)
        self._stack.addWidget(self._content_panel)  # index 0

        if not isinstance(component, DeclarativeSkill):
            transfer_on = component.transfer_on
        else:
            transfer_on = []
        self._transfer_on_panel = _TransferOnPanel(transfer_on)
        self._transfer_on_panel.transfer_on_changed.connect(self._on_model_changed)
        self._stack.addWidget(self._transfer_on_panel)  # index 1

        right_lay.addWidget(self._stack, 1)
        splitter.addWidget(right_area)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)

        root_lay.addWidget(splitter)

        # Variable popup
        self._var_popup = VariablePopup(self._variables, parent=self._content_panel)
        self._var_popup.variable_selected.connect(self._content_panel.insert_variable)
        self._var_popup.hide()

        # Initial selection
        if component.sections:
            first = component.sections[0]
            self._select_section(first)

    # --- Bidirectional sync ---

    def _select_section(self, section: Section) -> None:
        path = find_path(section, self._component.sections)
        if path is None:
            return
        path_titles = [s.title for s in path]
        self._section_tree.select_section(section)
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path_titles)
        self._stack.setCurrentIndex(0)

    def _on_tree_selected(self, section: Section, path: list[str]) -> None:
        self._breadcrumb.set_current(section)
        self._content_panel.show_section(section, path)
        self._stack.setCurrentIndex(0)

    def _on_breadcrumb_selected(self, section: Section, path: list[str]) -> None:
        self._section_tree.select_section(section)
        self._content_panel.show_section(section, path)
        self._stack.setCurrentIndex(0)

    def _on_breadcrumb_add(self, parent: Section | None, depth: int) -> None:
        new = Section(title="새 섹션")
        if parent is None:
            self._component.sections.append(new)
        else:
            parent.children.append(new)
        self._on_structure_changed()
        self._select_section(new)

    def _on_transfer_on_selected(self) -> None:
        self._stack.setCurrentIndex(1)

    def _on_structure_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
        self._on_model_changed()

    def _on_content_changed(self) -> None:
        self._section_tree.set_sections(self._component.sections)
        self._breadcrumb.set_sections(self._component.sections)
        self._on_model_changed()

    def _on_variable_insert(self) -> None:
        if self._var_popup.isVisible():
            self._var_popup.hide()
            return
        from PyQt6.QtCore import QPoint
        btn = self._content_panel._btn_variable
        pos = btn.mapTo(self._content_panel, QPoint(0, btn.height()))
        self._var_popup.move(pos)
        self._var_popup.show()
        self._var_popup.raise_()

    def _on_model_changed(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
