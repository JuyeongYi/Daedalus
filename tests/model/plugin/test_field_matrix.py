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
    from PyQt6.QtWidgets import QLineEdit
    r = FieldRule(FieldVisibility.REQUIRED, QLineEdit, default_value="test")
    assert r.visibility == FieldVisibility.REQUIRED
    assert r.widget is QLineEdit
    assert r.default_value == "test"
    assert r.fixed_value is None


def test_matrix_has_all_skill_kinds():
    expected = {"procedural", "declarative", "transfer", "reference", "local_procedural", "local_transfer"}
    assert set(SKILL_FIELD_MATRIX.keys()) == expected


def test_matrix_procedural_model_required():
    rules = SKILL_FIELD_MATRIX["procedural"]
    assert rules[SkillField.MODEL].visibility == FieldVisibility.REQUIRED
    assert rules[SkillField.MODEL].default_value == "sonnet"


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
    rules = SKILL_FIELD_MATRIX["local_procedural"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.FIXED
    assert rules[SkillField.CONTEXT].fixed_value == "fork"


def test_matrix_declarative_context_default():
    rules = SKILL_FIELD_MATRIX["declarative"]
    assert rules[SkillField.CONTEXT].visibility == FieldVisibility.DEFAULT


def test_matrix_all_kinds_have_all_fields():
    """모든 kind에 14개 SkillField가 전부 정의되어 있어야 함."""
    for kind, rules in SKILL_FIELD_MATRIX.items():
        for field in SkillField:
            assert field in rules, f"{kind} missing {field.value}"
