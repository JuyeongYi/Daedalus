"""스킬 노드 액션의 두 호출부 — 캔버스 우클릭 / 스킬 에디터 (A9-1,2,3).

**로직은 tests/view/actions/test_skill_node_actions.py가 검사한다.** 여기서
고정하는 것은 두 표면이 같은 함수를 부르는가, 그리고 대상이 아닌 노드에 항목을
만들지 않는가다.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import EffortLevel, ModelType
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow


def _proc(name: str = "worker") -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


@pytest.fixture
def window(qapp):
    skill = _proc()
    entry = EntryPoint(name="entry")
    agent = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=entry, states=[entry]),
        name="runner", description="d", transfer_on=[EventDef(name="done")],
    )
    project = PluginProject(name="p", skills=[skill], agents=[agent])
    project.graph.states.append(SimpleState(name="worker", skill_ref=skill))
    project.graph.states.append(SimpleState(name="agent", skill_ref=agent))
    project.graph.states.append(SimpleState(name="empty"))

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


def _state_vm(window, name: str):
    return next(vm for vm in window._project_vm.state_vms if vm.model.name == name)


def _labels(menu: QMenu) -> list[str]:
    return [a.text() for a in menu.actions()]


def _submenu(menu: QMenu, title: str) -> QMenu:
    """제목으로 서브메뉴를 찾는다.

    `QAction.menu()`가 돌려주는 임시 참조는 평가 직후 파괴될 수 있다(기존
    test_hook_panel.py가 같은 함정을 기록해 두었다) — findChildren으로 잡아야
    객체가 살아 있다.
    """
    return next(m for m in menu.findChildren(QMenu) if m.title() == title)


# --- 캔버스 메뉴 구성 ---


def test_menu_has_all_three_entries(window):
    scene = window._fsm_scene
    menu = QMenu()
    scene._add_component_actions_menu(menu, _state_vm(window, "worker"))
    labels = _labels(menu)
    assert any("컴파일 미리보기" in x for x in labels)
    assert any("모델 지정" in x for x in labels)
    assert any("effort 지정" in x for x in labels)
    assert any("관련 경고" in x for x in labels)
    menu.deleteLater()


def test_menu_empty_for_unplaced_node(window):
    """빈 상태 노드에는 컴포넌트가 없으니 항목도 없다."""
    scene = window._fsm_scene
    menu = QMenu()
    assert scene._add_component_actions_menu(menu, _state_vm(window, "empty")) == {}
    assert _labels(menu) == []
    menu.deleteLater()


def test_agent_node_gets_the_same_entries(window):
    """모델/effort는 config 필드 이름이 같아 에이전트에도 노출된다."""
    scene = window._fsm_scene
    menu = QMenu()
    scene._add_component_actions_menu(menu, _state_vm(window, "agent"))
    assert any("모델 지정" in x for x in _labels(menu))
    menu.deleteLater()


def test_menu_checks_current_model(window):
    scene = window._fsm_scene
    skill = window._project.skills[0]
    skill.config.model = ModelType.HAIKU

    menu = QMenu()
    scene._add_component_actions_menu(menu, _state_vm(window, "worker"))
    model_menu = _submenu(menu, "모델 지정")
    checked = [a.text() for a in model_menu.actions() if a.isChecked()]
    assert checked == ["haiku"]
    menu.deleteLater()


def test_menu_checks_current_effort_none(window):
    scene = window._fsm_scene
    menu = QMenu()
    scene._add_component_actions_menu(menu, _state_vm(window, "worker"))
    effort_menu = _submenu(menu, "effort 지정")
    checked = [a.text() for a in effort_menu.actions() if a.isChecked()]
    assert checked == ["(미지정)"]
    menu.deleteLater()


# --- 캔버스 메뉴가 공유 함수를 부르는가 ---


def test_menu_model_action_uses_shared_setter(window):
    scene = window._fsm_scene
    menu = QMenu()
    dispatch = scene._add_component_actions_menu(menu, _state_vm(window, "worker"))
    model_menu = _submenu(menu, "모델 지정")
    sonnet = next(a for a in model_menu.actions() if a.text() == "sonnet")

    dispatch[sonnet]()
    assert window._project.skills[0].config.model is ModelType.SONNET
    # 공유 함수(SetAttrCmd) 경로를 탔으므로 되돌릴 수 있다
    assert window._project_vm.command_stack.can_undo
    window._project_vm.command_stack.undo()
    assert window._project.skills[0].config.model is ModelType.INHERIT
    menu.deleteLater()


def test_menu_effort_action_uses_shared_setter(window):
    scene = window._fsm_scene
    menu = QMenu()
    dispatch = scene._add_component_actions_menu(menu, _state_vm(window, "worker"))
    effort_menu = _submenu(menu, "effort 지정")
    high = next(a for a in effort_menu.actions() if a.text() == "high")

    dispatch[high]()
    assert window._project.skills[0].config.effort is EffortLevel.HIGH
    menu.deleteLater()


def test_menu_preview_calls_shared_dialog(window, monkeypatch):
    import daedalus.view.actions.preview as preview

    calls: list = []
    monkeypatch.setattr(
        preview, "show_preview_dialog",
        lambda parent, comp, project=None, resolved_hooks=None: calls.append(
            (parent, comp, project)
        ),
    )
    window._fsm_scene._show_preview(window._project.skills[0])
    assert len(calls) == 1
    assert calls[0][1] is window._project.skills[0]
    assert calls[0][2] is window._project


def test_menu_findings_calls_window(window, monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        MainWindow, "show_component_findings",
        lambda self, comp: calls.append(comp) or 0,
    )
    window._fsm_scene._show_component_findings(window._project.skills[0])
    assert calls == [window._project.skills[0]]


# --- 에디터 호출부 ---


def _panel(window, component):
    from daedalus.view.editors.skill_editor import SkillEditor

    editor = SkillEditor(component, project_vm=window._project_vm)
    return editor, editor._editor._fm


def test_editor_has_action_buttons(window):
    editor, panel = _panel(window, window._project.skills[0])
    assert panel._preview_btn.text() == "미리보기"
    assert panel._findings_btn.text() == "관련 경고"
    editor.close()


def test_editor_preview_calls_shared_dialog(window, monkeypatch):
    import daedalus.view.actions.preview as preview

    calls: list = []
    monkeypatch.setattr(
        preview, "show_preview_dialog",
        lambda parent, comp, project=None, resolved_hooks=None: calls.append(comp),
    )
    editor, panel = _panel(window, window._project.skills[0])
    panel._preview_btn.click()
    assert calls == [window._project.skills[0]]
    editor.close()


def test_editor_findings_calls_window(window, monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        MainWindow, "show_component_findings",
        lambda self, comp: calls.append(comp) or 0,
    )
    # 창에 붙여야 _main_window()가 MainWindow에 닿는다
    window._open_component(window._project.skills[0])
    editor = window._tabs.widget(window._open_tabs[window._project.skills[0].id])
    editor._editor._fm._findings_btn.click()
    assert calls == [window._project.skills[0]]


# --- 검증 결과 필터가 실제로 패널을 채우는가 ---


def test_show_component_findings_fills_panel(window):
    from daedalus.model.fsm.transition import Transition

    skill = window._project.skills[0]
    second = _proc("beta")
    window._project.skills.append(second)
    nb = SimpleState(name="beta", skill_ref=second)
    window._project.graph.states.append(nb)
    na = next(
        s for s in window._project.graph.states
        if getattr(s, "skill_ref", None) is skill
    )
    window._project.graph.transitions.append(Transition(source=na, target=nb))

    count = window.show_component_findings(second)
    assert count >= 1
    rules = {e.rule for e in window._validation_panel._errors}
    assert "mid_chain_user_invocable" in rules


def test_show_component_findings_reports_zero(window):
    count = window.show_component_findings(window._project.skills[0])
    assert count == 0
    assert "검증 결과가 없습니다" in window._status_label.text()
