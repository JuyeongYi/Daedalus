"""전이 트리거 지정 — 공유 함수 + 두 호출부 (A9-8).

지금까지 트리거를 바꾸는 GUI가 없었다(전이를 그을 때 정해지고 MCP로만 수정).
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.actions.transitions import (
    current_trigger,
    set_trigger,
    trigger_choices,
)
from daedalus.view.app import MainWindow


def _proc(name: str, transfer=(), calls=()) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    skill = ProceduralSkill(fsm=fsm, name=name, description="d")
    skill.transfer_on = [EventDef(name=n) for n in transfer] or skill.transfer_on
    skill.call_agents = [EventDef(name=n) for n in calls]
    return skill


@pytest.fixture
def window(qapp):
    a = _proc("alpha", transfer=("ok", "fail"), calls=("delegate",))
    b = _proc("beta")
    project = PluginProject(name="p", skills=[a, b])
    na = SimpleState(name="alpha", skill_ref=a)
    nb = SimpleState(name="beta", skill_ref=b)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(
        Transition(source=na, target=nb, trigger=CompletionEvent(name="ok"))
    )

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


def _tvm(window):
    return window._project_vm.transition_vms[0]


# --- 공유 함수 ---


def test_choices_are_the_source_output_events(window):
    """후보는 출발 노드가 선언한 포트 — transfer_on 다음 call_agents."""
    assert trigger_choices(_tvm(window)) == ["ok", "fail", "delegate"]


def test_choices_empty_for_unplaced_source(qapp):
    from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

    src = StateViewModel(model=SimpleState(name="empty"))
    tgt = StateViewModel(model=SimpleState(name="other"))
    tvm = TransitionViewModel(
        model=Transition(source=src.model, target=tgt.model),
        source_vm=src, target_vm=tgt,
    )
    assert trigger_choices(tvm) == []


def test_current_trigger(window):
    assert current_trigger(_tvm(window)) == "ok"


def test_set_trigger_is_undoable(window):
    tvm = _tvm(window)
    assert set_trigger(window._project_vm, tvm, "fail") is True
    assert current_trigger(tvm) == "fail"

    window._project_vm.command_stack.undo()
    assert current_trigger(tvm) == "ok"


def test_set_trigger_creates_a_new_event_object(window):
    """기존 이벤트의 name을 제자리에서 고치면 undo가 죽는다(old/new가 같은 객체)."""
    tvm = _tvm(window)
    before = tvm.model.trigger
    set_trigger(window._project_vm, tvm, "fail")
    assert tvm.model.trigger is not before
    assert before.name == "ok"  # 옛 객체는 그대로


def test_empty_name_clears_the_trigger(window):
    tvm = _tvm(window)
    assert set_trigger(window._project_vm, tvm, "") is True
    assert tvm.model.trigger is None
    window._project_vm.command_stack.undo()
    assert current_trigger(tvm) == "ok"


def test_same_trigger_is_a_no_op(window):
    tvm = _tvm(window)
    before = len(window._project_vm.command_stack.history)
    assert set_trigger(window._project_vm, tvm, "ok") is False
    assert len(window._project_vm.command_stack.history) == before


# --- 캔버스 엣지 메뉴 ---


def _submenu(menu: QMenu, title: str) -> QMenu:
    return next(m for m in menu.findChildren(QMenu) if m.title() == title)


def test_edge_menu_lists_choices_and_none(window):
    from daedalus.view.canvas import context_menus

    menu = QMenu()
    mapping = context_menus.add_trigger_menu(menu, _tvm(window))
    assert list(mapping.values()) == ["", "ok", "fail", "delegate"]
    menu.deleteLater()


def test_edge_menu_checks_current(window):
    from daedalus.view.canvas import context_menus

    menu = QMenu()
    mapping = context_menus.add_trigger_menu(menu, _tvm(window))
    checked = [name for act, name in mapping.items() if act.isChecked()]
    assert checked == ["ok"]
    menu.deleteLater()


def test_edge_menu_shows_orphan_trigger(window):
    """포트 개명 잔재가 안 보이면 무엇이 걸려 있는지 모른 채 고르게 된다."""
    from daedalus.view.canvas import context_menus

    tvm = _tvm(window)
    tvm.model.trigger = CompletionEvent(name="gone")
    menu = QMenu()
    context_menus.add_trigger_menu(menu, tvm)
    sub = _submenu(menu, "트리거 지정")
    orphan = [a for a in sub.actions() if "포트에 없음" in a.text()]
    assert len(orphan) == 1
    assert orphan[0].isEnabled() is False
    menu.deleteLater()


def test_edge_menu_uses_the_shared_setter(window):
    from daedalus.view.canvas import context_menus

    menu = QMenu()
    mapping = context_menus.add_trigger_menu(menu, _tvm(window))
    act = next(a for a, name in mapping.items() if name == "fail")
    window._fsm_scene.set_transition_trigger(_tvm(window), mapping[act])

    assert current_trigger(_tvm(window)) == "fail"
    assert window._project_vm.command_stack.can_undo
    menu.deleteLater()


# --- PropertyPanel ---


def test_property_panel_shows_trigger_combo(window):
    panel = window._property_panel
    panel.show_transition(_tvm(window))
    combo = panel._trigger_combo
    assert [combo.itemData(i) for i in range(combo.count())] == [
        "", "ok", "fail", "delegate",
    ]
    assert combo.currentData() == "ok"


def test_property_panel_combo_sets_trigger(window):
    panel = window._property_panel
    tvm = _tvm(window)
    panel.show_transition(tvm)
    combo = panel._trigger_combo

    combo.setCurrentIndex(combo.findData("delegate"))
    assert current_trigger(tvm) == "delegate"
    window._project_vm.command_stack.undo()
    assert current_trigger(tvm) == "ok"


def test_property_panel_combo_can_clear(window):
    panel = window._property_panel
    tvm = _tvm(window)
    panel.show_transition(tvm)
    combo = panel._trigger_combo

    combo.setCurrentIndex(combo.findData(""))
    assert tvm.model.trigger is None


def test_property_panel_shows_orphan_trigger(window):
    panel = window._property_panel
    tvm = _tvm(window)
    tvm.model.trigger = CompletionEvent(name="gone")
    panel.show_transition(tvm)
    combo = panel._trigger_combo
    assert combo.currentData() == "gone"
    assert "포트에 없음" in combo.currentText()
