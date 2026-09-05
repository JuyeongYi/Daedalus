"""프론트매터 패널의 행 정렬 — 모든 행이 하나의 그리드를 공유한다 (항목 3).

증상(사용자 보고): Settings 그룹의 hooks / mcp_servers처럼 라벨 길이가 다른 행에서
값 위젯의 시작 x좌표가 서로 달라 계단처럼 보였다. 원인은 행마다 독립 레이아웃
(`_OptionalRow`의 자체 QHBoxLayout, REQUIRED 행의 별도 HBox/VBox)을 써서 열 폭이
공유되지 않은 것이다.

정렬 자체는 픽셀보다 **구조**로 고정하는 편이 안정적이다 — 위젯이 같은
QGridLayout의 같은 열에 있으면 폭은 Qt가 맞춘다. 다만 실제로 어긋났던 것이
좌표이므로, "모든 값 위젯의 x가 같다" 한 줄은 값을 하드코딩하지 않는 선에서
함께 둔다(회귀의 직접 증거).
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel

from daedalus.model.plugin.enums import AgentField, BuildTarget, SkillField
from daedalus.view.editors.skill_editor import (
    _COL_CHECK,
    _COL_COUNT,
    _COL_LABEL,
    _COL_WIDGET,
    _DIM_OPACITY,
    _FrontmatterPanel,
    _OptionalRow,
)

from tests.compiler.builders import make_agent, make_procedural


def _agent_panel(build_target=None) -> _FrontmatterPanel:
    return _FrontmatterPanel(
        make_agent(), skill_kind="agent", build_target=build_target
    )


def _cell_row(grid: QGridLayout, widget) -> int | None:
    """widget이 놓인 그리드 행. 없으면 None."""
    index = grid.indexOf(widget)
    if index < 0:
        return None
    return grid.getItemPosition(index)[0]


# ─────────────────────────── 구조 ───────────────────────────


@pytest.mark.parametrize("make_panel", [_agent_panel, lambda: _FrontmatterPanel(make_procedural())])
def test_every_field_widget_sits_in_the_widget_column(qapp, make_panel):
    """값 위젯은 전부 같은 그리드의 같은 열에 있다 — 폭 공유의 전제다."""
    panel = make_panel()
    grid = panel._grid
    assert isinstance(grid, QGridLayout)
    assert panel._field_widgets, "필드 위젯이 하나도 없다 — 매트릭스 확인 필요"

    for fld, widget in panel._field_widgets.items():
        # OPTIONAL 필드는 _OptionalRow가 그 칸이고, REQUIRED는 위젯이 곧 칸이다.
        cell = widget.parent() if isinstance(widget.parent(), _OptionalRow) else widget
        row = _cell_row(grid, cell)
        assert row is not None, f"{fld}의 칸이 그리드에 없다"
        item = grid.itemAtPosition(row, _COL_WIDGET)
        assert item is not None and item.widget() is cell, (
            f"{fld}가 값 위젯 열({_COL_WIDGET})에 없다"
        )


def test_optional_row_places_checkbox_and_label_in_their_own_columns(qapp):
    panel = _agent_panel()
    grid = panel._grid
    widget = panel._field_widgets[AgentField.HOOKS]
    row_widget = widget.parent()
    assert isinstance(row_widget, _OptionalRow)

    row = _cell_row(grid, row_widget)
    check = grid.itemAtPosition(row, _COL_CHECK)
    label = grid.itemAtPosition(row, _COL_LABEL)
    assert isinstance(check.widget(), QCheckBox)
    assert isinstance(label.widget(), QLabel)
    assert label.widget().text() == AgentField.HOOKS.value


def test_required_row_leaves_the_checkbox_column_empty(qapp):
    """REQUIRED 행에는 체크박스가 없지만 라벨·위젯 열은 OPTIONAL과 공유한다."""
    panel = _FrontmatterPanel(make_procedural())
    grid = panel._grid
    row = _cell_row(grid, panel._w_name)
    assert row is not None
    assert grid.itemAtPosition(row, _COL_CHECK) is None
    assert grid.itemAtPosition(row, _COL_LABEL).widget().text() == "name *"
    assert grid.itemAtPosition(row, _COL_WIDGET).widget() is panel._w_name


def test_group_divider_spans_the_whole_row(qapp):
    """"— Settings —" 같은 구분 라벨은 열 구분이 없다."""
    panel = _agent_panel()
    grid = panel._grid
    spans = [
        grid.getItemPosition(i)
        for i in range(grid.count())
        if isinstance(grid.itemAt(i).widget(), QLabel)
        and grid.itemAt(i).widget().text().startswith("—")
    ]
    assert spans, "그룹 구분 라벨을 찾지 못했다"
    for _row, col, _rowspan, colspan in spans:
        assert (col, colspan) == (0, _COL_COUNT)


# ─────────────────────────── 실제 좌표 ───────────────────────────


def test_all_field_widgets_start_at_the_same_x(qapp):
    """회귀의 직접 증거 — 이전에는 라벨 길이만큼 8가지 x가 나왔다."""
    panel = _agent_panel()
    panel.resize(360, 900)
    panel.show()
    try:
        inner = panel.widget()
        inner.layout().activate()
        xs = {
            widget.mapTo(inner, widget.rect().topLeft()).x()
            for widget in panel._field_widgets.values()
        }
        assert len(xs) == 1, f"값 위젯 시작 x가 어긋난다: {sorted(xs)}"
    finally:
        panel.close()


# ─────────────────────────── _OptionalRow 회귀 ───────────────────────────


def test_toggle_dims_label_and_widget_but_not_the_checkbox(qapp):
    """체크박스는 흐리지 않는다 — 다시 켜려면 눌러야 하는 컨트롤이다."""
    panel = _FrontmatterPanel(make_procedural())
    row = panel._field_widgets[SkillField.EFFORT].parent()
    assert isinstance(row, _OptionalRow)

    row.set_checked(False)
    assert row._opacity.opacity() == _DIM_OPACITY
    assert row._label_opacity.opacity() == _DIM_OPACITY
    assert row._cb.graphicsEffect() is None

    row.set_checked(True)
    assert row._opacity.opacity() == 1.0
    assert row._label_opacity.opacity() == 1.0


def test_lock_disables_the_checkbox_too(qapp):
    """세 칸이 그리드에 흩어졌으므로 행이 스스로 전부 잠가야 한다 (WP-EL).

    값 위젯만 잠그면 체크박스가 살아 있어 "켤 수는 있는데 아무 일도 안 일어나는"
    상태가 된다.
    """
    panel = _agent_panel(BuildTarget.MARKETPLACE)
    row = panel._field_widgets[AgentField.HOOKS].parent()
    assert isinstance(row, _OptionalRow)
    assert not row.isEnabled()
    assert not row._cb.isEnabled()
    assert not row._label.isEnabled()
    assert "hooks" in row._cb.toolTip()


def test_lock_leaves_supported_fields_alone(qapp):
    panel = _agent_panel(BuildTarget.MARKETPLACE)
    row = panel._field_widgets[AgentField.TOOLS].parent()
    assert isinstance(row, _OptionalRow)
    assert row.isEnabled() and row._cb.isEnabled()
