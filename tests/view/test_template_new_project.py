# tests/view/test_template_new_project.py
"""템플릿에서 새 프로젝트 (A7) — 노출 표면과 기존 Ctrl+N 흐름의 공존.

핵심 회귀 대상: **Ctrl+N은 손대지 않았다**. 템플릿은 File 메뉴의 별도 항목이고,
템플릿이 자기 빌드 타깃을 선언하므로 여기서는 타깃을 묻지 않는다.
"""
from __future__ import annotations

import pytest

from daedalus.model import templates
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.view import app as app_module
from daedalus.view.app import MainWindow
from daedalus.view.editors.project_properties import BUILD_TARGET_LABELS


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


def _stub_item_choice(monkeypatch, index: int = 0) -> None:
    """QInputDialog.getItem을 "index번째 항목 선택"으로 스텁."""
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (a[3][index], True)),
    )


def _stub_item_cancel(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("", False)),
    )


def test_file_menu_exposes_template_entry(qapp):
    window = MainWindow()
    texts = _menu_action_texts(window)
    assert "새 프로젝트" in texts
    assert "템플릿에서 새 프로젝트…" in texts
    # 기존 Ctrl+N 바로 다음 자리 — 두 생성 경로가 붙어 있어야 찾는다
    assert texts.index("템플릿에서 새 프로젝트…") == texts.index("새 프로젝트") + 1
    window.close()


@pytest.mark.parametrize("index", range(len(templates.TEMPLATES)))
def test_each_template_loads_into_window(qapp, monkeypatch, index):
    """카탈로그의 모든 템플릿이 실제로 창에 로드된다."""
    window = MainWindow()
    _stub_item_choice(monkeypatch, index)
    window._new_project_from_template()

    template = templates.TEMPLATES[index]
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


def test_template_dialog_cancel_keeps_current_project(qapp, monkeypatch):
    """취소하면 아무 일도 일어나지 않는다 — 현재 프로젝트 보존."""
    window = MainWindow()
    original = PluginProject(name="keep-me")
    window.load_project(original)
    _stub_item_cancel(monkeypatch)
    window._new_project_from_template()
    assert window._project is original
    window.close()


def test_template_load_does_not_prompt_build_target(qapp, monkeypatch):
    """템플릿이 자기 타깃을 선언하므로 타깃 프롬프트를 띄우지 않는다."""
    window = MainWindow()
    called: list[str] = []
    monkeypatch.setattr(
        MainWindow, "_prompt_build_target",
        lambda self: called.append("prompted") or BuildTarget.MARKETPLACE,
    )
    _stub_item_choice(monkeypatch, 0)
    window._new_project_from_template()
    assert called == []
    assert window._project is not None
    window.close()


def test_ctrl_n_flow_unchanged(qapp, monkeypatch):
    """Ctrl+N은 여전히 빈 프로젝트 + 빌드 타깃 선택(취소 시 생성 취소)이다."""
    window = MainWindow()
    kept = PluginProject(name="keep-me")
    window.load_project(kept)

    _stub_item_cancel(monkeypatch)
    window._new_project()
    assert window._project is kept  # 타깃 선택 취소 → 생성 취소

    monkeypatch.setattr(
        app_module.QInputDialog, "getItem",
        staticmethod(lambda *a, **k: (BUILD_TARGET_LABELS[1][1], True)),
    )
    window._new_project()
    assert window._project is not kept
    assert window._project.name == "new-plugin"
    assert window._project.skills == []
    assert window._project.build_target is BuildTarget.LOCAL
    window.close()


def test_template_load_failure_reports_and_keeps_project(qapp, monkeypatch):
    """템플릿 파일이 깨져 있으면 상태바로 알리고 현재 프로젝트를 유지한다."""
    window = MainWindow()
    original = PluginProject(name="keep-me")
    window.load_project(original)
    _stub_item_choice(monkeypatch, 0)

    def _boom(*_args, **_kwargs):
        raise templates.TemplateError("깨진 파일")

    monkeypatch.setattr(templates, "load_template", _boom)
    window._new_project_from_template()
    assert window._project is original
    assert "템플릿 열기 실패" in window._status_label.text()
    window.close()
