"""레지스트리 세 표의 완전성 + 드래그 가능 판정 (WP-A 리뷰 반영).

섹션 키·탭 라벨·아이콘 세 표가 **동시에** 늘어야 한다 — `tab_labels[kind]`는
맨 첨자라 하나만 빠져도 KeyError로 패널 전체가 뜨지 않고, `_ICON`이 빠지면
아이콘 없는 행이 조용히 생긴다. 드래그 가능 여부는 섹션 플래그가 아니라
**항목마다** `is_canvas_placeable`이 정한다(판정의 단일 진실).
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from daedalus.model.project import PluginProject

_ALL_KINDS = [
    "procedural",
    "sync_fork",
    "async_fork",
    "declarative",
    "transfer",
    "reference",
    "wrapped",
    "agent",
    "fork_agent",
]


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _panel_with_all_kinds(window):
    from daedalus.view.actions.creation import make_component

    for kind in _ALL_KINDS:
        window._register_component(make_component(window, kind, f"c-{kind}"))
    panel = window._registry_panel
    panel.set_project(window._project)
    return panel


def test_every_section_key_has_a_tab_label_and_an_icon(window):
    """세 표의 커버리지 — 하나라도 빠지면 패널이 KeyError로 죽는다."""
    from daedalus.view.panels.registry_panel import _ICON

    panel = window._registry_panel
    assert set(panel._sections) == set(_ALL_KINDS)
    # 탭은 섹션마다 정확히 하나 — tab_labels 누락은 생성 시점 KeyError다.
    assert panel._tabs.count() == len(panel._sections)
    kinds = {
        f"{k}_skill" if k not in ("agent", "fork_agent") else k
        for k in panel._sections
    }
    assert kinds <= set(_ICON)


def test_each_component_class_lands_in_exactly_one_section(window):
    """9종이 각각 자기 섹션에 하나씩 — 분기 순서가 어긋나면 여기서 잡힌다."""
    panel = _panel_with_all_kinds(window)
    counts = {k: s._list.count() for k, s in panel._sections.items()}
    assert counts == {k: 1 for k in _ALL_KINDS}
    for kind, section in panel._sections.items():
        assert section._list.item(0).text().endswith(f"c-{kind}")


def _draggable(section) -> bool:
    item = section._list.item(0)
    return bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled)


@pytest.mark.parametrize(
    "kind", ["procedural", "sync_fork", "async_fork", "wrapped", "reference", "agent"]
)
def test_canvas_placeable_items_stay_draggable(window, kind):
    """참조 스킬은 상태 노드는 못 되지만 참조 노드로 놓인다 — 드래그 가능."""
    panel = _panel_with_all_kinds(window)
    assert _draggable(panel._sections[kind]) is True


@pytest.mark.parametrize("kind", ["declarative", "transfer", "fork_agent"])
def test_non_placeable_items_are_not_draggable(window, kind):
    panel = _panel_with_all_kinds(window)
    assert _draggable(panel._sections[kind]) is False
