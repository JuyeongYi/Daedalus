# tests/view/editors/test_wrap_catalog_dialog.py
"""랩핑 스킬 카탈로그 창 (WP-WR D2) — 트리 구성 + 생성(undo) + ✔ 표시.

발견 로직 자체는 tests/model/plugin/test_wrap_catalog.py가 검증한다 — 여기서는
창이 그 결과를 트리로 옮기고 생성이 CreateComponentCmd(undo)를 타는지만 본다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def plugin_root(tmp_path):
    plugin_dir = tmp_path / "catalog" / "alpha"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(json.dumps({"name": "alpha"}), encoding="utf-8")
    sdir = plugin_dir / "skills" / "review"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text(
        "---\nname: review\ndescription: Reviews.\n---\n", encoding="utf-8"
    )
    return tmp_path / "catalog"


def _make_dialog(window):
    from daedalus.view.editors.wrap_catalog_dialog import WrapCatalogDialog

    return WrapCatalogDialog(window)


def test_empty_catalog_shows_guidance(window):
    dlg = _make_dialog(window)
    assert dlg._tree.topLevelItemCount() == 0
    assert "루트 추가" in dlg._status.text()


def test_tree_shows_root_plugin_skill(window, plugin_root):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    root_item = dlg._tree.topLevelItem(0)
    assert "mkt" in root_item.text(0)
    plugin_item = root_item.child(0)
    assert "alpha" in plugin_item.text(0)
    skill_item = plugin_item.child(0)
    assert skill_item.text(0) == "review"
    assert skill_item.toolTip(0) == "alpha@mkt:review"


def test_create_wrapped_registers_component_with_undo(window, plugin_root):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    component = dlg.create_wrapped("alpha@mkt:review")
    assert component is not None
    assert window._project.skills[0] is component
    assert component.kind == "wrapped_skill"
    assert component.name == "review"
    assert component.config.source == "alpha@mkt:review"

    window._undo()
    assert window._project.skills == []
    window._redo()
    assert window._project.skills[0].config.source == "alpha@mkt:review"


def test_create_wrapped_uniquifies_name(window):
    dlg = _make_dialog(window)
    first = dlg.create_wrapped("alpha@mkt:review")
    second = dlg.create_wrapped("alpha@mkt:review")
    assert first.name == "review"
    assert second.name == "review-2"


def test_already_wrapped_marker_in_tree(window, plugin_root):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    dlg.create_wrapped("alpha@mkt:review")
    dlg.refresh()
    skill_item = dlg._tree.topLevelItem(0).child(0).child(0)
    assert "✔" in skill_item.text(0)


def test_create_from_selection_requires_skill_row(window, plugin_root):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    # 선택 없음 → 안내만, 생성 없음
    assert dlg.create_wrapped_from_selection() is None
    assert window._project.skills == []
    # 스킬 행 선택 → 생성
    skill_item = dlg._tree.topLevelItem(0).child(0).child(0)
    dlg._tree.setCurrentItem(skill_item)
    assert dlg.create_wrapped_from_selection() is not None
    assert window._project.skills[0].config.source == "alpha@mkt:review"


def test_plugin_checkbox_toggles_exclusion(window, plugin_root, qapp):
    """플러그인 체크 해제 → 제외 목록 저장 + 스킬 후보 숨김 (사용자 확정 UX).

    저장은 즉시이고 트리 재구성은 singleShot(0)으로 미뤄진다(시그널을 쏜
    아이템을 같은 호출에서 파괴하면 안 된다) — processEvents로 소진한다.
    """
    from PySide6.QtCore import Qt

    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    plugin_item = dlg._tree.topLevelItem(0).child(0)
    assert plugin_item.checkState(0) == Qt.CheckState.Checked
    assert plugin_item.childCount() == 1

    plugin_item.setCheckState(0, Qt.CheckState.Unchecked)  # itemChanged → 저장
    assert wrap_catalog.load_plugin_roots()[0].excluded == ["alpha"]  # 저장은 즉시
    qapp.processEvents()  # 미뤄진 refresh 소진
    plugin_item = dlg._tree.topLevelItem(0).child(0)  # refresh로 새 아이템
    assert plugin_item.checkState(0) == Qt.CheckState.Unchecked
    assert plugin_item.childCount() == 0  # 제외되면 스킬을 펼치지 않는다
    assert "제외" in dlg._status.text()

    plugin_item.setCheckState(0, Qt.CheckState.Checked)  # 복귀
    assert wrap_catalog.load_plugin_roots()[0].excluded == []
    qapp.processEvents()
    assert dlg._tree.topLevelItem(0).child(0).childCount() == 1


def test_remove_selected_root(window, plugin_root):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_plugin_root(str(plugin_root), "mkt")
    dlg = _make_dialog(window)
    # 스킬 행을 선택해도 부모를 거슬러 올라 루트를 찾는다
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0).child(0).child(0))
    dlg.remove_selected_root()
    assert wrap_catalog.load_plugin_roots() == []
    assert dlg._tree.topLevelItemCount() == 0
