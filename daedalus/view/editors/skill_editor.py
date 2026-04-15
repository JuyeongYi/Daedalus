# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill, ReferenceSkill, TransferSkill


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
    """좌측 패널 — SKILL_FIELD_MATRIX 기반 프론트매터 편집."""

    changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        skill_kind: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component = component
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(3)

        lay.addWidget(QLabel("Frontmatter"))

        # name (필수, 항상 표시)
        lay.addWidget(QLabel("name *"))
        self._w_name = QLineEdit(component.name)
        self._w_name.editingFinished.connect(self._save_name)
        lay.addWidget(self._w_name)

        # description (필수, 항상 표시)
        lay.addWidget(QLabel("description *"))
        self._w_desc = QTextEdit()
        self._w_desc.setPlainText(component.description)
        self._w_desc.setFixedHeight(44)
        self._w_desc.textChanged.connect(self._save_desc)
        lay.addWidget(self._w_desc)

        # SKILL_FIELD_MATRIX 기반 필드 생성
        from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
        from daedalus.model.plugin.enums import FieldVisibility, SkillField

        kind = skill_kind or self._detect_kind(component)
        rules = SKILL_FIELD_MATRIX.get(kind, {})
        config = getattr(component, "config", None)

        skip = {SkillField.NAME, SkillField.DESCRIPTION}
        for field, rule in rules.items():
            if field in skip:
                continue
            if rule.visibility == FieldVisibility.REQUIRED:
                widget = rule.widget()
                self._apply_value(widget, config, field, rule)
                from PyQt6.QtWidgets import QComboBox as _QCB
                if isinstance(widget, _QCB):
                    row = QHBoxLayout()
                    row.addWidget(QLabel(field.value))
                    row.addWidget(widget, 1)
                    lay.addLayout(row)
                else:
                    lay.addWidget(QLabel(field.value))
                    lay.addWidget(widget)
            elif rule.visibility == FieldVisibility.OPTIONAL:
                widget = rule.widget()
                current = self._get_current(config, component, field)
                enabled = current is not None and current != "" and current != [] and current is not False
                self._apply_value(widget, config, field, rule)
                lay.addWidget(_OptionalRow(field.value, widget, initially_enabled=enabled))

        lay.addStretch()
        self.setWidget(inner)

    @staticmethod
    def _detect_kind(component: object) -> str:
        config = getattr(component, "config", None)
        if config is not None and hasattr(config, "kind"):
            return config.kind
        return "procedural"

    @staticmethod
    def _get_current(config: object, component: object, field) -> object:
        from daedalus.model.plugin.enums import SkillField
        # when_to_use is on the component, not config
        if field == SkillField.WHEN_TO_USE:
            return getattr(component, "when_to_use", None)
        attr_map = {
            SkillField.ARGUMENT_HINT: "argument_hint",
            SkillField.MODEL: "model",
            SkillField.EFFORT: "effort",
            SkillField.ALLOWED_TOOLS: "allowed_tools",
            SkillField.CONTEXT: "context",
            SkillField.AGENT: "agent",
            SkillField.SHELL: "shell",
            SkillField.PATHS: "paths",
            SkillField.HOOKS: "hooks",
            SkillField.DISABLE_MODEL: "disable_model_invocation",
            SkillField.USER_INVOCABLE: "user_invocable",
        }
        attr = attr_map.get(field)
        if attr and config is not None:
            return getattr(config, attr, None)
        return None

    @staticmethod
    def _apply_value(widget, config, field, rule) -> None:
        from PyQt6.QtWidgets import QComboBox, QCheckBox, QLineEdit, QTextEdit
        from daedalus.view.widgets.tag_input import TagInput
        from daedalus.model.plugin.enums import SkillField
        current = _FrontmatterPanel._get_current(config, None, field)

        if isinstance(widget, QComboBox):
            val = None
            if current is not None:
                val = current.value if hasattr(current, "value") else str(current)
            elif rule.default_value is not None:
                val = str(rule.default_value)
            if val is not None:
                idx = widget.findText(val)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(current) if current is not None else False)
        elif isinstance(widget, TagInput):
            if isinstance(current, list):
                widget.set_tags(current)
        elif isinstance(widget, QTextEdit):
            if current is not None:
                widget.setPlainText(str(current))
            widget.setFixedHeight(44)
        elif isinstance(widget, QLineEdit):
            if isinstance(current, list):
                widget.setText(" ".join(current) if current else "")
            elif current is not None:
                widget.setText(str(current))

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
        siblings: list[EventDef] | None = None,
        can_delete: bool = True,
        multiline_desc: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._event = event_def
        self._siblings = siblings or []
        self._multiline = multiline_desc
        self._popup = _ColorPickerPopup(parent=self)
        self._popup.color_selected.connect(self._on_color_picked)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._update_border()

        # 색상 버튼 (공통)
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(14, 14)
        self._color_btn.setStyleSheet(
            f"background: {event_def.color}; border: 2px solid #335; border-radius: 7px;"
        )
        self._color_btn.clicked.connect(self._show_color_popup)

        # 이름 (공통)
        self._w_name = QLineEdit(event_def.name)
        self._w_name.setFixedWidth(100)
        self._w_name.editingFinished.connect(self._on_name_changed)

        # 삭제 버튼 (공통)
        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(20, 20)
        self._del_btn.setEnabled(can_delete)
        self._del_btn.clicked.connect(lambda: self.delete_requested.emit(self._event))

        if multiline_desc:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(6)
            top = QHBoxLayout()
            top.addWidget(self._color_btn)
            top.addWidget(self._w_name)
            top.addWidget(QLabel("🤖"))
            top.addStretch()
            top.addWidget(self._del_btn)
            lay.addLayout(top)
            self._w_desc_multi = QTextEdit()
            self._w_desc_multi.setPlainText(event_def.description)
            self._w_desc_multi.setPlaceholderText("에이전트에 전달할 내용을 작성하세요...")
            self._w_desc_multi.setMinimumHeight(60)
            self._w_desc_multi.textChanged.connect(self._on_desc_multi_changed)
            lay.addWidget(self._w_desc_multi)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(8, 8, 8, 8)
            lay.setSpacing(8)
            lay.addWidget(self._color_btn)
            col = QVBoxLayout()
            col.setSpacing(3)
            name_row = QHBoxLayout()
            name_row.addWidget(self._w_name)
            name_row.addWidget(QLabel("이벤트 이름"))
            name_row.addStretch()
            col.addLayout(name_row)
            self._w_desc = QLineEdit(event_def.description)
            self._w_desc.setPlaceholderText("간략한 설명 (선택)")
            self._w_desc.editingFinished.connect(self._on_desc_changed)
            col.addWidget(self._w_desc)
            lay.addLayout(col, 1)
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
        new_name = self._w_name.text().strip()
        if not new_name:
            self._w_name.setText(self._event.name)
            return
        # 같은 리스트 내 이름 중복 방지
        if any(e.name == new_name and e is not self._event for e in self._siblings):
            self._w_name.setText(self._event.name)
            return
        self._event.name = new_name
        self.changed.emit()

    def _on_desc_changed(self) -> None:
        self._event.description = self._w_desc.text()
        self.changed.emit()

    def _on_desc_multi_changed(self) -> None:
        self._event.description = self._w_desc_multi.toPlainText()
        self.changed.emit()


class _ContractCard(QFrame):
    """계약 섹션 카드 — 타이틀 잠금, 내용 편집 가능."""

    changed = pyqtSignal()

    def __init__(self, section: Section, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section = section
        self.setFrameShape(QFrame.Shape.StyledPanel)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        title_lbl = QLabel(f"🔒 {section.title}")
        lay.addWidget(title_lbl)

        self._w_content = QTextEdit()
        self._w_content.setPlainText(section.content)
        self._w_content.setPlaceholderText("이 호출에서 기대하는 입력을 작성하세요...")
        self._w_content.setMinimumHeight(60)
        self._w_content.textChanged.connect(self._on_content_changed)
        lay.addWidget(self._w_content)

    def _on_content_changed(self) -> None:
        self._section.content = self._w_content.toPlainText()
        self.changed.emit()


class _ContractPanel(QScrollArea):
    """잠금 계약 섹션 패널 — 인라인 편집 카드 목록 (스크롤 지원)."""

    contract_changed = pyqtSignal()

    def __init__(
        self,
        label: str,
        contracts: list[Section],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._contracts = contracts
        self._label = label
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(8)
        self.setWidget(self._inner)
        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        while self._lay.count():
            child = self._lay.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        if not self._contracts:
            placeholder = QLabel("연결된 호출이 없습니다")
            self._lay.addWidget(placeholder)
            self._lay.addStretch()
            return
        lbl = QLabel(self._label)
        self._lay.addWidget(lbl)
        for sec in self._contracts:
            card = _ContractCard(sec)
            card.changed.connect(self.contract_changed)
            self._lay.addWidget(card)
        self._lay.addStretch()


class _TransferOnPanel(QScrollArea):
    """TransferOn / AgentCall 이벤트 카드 목록 (스크롤 지원)."""

    transfer_on_changed = pyqtSignal()

    def __init__(
        self,
        transfer_on: list[EventDef],
        title: str = "⇄ Transfer On",
        default_color: str = "#4488ff",
        multiline_desc: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_on = transfer_on
        self._default_color = default_color
        self._multiline = multiline_desc
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        hdr_row = QHBoxLayout()
        btn_add = QPushButton("＋")
        btn_add.setFixedWidth(28)
        btn_add.clicked.connect(self._on_add_event)
        hdr_row.addWidget(btn_add)
        hdr_row.addWidget(QLabel(title))
        hdr_row.addStretch()
        lay.addLayout(hdr_row)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(6)
        lay.addWidget(self._cards_widget)

        lay.addStretch()
        self.setWidget(inner)
        self._rebuild_cards()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            child = self._cards_layout.takeAt(0)
            if child is not None:
                w = child.widget()
                if w is not None:
                    w.deleteLater()
        for event_def in self._transfer_on:
            card = _EventCard(event_def, siblings=self._transfer_on, can_delete=True, multiline_desc=self._multiline)
            card.changed.connect(self.transfer_on_changed)
            card.delete_requested.connect(self._on_delete_event)
            self._cards_layout.addWidget(card)

    def _on_add_event(self) -> None:
        existing = {e.name for e in self._transfer_on}
        base = "new_event"
        name = base
        counter = 2
        while name in existing:
            name = f"{base}_{counter}"
            counter += 1
        self._transfer_on.append(EventDef(name, color=self._default_color))
        self._rebuild_cards()
        self.transfer_on_changed.emit()

    def _on_delete_event(self, event_def: EventDef) -> None:
        self._transfer_on.remove(event_def)
        self._rebuild_cards()
        self.transfer_on_changed.emit()


class SkillEditor(QWidget):
    """스킬/에이전트 편집기 — ComponentEditor + 타입별 우측 패널."""

    skill_changed = pyqtSignal()

    def __init__(
        self,
        component: ProceduralSkill | DeclarativeSkill | TransferSkill | ReferenceSkill | AgentDefinition,
        on_notify_fn: Callable[[], None] | None = None,
        show_call_agents: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from daedalus.view.editors.component_editor import ComponentEditor

        right_widgets: list[QWidget] = []
        if isinstance(component, ProceduralSkill):
            right_widgets.append(_TransferOnPanel(component.transfer_on, title="⇄ Transfer On"))
            if show_call_agents:
                right_widgets.append(
                    _TransferOnPanel(component.call_agents, title="🤖 Agent Call", default_color="#8a4a4a", multiline_desc=True)
                )

        # Determine skill_kind for field matrix
        if isinstance(component, ProceduralSkill):
            kind = "local_procedural" if not show_call_agents else "procedural"
        elif isinstance(component, TransferSkill):
            kind = "local_transfer" if not show_call_agents else "transfer"
        elif isinstance(component, DeclarativeSkill):
            kind = "declarative"
        elif isinstance(component, ReferenceSkill):
            kind = "reference"
        else:
            kind = None

        self._editor = ComponentEditor(
            component,
            right_widgets=right_widgets,
            on_notify_fn=self._on_notify,
            skill_kind=kind,
        )

        self._on_notify_fn = on_notify_fn

        # right_widgets의 changed 시그널 연결
        for w in right_widgets:
            if hasattr(w, "transfer_on_changed"):
                w.transfer_on_changed.connect(self._editor._on_model_changed)

        self._editor.changed.connect(self.skill_changed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._editor)

    def _on_notify(self) -> None:
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()
