# tests/view/editors/test_wrap_catalog_dialog.py
"""외부 플러그인 카탈로그 창 (WP-WR D2) — 트리 구성 + 사용 선언 체크 + 생성.

발견 로직 자체는 tests/model/plugin/test_wrap_catalog.py가 검증한다 — 여기서는
창이 그 결과를 트리로 옮기고, 체크가 external_plugins 선언(SetAttrCmd — undo)
을, 생성이 create_wrapped_skill(생성+선언 1 undo)을 타는지만 본다.
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
def marketplace(tmp_path):
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
    assert "마켓플레이스 폴더" in dlg._status.text()


def test_tree_shows_marketplace_plugin_skill(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    folder_item = dlg._tree.topLevelItem(0)
    assert "mkt" in folder_item.text(0)
    plugin_item = folder_item.child(0)
    assert "alpha" in plugin_item.text(0)
    skill_item = plugin_item.child(0)
    assert skill_item.text(0) == "review"
    assert skill_item.toolTip(0) == "alpha@mkt:review"


def test_plugin_checkbox_declares_external_plugin(window, marketplace, qapp):
    """체크 = external_plugins 선언 (SetAttrCmd — undo 가능). 트리 재구성은
    singleShot(0)으로 미뤄진다(시그널을 쏜 아이템을 같은 호출에서 파괴하면
    안 된다 — 실측 크래시) — processEvents로 소진한다."""
    from PySide6.QtCore import Qt

    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    plugin_item = dlg._tree.topLevelItem(0).child(0)
    assert plugin_item.checkState(0) == Qt.CheckState.Unchecked  # 미선언

    plugin_item.setCheckState(0, Qt.CheckState.Checked)  # itemChanged → 선언
    assert window._project.external_plugins == ["alpha@mkt"]  # 선언은 즉시
    qapp.processEvents()  # 미뤄진 refresh 소진
    plugin_item = dlg._tree.topLevelItem(0).child(0)
    assert plugin_item.checkState(0) == Qt.CheckState.Checked
    assert plugin_item.childCount() == 1  # 스킬은 체크와 무관하게 항상 보인다

    window._undo()  # 선언은 프로젝트 편집 — undo된다
    assert window._project.external_plugins == []

    window._redo()
    plugin_item = dlg._tree.topLevelItem(0).child(0)
    plugin_item.setCheckState(0, Qt.CheckState.Unchecked)  # 해제
    assert window._project.external_plugins == []
    qapp.processEvents()


def test_create_wrapped_registers_and_declares_with_undo(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    component = dlg.create_wrapped("alpha@mkt:review")
    assert component is not None
    assert window._project.skills[0] is component
    assert component.kind == "wrapped_skill"
    assert component.name == "review"
    assert component.config.source == "alpha@mkt:review"
    # 미선언 플러그인이면 선언까지 함께 (사용자 확정 — 자동 명시)
    assert window._project.external_plugins == ["alpha@mkt"]

    window._undo()  # 생성+선언 1 undo
    assert window._project.skills == []
    assert window._project.external_plugins == []
    window._redo()
    assert window._project.skills[0].config.source == "alpha@mkt:review"
    assert window._project.external_plugins == ["alpha@mkt"]


def test_create_wrapped_uniquifies_name(window):
    dlg = _make_dialog(window)
    first = dlg.create_wrapped("alpha@mkt:review")
    second = dlg.create_wrapped("alpha@mkt:review")
    assert first.name == "review"
    assert second.name == "review-2"


def test_already_wrapped_marker_in_tree(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    dlg.create_wrapped("alpha@mkt:review")
    dlg.refresh()
    skill_item = dlg._tree.topLevelItem(0).child(0).child(0)
    assert "✔" in skill_item.text(0)
    # 생성이 선언까지 했으므로 플러그인 체크도 켜져 있다
    from PySide6.QtCore import Qt

    assert dlg._tree.topLevelItem(0).child(0).checkState(0) == Qt.CheckState.Checked


def test_create_from_selection_requires_skill_row(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    # 선택 없음 → 안내만, 생성 없음
    assert dlg.create_wrapped_from_selection() is None
    assert window._project.skills == []
    # 스킬 행 선택 → 생성
    skill_item = dlg._tree.topLevelItem(0).child(0).child(0)
    dlg._tree.setCurrentItem(skill_item)
    assert dlg.create_wrapped_from_selection() is not None
    assert window._project.skills[0].config.source == "alpha@mkt:review"


def test_remove_selected_marketplace(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    # 스킬 행을 선택해도 부모를 거슬러 올라 마켓플레이스 행을 찾는다
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0).child(0).child(0))
    dlg.remove_selected_marketplace()
    assert wrap_catalog.load_marketplaces() == []
    assert dlg._tree.topLevelItemCount() == 0
