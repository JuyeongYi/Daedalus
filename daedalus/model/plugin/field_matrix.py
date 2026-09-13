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
    BuildTarget,
    FieldEmit,
    FieldVisibility,
    MemoryScope,
    ModelType,
    PermissionMode,
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

# WP-WR 랩핑 스킬 — 본문의 정본은 source가 가리키는 외부 스킬이라, 본문을
# 만드는 필드(shell/context/agent)는 없다. source는 프론트매터가 아니라 본문
# 지시로 emit된다(SkillField.SOURCE.frontmatter_key == None).
_WRAPPED: dict[SkillField, FieldRule] = {
    SkillField.NAME:           FieldRule(R),
    SkillField.DESCRIPTION:    FieldRule(R),
    SkillField.WHEN_TO_USE:    FieldRule(O, emit=FieldEmit.BODY),
    SkillField.SOURCE:         FieldRule(R, emit=FieldEmit.BODY),
    SkillField.ARGUMENT_HINT:  FieldRule(O),
    SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
    SkillField.EFFORT:         FieldRule(O),
    SkillField.ALLOWED_TOOLS:  FieldRule(O),
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

# fmt: on

SKILL_FIELD_MATRIX: dict[str, dict[SkillField, FieldRule]] = {
    "procedural": _PROCEDURAL,
    "declarative": _DECLARATIVE,
    "wrapped": _WRAPPED,
    "transfer": _TRANSFER,
    "reference": _REFERENCE,
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
    # max_turns/background/isolation은 CC 서브에이전트 프론트매터 필드다(공식 문서
    # 필드 표, 2026-08 확인). 이전에는 INVOCATION emit이라 "호출 파라미터" 본문
    # 안내문으로만 나갔는데, 그러면 부르는 쪽이 문장을 읽고 따라야 적용된다 —
    # 프론트매터에 있으면 CC 런타임이 직접 읽어 강제한다 (WP-FF).
    AgentField.MAX_TURNS:        FieldRule(O),
    AgentField.BACKGROUND:       FieldRule(O),
    AgentField.ISOLATION:        FieldRule(O, default_value=AgentIsolation.NONE),
    AgentField.MCP_SERVERS:      FieldRule(O, emit=FieldEmit.SETTINGS),
}
# fmt: on


# CC는 **보안상 플러그인 서브에이전트의 이 필드들을 무시한다**(공식 sub-agents
# 문서: "plugin subagents don't support the hooks, mcpServers, or permissionMode
# frontmatter fields. These fields are ignored when loading agents from a plugin.").
#
# 값이 파일에 남아 있어도 아무 일이 일어나지 않는다 — 설계자가 걸어 둔 제약이
# 조용히 사라진다. 그래서 마켓플레이스 빌드에서는 편집기가 잠그고(view), 컴파일러도
# 배출하지 않으며(compiler), 값이 설정돼 있으면 검증이 경고한다(validation).
# 세 계층이 같은 집합을 봐야 어긋나지 않으므로 여기가 단일 진실이다.
MARKETPLACE_UNSUPPORTED_AGENT_FIELDS: frozenset[AgentField] = frozenset({
    AgentField.HOOKS,
    AgentField.MCP_SERVERS,
    AgentField.PERMISSION_MODE,
})


def agent_field_supported(field: AgentField, build_target: BuildTarget) -> bool:
    """이 빌드 타깃에서 해당 에이전트 필드가 실제로 동작하는가.

    LOCAL(.claude/agents/ 반입)에서는 전부 동작한다 — 플러그인이 아니므로
    플러그인 제약을 받지 않는다.
    """
    if build_target is BuildTarget.MARKETPLACE:
        return field not in MARKETPLACE_UNSUPPORTED_AGENT_FIELDS
    return True
