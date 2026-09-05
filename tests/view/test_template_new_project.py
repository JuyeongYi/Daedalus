# tests/view/test_template_new_project.py
"""새 프로젝트 통합 다이얼로그 (A7 + 사용자 확정 통합) — 출발점 + 빌드 타깃.

초기 A7은 템플릿을 File 메뉴 별도 항목으로 뒀지만, 사용자 확정으로 Ctrl+N
한 흐름에 통합됐다: 출발점(빈 프로젝트|템플릿)과 빌드 타깃을 같이 고르고,
**생성 시 고른 타깃이 템플릿에 저장된 타깃을 항상 이긴다**.
"""
from __future__ import annotations

import pytest

from daedalus.model import templates
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.editors.new_project_dialog import NewProjectDialog
from daedalus.view.editors.project_properties import BUILD_TARGET_LABELS
from daedalus.view.session_io import SessionIO


def _menu_action_texts(window: MainWindow) -> list[str]:
    # 액션 목록을 먼저 실체화한다 — 제네레이터 안에서 임시로 다루면 shiboken이
    # 래퍼를 먼저 정리해 "already deleted"로 죽는다.
    actions = list(window.menuBar().actions())
    for action in actions:
        if action.text() != "File":
            continue
        menu = action.menu()
        assert menu is not None
        return [a.text() for a in menu.actions()]
    raise AssertionError("File 메뉴를 찾을 수 없다")


def _stub_dialog(monkeypatch, template_id, target) -> None:
    """통합 다이얼로그를 지정 선택으로 스텁 — 헤드리스에서 모달 금지."""
    monkeypatch.setattr(
        SessionIO, "exec_new_project_dialog",
        lambda self: (template_id, target),
    )


def _stub_dialog_cancel(monkeypatch) -> None:
    monkeypatch.setattr(
        SessionIO, "exec_new_project_dialog", lambda self: None
    )


# ─────────────────────── 다이얼로그 위젯 자체 ───────────────────────


def test_dialog_lists_empty_plus_all_templates(qapp):
    dlg = NewProjectDialog()
    assert dlg._list.count() == 1 + len(templates.TEMPLATES)
    assert dlg._list.currentRow() == 0  # 기본 선택 = 빈 프로젝트
    assert dlg.template_id() is None


def test_dialog_selection_maps_to_template_id(qapp):
    dlg = NewProjectDialog()
    for index, template in enumerate(templates.TEMPLATES):
        dlg._list.setCurrentRow(index + 1)
        assert dlg.template_id() == template.id


def test_dialog_target_combo_matches_build_target_labels(qapp):
    dlg = NewProjectDialog()
    labels = [dlg._target.itemText(i) for i in range(dlg._target.count())]
    assert labels == [label for _t, label in BUILD_TARGET_LABELS]
    for index, (target, _label) in enumerate(BUILD_TARGET_LABELS):
        dlg._target.setCurrentIndex(index)
        assert dlg.build_target() is target


# ─────────────────────── 생성 흐름 (SessionIO) ───────────────────────


def test_file_menu_has_single_new_project_entry(qapp):
    """별도 '템플릿에서 새 프로젝트' 항목은 통합으로 흡수됐다."""
    window = MainWindow()
    texts = _menu_action_texts(window)
    assert "새 프로젝트" in texts
    assert all("템플릿" not in t for t in texts)
    window.close()


def test_empty_start_creates_blank_project_with_chosen_target(qapp, monkeypatch):
    window = MainWindow()
    _stub_dialog(monkeypatch, None, BuildTarget.LOCAL)
    window._new_project()
    assert window._project is not None
    assert window._project.name == "new-plugin"
    assert window._project.skills == []
    assert window._project.build_target is BuildTarget.LOCAL
    assert window._current_path is None
    window.close()


@pytest.mark.parametrize("index", range(len(templates.TEMPLATES)))
def test_each_template_loads_into_window(qapp, monkeypatch, index):
    """카탈로그의 모든 템플릿이 실제로 창에 로드된다."""
    window = MainWindow()
    template = templates.TEMPLATES[index]
    _stub_dialog(monkeypatch, template.id, BuildTarget.MARKETPLACE)
    window._new_project()

    expected = templates.load_template(template.id)
    project = window._project
    assert project is not None
    assert [s.name for s in project.skills] == [s.name for s in expected.skills]
    assert [a.name for a in project.agents] == [a.name for a in expected.agents]
    # 저장 경로는 아직 없고, 잃을 내용이 있으므로 미저장 변경으로 표시된다
    assert window._current_path is None
    assert window._dirty is True
    assert window.windowTitle().startswith("*")
    window.close()


def test_chosen_target_overrides_template_target(qapp, monkeypatch):
    """생성 시 고른 타깃이 템플릿에 저장된 타깃을 이긴다 (사용자 확정 규칙)."""
    window = MainWindow()
    template = templates.TEMPLATES[0]
    stored = templates.load_template(template.id).build_target
    chosen = (
        BuildTarget.LOCAL if stored is BuildTarget.MARKETPLACE
        else BuildTarget.MARKETPLACE
    )
    _stub_dialog(monkeypatch, template.id, chosen)
    window._new_project()
    assert window._project.build_target is chosen
    window.close()


def test_dialog_cancel_keeps_current_project(qapp, monkeypatch):
    """취소 = 생성 취소 — 현재 프로젝트 보존 (기존 WP-TG 규약 그대로)."""
    window = MainWindow()
    original = PluginProject(name="keep-me")
    window.load_project(original)
    _stub_dialog_cancel(monkeypatch)
    window._new_project()
    assert window._project is original
    window.close()


def test_template_load_failure_reports_and_keeps_project(qapp, monkeypatch):
    """템플릿 파일이 깨져 있으면 상태바로 알리고 현재 프로젝트를 유지한다."""
    window = MainWindow()
    original = PluginProject(name="keep-me")
    window.load_project(original)
    _stub_dialog(monkeypatch, templates.TEMPLATES[0].id, BuildTarget.MARKETPLACE)

    def _boom(*_args, **_kwargs):
        raise templates.TemplateError("깨진 파일")

    monkeypatch.setattr(templates, "load_template", _boom)
    window._new_project()
    assert window._project is original
    assert "템플릿 열기 실패" in window._status_label.text()
    window.close()
