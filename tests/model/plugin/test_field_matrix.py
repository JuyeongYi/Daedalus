# tests/model/plugin/test_field_matrix.py
from __future__ import annotations

from daedalus.model.plugin.enums import FieldVisibility, SkillField


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
    """field_matrix(및 daedalus.model 전체)가 PyQt6 없이 import 가능해야 한다.

    builtins.__import__를 후킹해 'PyQt6'를 import하려는 순간 ImportError를 던지는
    하위 프로세스에서, daedalus.model.plugin.field_matrix를 import한다. model/
    어디서도 PyQt6가 import되지 않음을 CI 수준에서 고정한다.
    """
    import subprocess
    import sys

    code = (
        "import builtins\n"
        "_real = builtins.__import__\n"
        "def _blocked(name, *a, **k):\n"
        "    if name == 'PyQt6' or name.startswith('PyQt6.'):\n"
        "        raise ImportError('PyQt6 import blocked for purity test')\n"
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
        f"PyQt6 차단 하에 daedalus.model import 실패:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "OK" in result.stdout
