"""작업 폴더 문서 탭 2종 — CLAUDE.md · 규칙 (WP-WD).

CLAUDE.md와 규칙을 한 탭에 목록으로 묶지 않고 **각각 최상위 탭**으로 둔 것은
사용자 확정이다. 규칙은 파일이 여럿일 수 있으므로 선택 목록을 갖는다.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject
from daedalus.view import app as app_mod
from daedalus.view.app import MainWindow
from daedalus.view.editors import body_documents, workspace_editor
from daedalus.view.editors.workspace_editor import ClaudeMdPanel, RulesPanel


@pytest.fixture
def project() -> PluginProject:
    proj = PluginProject(name="my-plugin")
    proj.build_target = BuildTarget.LOCAL
    return proj


# ─────────────────────────── 탭 배치 ───────────────────────────


def test_tabs_are_resident_and_not_closable(qapp):
    window = MainWindow()
    titles = [window._tabs.tabText(i) for i in range(window._tabs.count())]
    assert "📌 CLAUDE.md" in titles
    assert "📐 규칙" in titles
    bar = window._tabs.tabBar()
    for index in (app_mod._CLAUDE_MD_TAB_INDEX, app_mod._RULES_TAB_INDEX):
        assert bar.tabButton(index, bar.ButtonPosition.RightSide) is None


def test_fixed_tabs_cannot_be_closed(qapp):
    window = MainWindow()
    before = window._tabs.count()
    window._close_tab(app_mod._RULES_TAB_INDEX)
    window._close_tab(app_mod._CLAUDE_MD_TAB_INDEX)
    assert window._tabs.count() == before


def test_set_project_wires_both_panels(qapp, project):
    window = MainWindow()
    window.set_project(project)
    assert window._claude_md_panel._project is project
    assert window._rules_panel._project is project


# ─────────────────────────── CLAUDE.md 탭 ───────────────────────────


def test_claude_md_doc_is_created_on_demand(qapp, project):
    """"만들기" 버튼 없이 바로 타이핑할 수 있어야 한다 — 빈 본문은 배출되지 않는다."""
    panel = ClaudeMdPanel()
    panel.set_project(project)
    assert project.claude_md is not None
    assert project.claude_md.name == "my-plugin"
    assert project.claude_md.body == ""


def test_claude_md_existing_doc_is_reused(qapp, project):
    doc = WorkspaceDoc(name="custom", body="keep me")
    project.claude_md = doc
    panel = ClaudeMdPanel()
    panel.set_project(project)
    assert project.claude_md is doc
    assert panel._title.text() == "custom"


def test_claude_md_title_edit_writes_through(qapp, project):
    panel = ClaudeMdPanel()
    panel.set_project(project)
    panel._title.setText("house rules")
    assert project.claude_md.name == "house rules"


def test_claude_md_empty_title_falls_back_to_project_name(qapp, project):
    panel = ClaudeMdPanel()
    panel.set_project(project)
    panel._title.setText("   ")
    assert project.claude_md.name == "my-plugin"


def test_marketplace_build_shows_notice(qapp, project):
    """띄우지 않은 위젯은 isVisible()이 항상 False라, 노출 의도는 플래그로 본다."""
    project.build_target = BuildTarget.MARKETPLACE
    panel = ClaudeMdPanel()
    panel.set_project(project)
    assert not panel._notice.isHidden()
    assert "마켓플레이스" in panel._notice.text()


def test_local_build_has_no_notice(qapp, project):
    panel = ClaudeMdPanel()
    panel.set_project(project)
    assert panel._notice.isHidden()


def test_notice_clears_when_target_changes_to_local(qapp, project):
    project.build_target = BuildTarget.MARKETPLACE
    panel = ClaudeMdPanel()
    panel.set_project(project)
    assert not panel._notice.isHidden()
    project.build_target = BuildTarget.LOCAL
    panel.set_project(project)
    assert panel._notice.isHidden()


# ─────────────────────────── 규칙 탭 ───────────────────────────


def test_rules_list_shows_every_rule(qapp, project):
    project.rules = [WorkspaceDoc(name="testing"), WorkspaceDoc(name="api-design")]
    panel = RulesPanel()
    panel.set_project(project)
    assert [panel._list.item(i).text() for i in range(panel._list.count())] == [
        "testing", "api-design"
    ]


def test_selecting_a_rule_attaches_its_body(qapp, project):
    project.rules = [
        WorkspaceDoc(name="testing", body="run pytest"),
        WorkspaceDoc(name="api-design", body="validate input"),
    ]
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(1)
    assert panel.content_panel()._component is project.rules[1]


def test_add_rule_appends_and_selects(qapp, project, monkeypatch):
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("testing", True))
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._add_rule()
    assert [doc.name for doc in project.rules] == ["testing"]
    assert panel._list.currentRow() == 0


def test_add_rule_rejects_duplicate_name(qapp, project, monkeypatch):
    project.rules = [WorkspaceDoc(name="testing")]
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("testing", True))
    )
    warned: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *a, **k: warned.append(a[2] if len(a) > 2 else "")),
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._add_rule()
    assert len(project.rules) == 1
    assert warned


def test_add_rule_cancelled_does_nothing(qapp, project, monkeypatch):
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", False))
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._add_rule()
    assert project.rules == []


def test_rename_rule(qapp, project, monkeypatch):
    project.rules = [WorkspaceDoc(name="testing")]
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("qa", True))
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    panel._rename_current()
    assert project.rules[0].name == "qa"
    assert panel._list.item(0).text() == "qa"


def test_delete_rule_drops_document_cache(qapp, project, monkeypatch):
    """삭제하면 본문 undo 문서도 버린다 — 남겨두면 세션 내내 메모리에 붙어 있다."""
    doc = WorkspaceDoc(name="testing", body="x")
    project.rules = [doc]
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    assert body_documents.registry().peek(doc) is not None
    panel._delete_current()
    assert project.rules == []
    assert body_documents.registry().peek(doc) is None


def test_delete_rule_cancelled_keeps_it(qapp, project, monkeypatch):
    project.rules = [WorkspaceDoc(name="testing")]
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    panel._delete_current()
    assert len(project.rules) == 1


def test_no_project_disables_editing(qapp):
    panel = RulesPanel()
    panel.set_project(None)
    assert not panel._btn_add.isEnabled()
    assert not panel.content_panel().isEnabled()


def test_body_undo_survives_switching_rules(qapp, project):
    """WP-BU와 같은 보장 — 문서를 옮겨다녀도 되돌리기 이력이 유지된다."""
    from PySide6.QtGui import QTextCursor

    project.rules = [WorkspaceDoc(name="a", body="A"), WorkspaceDoc(name="b", body="B")]
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    editor = panel.content_panel()._w_content
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" edited")
    assert project.rules[0].body == "A edited"

    panel._list.setCurrentRow(1)  # 다른 문서로 갔다가
    panel._list.setCurrentRow(0)  # 돌아온다
    panel.content_panel()._w_content.undo()
    assert project.rules[0].body == "A"


# ─────────────────────────── 프로젝트 전환 ───────────────────────────


def test_switching_projects_rebuilds_list(qapp, project):
    project.rules = [WorkspaceDoc(name="testing")]
    panel = RulesPanel()
    panel.set_project(project)
    other = PluginProject(name="other")
    other.build_target = BuildTarget.LOCAL
    panel.set_project(other)
    assert panel._list.count() == 0
    assert not panel.content_panel().isEnabled()


def test_notify_is_called_on_structure_edit(qapp, project, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("testing", True))
    )
    panel = RulesPanel(on_notify_fn=lambda scope="structure": calls.append(scope))
    panel.set_project(project)
    panel._add_rule()
    assert "structure" in calls


def test_module_exposes_panels():
    assert hasattr(workspace_editor, "ClaudeMdPanel")
    assert hasattr(workspace_editor, "RulesPanel")


# ─────────────────────────── 변수 삽입 ───────────────────────────
#
# 회귀: SectionContentPanel의 variable_insert_requested를 아무도 연결하지 않아
# 변수 버튼이 무동작이었다(ComponentEditor에만 배선이 있었다).


@pytest.mark.parametrize("panel_cls", [ClaudeMdPanel, RulesPanel])
def test_variable_button_opens_popup_at_button_pos(qapp, project, panel_cls):
    from PySide6.QtCore import QPoint

    # 규칙 탭은 선택된 문서가 없으면 본문이 비활성이라 버튼이 눌리지 않는다
    project.rules = [WorkspaceDoc(name="testing")]
    panel = panel_cls()
    panel.set_project(project)
    panel.show()
    try:
        panel.content_panel()._btn_variable.click()
        btn = panel.content_panel()._btn_variable
        assert panel._var_popup.isVisible()
        assert panel._var_popup.pos() == btn.mapToGlobal(QPoint(0, btn.height()))
        # 다시 누르면 닫힌다
        panel.content_panel()._btn_variable.click()
        assert not panel._var_popup.isVisible()
    finally:
        panel._var_popup.hide()
        panel.close()


def test_variable_selection_inserts_into_rule_body(qapp, project):
    project.rules = [WorkspaceDoc(name="testing", body="use ")]
    panel = RulesPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    editor = panel.content_panel()._w_content
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    panel._var_popup.variable_selected.emit("${CLAUDE_SKILL_DIR}")
    assert project.rules[0].body == "use ${CLAUDE_SKILL_DIR}"


def test_variable_selection_inserts_into_claude_md_body(qapp, project):
    panel = ClaudeMdPanel()
    panel.set_project(project)
    panel._var_popup.variable_selected.emit("$ARGUMENTS")
    assert project.claude_md.body == "$ARGUMENTS"
