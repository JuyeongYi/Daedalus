# daedalus/view/editors/field_widgets.py
"""SkillField / AgentField → 편집 위젯 매핑 (view 레이어).

field_matrix.py(model)에서 분리된 위젯 선택 책임을 담는다. 위젯 선택은
스킬 kind와 무관함이 확인되어 1차원 dict로 충분하다 — 한 SkillField는
모든 kind에서 동일한 위젯 타입을 사용한다.

CONTEXT·BACKGROUND는 fork 스킬에서만 FIXED로 쓰여 편집기에 나오지 않는다
(표 완전성 때문에 등재). AGENT는 fork 스킬 전용이다(`ForkSkillConfig.agent`).
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLineEdit, QSpinBox, QTextEdit, QWidget

from daedalus.model.plugin.enums import AgentField, SkillField
from daedalus.view.widgets.combo_widgets import (
    AgentColorComboBox,
    AgentIsolationComboBox,
    EffortComboBox,
    ForkAgentComboBox,
    MemoryScopeComboBox,
    ModelComboBox,
    PermissionModeComboBox,
    ShellComboBox,
)
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
    SkillField.CONTEXT:        QLineEdit,  # fork 전용 FIXED — 편집기에 그려지지 않는다
    SkillField.AGENT:          ForkAgentComboBox,
    SkillField.BACKGROUND:     QCheckBox,  # fork 2종 FIXED — 종류가 값이라 그려지지 않는다
    SkillField.SHELL:          ShellComboBox,
    SkillField.PATHS:          TagInput,
    SkillField.SOURCE:         QLineEdit,  # WP-WR — plugin@marketplace:skill
    SkillField.HOOKS:          TagInput,
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
    AgentField.HOOKS:            TagInput,
    AgentField.MAX_TURNS:        QSpinBox,
    AgentField.BACKGROUND:       QCheckBox,
    AgentField.ISOLATION:        AgentIsolationComboBox,
    AgentField.MCP_SERVERS:      TagInput,
}
