# daedalus/view/editors/skill_editor.py
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from daedalus.model.fsm.section import SkillSection
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.enums import EffortLevel, ModelType, SkillContext, SkillShell
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.plugin.agent import AgentDefinition

_INPUT_STYLE = (
    "background: #1a1a2e; border: 1px solid #446; color: #aac; "
    "padding: 3px 5px; border-radius: 3px;"
)
_DARK_BG = "background: #13132a; color: #aac;"


class _SectionCard(QFrame):
    """SkillSection 하나를 표현하는 카드."""

    def __init__(
        self,
        section: SkillSection,
        always_active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._section = section
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #13132a; border: 1px solid #336; border-radius: 5px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: #1a1a3a; border-radius: 4px 4px 0 0;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 8, 4)

        if always_active:
            lbl = QLabel(section.name)
            lbl.setStyleSheet("color: #88aaff; font-weight: bold; font-size: 11px;")
            h_layout.addWidget(lbl)
            self._checkbox: QCheckBox | None = None
        else:
            self._checkbox = QCheckBox(section.name)
            self._checkbox.setStyleSheet("color: #88cc88; font-weight: bold; font-size: 11px;")
            self._checkbox.toggled.connect(self._on_toggled)
            h_layout.addWidget(self._checkbox)

        h_layout.addStretch()
        key_lbl = QLabel(section.value)
        key_lbl.setStyleSheet("color: #446; font-size: 9px; font-family: Consolas;")
        h_layout.addWidget(key_lbl)
        layout.addWidget(header)

        self._body = QTextEdit()
        self._body.setStyleSheet(
            "background: #0d0d1f; color: #ccc; border: 1px solid #335; "
            "font-family: Consolas; font-size: 10px; padding: 4px;"
        )
        self._body.setMinimumHeight(50)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._body)

        if not always_active:
            self._body.hide()

    @property
    def section(self) -> SkillSection:
        return self._section

    def is_active(self) -> bool:
        if self._checkbox is None:
            return True
        return self._checkbox.isChecked()

    def get_text(self) -> str:
        return self._body.toPlainText()

    def set_text(self, text: str) -> None:
        self._body.setPlainText(text)

    def set_active(self, active: bool) -> None:
        if self._checkbox is not None:
            self._checkbox.setChecked(active)

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)


class SkillEditor(QWidget):
    """ProceduralSkill / DeclarativeSkill / AgentDefinition 편집기."""

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
        self._section_cards: list[_SectionCard] = []

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 좌측: Frontmatter
        fm_scroll = QScrollArea()
        fm_scroll.setWidgetResizable(True)
        fm_scroll.setFixedWidth(285)
        fm_scroll.setStyleSheet(_DARK_BG)
        fm_inner = QWidget()
        fm_inner.setStyleSheet(_DARK_BG)
        self._fm_layout = QFormLayout(fm_inner)
        self._fm_layout.setContentsMargins(8, 8, 8, 8)
        self._fm_layout.setSpacing(6)
        fm_scroll.setWidget(fm_inner)
        main_layout.addWidget(fm_scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #333;")
        main_layout.addWidget(sep)

        # 우측: Body sections
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setStyleSheet(_DARK_BG)
        body_inner = QWidget()
        body_inner.setStyleSheet(_DARK_BG)
        self._body_layout = QVBoxLayout(body_inner)
        self._body_layout.setContentsMargins(8, 8, 8, 8)
        self._body_layout.setSpacing(8)
        body_scroll.setWidget(body_inner)
        main_layout.addWidget(body_scroll, 1)

        self._build_frontmatter()
        self._build_sections()
        self._build_buttons()

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #666; font-size: 10px;")
        return lbl

    def _input(self) -> QLineEdit:
        w = QLineEdit()
        w.setStyleSheet(_INPUT_STYLE)
        return w

    def _combo(self, values: list[str]) -> QComboBox:
        w = QComboBox()
        w.setStyleSheet(_INPUT_STYLE)
        for v in values:
            w.addItem(v)
        return w

    def _build_frontmatter(self) -> None:
        lay = self._fm_layout
        comp = self._component
        config = getattr(comp, "config", None)

        self._w_name = self._input()
        self._w_name.setText(comp.name)
        lay.addRow(self._lbl("name"), self._w_name)

        self._w_desc = QTextEdit()
        self._w_desc.setStyleSheet(_INPUT_STYLE)
        self._w_desc.setFixedHeight(48)
        self._w_desc.setPlainText(comp.description)
        lay.addRow(self._lbl("description *"), self._w_desc)

        if config is not None and hasattr(config, "argument_hint"):
            self._w_arg_hint = self._input()
            self._w_arg_hint.setPlaceholderText("[topic]")
            if config.argument_hint:
                self._w_arg_hint.setText(config.argument_hint)
            lay.addRow(self._lbl("argument-hint"), self._w_arg_hint)

        self._w_model = self._combo([e.value for e in ModelType])
        if config is not None:
            mv = config.model.value if isinstance(config.model, ModelType) else str(config.model)
            idx = self._w_model.findText(mv)
            if idx >= 0:
                self._w_model.setCurrentIndex(idx)
        lay.addRow(self._lbl("model"), self._w_model)

        self._w_effort = self._combo(["(inherit)"] + [e.value for e in EffortLevel])
        if config is not None and config.effort is not None:
            idx = self._w_effort.findText(config.effort.value)
            if idx >= 0:
                self._w_effort.setCurrentIndex(idx)
        lay.addRow(self._lbl("effort"), self._w_effort)

        if config is not None and hasattr(config, "allowed_tools"):
            self._w_tools = self._input()
            self._w_tools.setPlaceholderText("Read Grep WebSearch")
            self._w_tools.setText(" ".join(config.allowed_tools))
            lay.addRow(self._lbl("allowed-tools"), self._w_tools)

        if isinstance(config, ProceduralSkillConfig):
            self._w_context = self._combo([e.value for e in SkillContext])
            idx = self._w_context.findText(config.context.value)
            if idx >= 0:
                self._w_context.setCurrentIndex(idx)
            lay.addRow(self._lbl("context"), self._w_context)

            self._w_disable_model = QCheckBox()
            self._w_disable_model.setChecked(config.disable_model_invocation)
            lay.addRow(self._lbl("disable-model-invocation"), self._w_disable_model)

            self._w_user_invocable = QCheckBox()
            self._w_user_invocable.setChecked(config.user_invocable)
            lay.addRow(self._lbl("user-invocable"), self._w_user_invocable)

            self._w_paths = self._input()
            self._w_paths.setPlaceholderText("src/**/*.py")
            if config.paths:
                self._w_paths.setText(" ".join(config.paths))
            lay.addRow(self._lbl("paths (glob)"), self._w_paths)

            self._w_shell = self._combo([e.value for e in SkillShell])
            idx = self._w_shell.findText(config.shell.value)
            if idx >= 0:
                self._w_shell.setCurrentIndex(idx)
            lay.addRow(self._lbl("shell"), self._w_shell)

        # output_events (ProceduralSkill / AgentDefinition)
        if hasattr(comp, "output_events"):
            self._w_output_events = self._input()
            self._w_output_events.setPlaceholderText("done error")
            self._w_output_events.setText(" ".join(comp.output_events))
            self._w_output_events.editingFinished.connect(self._on_output_events_changed)
            lay.addRow(self._lbl("output_events"), self._w_output_events)

    def _on_output_events_changed(self) -> None:
        if not hasattr(self, "_w_output_events"):
            return
        raw = self._w_output_events.text().strip()
        events = [e for e in raw.split() if e] or ["done"]
        if hasattr(self._component, "output_events"):
            self._component.output_events = events
        self.skill_changed.emit()
        if self._on_notify_fn is not None:
            self._on_notify_fn()

    def _build_sections(self) -> None:
        for section in SkillSection:
            always = section == SkillSection.INSTRUCTIONS
            card = _SectionCard(section, always_active=always)
            self._section_cards.append(card)
            self._body_layout.addWidget(card)
        self._body_layout.addStretch()

    def _build_buttons(self) -> None:
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(
            "background: #1a3a1a; border: 1px solid #4a8a4a; color: #88cc88; padding: 5px 14px;"
        )
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        preview_btn = QPushButton("SKILL.md 미리보기")
        preview_btn.setStyleSheet(
            "background: #2a1a2a; border: 1px solid #6a4a8a; color: #aa88cc; padding: 5px 14px;"
        )
        preview_btn.clicked.connect(self._on_preview)
        btn_layout.addWidget(preview_btn)

        self._body_layout.insertWidget(self._body_layout.count() - 1, btn_row)

    def _on_save(self) -> None:
        self._component.name = self._w_name.text().strip()
        self._component.description = self._w_desc.toPlainText().strip()
        self.skill_changed.emit()

    def _on_preview(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "SKILL.md 미리보기", "컴파일러 미구현 (B-stage 스코프 외)"
        )
