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


def test_every_kind_lands_in_a_section_and_every_section_has_a_tab(window):
    """종류마다 섹션이 있고, 섹션마다 탭·라벨·아이콘이 있다.

    섹션은 종류 수보다 **적을 수 있다** — `KindUI.section_group`이 같은 종류는
    한 탭을 나눠 쓴다(WP-C: 🔌 EXTERNAL AGENTS). 그래도 "어느 종류도 갈 곳이
    없어 조용히 사라지지 않는다"는 사실은 그대로 고정한다.
    """
    from daedalus.view.kind_ui import KIND_UI, ui_by_config_kind

    panel = window._registry_panel
    assert list(panel._section_of_kind) == _ALL_KINDS  # 순서까지 선언 순서다
    assert set(panel._section_of_kind.values()) == set(panel._sections)
    # 탭 = 종류 섹션들 + 🧷 EXTERNAL SKILLS(컴포넌트 종류가 아닌 카탈로그 섹션).
    assert panel._tabs.count() == len(panel._sections) + 1
    for kind in _ALL_KINDS:
        ui = ui_by_config_kind(kind)
        assert ui in KIND_UI.values()
        assert ui.icon and ui.tab_label and ui.section_label


def test_external_agent_kinds_share_one_tab(window):
    """역할만 다른 외부 정본 에이전트 2종은 **한 탭**이다 (WP-C, 사용자 확정).

    나누면 "이 플러그인의 에이전트를 어디서 찾나"가 두 곳이 된다. 항목의 역할은
    종류 아이콘이 말한다(🔌 노드 / 🔌🧩 fork 기반).
    """
    from daedalus.view.kind_ui import EXTERNAL_AGENTS_GROUP

    panel = _panel_with_all_kinds(window)
    key = panel._section_of_kind["external_agent"]
    assert key == EXTERNAL_AGENTS_GROUP
    assert panel._section_of_kind["external_fork_agent"] == key
    section = panel._sections[key]
    assert section._list.count() == 2
    labels = [section._list.item(i).text() for i in range(2)]
    assert labels[0].startswith("🔌 ") and labels[1].startswith("🔌🧩 ")


def test_each_component_lands_in_exactly_one_section(window):
    """종류마다 항목 하나씩 — 분기 순서가 어긋나면 여기서 잡힌다."""
    panel = _panel_with_all_kinds(window)
    total = sum(s._list.count() for s in panel._sections.values())
    assert total == len(_ALL_KINDS)
    for kind in _ALL_KINDS:
        section = panel._sections[panel._section_of_kind[kind]]
        texts = [section._list.item(i).text() for i in range(section._list.count())]
        assert any(t.endswith(f"c-{kind}") for t in texts)


def _draggable(item) -> bool:
    return bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled)


def _item_for(panel, kind):
    """그 종류로 만든 항목 (섹션을 나눠 쓰는 종류도 자기 항목을 찾는다)."""
    section = panel._sections[panel._section_of_kind[kind]]
    for i in range(section._list.count()):
        item = section._list.item(i)
        if item.text().endswith(f"c-{kind}"):
            return item
    raise AssertionError(f"'{kind}' 항목이 섹션에 없습니다.")


@pytest.mark.parametrize(
    "kind",
    ["procedural", "sync_fork", "async_fork", "reference", "agent",
     "external_agent"],
)
def test_canvas_placeable_items_stay_draggable(window, kind):
    """참조 스킬은 상태 노드는 못 되지만 참조 노드로 놓인다 — 드래그 가능."""
    panel = _panel_with_all_kinds(window)
    assert _draggable(_item_for(panel, kind)) is True


@pytest.mark.parametrize(
    "kind", ["declarative", "transfer", "fork_agent", "external_fork_agent"]
)
def test_non_placeable_items_are_not_draggable(window, kind):
    """한 탭을 나눠 써도 드래그 가능 여부는 **항목마다** 판정한다."""
    panel = _panel_with_all_kinds(window)
    assert _draggable(_item_for(panel, kind)) is False
