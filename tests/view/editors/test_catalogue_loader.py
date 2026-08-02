# tests/view/editors/test_catalogue_loader.py
from __future__ import annotations

import json

from daedalus.view.editors.catalogue_loader import (
    CatalogueEntry,
    candidate_strings,
    expanded_mcp,
    load_catalogue,
)


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
    assert expanded_mcp(entry) == [
        "mcp__playwright__browser_click",
        "mcp__playwright__browser_navigate",
    ]


def test_expanded_mcp_leaves_already_prefixed_names_alone():
    entry = CatalogueEntry(
        name="playwright",
        description="",
        tools=(),
        mcp=("mcp__other-server__browser_click",),
        source="project",
    )
    assert expanded_mcp(entry) == ["mcp__other-server__browser_click"]


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
