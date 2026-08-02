# tests/view/test_project_properties.py
"""WP-T Part C: ProjectPropertiesDialog + 새 프로젝트 기본 이름.

WP-TG: 빌드 타깃 콤보 + 새 프로젝트 생성 시 빌드 타깃 선택 다이얼로그.
"""
from __future__ import annotations

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.view import app as app_module
from daedalus.view.app import MainWindow
from daedalus.view.editors.project_properties import (
    BUILD_TARGET_LABELS,
    ProjectPropertiesDialog,
)


def _stub_build_target_dialog(monkeypatch, choice: str = "마켓플레이스 플러그인") -> None:
    """QInputDialog.getItem을 지정 선택지로 스텁 (다이얼로그 테스트는 몽키패치로)."""
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (choice, True)),
    )


def _stub_build_target_cancel(monkeypatch) -> None:
    """QInputDialog.getItem 취소 스텁 — ok=False."""
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("", False)),
    )


def test_dialog_initial_values_match_project(qapp):
    project = PluginProject(name="my-plugin", description="desc", version="1.0.0")
    dialog = ProjectPropertiesDialog(project)
    assert dialog._name_edit.text() == "my-plugin"
    assert dialog._description_edit.text() == "desc"
    assert dialog._version_edit.text() == "1.0.0"
    assert dialog._emit_progress_hook_cb.isChecked() is True  # 기본 True


def test_apply_to_updates_project(qapp):
    project = PluginProject(name="old-name", description="old desc", version="0.1.0")
    dialog = ProjectPropertiesDialog(project)
    dialog._name_edit.setText("new-name")
    dialog._description_edit.setText("new desc")
    dialog._version_edit.setText("2.0.0")

    dialog.apply_to(project)

    assert project.name == "new-name"
    assert project.description == "new desc"
    assert project.version == "2.0.0"


def test_dialog_reflects_emit_progress_hook_false(qapp):
    project = PluginProject(name="p", emit_progress_hook=False)
    dialog = ProjectPropertiesDialog(project)
    assert dialog._emit_progress_hook_cb.isChecked() is False


def test_apply_to_updates_emit_progress_hook(qapp):
    project = PluginProject(name="p")
    dialog = ProjectPropertiesDialog(project)
    dialog._emit_progress_hook_cb.setChecked(False)
    dialog.apply_to(project)
    assert project.emit_progress_hook is False


def test_apply_to_does_not_enforce_name_convention(qapp):
    """이름 규약 검사는 다이얼로그에서 막지 않는다 — 편집 중 자유."""
    project = PluginProject(name="old-name")
    dialog = ProjectPropertiesDialog(project)
    dialog._name_edit.setText("Bad Name With Spaces")
    dialog.apply_to(project)
    assert project.name == "Bad Name With Spaces"


def test_new_project_default_name_is_new_plugin(qapp, monkeypatch):
    window = MainWindow()
    _stub_build_target_dialog(monkeypatch)
    window._new_project()
    assert window._project is not None
    assert window._project.name == "new-plugin"
    window.close()


# ─────────────────────── WP-TG: 빌드 타깃 콤보 ───────────────────────


def test_dialog_build_target_combo_default_marketplace(qapp):
    project = PluginProject(name="p")
    dialog = ProjectPropertiesDialog(project)
    assert dialog._build_target_combo.currentData() is BuildTarget.MARKETPLACE


def test_dialog_build_target_combo_reflects_local(qapp):
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    dialog = ProjectPropertiesDialog(project)
    assert dialog._build_target_combo.currentData() is BuildTarget.LOCAL


def test_apply_to_updates_build_target(qapp):
    project = PluginProject(name="p", build_target=BuildTarget.MARKETPLACE)
    dialog = ProjectPropertiesDialog(project)
    local_label = next(
        label for target, label in BUILD_TARGET_LABELS if target is BuildTarget.LOCAL
    )
    idx = dialog._build_target_combo.findText(local_label)
    assert idx >= 0
    dialog._build_target_combo.setCurrentIndex(idx)

    dialog.apply_to(project)

    assert project.build_target is BuildTarget.LOCAL


# ─────────────────────── WP-TG: 새 프로젝트 빌드 타깃 선택 ───────────────────────


def test_new_project_default_target_is_marketplace(qapp, monkeypatch):
    window = MainWindow()
    _stub_build_target_dialog(monkeypatch, "마켓플레이스 플러그인")
    window._new_project()
    assert window._project is not None
    assert window._project.build_target is BuildTarget.MARKETPLACE
    window.close()


def test_new_project_local_target_selected(qapp, monkeypatch):
    window = MainWindow()
    _stub_build_target_dialog(monkeypatch, "로컬 플러그인")
    window._new_project()
    assert window._project is not None
    assert window._project.build_target is BuildTarget.LOCAL
    window.close()


def test_new_project_cancelled_build_target_aborts_creation(qapp, monkeypatch):
    """빌드 타깃 선택을 취소하면 새 프로젝트 생성 자체가 취소된다."""
    window = MainWindow()
    original = PluginProject(name="original-project")
    window.set_project(original)

    _stub_build_target_cancel(monkeypatch)
    window._new_project()

    assert window._project is original
    assert window._project.name == "original-project"
    window.close()
