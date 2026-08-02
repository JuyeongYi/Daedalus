"""_handle_transition_edge_menu — 전이 엣지 컨텍스트 메뉴 템플릿 메서드 회귀.

FsmScene/AgentFsmScene가 동일 메서드를 공유하며(중복 제거),
스킬 목록/생성 정책 차이는 오버라이드로 흡수됨을 검증한다.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.canvas.scene import AgentFsmScene, FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def test_both_scenes_share_transition_menu_method():
    """AgentFsmScene는 _handle_transition_edge_menu를 오버라이드하지 않는다."""
    assert (
        AgentFsmScene._handle_transition_edge_menu
        is FsmScene._handle_transition_edge_menu
    )


def _make_agent_fsm() -> StateMachine:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    return StateMachine(
        name="agent_fsm", states=[entry, done],
        initial_state=entry, final_states=[done],
    )


def _setup_edge(scene, vm, fsm):
    a = SimpleState(name="a")
    b = SimpleState(name="b")
    fsm.states.extend([a, b])
    avm = StateViewModel(model=a, x=0, y=0)
    bvm = StateViewModel(model=b, x=200, y=0)
    vm.state_vms.extend([avm, bvm])
    model = Transition(source=a, target=b, trigger=CompletionEvent(name="done"))
    fsm.transitions.append(model)
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    vm.transition_vms.append(tvm)
    vm.notify()
    return tvm


def test_transition_menu_delete_dispatch(qapp, monkeypatch):
    """메뉴에서 '전이 삭제' 선택 시 전이가 삭제된다 (delete_act 디스패치)."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    tvm = _setup_edge(scene, vm, fsm)
    edge_item = scene._edge_items[tvm]

    menu = QMenu()
    # menu.exec가 '전이 삭제' 액션을 반환하도록 — 마지막에 addAction된 것
    def fake_exec(_pos):
        # 메뉴에 추가된 액션 중 '전이 삭제' 텍스트를 찾아 반환
        for act in menu.actions():
            if act.text() == "전이 삭제":
                return act
        return None
    monkeypatch.setattr(menu, "exec", fake_exec)

    scene._handle_transition_edge_menu(menu, edge_item, None, None)

    assert tvm not in vm.transition_vms
    assert tvm.model not in fsm.transitions


def test_transition_menu_cancel_does_nothing(qapp, monkeypatch):
    """메뉴 취소(None 반환) 시 전이가 유지된다."""
    vm = ProjectViewModel()
    fsm = _make_agent_fsm()
    scene = AgentFsmScene(vm, agent_fsm=fsm)
    tvm = _setup_edge(scene, vm, fsm)
    edge_item = scene._edge_items[tvm]

    menu = QMenu()
    monkeypatch.setattr(menu, "exec", lambda _pos: None)

    scene._handle_transition_edge_menu(menu, edge_item, None, None)

    assert tvm in vm.transition_vms
