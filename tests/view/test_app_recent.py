"""최근 프로젝트 메뉴 배선 (WP-RP).

목록 규칙 자체는 ``test_recent.py``가 다룬다. 여기서는 "저장·열기가 목록에
기록되는가"와 "메뉴가 그 목록을 그대로 반영하는가"를 확인한다.
"""
from __future__ import annotations

import os

import pytest

from daedalus.model.project import PluginProject
from daedalus.view import recent
from daedalus.view.app import MainWindow


@pytest.fixture
def window(qapp):
    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


def _recent_action_texts(win) -> list[str]:
    """"목록 지우기"/구분선을 뺀 실제 항목 라벨."""
    menu = win._recent_menu
    assert menu is not None
    return [
        a.text()
        for a in menu.actions()
        if not a.isSeparator() and a.text() != "목록 지우기"
    ]


def test_menu_shows_placeholder_when_empty(window):
    window._rebuild_recent_menu()
    texts = _recent_action_texts(window)
    assert texts == ["(없음)"]
    # 비어 있을 때는 "목록 지우기"도 내놓지 않는다
    assert all(a.text() != "목록 지우기" for a in window._recent_menu.actions())


def test_saving_records_recent(window, tmp_path):
    path = str(tmp_path / "proj.daedalus.json")
    window._save_to_path(path)
    assert recent.load() == [os.path.abspath(path)]


def test_opening_records_recent(window, tmp_path):
    path = str(tmp_path / "proj.daedalus.json")
    window._save_to_path(path)
    recent.clear()

    window.open_path(path)
    assert recent.load() == [os.path.abspath(path)]


def test_failed_open_is_not_recorded(window, tmp_path):
    """열기에 실패한 경로가 메뉴에 남으면 다음에도 실패만 반복한다."""
    window.open_path(str(tmp_path / "missing.daedalus.json"))
    assert recent.load() == []


def test_menu_reflects_list_after_save(window, tmp_path):
    first = str(tmp_path / "a.daedalus.json")
    second = str(tmp_path / "b.daedalus.json")
    window._save_to_path(first)
    window._save_to_path(second)

    texts = _recent_action_texts(window)
    assert len(texts) == 2
    assert "b.daedalus.json" in texts[0], "최근 것이 앞"
    assert "a.daedalus.json" in texts[1]


def test_menu_item_carries_full_path_in_tooltip(window, tmp_path):
    path = str(tmp_path / "a.daedalus.json")
    window._save_to_path(path)
    action = window._recent_menu.actions()[0]
    assert action.toolTip() == os.path.abspath(path)


def test_label_escapes_ampersand():
    """파일명의 &가 니모닉으로 먹혀 글자가 사라지면 안 된다."""
    label = MainWindow._recent_label(1, os.path.join("dir", "a&b.json"))
    assert "a&&b.json" in label
    assert label.startswith("&1 ")


def test_label_includes_parent_folder():
    label = MainWindow._recent_label(2, os.path.join("proj", "work", "a.json"))
    assert "a.json" in label and "work" in label


def test_open_recent_loads_project(window, tmp_path):
    path = str(tmp_path / "a.daedalus.json")
    window._project.skills.clear()
    window._save_to_path(path)
    window.load_project(PluginProject(name="other"))

    window._open_recent(path)
    assert window._current_path == path
    assert window._project.name == "p"


def test_open_recent_drops_missing_file(window, tmp_path):
    path = str(tmp_path / "gone.daedalus.json")
    window._save_to_path(path)
    os.remove(path)

    window._open_recent(path)
    assert recent.load() == [], "사라진 파일은 목록에서 제거돼야 한다"
    assert _recent_action_texts(window) == ["(없음)"]
    assert "찾을 수 없어" in window._status_label.text()


def test_clear_recent_empties_menu(window, tmp_path):
    window._save_to_path(str(tmp_path / "a.daedalus.json"))
    window._clear_recent()
    assert recent.load() == []
    assert _recent_action_texts(window) == ["(없음)"]


def test_menu_survives_window_restart(window, tmp_path):
    """목록은 파일에 있으므로 새 창에서도 그대로 보인다 — 기능의 요지."""
    path = str(tmp_path / "a.daedalus.json")
    window._save_to_path(path)

    fresh = MainWindow()
    try:
        assert any("a.daedalus.json" in t for t in _recent_action_texts(fresh))
    finally:
        fresh.close()
