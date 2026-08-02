# daedalus/model/plugin/field_matrix.py
"""스킬 프론트매터 필드 규칙 매트릭스 (순수 도메인 모델 — Qt 무관).

FieldRule은 visibility + 값만 관리한다. 편집 위젯 선택은 view 레이어의
`daedalus.view.editors.field_widgets.FIELD_WIDGETS`로 분리되어 있다.

FIXED 필드 정책:
    FIXED 필드는 편집기에 노출하지 않으며, fixed_value는 컴파일러가 출력(SKILL.md
    프론트매터 생성) 시점에 강제한다. config 객체에는 기록하지 않는다 — 즉
    fixed_value는 "이 kind에서는 이 값으로 고정 출력하라"는 컴파일러 지시이지,
    런타임 config의 기본값이 아니다. (구현은 컴파일러 WP에서 처리한다.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daedalus.model.plugin.enums import (
    AgentColor,
    AgentField,
    AgentIsolation,
    FieldEmit,
    FieldVisibility,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillField,
)

R = FieldVisibility.REQUIRED
O = FieldVisibility.OPTIONAL
D = FieldVisibility.DEFAULT
F = FieldVisibility.FIXED


@dataclass
class FieldRule:
    """프론트매터 필드 규칙 — visibility + 값 + emit 위치.

    위젯 클래스는 더 이상 여기에 두지 않는다(model→view 의존 역전).
    fixed_value: FIXED일 때 컴파일러가 강제할 출력값 (enum 또는 스칼라).
    default_value: 위젯 초기 표시용 기본값 (단일 진실은 config 선언 기본값).
    emit: 컴파일러가 이 필드를 배출할 위치 (기본값: FRONTMATTER).
    """
    visibility: FieldVisibility
    fixed_value: Any = None
    default_value: Any = None
    emit: FieldEmit = FieldEmit.FRONTMATTER


# fmt: off
_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(O, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(O),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(O),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
    SkillField.CONTEXT:        FieldRule(O),
    SkillField.AGENT:          FieldRule(O),
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(O),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(O),
    SkillField.USER_INVOCABLE: FieldRule(O),
}

_DECLARATIVE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(O, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(O),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(O),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
    SkillField.CONTEXT:        FieldRule(D),
    SkillField.AGENT:          FieldRule(D),
    SkillField.SHELL:          FieldRule(D),
    SkillField.PATHS:          FieldRule(O),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(O),
    SkillField.USER_INVOCABLE: FieldRule(O),
}

_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(D, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(D),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(O),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
    SkillField.CONTEXT:        FieldRule(O),
    SkillField.AGENT:          FieldRule(D),
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(F, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, fixed_value=False),
}

_REFERENCE: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(D, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(D),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(O),
    SkillField.ALLOWED_TOOLS:  FieldRule(D),
    SkillField.CONTEXT:        FieldRule(D),
    SkillField.AGENT:          FieldRule(D),
    SkillField.SHELL:          FieldRule(D),
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(D),
    SkillField.DISABLE_MODEL:  FieldRule(D),
    SkillField.USER_INVOCABLE: FieldRule(F, fixed_value=False),
}

_LOCAL_PROCEDURAL: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(D, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(D),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(D),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
    SkillField.CONTEXT:        FieldRule(F, fixed_value=SkillContext.FORK),
    SkillField.AGENT:          FieldRule(D),
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(F, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, fixed_value=False),
}

_LOCAL_TRANSFER: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(D, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(D),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(D),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
    SkillField.CONTEXT:        FieldRule(F, fixed_value=SkillContext.FORK),
    SkillField.AGENT:          FieldRule(D),
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(F, fixed_value=True),
    SkillField.USER_INVOCABLE: FieldRule(F, fixed_value=False),
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

# fmt: off
AGENT_FIELD_MATRIX: dict[AgentField, FieldRule] = {
    AgentField.NAME:             FieldRule(R),
    AgentField.DESCRIPTION:      FieldRule(R),
    AgentField.MODEL:            FieldRule(R, default_value=ModelType.INHERIT),
    AgentField.EFFORT:           FieldRule(O),
    AgentField.TOOLS:            FieldRule(O),
    AgentField.DISALLOWED_TOOLS: FieldRule(O),
    AgentField.PERMISSION_MODE:  FieldRule(O, default_value=PermissionMode.DEFAULT),
    AgentField.SKILLS:           FieldRule(O),
    AgentField.MEMORY:           FieldRule(O),
    AgentField.COLOR:            FieldRule(O),
    AgentField.HOOKS:            FieldRule(O, emit=FieldEmit.SETTINGS),
    AgentField.MAX_TURNS:        FieldRule(O, emit=FieldEmit.INVOCATION),
    AgentField.BACKGROUND:       FieldRule(O, emit=FieldEmit.INVOCATION),
    AgentField.ISOLATION:        FieldRule(O, default_value=AgentIsolation.NONE, emit=FieldEmit.INVOCATION),
    AgentField.MCP_SERVERS:      FieldRule(O, emit=FieldEmit.SETTINGS),
}
# fmt: on
