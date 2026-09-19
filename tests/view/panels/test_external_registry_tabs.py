"""레지스트리 도크의 외부 플러그인 탭 (WP-C) — 🔌 미등록 목록 + 🧷 스킬 참조.

카탈로그는 파일시스템을 읽으므로 `wrap_catalog.scan_catalog`를 **몽키패치로
주입**한다(폴더 등록에 매이지 않는 봉합선). 여기서 고정하는 것:

- 🔌 탭 하단은 사용 선언한 플러그인의 **미등록** 에이전트만 보여 준다.
- 스캔은 `_rebuild`마다가 아니라 **명시 새로고침**에서만 일어난다(느린 폴더
  훑기가 매 키 입력·매 구조 변경에 끼어들면 화면이 멈춘다).
- 🧷 탭은 외부 스킬 참조와 그것을 쓰는 에이전트(✔)를 보여 주고, "+"는 카탈로그
  창을 연다(이름을 물어 만들 수 없는 것들이다).
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin import wrap_catalog
from daedalus.model.plugin.wrap_catalog import (
    CataloguedAgent,
    CataloguedPlugin,
    CataloguedSkill,
    MarketplaceFolder,
)
from daedalus.model.project import PluginProject


def _fake_catalog():
    plugin = CataloguedPlugin(
        name="hookify",
        path="/nowhere",
        marketplace="mkt",
        skills=[CataloguedSkill("review", "Reviews.", "hookify@mkt:review")],
        agents=[
            CataloguedAgent("doctor", "Doctors.", "hookify:doctor"),
            CataloguedAgent("auditor", "Audits.", "hookify:auditor"),
        ],
    )
    return [(MarketplaceFolder(path="/nowhere", marketplace="mkt"), [plugin])]


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(wrap_catalog, "scan_catalog", lambda *a, **k: _fake_catalog())
    from daedalus.view.app import MainWindow

    win = MainWindow()
    project = PluginProject(name="p")
    project.external_plugins.append("hookify@mkt")
    win.set_project(project)
    yield win
    win.close()


def _catalog_list(panel):
    from daedalus.view.kind_ui import EXTERNAL_AGENTS_GROUP

    return panel._catalog_agents[EXTERNAL_AGENTS_GROUP]._list


def _texts(list_widget):
    return [list_widget.item(i).text() for i in range(list_widget.count())]


# ── 🔌 미등록 에이전트 ───────────────────────────────────────────────────

def test_the_external_tab_lists_unregistered_catalog_agents(window):
    assert _texts(_catalog_list(window._registry_panel)) == [
        "🔌 hookify:auditor", "🔌 hookify:doctor",
    ]


def test_registering_removes_the_item_from_the_unregistered_list(window):
    window._on_register_external_agent("hookify:doctor", "external_fork_agent")
    panel = window._registry_panel
    assert _texts(_catalog_list(panel)) == ["🔌 hookify:auditor"]
    # 등록된 것은 위쪽(컴포넌트) 섹션에 나타난다 — 두 역할이 한 탭이다.
    from daedalus.view.kind_ui import EXTERNAL_AGENTS_GROUP

    section = panel._sections[EXTERNAL_AGENTS_GROUP]
    assert _texts(section._list) == ["🔌🧩 doctor"]


def test_an_undeclared_plugin_contributes_nothing(window):
    window._project.external_plugins.clear()
    window._registry_panel.set_project(window._project)
    assert _texts(_catalog_list(window._registry_panel)) == []


def test_registering_the_same_source_twice_is_refused_loudly(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *args, **kwargs: seen.append(str(args[2])),
    )
    window._on_register_external_agent("hookify:doctor", "external_agent")
    window._on_register_external_agent("hookify:doctor", "external_fork_agent")
    assert seen and "역할" in seen[0]
    assert len(window._project.agents) == 1


def test_the_catalog_is_scanned_only_on_explicit_refresh(window, monkeypatch):
    """`_rebuild`는 파일시스템을 읽지 않는다 — 캐시된 스캔 결과를 쓴다."""
    calls: list[int] = []
    monkeypatch.setattr(
        wrap_catalog, "scan_catalog",
        lambda *a, **k: (calls.append(1), _fake_catalog())[1],
    )
    panel = window._registry_panel
    panel.set_placed_ids(set())
    panel.set_project(window._project)  # 같은 프로젝트 — 다시 훑지 않는다
    assert calls == []
    panel.refresh_catalog()
    assert calls == [1]


# ── 🧷 EXTERNAL SKILLS ───────────────────────────────────────────────────

def test_the_skills_tab_lists_refs_and_their_users(window):
    from daedalus.view.actions.creation import make_component
    from daedalus.view.actions.external_registration import add_skill_ref_to_agent

    panel = window._registry_panel
    assert _texts(panel._skills_section._list) == ["🧷 hookify:review"]

    agent = make_component(window, "fork_agent", "worker")
    window._register_component(agent)
    add_skill_ref_to_agent(window, agent, "hookify:review")
    panel.set_project(window._project)
    assert _texts(panel._skills_section._list) == ["🧷 hookify:review  ✔ worker"]


def test_the_skills_tab_attach_signal_reaches_the_action(window):
    from daedalus.view.actions.creation import make_component

    agent = make_component(window, "fork_agent", "worker")
    window._register_component(agent)
    window._registry_panel._skills_section.attach_requested.emit(
        "hookify:review", agent
    )
    assert agent.config.skills == ["hookify:review"]


def test_the_plus_button_of_external_tabs_opens_the_catalog(qapp, monkeypatch):
    """외부 정본 종류는 이름을 물어 만들 수 없다 — "+"는 카탈로그 창이다.

    창을 실제로 띄우는 `MainWindow._show_wrap_catalog`는 `exec()`라 헤드리스에서
    멈춘다 — 그래서 **패널 단독**으로 시그널만 본다(창과의 배선은 아래 테스트).
    """
    monkeypatch.setattr(wrap_catalog, "scan_catalog", lambda *a, **k: _fake_catalog())
    from daedalus.view.kind_ui import EXTERNAL_AGENTS_GROUP
    from daedalus.view.panels.registry_panel import RegistryPanel

    panel = RegistryPanel()
    opened: list[int] = []
    requested: list[str] = []
    panel.catalog_requested.connect(lambda: opened.append(1))
    panel.new_component_requested.connect(requested.append)

    panel._sections[EXTERNAL_AGENTS_GROUP].add_requested.emit()
    panel._skills_section.add_requested.emit()
    assert opened == [1, 1]
    assert requested == []

    # 자체 정본 종류의 "+"는 그대로 이름 다이얼로그 경로다.
    panel._sections["procedural"].add_requested.emit()
    assert requested == ["procedural"]


def test_the_window_wires_the_catalog_signals(window, monkeypatch):
    """패널의 세 시그널이 창의 핸들러에 **닿는다** — 배선이 빠지면 조용하다."""
    from PySide6.QtWidgets import QMessageBox

    from daedalus.view.editors.wrap_catalog_dialog import WrapCatalogDialog

    opened: list[int] = []
    warned: list[str] = []
    monkeypatch.setattr(WrapCatalogDialog, "exec", lambda self: opened.append(1))
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.append(str(a[2])),
    )
    panel = window._registry_panel

    panel.catalog_requested.emit()
    assert opened == [1]

    panel.external_agent_register_requested.emit(
        "hookify:doctor", "external_agent"
    )
    assert [a.config.source for a in window._project.agents] == ["hookify:doctor"]

    fork = window._project.agents[0]
    panel.external_skill_attach_requested.emit("hookify:review", fork)
    # 외부 정본 에이전트에는 skills 칸이 없다 — 거절이 **조용하지 않아야** 한다.
    assert getattr(fork.config, "skills", None) is None
    assert warned and "skills" in warned[0]
