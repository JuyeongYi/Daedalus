# tests/model/plugin/test_field_matrix.py
from __future__ import annotations

from daedalus.model.plugin.enums import AgentField, FieldEmit, FieldVisibility, SkillField


def test_field_visibility_values():
    assert FieldVisibility.REQUIRED.value == "required"
    assert FieldVisibility.OPTIONAL.value == "optional"
    assert FieldVisibility.DEFAULT.value == "default"
    assert FieldVisibility.FIXED.value == "fixed"


def test_skill_field_values():
    assert SkillField.NAME.value == "name"
    assert SkillField.MODEL.value == "model"
    assert SkillField.HOOKS.value == "hooks"
    assert SkillField.DISABLE_MODEL.value == "disable_model_invocation"
    assert SkillField.USER_INVOCABLE.value == "user_invocable"
    assert SkillField.BACKGROUND.value == "background"  # fork 2종 FIXED
    assert len(SkillField) == 15
    # 프론트매터 출력 순서는 enum 선언 순서다 — fork는 context·agent·background가
    # 붙어 나와야 읽힌다.
    order = [f.name for f in SkillField]
    assert order[order.index("CONTEXT"):order.index("CONTEXT") + 3] == [
        "CONTEXT", "AGENT", "BACKGROUND",
    ]


from daedalus.model.plugin.field_matrix import FieldRule, SKILL_FIELD_MATRIX


def test_field_rule_dataclass():
    r = FieldRule(FieldVisibility.REQUIRED, default_value="test")
    assert r.visibility == FieldVisibility.REQUIRED
    assert r.default_value == "test"
    assert r.fixed_value is None
    # FieldRule은 순수 모델 — widget 속성을 갖지 않는다.
    assert not hasattr(r, "widget")


def test_matrix_has_all_skill_kinds():
    expected = {
        "procedural", "sync_fork", "async_fork", "declarative", "transfer",
        "reference",
    }
    assert set(SKILL_FIELD_MATRIX.keys()) == expected


def test_matrix_procedural_model_required():
    from daedalus.model.plugin.enums import ModelType
    rules = SKILL_FIELD_MATRIX["procedural"]
    assert rules[SkillField.MODEL].visibility == FieldVisibility.REQUIRED
    assert rules[SkillField.MODEL].default_value == ModelType.INHERIT


def test_matrix_transfer_fixed_values():
    rules = SKILL_FIELD_MATRIX["transfer"]
    assert rules[SkillField.DISABLE_MODEL].visibility == FieldVisibility.FIXED
    assert rules[SkillField.DISABLE_MODEL].fixed_value is False
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_reference_user_invocable_fixed():
    rules = SKILL_FIELD_MATRIX["reference"]
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_fork_context_fixed_agent_required():
    """fork 2종 — context는 고정 출력, agent는 필수(기본 general-purpose 명시)."""
    for kind in ("sync_fork", "async_fork"):
        rules = SKILL_FIELD_MATRIX[kind]
        assert rules[SkillField.CONTEXT].visibility == FieldVisibility.FIXED
        assert rules[SkillField.CONTEXT].fixed_value == "fork"
        assert rules[SkillField.AGENT].visibility == FieldVisibility.REQUIRED
        assert rules[SkillField.AGENT].default_value == "general-purpose"
        # 편집기는 선언 순서로 그린다 — fork 에이전트가 이름·설명 바로 다음에 보인다.
        assert list(rules)[:3] == [
            SkillField.NAME, SkillField.DESCRIPTION, SkillField.AGENT,
        ]


def test_matrix_background_fixed_splits_the_two_forks():
    """background가 두 fork 종류를 가른다 — 동기 false / 비동기 true, 둘 다 FIXED.

    FIXED라 편집기에 나오지 않고 config에도 없다(종류가 곧 값이다).
    """
    sync_rule = SKILL_FIELD_MATRIX["sync_fork"][SkillField.BACKGROUND]
    async_rule = SKILL_FIELD_MATRIX["async_fork"][SkillField.BACKGROUND]
    assert sync_rule.visibility == FieldVisibility.FIXED
    assert sync_rule.fixed_value is False
    assert async_rule.visibility == FieldVisibility.FIXED
    assert async_rule.fixed_value is True
    # 두 표는 background 말고 완전히 같다.
    def without_background(kind):
        return {
            k: v for k, v in SKILL_FIELD_MATRIX[kind].items()
            if k is not SkillField.BACKGROUND
        }

    assert without_background("sync_fork") == without_background("async_fork")


# kind별 **명시적 부재** 필드 (WP-WR) — 매트릭스 부재 = 그 kind에 비적용.
# 컴파일러(_frontmatter_lines_skill)는 부재를 건너뛰므로 KeyError는 없지만,
# 부재는 여기 등재된 것만 허용한다 — 등재 없는 누락은 실수다.
# HOOKS는 전 스킬 종류에 **있다** (2026-09-13 실측 — SKILL.md 스키마에 "Hooks
# registered while this skill is active" 필드가 있고 로컬·플러그인 스킬 모두 훅이
# 돈다). 2026-09-07에 전 종류에서 뺐던 것은 틀린 판단이었다.
# context·agent는 fork 스킬 전용이다(사용자 확정 2026-09-13 — 나머지 스킬은 fork·
# agent 지정 불가). fork는 allowed_tools가 없다(에이전트 도구가 이긴다 — 실측).
_FORK_ONLY = {SkillField.CONTEXT, SkillField.AGENT, SkillField.BACKGROUND}
_KIND_ABSENT_FIELDS = {
    "procedural": set(_FORK_ONLY),
    "sync_fork": {SkillField.ALLOWED_TOOLS},
    "async_fork": {SkillField.ALLOWED_TOOLS},
    # declarative/reference에는 SHELL이 없다 — 두 config가 `shell`을 선언하지
    # 않고 직렬화도 그 키를 쓰지 않는다(2026-09-18 리뷰: 표에만 있던 시절에는
    # 편집기가 콤보박스를 그려 주고 그 값이 저장 한 번에 사라졌다).
    "declarative": {SkillField.SHELL} | _FORK_ONLY,
    "transfer": set(_FORK_ONLY),
    # reference는 DISABLE_MODEL도 없다 — ReferenceSkillConfig는 user_invocable만
    # 선언한다.
    "reference": {
        SkillField.SHELL, SkillField.DISABLE_MODEL,
    } | _FORK_ONLY,
}


def test_matrix_all_kinds_have_all_fields():
    """모든 kind가 전 SkillField를 커버한다 — 명시 부재 목록 제외 (WP-WR)."""
    for kind, rules in SKILL_FIELD_MATRIX.items():
        absent = _KIND_ABSENT_FIELDS[kind]
        assert set(rules) == set(SkillField) - absent, f"{kind} 필드 집합 불일치"


# ---------------------------------------------------------------------------
# 표 ↔ config 일치 (2026-09-18 리뷰) — 표에 있는 편집 가능 필드는 config에 있다
# ---------------------------------------------------------------------------

#: 컴포넌트 본체가 가진 필드 — config가 아니라 name/description/when_to_use다.
_COMPONENT_LEVEL_FIELDS = frozenset({
    SkillField.NAME, SkillField.DESCRIPTION, SkillField.WHEN_TO_USE,
    AgentField.NAME, AgentField.DESCRIPTION,
})


def _configs_by_kind() -> dict:
    """구체 config 클래스 전부를 `kind` → 인스턴스로. 손으로 적은 표가 아니다."""
    from daedalus.model.plugin.config import ComponentConfig

    out: dict = {}
    stack = [ComponentConfig]
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if getattr(cls, "__abstractmethods__", None):
            continue  # 추상 — 인스턴스화 금지
        cfg = cls()
        out[cfg.kind] = cfg
    return out


def test_every_editable_matrix_field_exists_on_the_config():
    """표에 있는 **비-FIXED** 필드는 그 종류의 config에 실제로 있다.

    없으면 편집기가 위젯을 그려 주고 그 편집이 아무 데도 남지 않는다 —
    write-back은 유령 인스턴스 속성을 만들거나(저장 한 번에 소멸) 가드에
    삼켜진다. MCP `list_component_fields`는 `hasattr`로 건너뛰므로 같은 종류에
    대해 GUI와 MCP가 **다른 필드 목록**을 말하게 된다(원칙 1·2·5).

    2026-09-18 실측으로 걸린 세 행: declarative/reference의 `shell`,
    reference의 `disable_model_invocation`.
    """
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX

    configs = _configs_by_kind()
    for table in (SKILL_FIELD_MATRIX, AGENT_FIELD_MATRIX):
        for kind, rules in table.items():
            assert kind in configs, f"매트릭스 종류 '{kind}'에 대응하는 config 클래스가 없다"
            cfg = configs[kind]
            for fld, rule in rules.items():
                if fld in _COMPONENT_LEVEL_FIELDS:
                    continue
                if rule.visibility is FieldVisibility.FIXED:
                    continue  # FIXED는 컴파일러 지시라 config에 두지 않는다
                assert hasattr(cfg, fld.value), (
                    f"{kind} 표의 {fld.name}에 대응하는 "
                    f"{type(cfg).__name__}.{fld.value} 필드가 없다"
                )


def test_declarative_and_reference_have_no_shell_row():
    """부재를 명시로 고정한다 — 되돌리려면 config·직렬화를 같이 고쳐야 한다."""
    assert SkillField.SHELL not in SKILL_FIELD_MATRIX["declarative"]
    assert SkillField.SHELL not in SKILL_FIELD_MATRIX["reference"]
    assert SkillField.DISABLE_MODEL not in SKILL_FIELD_MATRIX["reference"]
    # 형제 종류에는 그대로 있다(전면 삭제가 아니다).
    assert SkillField.SHELL in SKILL_FIELD_MATRIX["procedural"]
    assert SkillField.SHELL in SKILL_FIELD_MATRIX["transfer"]
    assert SkillField.DISABLE_MODEL in SKILL_FIELD_MATRIX["declarative"]


# ---------------------------------------------------------------------------
# WP-E: frontmatter_key 매핑
# ---------------------------------------------------------------------------

def test_frontmatter_key_mapping():
    """WHEN_TO_USE → None(직출 금지), 나머지 → kebab-case."""
    assert SkillField.WHEN_TO_USE.frontmatter_key is None
    for field in SkillField:
        if field is SkillField.WHEN_TO_USE:
            continue
        key = field.frontmatter_key
        assert key is not None
        assert "_" not in key, f"{field.value} → {key!r} (snake_case 잔존)"
        assert key == field.value.replace("_", "-")

    # 대표 케이스 명시 단언
    assert SkillField.ARGUMENT_HINT.frontmatter_key == "argument-hint"
    assert SkillField.ALLOWED_TOOLS.frontmatter_key == "allowed-tools"
    assert SkillField.DISABLE_MODEL.frontmatter_key == "disable-model-invocation"
    assert SkillField.USER_INVOCABLE.frontmatter_key == "user-invocable"
    assert SkillField.NAME.frontmatter_key == "name"
    assert SkillField.MODEL.frontmatter_key == "model"


def test_model_default_is_inherit():
    """MODEL default_value의 단일 진실은 ModelType.INHERIT."""
    from daedalus.model.plugin.enums import ModelType

    for kind, rules in SKILL_FIELD_MATRIX.items():
        rule = rules[SkillField.MODEL]
        assert rule.default_value == ModelType.INHERIT, (
            f"{kind} MODEL default_value: {rule.default_value!r}"
        )
        assert rule.default_value != "sonnet"


def test_field_matrix_is_pyqt_free():
    """field_matrix(및 daedalus.model 전체)가 PySide6 없이 import 가능해야 한다.

    builtins.__import__를 후킹해 'PySide6'를 import하려는 순간 ImportError를 던지는
    하위 프로세스에서, daedalus.model.plugin.field_matrix를 import한다. model/
    어디서도 PySide6가 import되지 않음을 CI 수준에서 고정한다.
    """
    import subprocess
    import sys

    code = (
        "import builtins\n"
        "_real = builtins.__import__\n"
        "def _blocked(name, *a, **k):\n"
        "    if name == 'PySide6' or name.startswith('PySide6.'):\n"
        "        raise ImportError('PySide6 import blocked for purity test')\n"
        "    return _real(name, *a, **k)\n"
        "builtins.__import__ = _blocked\n"
        "import daedalus.model.plugin.field_matrix  # noqa: F401\n"
        "import daedalus.model  # noqa: F401\n"
        "from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX, FieldRule\n"
        "assert SKILL_FIELD_MATRIX\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"PySide6 차단 하에 daedalus.model import 실패:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# WP-H: AGENT_FIELD_MATRIX + FieldEmit 신설
# ---------------------------------------------------------------------------

# 에이전트 kind별 **명시적 부재** 필드 — 스킬 쪽 `_KIND_ABSENT_FIELDS`와 같은 규약이다.
# 부재는 여기 등재된 것만 허용한다 — 등재 없는 누락은 실수다.
_AGENT_KIND_ABSENT_FIELDS = {
    # 워크플로 에이전트는 전 필드를 갖는다 — SOURCE만 외부 에이전트 전용이다(WP-9).
    "agent": {AgentField.SOURCE},
    # background는 fork 스킬 종류가 정하고 isolation은 fork 실행에 적용되지
    # 않는다(실측 2026-09-13) — 없는 필드를 두면 걸어 둔 제약이 조용히 사라진다.
    "fork_agent": {
        AgentField.SOURCE, AgentField.BACKGROUND, AgentField.ISOLATION,
    },
    # 외부 플러그인 에이전트 2역할(WP-9/WP-EX)은 **산출 파일이 없다** —
    # 프론트매터가 나갈 자리 자체가 없으므로 우리가 쓸 수 없는 필드를 두지
    # 않는다. 두 역할은 같은 표를 쓴다(편집할 수 있는 것이 같다).
    "external_agent": set(AgentField) - {
        AgentField.NAME, AgentField.DESCRIPTION, AgentField.SOURCE,
    },
    "external_fork_agent": set(AgentField) - {
        AgentField.NAME, AgentField.DESCRIPTION, AgentField.SOURCE,
    },
}


def test_agent_matrix_all_kinds_have_all_fields():
    """모든 에이전트 kind가 전 AgentField를 커버한다 — 명시 부재 목록 제외."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    assert set(AGENT_FIELD_MATRIX) == set(_AGENT_KIND_ABSENT_FIELDS)
    for kind, rules in AGENT_FIELD_MATRIX.items():
        absent = _AGENT_KIND_ABSENT_FIELDS[kind]
        assert set(rules) == set(AgentField) - absent, f"{kind} 필드 집합 불일치"


def test_external_agent_matrix_emits_nothing():
    """산출 파일이 없는 종류는 **배출 행을 하나도 갖지 않는다** (WP-9).

    표에 FRONTMATTER/BODY/SETTINGS 행을 남기면 편집기와 MCP `set_component_field`가
    값을 받아 놓고 아무 일도 하지 않는다(원칙 5).
    """
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    rules = AGENT_FIELD_MATRIX["external_agent"]
    assert {rule.emit for rule in rules.values()} == {FieldEmit.NONE}


def test_max_turns_background_isolation_are_frontmatter():
    """MAX_TURNS/BACKGROUND/ISOLATION은 프론트매터 필드다 (WP-FF).

    CC 서브에이전트 프론트매터가 이 셋을 지원하므로, 본문 안내문("호출 파라미터")이
    아니라 프론트매터로 나가야 CC 런타임이 직접 강제한다.
    """
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    rules = AGENT_FIELD_MATRIX["agent"]
    for af in (AgentField.MAX_TURNS, AgentField.BACKGROUND, AgentField.ISOLATION):
        assert rules[af].emit == FieldEmit.FRONTMATTER, (
            f"{af} emit이 FRONTMATTER가 아님: {rules[af].emit!r}"
        )


def test_agent_field_matrix_emit_settings():
    """HOOKS/MCP_SERVERS의 emit은 SETTINGS이어야 한다 (가진 종류 전수)."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    for kind, rules in AGENT_FIELD_MATRIX.items():
        for af in (AgentField.HOOKS, AgentField.MCP_SERVERS):
            if af not in rules:
                # 부재는 `_AGENT_KIND_ABSENT_FIELDS`가 이미 전수 고정한다.
                assert af in _AGENT_KIND_ABSENT_FIELDS[kind]
                continue
            assert rules[af].emit == FieldEmit.SETTINGS, (
                f"{kind}/{af} emit이 SETTINGS이 아님: {rules[af].emit!r}"
            )


def test_agent_field_matrix_emit_frontmatter():
    """HOOKS/MCP_SERVERS/MAX_TURNS/BACKGROUND/ISOLATION을 제외한 나머지는 FRONTMATTER이어야 한다."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    non_frontmatter = {
        AgentField.HOOKS, AgentField.MCP_SERVERS,
        AgentField.MAX_TURNS, AgentField.BACKGROUND, AgentField.ISOLATION,
    }
    for kind, rules in AGENT_FIELD_MATRIX.items():
        # 산출 파일이 없는 종류는 배출 행이 없다 —
        # `test_external_agent_matrix_emits_nothing`이 그쪽을 전수 고정한다.
        if {rule.emit for rule in rules.values()} == {FieldEmit.NONE}:
            continue
        for af, rule in rules.items():
            if af in non_frontmatter:
                continue
            assert rule.emit == FieldEmit.FRONTMATTER, (
                f"{kind}/{af} emit이 FRONTMATTER이 아님: {rule.emit!r}"
            )


def test_skill_matrix_when_to_use_emit_body():
    """모든 스킬 매트릭스에서 WHEN_TO_USE.emit == BODY이어야 한다."""
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
    for kind, rules in SKILL_FIELD_MATRIX.items():
        rule = rules[SkillField.WHEN_TO_USE]
        assert rule.emit == FieldEmit.BODY, (
            f"{kind} WHEN_TO_USE.emit이 BODY가 아님: {rule.emit!r}"
        )


def test_skill_matrix_other_fields_emit_frontmatter():
    """스킬 매트릭스에서 WHEN_TO_USE(본문 배출) 외 필드의 emit은 FRONTMATTER."""
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
    for kind, rules in SKILL_FIELD_MATRIX.items():
        for fld, rule in rules.items():
            if fld is SkillField.WHEN_TO_USE:
                continue
            assert rule.emit == FieldEmit.FRONTMATTER, (
                f"{kind}/{fld} emit이 FRONTMATTER이 아님: {rule.emit!r}"
            )


def test_agent_field_frontmatter_key_kebab_case():
    """AgentField 전 멤버의 frontmatter_key가 camelCase여야 한다 — SOURCE는 None."""
    # SOURCE(WP-9)는 프론트매터 키가 아니다 — 외부 플러그인 에이전트는 산출
    # 파일 자체가 없고, 내면 CC가 모르는 키라 조용히 무시된다.
    assert AgentField.SOURCE.frontmatter_key is None
    for af in AgentField:
        if af is AgentField.SOURCE:
            continue
        key = af.frontmatter_key
        assert key is not None, f"{af} frontmatter_key가 None"
        assert "_" not in key, f"{af} frontmatter_key에 underscore 잔존: {key!r}"
        assert "-" not in key, f"{af} frontmatter_key는 camelCase여야 한다: {key!r}"

    # 대표 케이스 명시 단언 — CC 공식 sub-agents 문서의 필드 표와 일치해야 한다.
    # 스킬 프론트매터(allowed-tools 등 kebab-case)와 규약이 다르므로 유추 금지.
    assert AgentField.PERMISSION_MODE.frontmatter_key == "permissionMode"
    assert AgentField.DISALLOWED_TOOLS.frontmatter_key == "disallowedTools"
    assert AgentField.MCP_SERVERS.frontmatter_key == "mcpServers"
    assert AgentField.MAX_TURNS.frontmatter_key == "maxTurns"
    assert AgentField.NAME.frontmatter_key == "name"


def test_field_rule_has_emit_field():
    """FieldRule 인스턴스에 emit 필드가 존재하고 기본값은 FRONTMATTER이다."""
    from daedalus.model.plugin.field_matrix import FieldRule
    r = FieldRule(FieldVisibility.REQUIRED)
    assert hasattr(r, "emit")
    assert r.emit == FieldEmit.FRONTMATTER

    r_body = FieldRule(FieldVisibility.OPTIONAL, emit=FieldEmit.BODY)
    assert r_body.emit == FieldEmit.BODY
