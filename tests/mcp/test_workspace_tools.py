"""작업 폴더 문서 MCP 도구 — CLAUDE.md 구역 + 규칙 파일 (WP-WD).

"MCP로 접근·수정 가능해야 한다"는 것이 이 WP의 확정 요구(D7)다. GUI 패널과 같은
모델을 만지고, 편집 결과가 화면에도 반영되어야 한다.
"""
from __future__ import annotations

import pytest

from daedalus.mcp.tools import DaedalusTools
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.workspace_doc import WorkspaceDoc
from daedalus.model.project import PluginProject


@pytest.fixture
def tools(qapp):
    from daedalus.view.app import MainWindow

    project = PluginProject(name="my-plugin")
    project.build_target = BuildTarget.LOCAL
    win = MainWindow()
    win.set_project(project)
    yield DaedalusTools(win), win, project
    win.close()


# ─────────────────────────── 조회 ───────────────────────────


def test_list_reports_build_target_and_emission(tools):
    api, _win, project = tools
    result = api.list_workspace_docs()
    assert result["build_target"] == "local"
    assert result["emitted"] is True


def test_list_warns_via_emitted_flag_in_marketplace(tools):
    api, win, project = tools
    project.build_target = BuildTarget.MARKETPLACE
    assert api.list_workspace_docs()["emitted"] is False


def test_list_shows_rules_with_lengths(tools):
    api, _win, project = tools
    project.rules = [WorkspaceDoc(name="testing", body="12345", paths=["src/**"])]
    assert api.list_workspace_docs()["rules"] == [
        {"name": "testing", "length": 5, "paths": ["src/**"]}
    ]


def test_get_rule_returns_body(tools):
    api, _win, project = tools
    project.rules = [WorkspaceDoc(name="testing", body="run pytest")]
    assert api.get_workspace_doc("testing")["body"] == "run pytest"


def test_get_unknown_rule_lists_available(tools):
    api, _win, project = tools
    project.rules = [WorkspaceDoc(name="testing")]
    with pytest.raises(ValueError) as excinfo:
        api.get_workspace_doc("typo")
    assert "testing" in str(excinfo.value)


# ─────────────────────────── CLAUDE.md 구역 ───────────────────────────


def test_set_claude_md_creates_doc(tools):
    api, _win, project = tools
    result = api.set_claude_md("always lint")
    assert project.claude_md is not None
    assert project.claude_md.body == "always lint"
    assert result["title"] == "my-plugin"


def test_set_claude_md_title(tools):
    api, _win, project = tools
    api.set_claude_md("x", title="house rules")
    assert project.claude_md.name == "house rules"


def test_set_claude_md_replaces_body(tools):
    api, _win, project = tools
    api.set_claude_md("first")
    result = api.set_claude_md("second")
    assert project.claude_md.body == "second"
    assert result["old_length"] == 5


def test_set_claude_md_is_undoable_in_the_editor(tools):
    """본문은 자체 undo 스택을 쓴다(WP-BU) — MCP 편집도 그 문서에 올라간다."""
    api, win, project = tools
    api.set_claude_md("first")
    api.set_claude_md("second")
    editor = win._claude_md_panel.content_panel()._w_content
    editor.undo()
    assert project.claude_md.body == "first"


def test_set_claude_md_shows_up_in_the_panel(tools):
    api, win, project = tools
    api.set_claude_md("visible text")
    assert "visible text" in win._claude_md_panel.content_panel()._w_content.toPlainText()


# ─────────────────────────── 규칙 파일 ───────────────────────────


def test_create_rule(tools):
    api, _win, project = tools
    api.create_rule("testing", body="run pytest")
    assert [(d.name, d.body) for d in project.rules] == [("testing", "run pytest")]


def test_create_rule_rejects_duplicate(tools):
    api, _win, project = tools
    api.create_rule("testing")
    with pytest.raises(ValueError):
        api.create_rule("testing")
    assert len(project.rules) == 1


def test_create_rule_shows_in_panel_list(tools):
    api, win, _project = tools
    api.create_rule("testing")
    panel = win._rules_panel
    assert [panel._list.item(i).text() for i in range(panel._list.count())] == [
        "testing"
    ]


def test_set_rule_body(tools):
    api, _win, project = tools
    api.create_rule("testing")
    api.set_rule_body("testing", "validate input")
    assert project.rules[0].body == "validate input"


def test_set_rule_paths(tools):
    api, _win, project = tools
    api.create_rule("testing")
    result = api.set_rule_paths("testing", ["src/**/*.ts", "lib/**"])
    assert project.rules[0].paths == ["src/**/*.ts", "lib/**"]
    assert result["old_paths"] == []


def test_set_rule_paths_drops_blank_entries(tools):
    api, _win, project = tools
    api.create_rule("testing")
    api.set_rule_paths("testing", ["  ", " src/** "])
    assert project.rules[0].paths == ["src/**"]


def test_set_rule_paths_empty_list_clears(tools):
    """비우면 프론트매터가 나가지 않아 규칙이 항상 로드된다."""
    api, _win, project = tools
    api.create_rule("testing")
    api.set_rule_paths("testing", ["src/**"])
    api.set_rule_paths("testing", [])
    assert project.rules[0].paths == []


def test_set_rule_paths_rejects_unknown_rule(tools):
    api, _win, _project = tools
    with pytest.raises(ValueError):
        api.set_rule_paths("typo", ["src/**"])


def test_set_rule_paths_shows_in_panel(tools):
    api, win, _project = tools
    api.create_rule("testing")
    api.set_rule_paths("testing", ["src/**"])
    assert win._rules_panel._paths.get_tags() == ["src/**"]


def test_get_rule_returns_paths(tools):
    api, _win, project = tools
    project.rules = [WorkspaceDoc(name="testing", paths=["src/**"])]
    assert api.get_workspace_doc("testing")["paths"] == ["src/**"]


def test_rename_rule(tools):
    api, _win, project = tools
    api.create_rule("testing")
    api.rename_rule("testing", "qa")
    assert project.rules[0].name == "qa"


def test_rename_rule_rejects_collision(tools):
    api, _win, project = tools
    api.create_rule("testing")
    api.create_rule("qa")
    with pytest.raises(ValueError):
        api.rename_rule("testing", "qa")
    assert [d.name for d in project.rules] == ["testing", "qa"]


def test_rename_rule_to_same_name_is_allowed(tools):
    api, _win, project = tools
    api.create_rule("testing")
    api.rename_rule("testing", "testing")
    assert project.rules[0].name == "testing"


def test_delete_rule(tools):
    api, _win, project = tools
    api.create_rule("testing")
    result = api.delete_rule("testing")
    assert project.rules == []
    assert "지우지 않습니다" in result["note"]


def test_delete_rule_drops_document_cache(tools):
    from daedalus.view.editors import body_documents

    api, _win, project = tools
    api.create_rule("testing", body="x")
    doc = project.rules[0]
    api.set_rule_body("testing", "y")  # 문서를 만든다
    assert body_documents.registry().peek(doc) is not None
    api.delete_rule("testing")
    assert body_documents.registry().peek(doc) is None


def test_delete_unknown_rule_raises(tools):
    api, _win, _project = tools
    with pytest.raises(ValueError):
        api.delete_rule("nope")


# ─────────────────────────── 노출 ───────────────────────────


def test_tools_are_exposed_over_mcp():
    from daedalus.mcp.service import TOOL_NAMES

    for name in (
        "list_workspace_docs", "get_workspace_doc", "set_claude_md",
        "create_rule", "set_rule_body", "rename_rule", "delete_rule",
    ):
        assert name in TOOL_NAMES
        assert callable(getattr(DaedalusTools, name))
