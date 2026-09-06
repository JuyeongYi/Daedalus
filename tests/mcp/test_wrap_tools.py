# tests/mcp/test_wrap_tools.py
"""랩핑 카탈로그 MCP 도구 (WP-WR D2) — GUI 카탈로그 창과의 패리티.

list_wrappable_skills/list_plugin_roots/add_plugin_root/remove_plugin_root +
create_skill(kind="wrapped", source=...) 경로. 루트 파일은 conftest가 격리한다.
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
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


@pytest.fixture
def plugin_root(tmp_path):
    """플러그인 1개(스킬 2개) 픽스처 트리."""
    plugin_dir = tmp_path / "catalog" / "alpha"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(
        json.dumps({"name": "alpha", "description": "Alpha."}), encoding="utf-8"
    )
    for skill in ("review", "lint"):
        sdir = plugin_dir / "skills" / skill
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Does {skill}.\n---\n", encoding="utf-8"
        )
    return tmp_path / "catalog"


def test_roots_empty_note(tools):
    out = tools.list_wrappable_skills()
    assert out["roots"] == []
    assert "add_plugin_root" in out["note"]


def test_add_list_remove_roots(tools, plugin_root):
    out = tools.add_plugin_root(str(plugin_root), "mkt")
    assert out["roots"][0]["marketplace"] == "mkt"
    assert tools.list_plugin_roots()["roots"][0]["path"] == str(plugin_root)
    assert tools.remove_plugin_root(str(plugin_root)) == {"removed": str(plugin_root)}
    assert tools.list_plugin_roots()["roots"] == []


def test_add_nonexistent_root_rejected(tools):
    with pytest.raises(ValueError, match="실존"):
        tools.add_plugin_root("Z:/no/such/dir")


def test_remove_unknown_root_rejected(tools):
    with pytest.raises(ValueError, match="등록되지 않은"):
        tools.remove_plugin_root("C:/never")


def test_list_wrappable_skills(tools, plugin_root):
    tools.add_plugin_root(str(plugin_root), "mkt")
    out = tools.list_wrappable_skills()
    plugins = out["roots"][0]["plugins"]
    assert [p["name"] for p in plugins] == ["alpha"]
    sources = [s["source"] for s in plugins[0]["skills"]]
    assert sources == ["alpha@mkt:lint", "alpha@mkt:review"]
    assert all(s["already_wrapped"] is False for s in plugins[0]["skills"])


def test_already_wrapped_marker(tools, plugin_root):
    tools.add_plugin_root(str(plugin_root), "mkt")
    tools.create_skill("my-review", kind="wrapped", source="alpha@mkt:review")
    skills = tools.list_wrappable_skills()["roots"][0]["plugins"][0]["skills"]
    by_name = {s["name"]: s["already_wrapped"] for s in skills}
    assert by_name == {"review": True, "lint": False}


def test_set_plugin_excluded_filters_listing(tools, plugin_root):
    """체크 해제된 플러그인은 스킬 목록 없이 excluded 표시만 — GUI 체크박스와
    같은 실체(wrap_catalog.set_plugin_excluded)."""
    tools.add_plugin_root(str(plugin_root), "mkt")
    out = tools.set_plugin_excluded(str(plugin_root), "alpha", True)
    assert out["excluded_now"] == ["alpha"]
    assert tools.list_plugin_roots()["roots"][0]["excluded"] == ["alpha"]
    plugins = tools.list_wrappable_skills()["roots"][0]["plugins"]
    assert plugins == [{"name": "alpha", "excluded": True}]
    # 복귀하면 스킬이 다시 나온다
    tools.set_plugin_excluded(str(plugin_root), "alpha", False)
    plugins = tools.list_wrappable_skills()["roots"][0]["plugins"]
    assert [s["name"] for s in plugins[0]["skills"]] == ["lint", "review"]


def test_set_plugin_excluded_unknown_root_rejected(tools):
    with pytest.raises(ValueError, match="등록되지 않은"):
        tools.set_plugin_excluded("C:/never", "p", True)


def test_create_skill_with_source(tools, window):
    out = tools.create_skill("wrap-it", kind="wrapped", source="other@mkt:code-review")
    assert out["source"] == "other@mkt:code-review"
    skill = window._project.skills[0]
    assert skill.kind == "wrapped_skill"
    assert skill.config.source == "other@mkt:code-review"


def test_create_skill_with_source_is_one_undo(tools, window):
    tools.create_skill("wrap-it", kind="wrapped", source="other@mkt:code-review")
    tools.undo()
    assert window._project.skills == []
    tools.redo()
    assert window._project.skills[0].config.source == "other@mkt:code-review"


def test_source_rejected_for_non_wrapped(tools, window):
    with pytest.raises(ValueError, match="wrapped"):
        tools.create_skill("s", kind="procedural", source="other@mkt:x")
    assert window._project.skills == []  # 거절이면 생성도 없어야 한다
