# tests/view/editors/test_variable_loader.py
from __future__ import annotations

from pathlib import Path

import pytest

from daedalus.view.editors.variable_loader import VariableEntry, load_variables


def test_builtin_variables_always_present():
    entries = load_variables()
    names = [e.name for e in entries]
    assert "$ARGUMENTS" in names
    assert "${CLAUDE_SESSION_ID}" in names
    assert "${CLAUDE_SKILL_DIR}" in names


def test_builtin_source_tag():
    entries = load_variables()
    builtins = [e for e in entries if e.source == "builtin"]
    assert len(builtins) == 5


def test_missing_project_yaml_returns_no_project_entries(tmp_path):
    entries = load_variables(project_dir=tmp_path)
    assert [e for e in entries if e.source == "project"] == []
    assert len([e for e in entries if e.source == "builtin"]) == 5


def test_project_yaml_loaded(tmp_path):
    daedalus_dir = tmp_path / ".daedalus"
    daedalus_dir.mkdir()
    (daedalus_dir / "variables.yaml").write_text(
        '- name: "$MY_VAR"\n  description: "내 변수"\n',
        encoding="utf-8",
    )
    entries = load_variables(project_dir=tmp_path)
    project = [e for e in entries if e.source == "project"]
    assert len(project) == 1
    assert project[0].name == "$MY_VAR"
    assert project[0].description == "내 변수"


def test_invalid_yaml_returns_empty_gracefully(tmp_path):
    daedalus_dir = tmp_path / ".daedalus"
    daedalus_dir.mkdir()
    (daedalus_dir / "variables.yaml").write_text(": invalid: yaml: [", encoding="utf-8")
    entries = load_variables(project_dir=tmp_path)
    assert [e for e in entries if e.source == "project"] == []


def test_variable_entry_dataclass():
    e = VariableEntry(name="$X", description="설명", source="builtin")
    assert e.name == "$X"
    assert e.source == "builtin"


def test_global_yaml_loaded(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daedalus.view.editors.variable_loader.Path.home",
        lambda: tmp_path,
    )
    (tmp_path / ".daedalus").mkdir()
    (tmp_path / ".daedalus" / "variables.yaml").write_text(
        '- name: "$GLOBAL"\n  description: "global var"\n',
        encoding="utf-8",
    )
    entries = load_variables()
    global_entries = [e for e in entries if e.source == "global"]
    assert len(global_entries) == 1
    assert global_entries[0].name == "$GLOBAL"
