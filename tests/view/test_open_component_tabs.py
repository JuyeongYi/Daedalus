"""편집 탭 열기 — 모든 컴포넌트 종류 (WP-A 리뷰 반영).

`MainWindow._open_component`는 레지스트리 더블클릭·캔버스 노드 더블클릭·
"출력 포트 편집…" 세 표면이 전부 지나는 길목이다. 분기 튜플이 한 종류를
빠뜨리면 **아무 일도 일어나지 않는다**(예외도 메시지도 없다 — 원칙 5).
계층이 갈라질 때마다 조용히 사라지므로 종류별로 고정한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject

_SKILL_KINDS = [
    "procedural",
    "sync_fork",
    "async_fork",
    "declarative",
    "transfer",
    "reference",
    "wrapped",
]
_AGENT_KINDS = ["agent", "fork_agent"]


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _make(window, kind: str):
    from daedalus.view.actions.creation import make_component

    comp = make_component(window, kind, f"c-{kind}", description="d")
    window._register_component(comp)
    return comp


@pytest.mark.parametrize("kind", _SKILL_KINDS + _AGENT_KINDS)
def test_open_component_opens_a_tab_for_every_kind(window, kind):
    comp = _make(window, kind)
    before = window._tabs.count()
    window._open_component(comp)
    assert window._tabs.count() == before + 1
    assert window._tabs.tabText(window._tabs.currentIndex()).endswith(comp.name)


@pytest.mark.parametrize("kind", _SKILL_KINDS + _AGENT_KINDS)
def test_open_component_is_idempotent(window, kind):
    """이미 열린 탭은 다시 만들지 않고 그 탭으로 옮긴다."""
    comp = _make(window, kind)
    window._open_component(comp)
    count = window._tabs.count()
    window._open_component(comp)
    assert window._tabs.count() == count


@pytest.mark.parametrize("kind", ["procedural", "sync_fork", "async_fork", "agent"])
def test_open_component_ports_opens_the_tab(window, kind):
    """캔버스 "출력 포트 편집…"도 `_open_component`를 지난다.

    분기가 종류를 빠뜨리면 메뉴를 눌러도 탭조차 열리지 않는다(무동작).
    """
    comp = _make(window, kind)
    window.open_component_ports(comp)
    assert comp.id in window._open_tabs
