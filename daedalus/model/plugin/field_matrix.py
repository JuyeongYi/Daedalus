# daedalus/model/plugin/field_matrix.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PyQt6.QtWidgets import QCheckBox, QLineEdit, QTextEdit, QWidget

from daedalus.model.plugin.enums import FieldVisibility, SkillField
from daedalus.view.widgets.combo_widgets import (
    ContextComboBox,
    EffortComboBox,
    ModelComboBox,
    ShellComboBox,
)
from daedalus.view.widgets.preset_picker import HookPresetPicker
from daedalus.view.widgets.tag_input import TagInput

R = FieldVisibility.REQUIRED
O = FieldVisibility.OPTIONAL
D = FieldVisibility.DEFAULT
F = FieldVisibility.FIXED


@dataclass
class FieldRule:
    """프론트매터 필드 규칙 — visibility + widget 클래스 + 값."""
    visibility: FieldVisibility
    widget: type[QWidget]
    fixed_value: Any = None
    default_value: Any = None


# fmt: off
_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(O, QTextEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(O, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(O, ContextComboBox),
    SkillField.AGENT:          FieldRule(O, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(O, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(O, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(O, QCheckBox),
}

_DECLARATIVE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(O, QTextEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(O, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(D, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(D, ShellComboBox),
    SkillField.PATHS:          FieldRule(O, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(O, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(O, QCheckBox),
}

_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(O, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_REFERENCE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(O, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(D, TagInput),
    SkillField.CONTEXT:        FieldRule(D, ContextComboBox),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(D, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(D, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(D, QCheckBox),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_LOCAL_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(D, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(F, ContextComboBox, fixed_value="fork"),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}

_LOCAL_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R, QLineEdit),
    SkillField.DESCRIPTION:    FieldRule(R, QLineEdit),
    SkillField.WHEN_TO_USE:    FieldRule(D, QLineEdit),
    SkillField.ARGUMENT_HINT:  FieldRule(D, QLineEdit),
    SkillField.MODEL:          FieldRule(R, ModelComboBox, default_value="sonnet"),
    SkillField.EFFORT:         FieldRule(D, EffortComboBox),
    SkillField.ALLOWED_TOOLS:  FieldRule(O, TagInput),
    SkillField.CONTEXT:        FieldRule(F, ContextComboBox, fixed_value="fork"),
    SkillField.AGENT:          FieldRule(D, QLineEdit),
    SkillField.SHELL:          FieldRule(O, ShellComboBox),
    SkillField.PATHS:          FieldRule(D, QLineEdit),
    SkillField.HOOKS:          FieldRule(O, HookPresetPicker),
    SkillField.DISABLE_MODEL:  FieldRule(F, QCheckBox, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, QCheckBox, fixed_value=False),
}
# fmt: on

SKILL_FIELD_MATRIX: dict[str, dict[SkillField, FieldRule]] = {
    "procedural": _PROCEDURAL,
    "declarative": _DECLARATIVE,
    "transfer": _TRANSFER,
    "reference": _REFERENCE,
    "local_procedural": _LOCAL_PROCEDURAL,
    "local_transfer": _LOCAL_TRANSFER,
}
