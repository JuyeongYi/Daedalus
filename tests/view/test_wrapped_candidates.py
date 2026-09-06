# tests/view/test_wrapped_candidates.py
"""외부 스킬 후보 흐름 (WP-WR) — 체크(선언)만 하면 레지스트리 🔗 목록에 후보가
자동으로 나타나고, 캔버스 드롭 시점에 WrappedSkill이 생성·배치된다.

+ wrapped 에디터 중앙 패널: 본문 편집기 없음 — 원본 경로 + "원본 열기"만
(사용자 확정: 프론트매터·연결선 정의만 여기서 한다).
"""
from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QPointF

from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def marketplace(tmp_path):
    plugin_dir = tmp_path / "catalog" / "alpha"
    meta = plugin_dir / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(json.dumps({"name": "alpha"}), encoding="utf-8")
    for skill in ("review", "lint"):
        sdir = plugin_dir / "skills" / skill
        sdir.mkdir(parents=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: Does {skill}.\n---\n", encoding="utf-8"
        )
    return tmp_path / "catalog"


def _declare(window, marketplace, plugin_id="alpha@mkt"):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    window._project.external_plugins.append(plugin_id)
    window._project_vm.notify()  # 레지스트리 재구성


def _wrapped_rows(window) -> list:
    section = window._registry_panel._sections["wrapped"]
    lst = section._list
    return [lst.item(i) for i in range(lst.count())]


# ─────────────────────────── 레지스트리 후보 노출 ───────────────────────────


def test_declared_plugin_skills_appear_as_candidates(window, marketplace):
    assert _wrapped_rows(window) == []  # 선언 전 — 아무것도 없다
    _declare(window, marketplace)
    labels = [item.text() for item in _wrapped_rows(window)]
    assert labels == ["🔗 lint (alpha@mkt)", "🔗 review (alpha@mkt)"]


def test_candidate_drag_text_carries_source(window, marketplace):
    from daedalus.view.panels.registry_panel import _ROLE_DRAG_TEXT

    _declare(window, marketplace)
    item = _wrapped_rows(window)[0]
    assert item.data(_ROLE_DRAG_TEXT) == "wrapped-source:alpha@mkt:lint"


def test_already_wrapped_source_not_listed_as_candidate(window, marketplace):
    from daedalus.view.actions.creation import create_wrapped_skill

    _declare(window, marketplace)
    create_wrapped_skill(window, "alpha@mkt:review")
    labels = [item.text() for item in _wrapped_rows(window)]
    # review는 실제 컴포넌트 행으로, lint만 후보로 남는다
    assert "🔗 review" in labels[0]  # 컴포넌트 행 (아이콘+이름)
    assert labels.count("🔗 lint (alpha@mkt)") == 1
    assert not any("review (alpha@mkt)" in t for t in labels)


def test_undeclared_plugin_has_no_candidates(window, marketplace):
    from daedalus.model.plugin import wrap_catalog

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    window._project_vm.notify()
    assert _wrapped_rows(window) == []


# ─────────────────────────── 캔버스 드롭 → 생성+배치 ───────────────────────────


def test_drop_wrapped_source_creates_and_places(window):
    scene = window._fsm_scene
    scene.drop_wrapped_source("alpha@mkt:review", QPointF(150.0, 250.0))

    skill = window._project.skills[0]
    assert skill.kind == "wrapped_skill"
    assert skill.config.source == "alpha@mkt:review"
    assert window._project.external_plugins == ["alpha@mkt"]  # 자동 선언
    placements = [
        s for s in window._project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is skill
    ]
    assert len(placements) == 1
    vm = next(v for v in window._project_vm.state_vms if v.model is placements[0])
    assert (vm.x, vm.y) == (150.0, 250.0)

    window._undo()  # 생성+선언+배치 1 undo
    assert window._project.skills == []
    assert window._project.external_plugins == []
    assert [
        s for s in window._project.graph.states if isinstance(s, SimpleState)
    ] == []


def test_canvas_view_routes_wrapped_mime(window):
    """드롭 mime 접두 판정 — 일반 컴포넌트 이름과 후보 소스를 가른다."""
    from daedalus.view.actions.creation import WRAPPED_SOURCE_MIME_PREFIX

    scene = window._fsm_scene
    text = f"{WRAPPED_SOURCE_MIME_PREFIX}alpha@mkt:review"
    assert text.startswith(WRAPPED_SOURCE_MIME_PREFIX)
    scene.drop_wrapped_source(
        text[len(WRAPPED_SOURCE_MIME_PREFIX):], QPointF(0.0, 0.0)
    )
    assert window._project.skills[0].config.source == "alpha@mkt:review"


# ─────────────────────────── wrapped 에디터 중앙 패널 ───────────────────────────


def _make_wrapped(window, source="alpha@mkt:review"):
    from daedalus.view.actions.creation import create_wrapped_skill

    return create_wrapped_skill(window, source)


def test_wrapped_skill_editor_has_output_port_panels(window, qapp):
    """wrapped도 워크플로 단계 — 출력 포트·에이전트 호출 패널이 procedural과
    동일하게 붙는다(빠져 있어 GUI에서 출력 추가가 불가능했다 — 사용자 보고)."""
    from daedalus.view.editors.skill_editor import SkillEditor, _TransferOnPanel

    comp = _make_wrapped(window)
    editor = SkillEditor(comp, project_vm=window._project_vm)
    panels = editor.findChildren(_TransferOnPanel)
    assert len(panels) == 2  # ⇄ Transfer On + 🤖 Agent Call
    editor.deleteLater()


def test_wrapped_editor_has_no_body_editor(window, qapp):
    from daedalus.view.editors.component_editor import ComponentEditor

    comp = _make_wrapped(window)
    editor = ComponentEditor(comp, skill_kind="wrapped")
    assert editor._content_panel is None  # 본문 편집기 자체가 없다
    assert editor._wrapped_panel is not None
    assert editor._wrapped_panel._w_source.text() == "alpha@mkt:review"
    assert editor._wrapped_panel._w_source.isReadOnly()
    editor.deleteLater()


def test_wrapped_editor_open_source_resolves_via_catalog(window, marketplace, monkeypatch):
    from daedalus.model.plugin import wrap_catalog
    from daedalus.view.editors.component_editor import ComponentEditor

    wrap_catalog.add_marketplace(str(marketplace), "mkt")
    comp = _make_wrapped(window, "alpha@mkt:review")
    editor = ComponentEditor(comp, skill_kind="wrapped")

    opened: list[str] = []
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(
        QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toLocalFile()))
    )
    assert editor._wrapped_panel.open_source() is True
    assert opened and opened[0].endswith("SKILL.md")
    editor.deleteLater()


def test_wrapped_editor_open_source_unresolved_shows_guidance(window, qapp):
    from daedalus.view.editors.component_editor import ComponentEditor

    comp = _make_wrapped(window, "ghost@mkt:nope")
    editor = ComponentEditor(comp, skill_kind="wrapped")
    assert editor._wrapped_panel.open_source() is False
    assert "마켓플레이스 폴더" in editor._wrapped_panel._w_status.text()
    editor.deleteLater()
