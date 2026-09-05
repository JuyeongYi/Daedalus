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
    assert len(builtins) == 7  # 루트 변수 2종 추가 (컨텍스트 매트릭스)


def test_missing_project_yaml_returns_no_project_entries(tmp_path):
    entries = load_variables(project_dir=tmp_path)
    assert [e for e in entries if e.source == "project"] == []
    assert len([e for e in entries if e.source == "builtin"]) == 7


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


# ─────── 컨텍스트·빌드 타깃 필터 (사용자 확정 매트릭스) ───────
# 스킬 = 풀 지원 / 에이전트·작업 폴더 문서 = 루트 변수 2종만 /
# 로컬 빌드 = ${CLAUDE_PLUGIN_ROOT} 사용 불가.


def _names(entries):
    return [e.name for e in entries]


def test_skill_context_gets_full_builtin_set():
    from daedalus.view.editors.variable_loader import variables_for
    names = _names(variables_for("skill"))
    for expected in (
        "$ARGUMENTS", "${CLAUDE_SKILL_DIR}", "${CLAUDE_SESSION_ID}",
        "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}",
    ):
        assert expected in names


def test_agent_and_workspace_get_roots_only():
    from daedalus.view.editors.variable_loader import variables_for
    for ctx in ("agent", "workspace"):
        builtin = [e for e in variables_for(ctx) if e.source == "builtin"]
        assert _names(builtin) == [
            "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}",
        ], f"context={ctx}"


def test_local_build_excludes_plugin_root_everywhere():
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.view.editors.variable_loader import variables_for
    for ctx in ("skill", "agent", "workspace"):
        names = _names(variables_for(ctx, BuildTarget.LOCAL))
        assert "${CLAUDE_PLUGIN_ROOT}" not in names, f"context={ctx}"
        assert "${CLAUDE_PROJECT_DIR}" in names, f"context={ctx}"


def test_marketplace_build_keeps_plugin_root():
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.view.editors.variable_loader import variables_for
    names = _names(variables_for("agent", BuildTarget.MARKETPLACE))
    assert "${CLAUDE_PLUGIN_ROOT}" in names


def test_user_defined_variables_visible_in_every_context(tmp_path):
    """global/project yaml 변수는 기본 전 컨텍스트 — 자기 토큰의 범위는 자기가 안다."""
    from daedalus.view.editors.variable_loader import variables_for
    proj = tmp_path / "p"
    (proj / ".daedalus").mkdir(parents=True)
    (proj / ".daedalus" / "variables.yaml").write_text(
        '- name: "${MY_VAR}"\n  description: custom\n', encoding="utf-8"
    )
    for ctx in ("skill", "agent", "workspace"):
        assert "${MY_VAR}" in _names(variables_for(ctx, project_dir=proj))


def test_build_target_provider_roundtrip():
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.view.editors.variable_loader import (
        get_build_target,
        set_build_target_provider,
    )
    assert get_build_target() is None
    set_build_target_provider(lambda: BuildTarget.LOCAL)
    try:
        assert get_build_target() is BuildTarget.LOCAL
    finally:
        set_build_target_provider(None)
