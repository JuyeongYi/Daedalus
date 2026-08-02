# tests/model/test_build_target.py
"""WP-TG Part A: PluginProject.build_target — 모델 기본값 + 직렬화 왕복."""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def test_default_build_target_is_marketplace():
    project = PluginProject(name="p")
    assert project.build_target is BuildTarget.MARKETPLACE


def test_serialize_round_trip_marketplace():
    project = PluginProject(name="p", build_target=BuildTarget.MARKETPLACE)
    data = serialize_project(project)
    assert data["build_target"] == "marketplace"
    restored = deserialize_project(data)
    assert restored.build_target is BuildTarget.MARKETPLACE


def test_serialize_round_trip_local():
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    data = serialize_project(project)
    assert data["build_target"] == "local"
    restored = deserialize_project(data)
    assert restored.build_target is BuildTarget.LOCAL


def test_deserialize_old_file_without_build_target_key_defaults_marketplace_no_warning():
    """구버전 파일(build_target 키 부재) → MARKETPLACE로 조용히 복원 — 경고 없음."""
    project = PluginProject(name="p")
    data = serialize_project(project)
    del data["build_target"]

    warnings: list[str] = []
    restored = deserialize_project(data, collect_warnings=warnings)
    assert restored.build_target is BuildTarget.MARKETPLACE
    assert warnings == []


def test_deserialize_unknown_build_target_value_falls_back_to_marketplace():
    """알 수 없는 build_target 값도 MARKETPLACE로 안전하게 폴백한다."""
    project = PluginProject(name="p")
    data = serialize_project(project)
    data["build_target"] = "unknown-target"

    restored = deserialize_project(data)
    assert restored.build_target is BuildTarget.MARKETPLACE
