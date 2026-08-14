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
    assert len(SkillField) == 14


from daedalus.model.plugin.field_matrix import FieldRule, SKILL_FIELD_MATRIX


def test_field_rule_dataclass():
    r = FieldRule(FieldVisibility.REQUIRED, default_value="test")
    assert r.visibility == FieldVisibility.REQUIRED
    assert r.default_value == "test"
    assert r.fixed_value is None
    # FieldRule은 순수 모델 — widget 속성을 갖지 않는다.
    assert not hasattr(r, "widget")


def test_matrix_has_all_skill_kinds():
    expected = {"procedural", "declarative", "transfer", "reference", "local_procedural", "local_transfer"}
    assert set(SKILL_FIELD_MATRIX.keys()) == expected


def test_matrix_procedural_model_required():
    from daedalus.model.plugin.enums import ModelType
    rules = SKILL_FIELD_MATRIX["procedural"]
    assert rules[SkillField.MODEL].visibility == FieldVisibility.REQUIRED
    assert rules[SkillField.MODEL].default_value == ModelType.INHERIT


def test_matrix_transfer_fixed_values():
    rules = SKILL_FIELD_MATRIX["transfer"]
    assert rules[SkillField.DISABLE_MODEL].visibility == FieldVisibility.FIXED
    assert rules[SkillField.DISABLE_MODEL].fixed_value is True
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_reference_user_invocable_fixed():
    rules = SKILL_FIELD_MATRIX["reference"]
    assert rules[SkillField.USER_INVOCABLE].visibility == FieldVisibility.FIXED
    assert rules[SkillField.USER_INVOCABLE].fixed_value is False


def test_matrix_local_procedural_context_fixed_fork():
    from daedalus.model.plugin.enums import SkillContext
    rules = SKILL_FIELD_MATRIX["local_procedural"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.FIXED
    assert rules[SkillField.CONTEXT].fixed_value == SkillContext.FORK


def test_matrix_declarative_context_default():
    rules = SKILL_FIELD_MATRIX["declarative"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.DEFAULT


def test_matrix_all_kinds_have_all_fields():
    """모든 kind에 14개 SkillField가 전부 정의되어 있어야 함."""
    for kind, rules in SKILL_FIELD_MATRIX.items():
        for field in SkillField:
            assert field in rules, f"{kind} missing {field.value}"


# ---------------------------------------------------------------------------
# WP-E: frontmatter_key 매핑
# ---------------------------------------------------------------------------

def test_frontmatter_key_mapping():
    """WHEN_TO_USE → None, 나머지 → kebab-case."""
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


def test_fixed_values_are_enums():
    """매트릭스의 CONTEXT fixed_value는 raw 문자열 'fork'가 아닌 SkillContext enum."""
    from daedalus.model.plugin.enums import SkillContext

    seen_context_fixed = False
    for kind, rules in SKILL_FIELD_MATRIX.items():
        ctx = rules[SkillField.CONTEXT]
        if ctx.visibility == FieldVisibility.FIXED:
            seen_context_fixed = True
            assert ctx.fixed_value != "fork", f"{kind} CONTEXT fixed_value가 raw 'fork'"
            assert isinstance(ctx.fixed_value, SkillContext), (
                f"{kind} CONTEXT fixed_value 타입: {type(ctx.fixed_value)!r}"
            )
            assert ctx.fixed_value is SkillContext.FORK
    assert seen_context_fixed, "FIXED CONTEXT를 가진 kind가 없음 — 테스트 전제 붕괴"


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

def test_agent_field_matrix_completeness():
    """AGENT_FIELD_MATRIX에 AgentField 전 멤버가 키로 존재해야 한다."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    for af in AgentField:
        assert af in AGENT_FIELD_MATRIX, f"AGENT_FIELD_MATRIX에 {af} 누락"


def test_max_turns_background_isolation_are_frontmatter():
    """MAX_TURNS/BACKGROUND/ISOLATION은 프론트매터 필드다 (WP-FF).

    CC 서브에이전트 프론트매터가 이 셋을 지원하므로, 본문 안내문("호출 파라미터")이
    아니라 프론트매터로 나가야 CC 런타임이 직접 강제한다.
    """
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    for af in (AgentField.MAX_TURNS, AgentField.BACKGROUND, AgentField.ISOLATION):
        assert AGENT_FIELD_MATRIX[af].emit == FieldEmit.FRONTMATTER, (
            f"{af} emit이 FRONTMATTER가 아님: {AGENT_FIELD_MATRIX[af].emit!r}"
        )


def test_no_agent_field_uses_invocation_emit():
    """WP-FF 이후 INVOCATION emit을 쓰는 에이전트 필드는 없다.

    다시 생기면 그 필드가 정말 호출 시점에만 의미가 있는지 — 프론트매터가
    지원하지 않는지 — 확인하고 이 테스트를 갱신하라.
    """
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    using = [af for af, rule in AGENT_FIELD_MATRIX.items()
             if rule.emit is FieldEmit.INVOCATION]
    assert using == [], f"INVOCATION emit 잔존: {using}"


def test_agent_field_matrix_emit_settings():
    """HOOKS/MCP_SERVERS의 emit은 SETTINGS이어야 한다."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    for af in (AgentField.HOOKS, AgentField.MCP_SERVERS):
        assert AGENT_FIELD_MATRIX[af].emit == FieldEmit.SETTINGS, (
            f"{af} emit이 SETTINGS이 아님: {AGENT_FIELD_MATRIX[af].emit!r}"
        )


def test_agent_field_matrix_emit_frontmatter():
    """HOOKS/MCP_SERVERS/MAX_TURNS/BACKGROUND/ISOLATION을 제외한 나머지는 FRONTMATTER이어야 한다."""
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    non_frontmatter = {
        AgentField.HOOKS, AgentField.MCP_SERVERS,
        AgentField.MAX_TURNS, AgentField.BACKGROUND, AgentField.ISOLATION,
    }
    for af, rule in AGENT_FIELD_MATRIX.items():
        if af in non_frontmatter:
            continue
        assert rule.emit == FieldEmit.FRONTMATTER, (
            f"{af} emit이 FRONTMATTER이 아님: {rule.emit!r}"
        )


def test_skill_matrix_when_to_use_emit_body():
    """6개 스킬 매트릭스 전부에서 WHEN_TO_USE.emit == BODY이어야 한다."""
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
    for kind, rules in SKILL_FIELD_MATRIX.items():
        rule = rules[SkillField.WHEN_TO_USE]
        assert rule.emit == FieldEmit.BODY, (
            f"{kind} WHEN_TO_USE.emit이 BODY가 아님: {rule.emit!r}"
        )


def test_skill_matrix_other_fields_emit_frontmatter():
    """6개 스킬 매트릭스에서 WHEN_TO_USE 외 필드의 emit은 FRONTMATTER이어야 한다."""
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
    for kind, rules in SKILL_FIELD_MATRIX.items():
        for fld, rule in rules.items():
            if fld is SkillField.WHEN_TO_USE:
                continue
            assert rule.emit == FieldEmit.FRONTMATTER, (
                f"{kind}/{fld} emit이 FRONTMATTER이 아님: {rule.emit!r}"
            )


def test_agent_field_frontmatter_key_kebab_case():
    """AgentField 전 멤버의 frontmatter_key가 kebab-case여야 한다."""
    for af in AgentField:
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
