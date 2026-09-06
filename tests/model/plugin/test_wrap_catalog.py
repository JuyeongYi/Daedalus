# tests/model/plugin/test_wrap_catalog.py
"""외부 마켓플레이스 카탈로그 (WP-WR D2) — 폴더 등록 파일 + 플러그인/스킬 발견.

등록 파일(~/.daedalus/external_marketplaces.json)은 conftest의
_isolate_external_marketplaces가 tmp 홈으로 격리한다 — 실제 홈을 읽으면
개발자가 등록해 둔 폴더에 따라 단언이 그 머신에서만 깨진다.
"""
from __future__ import annotations

import json

from daedalus.model.plugin import wrap_catalog
from daedalus.model.plugin.wrap_catalog import (
    MarketplaceFolder,
    add_marketplace,
    discover_plugins,
    load_marketplaces,
    remove_marketplace,
    save_marketplaces,
    scan_catalog,
    used_plugin_mcp_servers,
)


def _make_plugin(root, name, skills=(), manifest_name=None, description="",
                 mcp_servers=None):
    plugin_dir = root / name
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    manifest = {"name": manifest_name if manifest_name is not None else name}
    if description:
        manifest["description"] = description
    (meta / "plugin.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    for skill in skills:
        sdir = plugin_dir / "skills" / skill
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Does {skill}.\n---\n\nBody.\n",
            encoding="utf-8",
        )
    if mcp_servers:
        (plugin_dir / ".mcp.json").write_text(
            json.dumps({"mcpServers": {s: {"command": "x"} for s in mcp_servers}}),
            encoding="utf-8",
        )
    return plugin_dir


# ─────────────────────────── 등록 파일 ───────────────────────────


def test_marketplaces_roundtrip():
    save_marketplaces([MarketplaceFolder(path="C:/x", marketplace="mkt")])
    folders = load_marketplaces()
    assert [(f.path, f.marketplace) for f in folders] == [("C:/x", "mkt")]


def test_missing_file_is_empty():
    assert load_marketplaces() == []


def test_broken_file_is_empty(capsys):
    path = wrap_catalog.marketplaces_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_marketplaces() == []
    assert "읽지 못했습니다" in capsys.readouterr().err


def test_add_dedupes_by_normalized_path():
    add_marketplace("C:/one", "a")
    # 대소문자·구분자만 다른 같은 경로 — 이름 갱신으로 취급 (중복 등재 금지)
    folders = add_marketplace("c:\\one", "b")
    assert len(folders) == 1
    assert folders[0].marketplace == "b"


def test_remove_marketplace():
    add_marketplace("C:/one")
    assert remove_marketplace("C:/one") is True
    assert load_marketplaces() == []
    assert remove_marketplace("C:/one") is False


# ─────────────────────────── 발견 ───────────────────────────


def test_discover_plugins_and_skills(tmp_path):
    root = tmp_path / "mkt-repo"
    _make_plugin(root / "plugins", "alpha", skills=["review", "lint"],
                 description="Alpha plugin.")
    plugins = discover_plugins(MarketplaceFolder(path=str(root), marketplace="my-mkt"))
    assert [p.name for p in plugins] == ["alpha"]
    alpha = plugins[0]
    assert alpha.description == "Alpha plugin."
    assert alpha.plugin_id == "alpha@my-mkt"
    assert [(s.name, s.source) for s in alpha.skills] == [
        ("lint", "alpha@my-mkt:lint"),
        ("review", "alpha@my-mkt:review"),
    ]
    assert alpha.skills[1].description == "Does review."


def test_marketplace_name_autodetected_from_marketplace_json(tmp_path):
    root = tmp_path / "repo"
    meta = root / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "marketplace.json").write_text(
        json.dumps({"name": "auto-mkt"}), encoding="utf-8"
    )
    _make_plugin(root / "plugins", "beta", skills=["run"])
    plugins = discover_plugins(MarketplaceFolder(path=str(root)))
    assert plugins[0].marketplace == "auto-mkt"
    assert plugins[0].skills[0].source == "beta@auto-mkt:run"


def test_explicit_marketplace_beats_autodetect(tmp_path):
    root = tmp_path / "repo"
    meta = root / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "marketplace.json").write_text(
        json.dumps({"name": "auto-mkt"}), encoding="utf-8"
    )
    _make_plugin(root / "plugins", "beta", skills=["run"])
    plugins = discover_plugins(MarketplaceFolder(path=str(root), marketplace="manual"))
    assert plugins[0].skills[0].source == "beta@manual:run"


def test_bare_source_without_marketplace(tmp_path):
    _make_plugin(tmp_path, "gamma", skills=["go"])
    plugins = discover_plugins(MarketplaceFolder(path=str(tmp_path)))
    assert plugins[0].plugin_id == "gamma"
    assert plugins[0].skills[0].source == "gamma:go"


def test_root_itself_can_be_a_plugin(tmp_path):
    plugin_dir = _make_plugin(tmp_path, "solo", skills=["one"])
    plugins = discover_plugins(MarketplaceFolder(path=str(plugin_dir)))
    assert [p.name for p in plugins] == ["solo"]


def test_manifest_name_fallback_to_dir_name(tmp_path):
    plugin_dir = tmp_path / "dirname"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text("{}", encoding="utf-8")
    plugins = discover_plugins(MarketplaceFolder(path=str(tmp_path)))
    assert [p.name for p in plugins] == ["dirname"]


def test_skill_dir_without_skill_md_is_skipped(tmp_path):
    plugin_dir = _make_plugin(tmp_path, "p", skills=["real"])
    (plugin_dir / "skills" / "empty").mkdir()
    plugins = discover_plugins(MarketplaceFolder(path=str(tmp_path)))
    assert [s.name for s in plugins[0].skills] == ["real"]


def test_no_recursion_into_plugin_or_skip_dirs(tmp_path):
    root = tmp_path
    outer = _make_plugin(root, "outer", skills=["a"])
    # 플러그인 안의 플러그인은 세지 않는다 (재귀 중단)
    _make_plugin(outer / "vendor", "inner", skills=["b"])
    # 스킵 디렉토리 밑도 세지 않는다
    _make_plugin(root / "node_modules", "dep", skills=["c"])
    plugins = discover_plugins(MarketplaceFolder(path=str(root)))
    assert [p.name for p in plugins] == ["outer"]


def test_missing_folder_is_empty():
    assert discover_plugins(MarketplaceFolder(path="Z:/no/such/dir")) == []


def test_scan_catalog_uses_registered_folders(tmp_path):
    _make_plugin(tmp_path, "alpha", skills=["s"])
    add_marketplace(str(tmp_path), "m")
    catalog = scan_catalog()
    assert len(catalog) == 1
    folder, plugins = catalog[0]
    assert folder.marketplace == "m"
    assert plugins[0].skills[0].source == "alpha@m:s"


# ─────────────────────────── 동봉 MCP 서버 (.mcp.json) ───────────────────────────


def test_plugin_mcp_servers_discovered(tmp_path):
    _make_plugin(tmp_path, "alpha", skills=["s"], mcp_servers=["srv-b", "srv-a"])
    plugins = discover_plugins(MarketplaceFolder(path=str(tmp_path), marketplace="m"))
    assert plugins[0].mcp_servers == ["srv-a", "srv-b"]  # 이름순


def test_resolve_skill_file(tmp_path):
    plugin_dir = _make_plugin(tmp_path, "alpha", skills=["review"])
    add_marketplace(str(tmp_path), "m")
    md = wrap_catalog.resolve_skill_file("alpha@m:review")
    assert md == plugin_dir / "skills" / "review" / "SKILL.md"
    assert wrap_catalog.resolve_skill_file("alpha@other:review") is None  # 마켓 불일치
    assert wrap_catalog.resolve_skill_file("alpha@m:nope") is None
    assert wrap_catalog.resolve_skill_file("") is None


def test_used_plugin_mcp_servers_filters_by_declaration(tmp_path):
    from daedalus.model.project import PluginProject

    _make_plugin(tmp_path, "alpha", skills=["s"], mcp_servers=["srv-a"])
    _make_plugin(tmp_path, "beta", skills=["t"], mcp_servers=["srv-b"])
    add_marketplace(str(tmp_path), "m")

    project = PluginProject(name="p")
    assert used_plugin_mcp_servers(project) == []  # 선언 없음 — 스캔도 생략
    project.external_plugins.append("alpha@m")
    assert used_plugin_mcp_servers(project) == ["srv-a"]  # 선언된 것만
