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
_ROLE_IS_TRANSFER_ON = Qt.ItemDataRole.UserRole + 1

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

        self._cb.toggled.connect(self._update_state)
        self._update_state(initially_enabled)

    def _update_state(self, checked: bool) -> None:
        self._widget.setEnabled(checked)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0 if checked else 0.4)
        self.setGraphicsEffect(effect)
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
        w_model = QComboBox()
        for e in ModelType:
            w_model.addItem(e.value)
        if config is not None:
            mv = config.model.value if isinstance(config.model, ModelType) else str(config.model)
            idx = w_model.findText(mv)
            if idx >= 0:
                w_model.setCurrentIndex(idx)
        lay.addWidget(
            _OptionalRow(
                "model", w_model,
                initially_enabled=(config is not None and config.model != ModelType.INHERIT),
            )
        )

        # effort
        w_effort = QComboBox()
        for e in EffortLevel:
            w_effort.addItem(e.value)
        if config is not None and config.effort is not None:
            idx = w_effort.findText(config.effort.value)
            if idx >= 0:
                w_effort.setCurrentIndex(idx)
        lay.addWidget(
            _OptionalRow(
                "effort", w_effort,
                initially_enabled=(config is not None and config.effort is not None),
            )
        )

        # allowed-tools (SkillConfig 계열)
        if config is not None and hasattr(config, "allowed_tools"):
            w_tools = QLineEdit(" ".join(config.allowed_tools))
            w_tools.setPlaceholderText("Read Grep WebSearch")
            lay.addWidget(
                _OptionalRow(
                    "allowed-tools", w_tools,
                    initially_enabled=bool(config.allowed_tools),
                )
            )

        # ProceduralSkill 전용 필드
        if isinstance(config, ProceduralSkillConfig):
            w_ctx = QComboBox()
            for e in SkillContext:
                w_ctx.addItem(e.value)
            idx = w_ctx.findText(config.context.value)
            if idx >= 0:
                w_ctx.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("context", w_ctx, initially_enabled=True))

            w_paths = QLineEdit(" ".join(config.paths) if config.paths else "")
            w_paths.setPlaceholderText("src/**/*.py")
            lay.addWidget(
                _OptionalRow(
                    "paths", w_paths,
                    initially_enabled=bool(config.paths),
                )
            )

            w_shell = QComboBox()
            for e in SkillShell:
                w_shell.addItem(e.value)
            idx = w_shell.findText(config.shell.value)
            if idx >= 0:
                w_shell.setCurrentIndex(idx)
            lay.addWidget(_OptionalRow("shell", w_shell, initially_enabled=True))

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
            w_hint = QLineEdit(config.argument_hint or "")
            w_hint.setPlaceholderText("[topic]")
            lay.addWidget(
                _OptionalRow(
                    "argument-hint", w_hint,
                    initially_enabled=bool(config.argument_hint),
                )
            )

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
