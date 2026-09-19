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


def test_agent_field_widgets_cover_every_agent_matrix_field(qapp):
    """AGENT_FIELD_MATRIX **두 표**의 모든 필드에 위젯이 있어야 한다.

    표에 있는데 위젯이 없으면 그 행은 조용히 그려지지 않는다(`fld not in
    widget_map: continue`) — 종류가 늘어난 뒤 이 커버리지가 없으면 "새 종류의
    폼에서 필드 하나가 사라졌다"를 아무도 잡지 못한다.
    """
    from daedalus.model.plugin.enums import AgentField
    from daedalus.model.plugin.field_matrix import AGENT_FIELD_MATRIX
    from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS

    matrix_fields: set[AgentField] = set()
    for rules in AGENT_FIELD_MATRIX.values():
        matrix_fields.update(rules.keys())
    # NAME/DESCRIPTION은 공통 헤더가 그린다(위젯 표 대상이 아니다).
    matrix_fields -= {AgentField.NAME, AgentField.DESCRIPTION}

    missing = matrix_fields - set(AGENT_FIELD_WIDGETS)
    assert not missing, f"AGENT_FIELD_WIDGETS에 누락된 필드: {[f.value for f in missing]}"


def test_agent_field_widgets_values_are_widget_types(qapp):
    from PySide6.QtWidgets import QWidget

    from daedalus.view.editors.field_widgets import AGENT_FIELD_WIDGETS

    for fld, cls in AGENT_FIELD_WIDGETS.items():
        assert isinstance(cls, type), f"{fld.value} 매핑이 타입이 아님"
        assert issubclass(cls, QWidget), f"{fld.value} 매핑이 QWidget 서브클래스 아님"


def test_fork_skill_fields_have_widgets(qapp):
    """fork 2종 표의 필드도 전부 위젯이 있다 — AGENT는 fork 전용 행이다."""
    from daedalus.model.plugin.field_matrix import SKILL_FIELD_MATRIX

    for key in ("sync_fork", "async_fork"):
        missing = set(SKILL_FIELD_MATRIX[key]) - set(FIELD_WIDGETS)
        assert not missing, f"{key}: {[f.value for f in missing]}"
    assert SkillField.AGENT in FIELD_WIDGETS
    # BACKGROUND는 FIXED라 그려지지 않지만 표 완전성 때문에 등재한다(CONTEXT 선례).
    assert SkillField.BACKGROUND in FIELD_WIDGETS


# ─── fork 에이전트 피커는 팝업을 열 때마다 후보를 다시 읽는다 (2026-09-19) ───


def test_fork_agent_combo_reloads_choices_and_keeps_selection(qapp):
    """탭이 열린 뒤 선언·생성으로 늘어난 후보가 다시 열면 보인다 — 선택값은 보존."""
    from daedalus.view.widgets.combo_widgets import ForkAgentComboBox
    from daedalus.view.widgets.tag_input import set_fork_agent_choice_provider

    choices = [("general-purpose", "내장"), ("helper", "프로젝트 fork 에이전트")]
    set_fork_agent_choice_provider(lambda: list(choices))
    try:
        combo = ForkAgentComboBox()
        combo.setCurrentText("helper")
        assert [combo.itemText(i) for i in range(combo.count())] == [
            "general-purpose", "helper",
        ]
        # 사용 선언으로 외부 플러그인 에이전트가 후보에 합류했다.
        choices.append(("hookify:conversation-analyzer", "외부 플러그인 에이전트"))
        combo.reload_choices()
        assert "hookify:conversation-analyzer" in [
            combo.itemText(i) for i in range(combo.count())
        ]
        assert combo.currentText() == "helper"
    finally:
        set_fork_agent_choice_provider(None)


def test_fork_agent_combo_reload_keeps_unlisted_saved_value(qapp):
    """새 목록에 없는 저장값은 사라지지 않고 '목록에 없음'으로 남는다."""
    from daedalus.view.widgets.combo_widgets import ForkAgentComboBox
    from daedalus.view.widgets.tag_input import set_fork_agent_choice_provider

    choices = [("general-purpose", "내장"), ("helper", "프로젝트 fork 에이전트")]
    set_fork_agent_choice_provider(lambda: list(choices))
    try:
        combo = ForkAgentComboBox()
        combo.setCurrentText("helper")
        choices.pop()  # helper가 삭제됐다
        combo.reload_choices()
        assert combo.currentText() == "helper"
        assert "목록에 없음" in combo.itemData(combo.currentIndex(), 3)  # ToolTipRole
    finally:
        set_fork_agent_choice_provider(None)
