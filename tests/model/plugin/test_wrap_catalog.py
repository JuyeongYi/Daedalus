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


# ────────── 마켓이 선언만 하고 실물은 없는 플러그인 (사용자 보고 2026-09-07) ──────────


def _make_marketplace(root, name, declared):
    """marketplace.json에 plugins를 선언한 마켓 폴더."""
    meta = root / ".claude-plugin"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "marketplace.json").write_text(
        json.dumps({"name": name, "plugins": declared}), encoding="utf-8"
    )


def test_declared_without_files_is_listed_by_name_only(tmp_path):
    """마켓은 목록을 **선언**하고 실물은 따로 온다 — 실물이 없어도 이름·설명은
    알 수 있어야 사용 선언을 할 수 있다(실측: 공식 마켓 291개 선언 / 저장소
    동봉 40개라 나머지가 카탈로그에서 통째로 빠져 있었다).
    """
    root = tmp_path / "mkt"
    _make_marketplace(root, "m", [
        {"name": "alpha", "description": "동봉"},
        {"name": "remote-only", "description": "아직 안 받음",
         "source": {"source": "git-subdir", "url": "https://x/y.git"}},
    ])
    _make_plugin(root / "plugins", "alpha", skills=["s"])

    plugins = {p.name: p for p in discover_plugins(MarketplaceFolder(path=str(root)))}
    assert set(plugins) == {"alpha", "remote-only"}

    assert plugins["alpha"].files_from == "marketplace"
    assert plugins["alpha"].has_files is True
    assert [s.name for s in plugins["alpha"].skills] == ["s"]

    remote = plugins["remote-only"]
    assert remote.has_files is False
    assert remote.files_from == ""
    assert remote.description == "아직 안 받음"
    assert remote.plugin_id == "remote-only@m"  # 사용 선언은 이것만 있으면 된다
    # **스킬은 실물이 있어야 안다** — 랩핑은 받아온 뒤에
    assert remote.skills == []


def test_local_실물이_선언을_이긴다(tmp_path):
    """같은 이름이면 로컬 실물 쪽이 남는다 — 그쪽만 스킬을 안다."""
    root = tmp_path / "mkt"
    _make_marketplace(root, "m", [{"name": "alpha", "description": "선언 설명"}])
    _make_plugin(root / "plugins", "alpha", skills=["s"], description="실물 설명")

    plugins = discover_plugins(MarketplaceFolder(path=str(root)))
    assert len(plugins) == 1
    assert plugins[0].files_from == "marketplace"
    assert plugins[0].description == "실물 설명"


# --- 실물의 출처 세 곳 (사용자 보고 2026-09-07) ---


def test_cc_installed_plugin_is_read(tmp_path, monkeypatch):
    """CC가 설치한 플러그인의 실물은 **마켓 저장소가 아니라** 별도 캐시에 있다.

    그곳을 안 보던 시절에는 사용자가 실제로 설치한 플러그인이 카탈로그에
    "미설치"로 나왔다(사용자 보고 — 이 테스트가 그 회귀를 막는다).
    """
    from daedalus.model.plugin import wrap_catalog

    root = tmp_path / "mkt"
    _make_marketplace(root, "m", [{"name": "installed-one", "description": "선언"}])
    installed_dir = tmp_path / "cc" / "cache" / "m" / "installed-one" / "1.0.0"
    _make_plugin(installed_dir.parent, "1.0.0", skills=["review"])

    record = tmp_path / "cc" / "installed_plugins.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"version": 2, "plugins": {
        "installed-one@m": [{"scope": "user", "installPath": str(installed_dir),
                             "lastUpdated": "2026-09-01T00:00:00Z"}],
    }}), encoding="utf-8")
    monkeypatch.setattr(wrap_catalog, "cc_install_file", lambda home_dir=None: record)

    plugin = discover_plugins(MarketplaceFolder(path=str(root)))[0]
    assert plugin.files_from == "installed"
    assert [s.name for s in plugin.skills] == ["review"]
    # 선언의 설명이 정본 — 목록에서 이름 옆에 보이는 그것이다
    assert plugin.description == "선언"


def test_cc_install_record_ignores_missing_dirs(tmp_path, monkeypatch):
    """기록만 남고 폴더가 지워졌으면 '읽었다'고 말하지 않는다."""
    from daedalus.model.plugin import wrap_catalog

    record = tmp_path / "installed_plugins.json"
    record.write_text(json.dumps({"plugins": {
        "gone@m": [{"installPath": str(tmp_path / "nope")}],
    }}), encoding="utf-8")
    monkeypatch.setattr(wrap_catalog, "cc_install_file", lambda home_dir=None: record)
    assert wrap_catalog.cc_installed_dirs() == {}


def test_cc_install_record_takes_latest(tmp_path, monkeypatch):
    """같은 id에 여러 설치가 있으면 마지막으로 갱신된 것."""
    from daedalus.model.plugin import wrap_catalog

    old_dir, new_dir = tmp_path / "v1", tmp_path / "v2"
    old_dir.mkdir(); new_dir.mkdir()
    record = tmp_path / "installed_plugins.json"
    record.write_text(json.dumps({"plugins": {"p@m": [
        {"installPath": str(old_dir), "lastUpdated": "2026-01-01T00:00:00Z"},
        {"installPath": str(new_dir), "lastUpdated": "2026-08-01T00:00:00Z"},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(wrap_catalog, "cc_install_file", lambda home_dir=None: record)
    assert wrap_catalog.cc_installed_dirs() == {"p@m": new_dir}


def test_cloned_cache_is_read(tmp_path, monkeypatch):
    """받아 둔 클론도 실물이다 — 카탈로그가 그것을 읽어야 랩핑까지 이어진다.

    창 안 세션 dict에만 담아 두면 "스킬 목록을 받아왔는데 어디서도 랩핑할 수
    없다"가 된다(사용자 보고 2026-09-07).
    """
    from daedalus.model.plugin import plugin_cache

    spec = {"source": "git-subdir", "url": "https://x/y.git", "path": "p",
            "sha": "abc"}
    root = tmp_path / "mkt"
    _make_marketplace(root, "m", [{"name": "cloned", "source": spec}])

    cached_dir = tmp_path / "cached-plugin"
    _make_plugin(cached_dir.parent, cached_dir.name, skills=["lint"])
    monkeypatch.setattr(plugin_cache, "cached_path", lambda s: cached_dir)

    plugin = discover_plugins(MarketplaceFolder(path=str(root)))[0]
    assert plugin.files_from == "cache"
    assert [s.name for s in plugin.skills] == ["lint"]


def test_files_without_manifest_are_not_an_error(tmp_path, monkeypatch, capsys):
    """스킬 없이 LSP·훅만 주는 플러그인이 있다(실측: pyright-lsp) — 매니페스트가
    없다고 목록을 열 때마다 경고를 쏟으면 안 된다."""
    from daedalus.model.plugin import wrap_catalog

    root = tmp_path / "mkt"
    _make_marketplace(root, "m", [{"name": "bare"}])
    bare = tmp_path / "bare-install"
    bare.mkdir()
    (bare / "README.md").write_text("x", encoding="utf-8")
    record = tmp_path / "installed_plugins.json"
    record.write_text(json.dumps({"plugins": {
        "bare@m": [{"installPath": str(bare)}],
    }}), encoding="utf-8")
    monkeypatch.setattr(wrap_catalog, "cc_install_file", lambda home_dir=None: record)

    plugin = discover_plugins(MarketplaceFolder(path=str(root)))[0]
    assert plugin.files_from == "installed"
    assert plugin.skills == []
    assert "읽지 못했습니다" not in capsys.readouterr().err


def test_block_scalar_description_is_read(tmp_path):
    """공식 마켓의 여러 스킬이 `description: >` 형식을 쓴다 — 한 줄만 보면
    설명이 문자 그대로 ">"로 표시된다(실측)."""
    root = tmp_path / "mkt"
    plugin_dir = root / "plugins" / "p"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(json.dumps({"name": "p"}), encoding="utf-8")
    sdir = plugin_dir / "skills" / "s"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text(
        "\n".join([
            "---",
            "name: s",
            "description: >",
            "  Edits photos in bulk.",
            "  Use when the user has many images.",
            "allowed-tools: [Read]",
            "---",
            "",
        ]),
        encoding="utf-8",
    )

    plugin = discover_plugins(MarketplaceFolder(path=str(root)))[0]
    assert plugin.skills[0].description == (
        "Edits photos in bulk. Use when the user has many images."
    )
