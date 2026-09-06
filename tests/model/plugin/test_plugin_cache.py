# tests/model/plugin/test_plugin_cache.py
"""미설치 플러그인 실물 캐시 (WP-WR) — `~/.daedalus/cache/plugin/`.

**이 테스트는 인터넷에 나가지 않고 git도 실행하지 않는다.** `_shallow_clone`을
가로채 "받았다면 이런 파일들이 생겼을 것"을 직접 만들고, 그것을 **몇 번**
불렀는지로 캐시 규약을 고정한다 — 진짜 클론을 돌리면 네트워크 상태에 따라
초록·빨강이 갈리고 상류 저장소가 바뀌면 이유 없이 깨진다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from daedalus.model.plugin import plugin_cache


@pytest.fixture
def cache_home(tmp_path, monkeypatch):
    """캐시 폴더를 tmp로 격리 — 실제 홈을 건드리면 개발자 머신에 쌓인다."""
    root = tmp_path / "cache" / "plugin"
    monkeypatch.setattr(plugin_cache, "cache_dir", lambda home_dir=None: root)
    return root


def _write_plugin(plugin_dir: Path, skills: dict[str, str]) -> None:
    """클론 결과를 흉내 낸다 — 스킬마다 프론트매터가 있는 SKILL.md."""
    for name, desc in skills.items():
        sdir = plugin_dir / "skills" / name
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8"
        )


@pytest.fixture
def fake_clone(monkeypatch):
    """`_shallow_clone`을 가로채 호출 기록 + 가짜 저장소 생성."""
    calls: list[plugin_cache.GitSource] = []

    def _clone(source, dest):
        calls.append(source)
        target = dest / source.path.strip("/") if source.path.strip("/") else dest
        _write_plugin(target, {"review": "Reviews code.", "lint": "Lints files."})

    monkeypatch.setattr(plugin_cache, "_shallow_clone", _clone)
    return calls


# --- source 해석 ---


def test_parse_git_subdir_prefers_sha():
    """SHA는 불변이라 캐시 키로 안전하다 — 태그(ref)는 옮겨 달릴 수 있다."""
    src = plugin_cache.parse_git_source({
        "source": "git-subdir",
        "url": "https://github.com/o/r.git",
        "path": "plugins/x",
        "ref": "v1.5.5",
        "sha": "30287f5e",
    })
    assert src == plugin_cache.GitSource(
        url="https://github.com/o/r.git", path="plugins/x", ref="30287f5e"
    )


def test_parse_github_shorthand():
    src = plugin_cache.parse_git_source({"source": "github", "repo": "o/r"})
    assert src is not None and src.url == "https://github.com/o/r.git"


@pytest.mark.parametrize("spec", [
    "./external_plugins/asana",      # 마켓 폴더 안 상대 경로 — 원격이 아니다
    {"source": "github"},            # repo도 url도 없다
    {"repo": "not a repo path"},
    None,
])
def test_parse_rejects_non_clonable(spec):
    assert plugin_cache.parse_git_source(spec) is None


def test_cache_key_is_path_safe_and_bounded():
    key = plugin_cache.GitSource(
        url="https://github.com/o/r.git", path="a/b", ref="x" * 300
    ).cache_key
    assert len(key) <= 120
    assert not set(key) - set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    )


def test_cache_key_separates_refs():
    """버전이 다르면 다른 폴더 — 같으면 낡은 실물을 새 것으로 오인한다."""
    base = {"url": "https://github.com/o/r.git", "path": "p"}
    a = plugin_cache.GitSource(**base, ref="aaa").cache_key
    b = plugin_cache.GitSource(**base, ref="bbb").cache_key
    assert a != b


# --- 캐시 규약 ---


SPEC = {
    "source": "git-subdir",
    "url": "https://github.com/o/r.git",
    "path": "plugins/x",
    "sha": "abc123",
}


def test_fetches_name_and_description(cache_home, fake_clone):
    """클론이므로 이름뿐 아니라 **설명까지** 나온다 — 설치본과 같은 스캐너."""
    skills = plugin_cache.cached_skills("remote-only@mkt", SPEC)
    assert [(s.name, s.description) for s in skills] == [
        ("lint", "Lints files."),
        ("review", "Reviews code."),
    ]
    # source는 그대로 랩핑에 쓸 수 있는 형식이다
    assert [s.source for s in skills] == [
        "remote-only@mkt:lint", "remote-only@mkt:review",
    ]


def test_same_ref_is_not_refetched(cache_home, fake_clone):
    plugin_cache.cached_skills("p@mkt", SPEC)
    plugin_cache.cached_skills("p@mkt", SPEC)
    assert len(fake_clone) == 1  # 두 번째는 인터넷에 나가지 않는다


def test_refresh_refetches(cache_home, fake_clone):
    plugin_cache.cached_skills("p@mkt", SPEC)
    plugin_cache.cached_skills("p@mkt", SPEC, refresh=True)
    assert len(fake_clone) == 2


def test_new_ref_refetches(cache_home, fake_clone):
    plugin_cache.cached_skills("p@mkt", SPEC)
    plugin_cache.cached_skills("p@mkt", {**SPEC, "sha": "def456"})
    assert len(fake_clone) == 2


def test_non_clonable_returns_none_without_touching_network(cache_home, fake_clone):
    assert plugin_cache.cached_skills("p@mkt", "./external_plugins/asana") is None
    assert fake_clone == []


def test_missing_path_in_repo_reports_declaration_mismatch(cache_home, monkeypatch):
    """받았는데 선언의 path가 저장소 구조와 다르면 그렇게 말한다."""
    monkeypatch.setattr(
        plugin_cache, "_shallow_clone",
        lambda source, dest: _write_plugin(dest / "elsewhere", {"a": "A."}),
    )
    with pytest.raises(plugin_cache.PluginCacheError, match="path"):
        plugin_cache.cached_skills("p@mkt", SPEC)


def test_failed_clone_leaves_no_half_cache(cache_home, monkeypatch):
    """받다 만 폴더를 남기면 다음 호출이 그것을 '이미 받은 것'으로 본다."""
    def _boom(source, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "partial").write_text("x", encoding="utf-8")
        raise plugin_cache.PluginCacheError("끊김")

    monkeypatch.setattr(plugin_cache, "_shallow_clone", _boom)
    with pytest.raises(plugin_cache.PluginCacheError):
        plugin_cache.cached_skills("p@mkt", SPEC)
    assert not list(cache_home.iterdir()) if cache_home.is_dir() else True


def test_clear_cache_counts_removed(cache_home, fake_clone):
    plugin_cache.cached_skills("p@mkt", SPEC)
    plugin_cache.cached_skills("p@mkt", {**SPEC, "sha": "other"})
    assert plugin_cache.clear_cache() == 2
    assert plugin_cache.clear_cache() == 0


def test_missing_git_is_reported_plainly(cache_home, monkeypatch):
    """git이 없는 환경에서 stack trace 대신 무엇을 깔라는지 말한다."""
    def _no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(plugin_cache.subprocess, "run", _no_git)
    with pytest.raises(plugin_cache.PluginCacheError, match="git"):
        plugin_cache.cached_skills("p@mkt", SPEC)
