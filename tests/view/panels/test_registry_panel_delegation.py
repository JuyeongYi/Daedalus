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

def test_empty_project_hides_delegation_section(qapp):
    """빈 프로젝트 → delegation 섹션이 비표시.

    최상위 위젯을 show()한 적이 없어 isVisible()은 항상 False이므로(Qt 조상 체인
    의존), 명시적 표시/은닉 플래그를 반영하는 isHidden()으로 판정한다
    (tests/view/test_app_compile.py의 기존 관례와 동일).
    """
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    panel.set_project(proj)

    assert panel._sections["delegation"].isHidden() is True


def test_project_with_delegation_shows_section_and_renders_item(qapp):
    """위임 보유 프로젝트 → 섹션 표시 + 항목 렌더."""
    panel = RegistryPanel()
    proj = PluginProject(name="p")
    deleg = TeamSpawnDef(name="team-a", description="")
    proj.delegations.append(deleg)
    panel.set_project(proj)

    section = panel._sections["delegation"]
    assert section.isHidden() is False
    assert section._list.count() == 1


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

def test_agent_editor_deleg_section_hidden_when_empty(qapp):
    """AgentEditor: 위임 없는 에이전트 → _deleg_section 비표시."""
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    project = PluginProject(name="p", agents=[agent])
    editor = AgentEditor(agent, project=project)

    assert editor._deleg_section.isHidden() is True


def test_agent_editor_deleg_section_visible_with_delegation(qapp):
    """AgentEditor: 프로젝트에 위임이 있으면 _deleg_section이 표시되고 항목이 렌더된다."""
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    project = PluginProject(name="p", agents=[agent])
    project.delegations.append(TeamSpawnDef(name="team-a", description=""))
    editor = AgentEditor(agent, project=project)

    assert editor._deleg_section.isHidden() is False
    assert editor._deleg_section._list.count() == 1


def test_agent_editor_deleg_section_has_no_add_button(qapp):
    """AgentEditor: _deleg_section에 '+' 추가 버튼이 없다."""
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    project = PluginProject(name="p", agents=[agent])
    project.delegations.append(TeamSpawnDef(name="team-a", description=""))
    editor = AgentEditor(agent, project=project)

    assert editor._deleg_section.findChild(QPushButton) is None


def test_agent_editor_has_no_on_add_delegation_method(qapp):
    """죽은 코드 제거 확인: _on_add_delegation 메서드가 더 이상 존재하지 않는다."""
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    editor = AgentEditor(agent)
    assert not hasattr(editor, "_on_add_delegation")


def test_agent_editor_deleg_double_click_still_opens_editor_path(qapp):
    """더블클릭 편집 경로(_open_delegation)는 격하 후에도 연결되어 있다."""
    from daedalus.view.editors.agent_editor import AgentEditor
    agent = _make_agent()
    project = PluginProject(name="p", agents=[agent])
    deleg = TeamSpawnDef(name="team-a", description="")
    project.delegations.append(deleg)
    editor = AgentEditor(agent, project=project)

    calls: list[object] = []
    monkey_target = editor._open_delegation
    editor._open_delegation = lambda comp: calls.append(comp)  # type: ignore[method-assign]
    editor._deleg_section.item_double_clicked.emit(deleg)

    assert calls == [deleg]
    editor._open_delegation = monkey_target


# ─────────────────────── app.py 죽은 코드 제거 ───────────────────────

def test_main_window_has_no_new_delegation_entry_point(qapp):
    """MainWindow에 더 이상 _on_new_delegation 메서드가 없다."""
    from daedalus.view.app import MainWindow
    window = MainWindow()
    assert not hasattr(window, "_on_new_delegation")
    window.close()


def test_component_titles_excludes_delegation(qapp):
    """_COMPONENT_TITLES에서 delegation 키가 제거되었다 (신규 생성 불가)."""
    from daedalus.view.app import MainWindow
    assert "delegation" not in MainWindow._COMPONENT_TITLES
