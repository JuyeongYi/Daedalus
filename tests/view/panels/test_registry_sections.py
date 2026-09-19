"""레지스트리 섹션의 완전성 + 드래그 가능 판정 (WP-A 리뷰 반영, WP-7 ②).

예전에는 섹션 키·탭 라벨·아이콘이 **세 표**였고 셋이 동시에 늘어야 했다. 이제
셋 다 `view/kind_ui.KIND_UI` 한 행에서 나오므로, 여기서 고정하는 것은
**모델 레지스트리와 팔레트가 같은 종류 집합을 말하는가**다 — 섹션 목록을 손으로
적어 두면 새 종류가 모델에만 생기고 팔레트에서는 조용히 사라진다.
드래그 가능 여부는 섹션 플래그가 아니라 **항목마다** `is_canvas_placeable`이
정한다(판정의 단일 진실).
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from daedalus.model.plugin.kinds import config_kinds_in
from daedalus.model.plugin.roles import Bucket
from daedalus.model.project import PluginProject

#: 종류 목록은 **모델 레지스트리에서 파생**한다(R14) — 손으로 적은 9줄이
#: 있으면 그 목록이 낡는 것을 아무도 알려 주지 않는다.
_ALL_KINDS = list(config_kinds_in(Bucket.SKILLS)) + list(
    config_kinds_in(Bucket.AGENTS)
)


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
    """섹션·탭·아이콘이 종류마다 하나씩 — 빠진 종류는 팔레트에서 사라진다."""
    from daedalus.model.plugin.kinds import spec_by_config_kind
    from daedalus.view.kind_ui import KIND_UI

    panel = window._registry_panel
    assert list(panel._sections) == _ALL_KINDS  # 순서까지 선언 순서다
    # 탭은 섹션마다 정확히 하나 — KIND_UI 행이 없으면 생성 시점에 ValueError다.
    assert panel._tabs.count() == len(panel._sections)
    for kind in panel._sections:
        ui = KIND_UI[spec_by_config_kind(kind).kind]
        assert ui.icon and ui.tab_label and ui.section_label


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
    "kind", ["procedural", "sync_fork", "async_fork", "reference", "agent"]
)
def test_canvas_placeable_items_stay_draggable(window, kind):
    """참조 스킬은 상태 노드는 못 되지만 참조 노드로 놓인다 — 드래그 가능."""
    panel = _panel_with_all_kinds(window)
    assert _draggable(panel._sections[kind]) is True


@pytest.mark.parametrize("kind", ["declarative", "transfer", "fork_agent"])
def test_non_placeable_items_are_not_draggable(window, kind):
    panel = _panel_with_all_kinds(window)
    assert _draggable(panel._sections[kind]) is False
