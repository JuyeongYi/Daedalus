"""에이전트 노드 액션의 두 호출부 — 캔버스 우클릭 / 에이전트 에디터 (A9-4,5).

로직(호출자 유도)은 tests/view/actions/test_agent_links.py가 검사한다.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _submenu(menu: QMenu, title: str) -> QMenu:
    """QAction.menu()의 임시 참조는 평가 직후 파괴될 수 있다 — findChildren으로."""
    return next(m for m in menu.findChildren(QMenu) if m.title() == title)


@pytest.fixture
def window(qapp):
    s = SimpleState(name="start")
    caller = ProceduralSkill(
        fsm=StateMachine(name="f", initial_state=s, states=[s]),
        name="driver", description="d",
    )
    caller.call_agents = [EventDef(name="analyze", description="파일을 넘긴다")]
    entry = EntryPoint(name="entry")
    agent = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=entry, states=[entry]),
        name="runner", description="d", transfer_on=[EventDef(name="done")],
    )
    lonely = AgentDefinition(
        fsm=StateMachine(name="af2", initial_state=EntryPoint(name="e2"),
                         states=[EntryPoint(name="e2")]),
        name="lonely", description="d", transfer_on=[EventDef(name="done")],
    )
    project = PluginProject(name="p", skills=[caller], agents=[agent, lonely])
    ns = SimpleState(name="driver", skill_ref=caller)
    na = SimpleState(name="runner", skill_ref=agent)
    nl = SimpleState(name="lonely", skill_ref=lonely)
    project.graph.states.extend([ns, na, nl])
    project.graph.transitions.append(
        Transition(source=ns, target=na, trigger=CompletionEvent(name="analyze"))
    )

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


def _state_vm(window, name: str):
    return next(vm for vm in window._project_vm.state_vms if vm.model.name == name)


def _agent(window, name: str):
    return next(a for a in window._project.agents if a.name == name)


# --- 캔버스 메뉴 ---


def test_menu_lists_callers(window):
    menu = QMenu()
    window._fsm_scene._add_agent_actions_menu(menu, _agent(window, "runner"))
    callers = _submenu(menu, "호출자 목록")
    assert [a.text() for a in callers.actions()] == ["driver · analyze"]
    assert callers.actions()[0].toolTip() == "파일을 넘긴다"
    menu.deleteLater()


def test_menu_shows_disabled_placeholder_without_callers(window):
    menu = QMenu()
    window._fsm_scene._add_agent_actions_menu(menu, _agent(window, "lonely"))
    callers = _submenu(menu, "호출자 목록")
    (act,) = callers.actions()
    assert act.text() == "(없음)"
    assert act.isEnabled() is False
    menu.deleteLater()


def test_menu_absent_for_non_agent(window):
    menu = QMenu()
    assert window._fsm_scene._add_agent_actions_menu(
        menu, window._project.skills[0]
    ) == {}
    menu.deleteLater()


def test_caller_click_focuses_the_caller_node(window):
    menu = QMenu()
    dispatch = window._fsm_scene._add_agent_actions_menu(
        menu, _agent(window, "runner")
    )
    callers = _submenu(menu, "호출자 목록")
    act = callers.actions()[0]

    dispatch[act]()
    selected = [
        svm for svm, item in window._fsm_scene._node_items.items()
        if item.isSelected()
    ]
    assert [svm.model.name for svm in selected] == ["driver"]
    menu.deleteLater()


def test_ports_action_opens_editor_tab(window, monkeypatch):
    """탭이 열리고 **그 탭이 앞으로 오며** 포트 패널에 포커스를 요청한다.

    실제 포커스는 창을 띄우지 않은 헤드리스에서 확인할 수 없으므로
    `setFocus` 호출을 잡는다 — 확인할 수 없는 것을 확인한 척하지 않는다.
    """
    from daedalus.view.editors.skill_editor import _TransferOnPanel

    focused: list = []
    monkeypatch.setattr(
        _TransferOnPanel, "setFocus", lambda self, *a: focused.append(self)
    )

    menu = QMenu()
    dispatch = window._fsm_scene._add_agent_actions_menu(
        menu, _agent(window, "runner")
    )
    ports_act = next(a for a in menu.actions() if a.text().startswith("출력 포트"))
    dispatch[ports_act]()

    agent = _agent(window, "runner")
    assert agent.id in window._open_tabs
    index = window._open_tabs[agent.id]
    assert window._tabs.currentIndex() == index
    widget = window._tabs.widget(index)
    assert focused == [widget._transfer_on_panel]
    menu.deleteLater()


def test_open_component_ports_is_idempotent(window):
    agent = _agent(window, "runner")
    window.open_component_ports(agent)
    before = window._tabs.count()
    window.open_component_ports(agent)
    assert window._tabs.count() == before


# --- 에이전트 에디터 ---


def test_editor_shows_caller_list(window):
    window._open_component(_agent(window, "runner"))
    editor = window._tabs.widget(window._open_tabs[_agent(window, "runner").id])
    panel = editor._callers_panel
    assert panel._list.count() == 1
    assert panel._list.item(0).text() == "driver · analyze"
    assert panel._list.item(0).toolTip() == "파일을 넘긴다"


def test_editor_shows_guidance_without_callers(window):
    window._open_component(_agent(window, "lonely"))
    editor = window._tabs.widget(window._open_tabs[_agent(window, "lonely").id])
    panel = editor._callers_panel
    assert panel._list.count() == 0
    assert "호출 포트" in panel._empty_label.text()


def test_editor_caller_list_refreshes(window):
    """캔버스에서 전이를 이은 뒤 탭으로 돌아오면 반영돼야 한다."""
    lonely = _agent(window, "lonely")
    window._open_component(lonely)
    editor = window._tabs.widget(window._open_tabs[lonely.id])
    assert editor._callers_panel._list.count() == 0

    caller = window._project.skills[0]
    ns = next(
        s for s in window._project.graph.states
        if getattr(s, "skill_ref", None) is caller
    )
    nl = next(
        s for s in window._project.graph.states
        if getattr(s, "skill_ref", None) is lonely
    )
    window._project.graph.transitions.append(
        Transition(source=ns, target=nl, trigger=CompletionEvent(name="analyze"))
    )
    editor._callers_panel.refresh()
    assert editor._callers_panel._list.count() == 1
