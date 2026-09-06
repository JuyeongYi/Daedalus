# tests/mcp/test_wrap_tools.py
"""외부 플러그인 카탈로그 MCP 도구 (WP-WR D2) — GUI 카탈로그 창과의 패리티.

list_wrappable_skills/list_marketplace_folders/add_marketplace_folder/
remove_marketplace_folder/set_external_plugins +
create_skill(kind="wrapped", source=...) 경로. 등록 파일은 conftest가 격리한다.
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
def marketplace(tmp_path):
    """플러그인 1개(스킬 2개 + .mcp.json 서버 1개) 픽스처 마켓플레이스 폴더."""
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
    (plugin_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"alpha-srv": {"command": "x"}}}), encoding="utf-8"
    )
    return tmp_path / "catalog"


def test_folders_empty_note(tools):
    out = tools.list_wrappable_skills()
    assert out["marketplace_folders"] == []
    assert "add_marketplace_folder" in out["note"]


def test_add_list_remove_folders(tools, marketplace):
    out = tools.add_marketplace_folder(str(marketplace), "mkt")
    assert out["marketplace_folders"][0]["marketplace"] == "mkt"
    assert tools.list_marketplace_folders()["marketplace_folders"][0]["path"] == str(marketplace)
    assert tools.remove_marketplace_folder(str(marketplace)) == {"removed": str(marketplace)}
    assert tools.list_marketplace_folders()["marketplace_folders"] == []


def test_add_nonexistent_folder_rejected(tools):
    with pytest.raises(ValueError, match="실존"):
        tools.add_marketplace_folder("Z:/no/such/dir")


def test_remove_unknown_folder_rejected(tools):
    with pytest.raises(ValueError, match="등록되지 않은"):
        tools.remove_marketplace_folder("C:/never")


def test_list_wrappable_skills(tools, marketplace):
    tools.add_marketplace_folder(str(marketplace), "mkt")
    out = tools.list_wrappable_skills()
    plugins = out["marketplace_folders"][0]["plugins"]
    assert [p["plugin_id"] for p in plugins] == ["alpha@mkt"]
    assert plugins[0]["used"] is False
    assert plugins[0]["mcp_servers"] == ["alpha-srv"]
    sources = [s["source"] for s in plugins[0]["skills"]]
    assert sources == ["alpha@mkt:lint", "alpha@mkt:review"]
    assert out["external_plugins"] == []


def test_set_external_plugins_replace_and_undo(tools, window):
    out = tools.set_external_plugins(["alpha@mkt", "beta@mkt", "alpha@mkt"])
    assert out["new"] == ["alpha@mkt", "beta@mkt"]  # 순서 보존·중복 제거
    assert window._project.external_plugins == ["alpha@mkt", "beta@mkt"]
    tools.undo()
    assert window._project.external_plugins == []
    tools.redo()
    assert window._project.external_plugins == ["alpha@mkt", "beta@mkt"]


def test_set_external_plugins_rejects_empty_id(tools):
    with pytest.raises(ValueError, match="빈 플러그인"):
        tools.set_external_plugins(["ok@mkt", "  "])


def test_used_flag_follows_declaration(tools, marketplace):
    tools.add_marketplace_folder(str(marketplace), "mkt")
    tools.set_external_plugins(["alpha@mkt"])
    plugins = tools.list_wrappable_skills()["marketplace_folders"][0]["plugins"]
    assert plugins[0]["used"] is True


def test_get_project_meta_lists_external_plugins(tools):
    tools.set_external_plugins(["alpha@mkt"])
    out = tools.get_project(sections=["meta"])
    assert out["external_plugins"] == ["alpha@mkt"]


def test_create_skill_with_source_declares_plugin(tools, window):
    """랩핑 생성 시 미선언 플러그인은 선언까지 함께 — 1 undo (GUI와 같은 실체)."""
    out = tools.create_skill("wrap-it", kind="wrapped", source="other@mkt:code-review")
    assert out["source"] == "other@mkt:code-review"
    assert out["external_plugins"] == ["other@mkt"]
    skill = window._project.skills[0]
    assert skill.kind == "wrapped_skill"
    assert skill.config.source == "other@mkt:code-review"
    assert window._project.external_plugins == ["other@mkt"]

    tools.undo()  # 생성+선언이 한 단위로 되돌아온다
    assert window._project.skills == []
    assert window._project.external_plugins == []
    tools.redo()
    assert window._project.skills[0].config.source == "other@mkt:code-review"
    assert window._project.external_plugins == ["other@mkt"]


def test_create_skill_with_source_already_declared(tools, window):
    tools.set_external_plugins(["other@mkt"])
    tools.create_skill("wrap-it", kind="wrapped", source="other@mkt:code-review")
    assert window._project.external_plugins == ["other@mkt"]  # 중복 선언 없음
    tools.undo()  # 생성만 되돌아온다 (선언은 이전 편집 소유)
    assert window._project.skills == []
    assert window._project.external_plugins == ["other@mkt"]


def test_source_rejected_for_non_wrapped(tools, window):
    with pytest.raises(ValueError, match="wrapped"):
        tools.create_skill("s", kind="procedural", source="other@mkt:x")
    assert window._project.skills == []  # 거절이면 생성도 없어야 한다


def test_source_with_xy_places_in_one_undo(tools, window):
    """source+x/y = 생성+선언+배치 1 undo — 레지스트리 후보 드롭과 같은 경로."""
    out = tools.create_skill("s", kind="wrapped", source="other@mkt:x", x=10, y=20)
    assert out["placed"] is True
    vm = next(v for v in window._project_vm.state_vms if v.model.name == "s")
    assert (vm.x, vm.y) == (10.0, 20.0)
    tools.undo()
    assert window._project.skills == []
    assert window._project.external_plugins == []


def test_source_with_half_coordinates_rejected(tools, window):
    with pytest.raises(ValueError, match="함께"):
        tools.create_skill("s", kind="wrapped", source="other@mkt:x", x=10)
    assert window._project.skills == []
