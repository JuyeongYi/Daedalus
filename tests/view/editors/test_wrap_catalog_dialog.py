# tests/view/editors/test_wrap_catalog_dialog.py
"""외부 플러그인 카탈로그 창 (WP-WR D2) — 트리 구성 + 사용 선언 체크.

발견 로직 자체는 tests/model/plugin/test_wrap_catalog.py가 검증한다. 이 창의
동작은 등록·선언뿐이고(사용자 확정 — 배선은 빌드 소관) 생성 버튼이 없다.
✔ 표시는 "이 프로젝트가 이미 그 source를 쓰고 있다"이고 판정의 실체는 모델
(`wrap_catalog.project_external_sources`)이다 — MCP `list_external_plugins`가
같은 함수를 부른다.
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
    adir = plugin_dir / "agents"
    adir.mkdir(parents=True)
    (adir / "critic.md").write_text(
        "---\nname: critic\ndescription: Critiques.\n---\n", encoding="utf-8"
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
    assert skill_item.text(0) == "\U0001F4C4 review"
    assert skill_item.toolTip(0) == "alpha@mkt:review"
    # 플러그인이 동봉한 **에이전트**도 같은 규약으로 한 행씩 나온다(WP-10).
    agent_item = plugin_item.child(1)
    assert agent_item.text(0) == "\U0001F916 critic"
    assert agent_item.toolTip(0) == "alpha:critic"


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
    # 스킬·에이전트 행은 체크와 무관하게 항상 보인다.
    assert plugin_item.childCount() == 2

    window._undo()  # 선언은 프로젝트 편집 — undo된다
    assert window._project.external_plugins == []

    window._redo()
    plugin_item = dlg._tree.topLevelItem(0).child(0)
    plugin_item.setCheckState(0, Qt.CheckState.Unchecked)  # 해제
    assert window._project.external_plugins == []
    qapp.processEvents()


def test_dialog_has_no_create_action(window):
    """이 창의 동작은 등록·선언뿐이다(사용자 확정) — 생성 버튼/메서드가 없다."""
    dlg = _make_dialog(window)
    from PySide6.QtWidgets import QPushButton

    labels = [b.text() for b in dlg.findChildren(QPushButton)]
    assert not any("감싸기" in t or "생성" in t for t in labels)
    assert not hasattr(dlg, "create_wrapped")


def test_already_used_marker_in_tree(window, marketplace):
    """✔ = 이 프로젝트의 어떤 컴포넌트가 그 source를 외부 정본으로 쓴다."""
    from daedalus.model.plugin import wrap_catalog
    from daedalus.model.plugin.agent import ExternalAgent
    from daedalus.model.plugin.config import ExternalAgentConfig

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    window._project.agents.append(ExternalAgent(
        name="critic", description="d",
        config=ExternalAgentConfig(source="alpha:critic"),
    ))
    dlg.refresh()
    agent_item = dlg._tree.topLevelItem(0).child(0).child(1)
    assert "✔" in agent_item.text(0)


def test_remove_selected_marketplace(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    dlg = _make_dialog(window)
    # 스킬 행을 선택해도 부모를 거슬러 올라 마켓플레이스 행을 찾는다
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0).child(0).child(0))
    dlg.remove_selected_marketplace()
    assert wrap_catalog.load_marketplaces() == []
    assert dlg._tree.topLevelItemCount() == 0
