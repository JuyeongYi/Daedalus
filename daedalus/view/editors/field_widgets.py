# daedalus/view/editors/field_widgets.py
"""SkillField / AgentField → 편집 위젯 매핑 (view 레이어).

field_matrix.py(model)에서 분리된 위젯 선택 책임을 담는다. 위젯 선택은
스킬 kind와 무관함이 확인되어 1차원 dict로 충분하다 — 한 SkillField는
모든 kind에서 동일한 위젯 타입을 사용한다.

주의(AGENT ↔ TransferSkillConfig 부재 함정):
    SKILL_FIELD_MATRIX에서 transfer/local_* kind는 AGENT 필드가 비노출(D)이라
    TransferSkillConfig에 `agent` 속성이 없어도 안전하다. 소비부(skill_editor)는
    attr 접근 시 getattr 기본값/hasattr 가드로 방어한다.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLineEdit, QSpinBox, QTextEdit, QWidget

from daedalus.model.plugin.enums import AgentField, SkillField
from daedalus.view.widgets.combo_widgets import (
    AgentColorComboBox,
    AgentIsolationComboBox,
    ContextComboBox,
    EffortComboBox,
    MemoryScopeComboBox,
    ModelComboBox,
    PermissionModeComboBox,
    ShellComboBox,
)
from daedalus.view.widgets.preset_picker import HookPresetPicker
from daedalus.view.widgets.tag_input import TagInput

# SkillField → 위젯 클래스. SKILL_FIELD_MATRIX의 전 필드를 커버해야 한다.
FIELD_WIDGETS: dict[SkillField, type[QWidget]] = {
    SkillField.NAME:           QLineEdit,
    SkillField.DESCRIPTION:    QLineEdit,
    SkillField.WHEN_TO_USE:    QTextEdit,
    SkillField.ARGUMENT_HINT:  QLineEdit,
    SkillField.MODEL:          ModelComboBox,
    SkillField.EFFORT:         EffortComboBox,
    SkillField.ALLOWED_TOOLS:  TagInput,
    SkillField.CONTEXT:        ContextComboBox,
    SkillField.AGENT:          QLineEdit,
    SkillField.SHELL:          ShellComboBox,
    SkillField.PATHS:          TagInput,
    SkillField.HOOKS:          HookPresetPicker,
    SkillField.DISABLE_MODEL:  QCheckBox,
    SkillField.USER_INVOCABLE: QCheckBox,
}

# AgentField → 위젯 클래스 (NAME/DESCRIPTION 제외 — 공통 헤더에서 처리).
AGENT_FIELD_WIDGETS: dict[AgentField, type[QWidget]] = {
    AgentField.MODEL:            ModelComboBox,
    AgentField.EFFORT:           EffortComboBox,
    AgentField.TOOLS:            TagInput,
    AgentField.DISALLOWED_TOOLS: TagInput,
    AgentField.PERMISSION_MODE:  PermissionModeComboBox,
    AgentField.SKILLS:           TagInput,
    AgentField.MEMORY:           MemoryScopeComboBox,
    AgentField.COLOR:            AgentColorComboBox,
    AgentField.HOOKS:            HookPresetPicker,
    AgentField.MAX_TURNS:        QSpinBox,
    AgentField.BACKGROUND:       QCheckBox,
    AgentField.ISOLATION:        AgentIsolationComboBox,
    AgentField.MCP_SERVERS:      TagInput,
}
