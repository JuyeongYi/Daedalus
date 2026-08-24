# tests/view/editors/test_catalogue_loader.py
from __future__ import annotations

import json

import pytest

from daedalus.view.editors.catalogue_loader import (
    CatalogueEntry,
    candidate_strings,
    expanded_mcp,
    load_catalogue,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """실제 ~/.daedalus 격리 — 모든 테스트가 빈 가짜 홈에서 돈다.

    이게 없으면 개발자 머신에 글로벌 카탈로그가 있는 순간(이 기능의 핵심 사용
    시나리오다) 스위트가 깨진다. 개별 테스트의 monkeypatch가 다시 덮을 수 있다.
    """
    fake_home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(
        "daedalus.view.editors.catalogue_loader.Path.home",
        lambda: fake_home,
    )
    yield


def _write_entry(dir_path, name: str, data: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_no_catalogue_dirs_returns_empty(tmp_path):
    entries = load_catalogue(project_dir=tmp_path)
    assert entries == []


def test_project_catalogue_loaded(tmp_path):
    _write_entry(
        tmp_path / ".daedalus" / "catalogue",
        "playwright",
        {"description": "브라우저 자동화", "mcp": ["browser_click", "browser_navigate"]},
    )
    entries = load_catalogue(project_dir=tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "playwright"
    assert entry.description == "브라우저 자동화"
    assert entry.mcp == ("browser_click", "browser_navigate")
    assert entry.tools == ()
    assert entry.source == "project"


def test_global_catalogue_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daedalus.view.editors.catalogue_loader.Path.home",
        lambda: tmp_path,
    )
    _write_entry(
        tmp_path / ".daedalus" / "catalogue",
        "git-tools",
        {"tool": ["Bash(git add *)", "Bash(git commit *)"]},
    )
    entries = load_catalogue()
    assert len(entries) == 1
    assert entries[0].source == "global"
    assert entries[0].tools == ("Bash(git add *)", "Bash(git commit *)")


def test_project_overrides_global_on_name_conflict(tmp_path, monkeypatch):
    global_home = tmp_path / "home"
    project_dir = tmp_path / "project"
    monkeypatch.setattr(
        "daedalus.view.editors.catalogue_loader.Path.home",
        lambda: global_home,
    )
    _write_entry(
        global_home / ".daedalus" / "catalogue",
        "shared",
        {"description": "글로벌 버전", "tool": ["Read"]},
    )
    _write_entry(
        project_dir / ".daedalus" / "catalogue",
        "shared",
        {"description": "프로젝트 버전", "tool": ["Write"]},
    )
    entries = load_catalogue(project_dir=project_dir)
    assert len(entries) == 1
    assert entries[0].source == "project"
    assert entries[0].description == "프로젝트 버전"
    assert entries[0].tools == ("Write",)


def test_malformed_json_file_is_skipped(tmp_path, capsys):
    catalogue_dir = tmp_path / ".daedalus" / "catalogue"
    catalogue_dir.mkdir(parents=True)
    (catalogue_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
    entries = load_catalogue(project_dir=tmp_path)
    assert entries == []
    captured = capsys.readouterr()
    assert "broken.json" in captured.err


def test_schema_mismatch_file_is_skipped(tmp_path, capsys):
    _write_entry(
        tmp_path / ".daedalus" / "catalogue",
        "bad-schema",
        {"tool": "not-a-list"},
    )
    entries = load_catalogue(project_dir=tmp_path)
    assert entries == []
    captured = capsys.readouterr()
    assert "bad-schema" in captured.err


def test_expanded_mcp_prefixes_with_entry_name():
    entry = CatalogueEntry(
        name="playwright",
        description="",
        tools=(),
        mcp=("browser_click", "browser_navigate"),
        source="project",
    )
    result = expanded_mcp(entry)
    assert result[0] == "mcp__playwright__*"  # 서버 전체 허용 와일드카드가 맨 앞
    assert "mcp__playwright__browser_click" in result
    assert "mcp__playwright__browser_navigate" in result


def test_expanded_mcp_leaves_already_prefixed_names_alone():
    entry = CatalogueEntry(
        name="playwright",
        description="",
        tools=(),
        mcp=("mcp__other-server__browser_click",),
        source="project",
    )
    result = expanded_mcp(entry)
    assert result[0] == "mcp__playwright__*"  # 와일드카드는 entry.name 기준
    assert "mcp__other-server__browser_click" in result  # 이미 접두된 항목은 그대로


def test_candidate_strings_includes_builtins():
    candidates = candidate_strings([])
    assert "Read" in candidates
    assert "Bash" in candidates


def test_candidate_strings_includes_catalogue_tools_and_mcp():
    entry = CatalogueEntry(
        name="playwright",
        description="",
        tools=("Bash(git add *)",),
        mcp=("browser_click",),
        source="project",
    )
    candidates = candidate_strings([entry])
    assert "Bash(git add *)" in candidates
    assert "mcp__playwright__browser_click" in candidates


def test_candidate_strings_includes_project_agents():
    class _FakeAgent:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeProject:
        def __init__(self) -> None:
            self.agents = [_FakeAgent("reviewer"), _FakeAgent("writer")]

    candidates = candidate_strings([], project=_FakeProject())
    assert "Agent(reviewer)" in candidates
    assert "Agent(writer)" in candidates


def test_candidate_strings_dedupes():
    entry_a = CatalogueEntry(
        name="a", description="", tools=("Read",), mcp=(), source="project"
    )
    entry_b = CatalogueEntry(
        name="b", description="", tools=("Read",), mcp=(), source="project"
    )
    candidates = candidate_strings([entry_a, entry_b])
    assert candidates.count("Read") == 1


def test_home_dir_injection_parameter(tmp_path):
    """home_dir 주입 파라미터 — Path.home() 몽키패치 없이도 격리 가능."""
    _write_entry(
        tmp_path / "h" / ".daedalus" / "catalogue", "injected", {"tool": ["Read"]}
    )
    entries = load_catalogue(home_dir=tmp_path / "h")
    assert [e.name for e in entries] == ["injected"]
    assert entries[0].source == "global"


def test_non_string_elements_file_is_skipped(tmp_path, capsys):
    """tool/mcp 배열의 비문자열 원소 → 파일 단위 스킵 + 경고 (쓰레기 후보 방지)."""
    _write_entry(
        tmp_path / ".daedalus" / "catalogue", "bad-elems", {"mcp": [123, True]}
    )
    entries = load_catalogue(project_dir=tmp_path)
    assert entries == []
    assert "bad-elems" in capsys.readouterr().err
