# tests/compiler/test_plugin_manifest.py
"""WP-T Part A: .claude-plugin/plugin.json 매니페스트."""
from __future__ import annotations

import json

from daedalus.compiler import compile_project
from daedalus.compiler.emit import compile_plugin_manifest
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project

from tests.compiler.builders import make_procedural


def test_manifest_key_order_and_content():
    project = PluginProject(name="my-plugin", description="A demo plugin", version="1.2.3")
    text = compile_plugin_manifest(project)
    obj = json.loads(text)
    assert list(obj.keys()) == ["name", "description", "version"]
    assert obj["name"] == "my-plugin"
    assert obj["description"] == "A demo plugin"
    assert obj["version"] == "1.2.3"


def test_manifest_omits_description_when_empty():
    project = PluginProject(name="my-plugin", description="", version="0.1.0")
    text = compile_plugin_manifest(project)
    obj = json.loads(text)
    assert list(obj.keys()) == ["name", "version"]
    assert "description" not in obj


def test_manifest_lf_and_trailing_newline():
    project = PluginProject(name="my-plugin")
    text = compile_plugin_manifest(project)
    assert "\r" not in text
    assert text.endswith("\n")


def test_compile_project_always_writes_manifest(tmp_path):
    project = PluginProject(
        name="my-plugin", description="desc", version="2.0.0",
        skills=[make_procedural(name="my-skill")],
    )
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    manifest_path = tmp_path / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists()
    assert any(p == manifest_path for p in result.written)

    written_text = manifest_path.read_text(encoding="utf-8")
    assert written_text == compile_plugin_manifest(project)


def test_compile_project_writes_manifest_even_without_skills(tmp_path):
    """스킬/에이전트가 없는 프로젝트도 매니페스트는 무조건 생성된다."""
    project = PluginProject(name="empty-plugin")
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert (tmp_path / ".claude-plugin" / "plugin.json").exists()


def test_nonconforming_project_name_rejected_at_gate(tmp_path):
    """프로젝트 이름이 규약 위반이면 컴파일 게이트가 거부한다 (파일 미생성)."""
    project = PluginProject(name="새 프로젝트", skills=[make_procedural(name="my-skill")])
    result = compile_project(project, tmp_path)
    assert not result.ok
    assert result.written == []
    assert not (tmp_path / ".claude-plugin" / "plugin.json").exists()

    named = [e for e in result.errors if e.rule == "compile_invalid_component_name"]
    assert named, [e.rule for e in result.errors]
    assert any(e.source == "새 프로젝트" for e in named)
    assert all(not e.is_warning for e in named)


def test_serialize_roundtrip_preserves_description_version():
    project = PluginProject(name="my-plugin", description="hello", version="3.4.5")
    data = serialize_project(project)
    assert data["description"] == "hello"
    assert data["version"] == "3.4.5"

    restored = deserialize_project(data)
    assert restored.description == "hello"
    assert restored.version == "3.4.5"


def test_deserialize_old_file_without_keys_defaults_no_warning():
    """구버전 파일(description/version 키 부재)은 기본값으로 조용히 복원 — 경고 없음."""
    project = PluginProject(name="my-plugin")
    data = serialize_project(project)
    del data["description"]
    del data["version"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.description == ""
    assert restored.version == "0.1.0"
    assert warnings == []
