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
    scene.drop_wrapped_source("alpha@mkt:review", QPointF(150.0, 250.0), usage="state")

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
        text[len(WRAPPED_SOURCE_MIME_PREFIX):], QPointF(0.0, 0.0), usage="state"
    )
    assert window._project.skills[0].config.source == "alpha@mkt:review"


# ─────────────────────────── 용도 고정 (state vs reference) ───────────────────────────


def test_create_wrapped_reference_places_ref_node(window):
    """usage=reference → 참조 노드 배치 + 산출 없음 용도 고정 — 1 undo."""
    from daedalus.view.actions.creation import create_wrapped_skill

    comp = create_wrapped_skill(
        window, "alpha@mkt:review", x=10.0, y=20.0, usage="reference",
    )
    assert comp.config.usage == "reference"
    assert [r.model for r in window._project_vm.reference_vms] == [comp]
    assert window._project.reference_placements[0].skill_name == "review"
    assert [s for s in window._project.graph.states
            if getattr(s, "skill_ref", None) is comp] == []

    window._undo()  # 생성+선언+참조 배치 1 undo
    assert window._project.skills == []
    assert window._project_vm.reference_vms == []


def test_drop_wrapped_source_asks_usage(window, monkeypatch):
    """후보 드롭은 usage를 묻는다 — 취소하면 아무것도 만들지 않는다."""
    from PySide6.QtCore import QPointF

    scene = window._fsm_scene
    monkeypatch.setattr(scene, "_ask_wrapped_usage", lambda: None)
    scene.drop_wrapped_source("alpha@mkt:review", QPointF(0, 0))
    assert window._project.skills == []

    monkeypatch.setattr(scene, "_ask_wrapped_usage", lambda: "reference")
    scene.drop_wrapped_source("alpha@mkt:review", QPointF(5, 6))
    assert window._project.skills[0].config.usage == "reference"
    assert window._project_vm.reference_vms != []


def test_undetermined_wrapped_drop_fixes_usage(window, monkeypatch):
    """레지스트리 '+'로 만든 미정 wrapped — 최초 드롭이 물어서 고정 + 배치가
    1 undo(undo하면 미정으로 되돌아온다)."""
    from PySide6.QtCore import QPointF

    from daedalus.view.actions.creation import make_component

    comp = make_component(window, "wrapped", "raw")
    window._register_component(comp)
    assert comp.config.usage == ""  # 미정

    scene = window._fsm_scene
    monkeypatch.setattr(scene, "_ask_wrapped_usage", lambda: "state")
    scene.drop_skill("raw", QPointF(30, 40))
    assert comp.config.usage == "state"
    assert any(getattr(s, "skill_ref", None) is comp
               for s in window._project.graph.states)

    window._undo()  # 고정+배치가 한 단위 — 반쪽 상태 없음
    assert comp.config.usage == ""
    assert not any(getattr(s, "skill_ref", None) is comp
                   for s in window._project.graph.states)


def test_reference_usage_wrapped_drops_as_ref_node(window):
    """용도가 reference로 고정된 wrapped는 일반 드롭도 참조 경로를 탄다
    (복수 배치 허용 — ReferenceSkill과 같은 의미론)."""
    from PySide6.QtCore import QPointF

    from daedalus.view.actions.creation import create_wrapped_skill

    comp = create_wrapped_skill(window, "alpha@mkt:review", usage="reference")
    scene = window._fsm_scene
    scene.drop_skill("review", QPointF(1, 2))
    scene.drop_skill("review", QPointF(3, 4))
    assert len(window._project_vm.reference_vms) == 2
    assert all(r.model is comp for r in window._project_vm.reference_vms)


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
    assert "워크플로 단계" in editor._wrapped_panel._w_usage.text()  # 용도 표시
    editor.deleteLater()


def test_reference_usage_editor_swaps_port_panel_for_links(window, qapp):
    """참조 용도 wrapped — 출력 포트 패널 없음 + 참조 링크 패널 있음."""
    from daedalus.view.actions.creation import create_wrapped_skill
    from daedalus.view.editors.reference_link_panel import _ReferenceLinkPanel
    from daedalus.view.editors.skill_editor import SkillEditor, _TransferOnPanel

    comp = create_wrapped_skill(window, "alpha@mkt:review", usage="reference")
    editor = SkillEditor(comp, project_vm=window._project_vm)
    assert editor.findChildren(_TransferOnPanel) == []
    assert len(editor.findChildren(_ReferenceLinkPanel)) == 1
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
