# tests/view/panels/test_registry_panel_delegation.py
"""WP-DG — Delegation 신규 생성 UI 제거(격하) 검증.

기존 위임의 로드·표시·더블클릭 편집·삭제·직렬화·컴파일·검증 경로는 건드리지
않았음을 함께 확인한다 (Part C 항목 4는 전체 스위트 통과로 증명 — 여기서는
격하 자체의 신규 동작만 다룬다).
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import TeamSpawnDef
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.panels.registry_panel import RegistryPanel, _RegistrySection


def _make_agent(name: str = "worker") -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name=f"{name}_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )
    return AgentDefinition(fsm=fsm, name=name, description="")


# ─────────────────────── RegistryPanel ───────────────────────

def _delegation_tab_visible(panel: RegistryPanel) -> bool:
    """레지스트리 탭화(WP-SF 배치 개편) 이후 노출 판정은 탭 가시성이다 —
    비활성 탭 페이지는 QTabWidget이 항상 숨기므로 위젯 isHidden은 무의미하다."""
    idx = panel._tabs.indexOf(panel._sections["delegation"])
    return panel._tabs.tabBar().isTabVisible(idx)


def test_empty_project_hides_delegation_section(qapp):
    """빈 프로젝트 → delegation 탭이 비표시."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    panel.set_project(proj)

    assert _delegation_tab_visible(panel) is False


def test_project_with_delegation_shows_section_and_renders_item(qapp):
    """위임 보유 프로젝트 → 탭 표시 + 항목 렌더."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    deleg = TeamSpawnDef(name="team-a", description="")
    proj.delegations.append(deleg)
    panel.set_project(proj)

    assert _delegation_tab_visible(panel) is True
    assert panel._sections["delegation"]._list.count() == 1


def test_delegation_double_click_signal_path_intact(qapp):
    """component_double_clicked 시그널 경로가 기존대로 동작 — 격하가 편집 진입점을 막지 않는다."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    deleg = TeamSpawnDef(name="team-a", description="")
    proj.delegations.append(deleg)
    panel.set_project(proj)

    received: list[object] = []
    panel.component_double_clicked.connect(lambda c: received.append(c))

    section = panel._sections["delegation"]
    section.item_double_clicked.emit(deleg)

    assert received == [deleg]


def test_delegation_delete_signal_path_intact(qapp):
    """component_delete_requested 시그널 경로가 기존대로 동작."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    deleg = TeamSpawnDef(name="team-a", description="")
    proj.delegations.append(deleg)
    panel.set_project(proj)

    received: list[object] = []
    panel.component_delete_requested.connect(lambda c: received.append(c))

    section = panel._sections["delegation"]
    section.delete_requested.emit(deleg)

    assert received == [deleg]


def test_delegation_section_has_no_add_button(qapp):
    """delegation 섹션에는 '+' 추가 버튼이 없다."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    proj.delegations.append(TeamSpawnDef(name="team-a", description=""))
    panel.set_project(proj)

    section = panel._sections["delegation"]
    assert section.findChild(QPushButton) is None


def test_other_sections_still_have_add_button(qapp):
    """다른 섹션(procedural 등)은 여전히 '+' 버튼을 가진다 — 격하가 전체 UI를 건드리지 않았음."""
    panel = RegistryPanel()
    section = panel._sections["procedural"]
    assert section.findChild(QPushButton) is not None


def test_registry_section_no_add_flag_creates_no_button(qapp):
    """_RegistrySection(no_add=True)는 '+' 버튼 위젯을 만들지 않는다."""
    from PySide6.QtGui import QColor
    section = _RegistrySection("TEST", QColor("#ffffff"), no_add=True)
    assert section.findChild(QPushButton) is None


# ─────────────────────── AgentEditor ───────────────────────
# WP-AF — 내부 FSM 퇴역과 함께 AgentEditor의 위임 사이드바(_deleg_section)도
# 사라졌다(그래프 탭 소속이었다). 위임 자체가 deprecated라 대체 UI는 없다.


def test_agent_editor_has_no_delegation_sidebar(qapp):
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    project = PluginProject(name="p", agents=[agent])
    project.delegations.append(TeamSpawnDef(name="team-a", description=""))
    editor = AgentEditor(agent, project=project)

    assert not hasattr(editor, "_deleg_section")
