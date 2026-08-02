# tests/view/editors/test_field_widgets.py
from __future__ import annotations

from daedalus.model.plugin.enums import SkillField
from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX
from daedalus.view.editors.field_widgets import FIELD_WIDGETS


def test_field_widgets_covers_all_matrix_fields(qapp):
    """SKILL_FIELD_MATRIX에 등장하는 모든 SkillField가 FIELD_WIDGETS에 존재한다."""
    matrix_fields: set[SkillField] = set()
    for rules in SKILL_FIELD_MATRIX.values():
        matrix_fields.update(rules.keys())

    missing = matrix_fields - set(FIELD_WIDGETS)
    assert not missing, f"FIELD_WIDGETS에 누락된 필드: {[f.value for f in missing]}"


def test_field_widgets_values_are_widget_types(qapp):
    """매핑 값은 인스턴스화 가능한 QWidget 서브클래스여야 한다."""
    from PySide6.QtWidgets import QWidget

    for fld, cls in FIELD_WIDGETS.items():
        assert isinstance(cls, type), f"{fld.value} 매핑이 타입이 아님"
        assert issubclass(cls, QWidget), f"{fld.value} 매핑이 QWidget 서브클래스 아님"


def test_paths_uses_tag_input(qapp):
    """PATHS는 공백 포함 경로 표현을 위해 TagInput을 사용한다 (QLineEdit 아님)."""
    from daedalus.view.widgets.tag_input import TagInput

    assert FIELD_WIDGETS[SkillField.PATHS] is TagInput


def test_model_uses_model_combo(qapp):
    from daedalus.view.widgets.combo_widgets import ModelComboBox

    assert FIELD_WIDGETS[SkillField.MODEL] is ModelComboBox


def test_model_combo_has_inherit(qapp):
    """ModelComboBox는 INHERIT 항목을 포함하고 기본값이 inherit이다."""
    from daedalus.view.widgets.combo_widgets import ModelComboBox
    from daedalus.model.plugin.enums import ModelType

    combo = ModelComboBox()
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "inherit" in items
    assert combo.currentText() == ModelType.INHERIT.value
