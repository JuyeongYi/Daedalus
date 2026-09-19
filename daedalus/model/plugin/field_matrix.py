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

from daedalus.model.plugin.config import (
    AgentConfig,
    AsyncForkSkillConfig,
    DeclarativeSkillConfig,
    ExternalAgentConfig,
    ForkAgentConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    SyncForkSkillConfig,
    TransferSkillConfig,
    WrappedSkillConfig,
)
from daedalus.model.plugin.enums import (
    AgentField,
    AgentIsolation,
    BuildTarget,
    FieldEmit,
    FieldVisibility,
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
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(O),
    SkillField.HOOKS:          FieldRule(O),
    SkillField.DISABLE_MODEL:  FieldRule(O),
    SkillField.USER_INVOCABLE: FieldRule(O),
}

# fork 스킬 (사용자 확정 2026-09-13/2026-09-17) — `context: fork`는 이 계열의
# 정체라 고정 출력이고, 실행할 서브에이전트(`agent`)는 반드시 있다(비우면 CC가
# 조용히 general-purpose로 돈다 — 기본값을 명시 배출한다). allowed_tools는 없다:
# fork에서는 에이전트 도구가 이기고 스킬 쪽은 도구를 늘리지 못한다(실측, CC 2.1.268).
#
# `background`는 동기/비동기를 가르는 **FIXED** 필드다 — 종류가 곧 값이라 편집기에
# 노출하지 않고 config에도 두지 않는다(컴파일러가 강제 배출).
# `CONTEXT`/`AGENT`/`BACKGROUND` 세 행은 이 두 표에만 있다(사용자 확정).
#
# 편집기는 스킬 매트릭스를 선언 순서대로 그린다 — AGENT를 설명 바로 아래에 두어
# "어느 서브에이전트에서 도는 스킬인가"가 먼저 보이게 한다(사용자 요청 2026-09-13).
def _fork_matrix(*, background: bool) -> dict[SkillField, FieldRule]:
    return {
        SkillField.NAME:           FieldRule(R),
        SkillField.DESCRIPTION:    FieldRule(R),
        SkillField.AGENT:          FieldRule(R, default_value="general-purpose"),
        SkillField.WHEN_TO_USE:    FieldRule(O, emit=FieldEmit.BODY),
        SkillField.ARGUMENT_HINT:  FieldRule(O),
        SkillField.MODEL:          FieldRule(R, default_value=ModelType.INHERIT),
        SkillField.EFFORT:         FieldRule(O),
        SkillField.CONTEXT:        FieldRule(F, fixed_value="fork"),
        SkillField.BACKGROUND:     FieldRule(F, fixed_value=background),
        SkillField.SHELL:          FieldRule(O),
        SkillField.PATHS:          FieldRule(O),
        SkillField.HOOKS:          FieldRule(O),
        SkillField.DISABLE_MODEL:  FieldRule(O),
        SkillField.USER_INVOCABLE: FieldRule(O),
    }


_SYNC_FORK: dict[SkillField, FieldRule] = _fork_matrix(background=False)
_ASYNC_FORK: dict[SkillField, FieldRule] = _fork_matrix(background=True)

# WP-WR 랩핑 스킬 — 본문의 정본은 source가 가리키는 외부 스킬이라, 본문을
# 만드는 필드(shell)는 없다. source는 프론트매터가 아니라 본문
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
    # SHELL은 없다 — `DeclarativeSkillConfig`에 `shell` 필드가 없고 직렬화도
    # 그 키를 쓰지 않는다(ser.py의 declarative 분기). 표에만 있던 시절에는
    # 편집기가 콤보박스를 그려 주고 그 값이 저장 한 번에 사라졌다(2026-09-18
    # 리뷰). **표와 config는 같은 사실을 말한다** — 커버리지 테스트가 고정한다.
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
    SkillField.SHELL:          FieldRule(O),
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(O),
    # 전이 스킬은 앞 스킬의 "다음 단계"가 **모델에게 인보크시키는** 단계다. 예전에는
    # disable-model-invocation을 true로 고정해 사용자(user-invocable false)도 모델도
    # 부를 수 없었다 — 지시문만 있고 본문은 영영 실리지 않는 죽은 단계(2026-09-13 점검).
    # 모델 호출은 열고, 슬래시 메뉴 노출만 막는다.
    SkillField.DISABLE_MODEL:  FieldRule(F, fixed_value=False),
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
    # SHELL·DISABLE_MODEL은 없다 — `ReferenceSkillConfig`는 둘 다 선언하지
    # 않고(config.py) 직렬화도 `user_invocable`만 왕복한다(ser.py의 reference
    # 분기). 표에만 있던 시절에는 편집기가 두 행을 그려 주고 그 편집이 저장
    # 한 번에 사라졌다(2026-09-18 리뷰).
    SkillField.PATHS:          FieldRule(D),
    SkillField.HOOKS:          FieldRule(D),
    SkillField.USER_INVOCABLE: FieldRule(F, fixed_value=False),
}

# fmt: on

#: 키는 **설정 클래스의 선언**에서 읽는다 — 문자열을 베껴 두면 종류 어휘를
#: 바꿀 때 여기만 남아 `matrix_for`가 조용히 "표가 없다"고 말한다(WP-3).
SKILL_FIELD_MATRIX: dict[str, dict[SkillField, FieldRule]] = {
    ProceduralSkillConfig.KIND: _PROCEDURAL,
    SyncForkSkillConfig.KIND: _SYNC_FORK,
    AsyncForkSkillConfig.KIND: _ASYNC_FORK,
    DeclarativeSkillConfig.KIND: _DECLARATIVE,
    WrappedSkillConfig.KIND: _WRAPPED,
    TransferSkillConfig.KIND: _TRANSFER,
    ReferenceSkillConfig.KIND: _REFERENCE,
}

# fmt: off
_AGENT: dict[AgentField, FieldRule] = {
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
    # 필드 표, 2026-08 확인). 이전에는 "호출 파라미터" 본문 안내문으로만 나갔는데,
    # 그러면 부르는 쪽이 문장을 읽고 따라야 적용된다 — 프론트매터에 있으면 CC
    # 런타임이 직접 읽어 강제한다 (WP-FF).
    AgentField.MAX_TURNS:        FieldRule(O),
    AgentField.BACKGROUND:       FieldRule(O),
    AgentField.ISOLATION:        FieldRule(O, default_value=AgentIsolation.NONE),
    AgentField.MCP_SERVERS:      FieldRule(O, emit=FieldEmit.SETTINGS),
}

# fork 에이전트 — background·isolation이 없다(ForkAgentConfig와 같은 사실):
# 백그라운드 여부는 fork 스킬 종류가 정하고, isolation은 fork 실행에 적용되지
# 않는다(실측 2026-09-13). 나머지 행은 워크플로 에이전트와 같다.
_FORK_AGENT: dict[AgentField, FieldRule] = {
    afield: rule for afield, rule in _AGENT.items()
    if afield not in (AgentField.BACKGROUND, AgentField.ISOLATION)
}

# WP-9 외부 플러그인 에이전트 — **산출 파일이 없는 종류는 프론트매터 필드를
# 갖지 않는다**. model/effort/tools/permission_mode/max_turns/skills/memory/color는
# 전부 그 플러그인이 소유한 파일의 값이라 우리가 쓸 수 없고, 표에 남기면
# 편집기와 MCP `set_component_field`가 값을 받아 놓고 아무 일도 하지 않는다
# (원칙 5). 그래서 세 행 전부 `FieldEmit.NONE`("편집 필드이지만 배출 없음")이고,
# `test_kind_registry_parity.test_kinds_that_emit_a_file_have_frontmatter_rows`가
# 산출 유무 ↔ 배출 행 유무를 양방향으로 고정한다.
_EXTERNAL_AGENT: dict[AgentField, FieldRule] = {
    AgentField.NAME:        FieldRule(R, emit=FieldEmit.NONE),
    AgentField.DESCRIPTION: FieldRule(R, emit=FieldEmit.NONE),
    AgentField.SOURCE:      FieldRule(R, emit=FieldEmit.NONE),
}
# fmt: on

AGENT_FIELD_MATRIX: dict[str, dict[AgentField, FieldRule]] = {
    AgentConfig.KIND: _AGENT,
    ForkAgentConfig.KIND: _FORK_AGENT,
    ExternalAgentConfig.KIND: _EXTERNAL_AGENT,
}


def matrix_for(component: object) -> dict[Any, FieldRule]:
    """이 컴포넌트가 따르는 프론트매터 표 — **표를 고르는 규칙의 실체는 여기 하나다**.

    키는 `component.config.kind`다(단일 진실). 컴파일러·MCP·편집기가 전부 이
    함수를 부른다 — 세 곳이 각자 맨 첨자/`.get(kind, {})`를 쓰면 한쪽은 앱을
    죽이고 다른 쪽은 조용한 빈 폼이 된다.

    Raises:
        ValueError: config가 없거나 그 kind가 어느 표에도 없을 때. 어느 종류가
            어느 표에 없는지 말한다(조용한 폴백 금지 — 원칙 5).
    """
    config = getattr(component, "config", None)
    kind = getattr(config, "kind", None)
    if kind is None:
        raise ValueError(
            f"'{getattr(component, 'name', '?')}'"
            f"({type(component).__name__})에는 config.kind가 없어 프론트매터 표를 "
            f"고를 수 없습니다."
        )
    if kind in AGENT_FIELD_MATRIX:
        return dict(AGENT_FIELD_MATRIX[kind])
    if kind in SKILL_FIELD_MATRIX:
        return dict(SKILL_FIELD_MATRIX[kind])
    raise ValueError(
        f"config 종류 '{kind}'에 해당하는 프론트매터 표가 없습니다 — "
        f"스킬 표: {', '.join(sorted(SKILL_FIELD_MATRIX))} / "
        f"에이전트 표: {', '.join(sorted(AGENT_FIELD_MATRIX))}."
    )


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
