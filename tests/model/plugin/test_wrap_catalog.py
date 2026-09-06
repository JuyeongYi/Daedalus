# tests/model/plugin/test_wrap_catalog.py
"""랩핑 소스 카탈로그 (WP-WR D2) — 루트 등록 파일 + 플러그인/스킬 발견.

루트 파일은 conftest의 _isolate_plugin_roots가 tmp 홈으로 격리한다 — 실제
홈을 읽으면 개발자가 등록해 둔 루트에 따라 단언이 그 머신에서만 깨진다.
"""
from __future__ import annotations

import json

from daedalus.model.plugin import wrap_catalog
from daedalus.model.plugin.wrap_catalog import (
    PluginRoot,
    add_plugin_root,
    discover_plugins,
    load_plugin_roots,
    remove_plugin_root,
    save_plugin_roots,
    scan_catalog,
)


def _make_plugin(root, name, skills=(), manifest_name=None, description=""):
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
    return plugin_dir


# ─────────────────────────── 루트 등록 파일 ───────────────────────────


def test_roots_roundtrip():
    save_plugin_roots([PluginRoot(path="C:/x", marketplace="mkt")])
    roots = load_plugin_roots()
    assert [(r.path, r.marketplace) for r in roots] == [("C:/x", "mkt")]


def test_missing_file_is_empty():
    assert load_plugin_roots() == []


def test_broken_file_is_empty(capsys):
    path = wrap_catalog.plugin_roots_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_plugin_roots() == []
    assert "읽지 못했습니다" in capsys.readouterr().err


def test_add_dedupes_by_normalized_path():
    add_plugin_root("C:/one", "a")
    # 대소문자·구분자만 다른 같은 경로 — marketplace 갱신으로 취급 (중복 등재 금지)
    roots = add_plugin_root("c:\\one", "b")
    assert len(roots) == 1
    assert roots[0].marketplace == "b"


def test_remove_root():
    add_plugin_root("C:/one")
    assert remove_plugin_root("C:/one") is True
    assert load_plugin_roots() == []
    assert remove_plugin_root("C:/one") is False


# ─────────────────────────── 발견 ───────────────────────────


def test_discover_plugins_and_skills(tmp_path):
    root = tmp_path / "mkt-repo"
    _make_plugin(root / "plugins", "alpha", skills=["review", "lint"],
                 description="Alpha plugin.")
    plugins = discover_plugins(PluginRoot(path=str(root), marketplace="my-mkt"))
    assert [p.name for p in plugins] == ["alpha"]
    alpha = plugins[0]
    assert alpha.description == "Alpha plugin."
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
    plugins = discover_plugins(PluginRoot(path=str(root)))
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
    plugins = discover_plugins(PluginRoot(path=str(root), marketplace="manual"))
    assert plugins[0].skills[0].source == "beta@manual:run"


def test_bare_source_without_marketplace(tmp_path):
    _make_plugin(tmp_path, "gamma", skills=["go"])
    plugins = discover_plugins(PluginRoot(path=str(tmp_path)))
    assert plugins[0].skills[0].source == "gamma:go"


def test_root_itself_can_be_a_plugin(tmp_path):
    plugin_dir = _make_plugin(tmp_path, "solo", skills=["one"])
    plugins = discover_plugins(PluginRoot(path=str(plugin_dir)))
    assert [p.name for p in plugins] == ["solo"]


def test_manifest_name_fallback_to_dir_name(tmp_path):
    plugin_dir = tmp_path / "dirname"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text("{}", encoding="utf-8")
    plugins = discover_plugins(PluginRoot(path=str(tmp_path)))
    assert [p.name for p in plugins] == ["dirname"]


def test_skill_dir_without_skill_md_is_skipped(tmp_path):
    plugin_dir = _make_plugin(tmp_path, "p", skills=["real"])
    (plugin_dir / "skills" / "empty").mkdir()
    plugins = discover_plugins(PluginRoot(path=str(tmp_path)))
    assert [s.name for s in plugins[0].skills] == ["real"]


def test_no_recursion_into_plugin_or_skip_dirs(tmp_path):
    root = tmp_path
    outer = _make_plugin(root, "outer", skills=["a"])
    # 플러그인 안의 플러그인은 세지 않는다 (재귀 중단)
    _make_plugin(outer / "vendor", "inner", skills=["b"])
    # 스킵 디렉토리 밑도 세지 않는다
    _make_plugin(root / "node_modules", "dep", skills=["c"])
    plugins = discover_plugins(PluginRoot(path=str(root)))
    assert [p.name for p in plugins] == ["outer"]


def test_missing_root_dir_is_empty():
    assert discover_plugins(PluginRoot(path="Z:/no/such/dir")) == []


def test_scan_catalog_uses_registered_roots(tmp_path):
    _make_plugin(tmp_path, "alpha", skills=["s"])
    add_plugin_root(str(tmp_path), "m")
    catalog = scan_catalog()
    assert len(catalog) == 1
    root, plugins = catalog[0]
    assert root.marketplace == "m"
    assert plugins[0].skills[0].source == "alpha@m:s"
