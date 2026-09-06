# tests/model/plugin/test_remote_skills.py
"""미설치 플러그인의 스킬 이름 원격 조회 (WP-WR).

**테스트는 인터넷에 나가지 않는다** — `fetch_skill_names`를 몽키패치해 호출
횟수까지 센다. "언제 요청이 나가는가"가 이 기능의 계약이기 때문이다(사용자
확정: 지목했을 때만, 캐시가 있으면 나가지 않는다).
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.plugin import remote_skills
from daedalus.model.plugin.remote_skills import (
    GithubRef,
    RemoteSkillsError,
    parse_github_source,
    skill_names,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        remote_skills, "cache_dir", lambda home_dir=None: tmp_path / "cache",
    )


# ─────────────────────────── source 해석 ───────────────────────────


def test_parses_git_subdir_source():
    """실측 형태 — 공식 마켓의 외부 플러그인 선언."""
    ref = parse_github_source({
        "source": "git-subdir",
        "url": "https://github.com/42Crunch-AI/claude-plugins.git",
        "path": "plugins/api-security-testing",
        "ref": "v1.5.5",
        "sha": "30287f5e3f122a646d1ac5ca3ab96e130c52a3ad",
    })
    assert ref == GithubRef(
        owner="42Crunch-AI", repo="claude-plugins",
        path="plugins/api-security-testing",
        # sha가 ref를 이긴다 — 태그는 옮겨 달릴 수 있고 SHA는 불변이다
        ref="30287f5e3f122a646d1ac5ca3ab96e130c52a3ad",
    )


def test_parses_github_repo_source():
    ref = parse_github_source({"source": "github", "repo": "owner/repo", "ref": "main"})
    assert (ref.owner, ref.repo, ref.ref) == ("owner", "repo", "main")


@pytest.mark.parametrize("spec", [
    "./external_plugins/asana",  # 마켓 폴더 안 상대 경로 — 원격이 아니다
    {"source": "git", "url": "https://gitlab.com/o/r.git"},  # GitHub 아님
    {"source": "url", "url": "https://example.com/marketplace.json"},
    None,
])
def test_non_github_sources_are_none(spec):
    """모르는 것은 모른다고 말한다 — 추측해 엉뚱한 목록을 보여주지 않는다."""
    assert parse_github_source(spec) is None


# ─────────────────────────── 조회·캐시 ───────────────────────────


_SPEC = {
    "source": "git-subdir",
    "url": "https://github.com/o/r.git",
    "path": "plugins/x",
    "sha": "abc123",
}


def test_fetches_once_then_uses_cache(monkeypatch):
    calls: list[GithubRef] = []

    def fake(ref: GithubRef) -> list[str]:
        calls.append(ref)
        return ["review", "lint"]

    monkeypatch.setattr(remote_skills, "fetch_skill_names", fake)

    assert skill_names("x@m", _SPEC) == ["review", "lint"]
    assert len(calls) == 1
    # 같은 버전을 다시 물으면 **요청이 나가지 않는다**
    assert skill_names("x@m", _SPEC) == ["review", "lint"]
    assert len(calls) == 1


def test_refresh_forces_new_request(monkeypatch):
    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["a"])
    skill_names("x@m", _SPEC)
    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["a", "b"])
    assert skill_names("x@m", _SPEC) == ["a"]  # 캐시
    assert skill_names("x@m", _SPEC, refresh=True) == ["a", "b"]


def test_new_version_bypasses_old_cache(monkeypatch):
    """캐시 키에 SHA가 들어가므로 버전이 바뀌면 자동으로 다시 받는다."""
    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["old"])
    skill_names("x@m", _SPEC)

    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["new"])
    newer = {**_SPEC, "sha": "def456"}
    assert skill_names("x@m", newer) == ["new"]


def test_non_github_returns_none_without_request(monkeypatch):
    def boom(ref):  # pragma: no cover - 호출되면 실패다
        raise AssertionError("GitHub이 아닌데 요청이 나갔다")

    monkeypatch.setattr(remote_skills, "fetch_skill_names", boom)
    assert skill_names("x@m", {"source": "git", "url": "https://gitlab.com/o/r.git"}) is None


def test_broken_cache_falls_back_to_request(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["ok"])
    skill_names("x@m", _SPEC)
    cached = next((tmp_path / "cache").glob("*.json"))
    cached.write_text("{not json", encoding="utf-8")
    assert skill_names("x@m", _SPEC) == ["ok"]  # 깨진 캐시는 무시하고 다시 받는다


def test_fetch_error_propagates(monkeypatch):
    def fail(ref):
        raise RemoteSkillsError("인터넷에 연결하지 못했습니다")

    monkeypatch.setattr(remote_skills, "fetch_skill_names", fail)
    with pytest.raises(RemoteSkillsError):
        skill_names("x@m", _SPEC)


# ─────────────────────────── 응답 해석 ───────────────────────────


def test_skill_names_from_directory_listing(monkeypatch):
    """디렉토리 이름이 곧 스킬 이름 — 파일 항목은 스킬이 아니다."""
    payload = [
        {"name": "review", "type": "dir"},
        {"name": "lint", "type": "dir"},
        {"name": "README.md", "type": "file"},
    ]
    monkeypatch.setattr(remote_skills, "_fetch_json", lambda url: payload)
    assert remote_skills.fetch_skill_names(GithubRef("o", "r")) == ["lint", "review"]


def test_api_url_includes_path_and_ref():
    url = remote_skills._api_url(GithubRef("o", "r", path="plugins/x", ref="abc"))
    assert url == (
        "https://api.github.com/repos/o/r/contents/plugins/x/skills?ref=abc"
    )
    assert remote_skills._api_url(GithubRef("o", "r")) == (
        "https://api.github.com/repos/o/r/contents/skills"
    )


def test_cache_file_records_ref(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_skills, "fetch_skill_names", lambda ref: ["s"])
    skill_names("x@m", _SPEC)
    data = json.loads(next((tmp_path / "cache").glob("*.json")).read_text(encoding="utf-8"))
    assert data == {"plugin_id": "x@m", "ref": "abc123", "skills": ["s"]}
