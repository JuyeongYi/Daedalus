"""_handle_transition_edge_menu — 전이 엣지 컨텍스트 메뉴 디스패치 회귀."""
from __future__ import annotations

from PySide6.QtWidgets import QMenu

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.project import PluginProject
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_scene():
    vm = ProjectViewModel()
    project = PluginProject(name="p")
    scene = FsmScene(vm)
    scene.set_project(project)
    return vm, project.graph, scene


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
    vm, fsm, scene = _make_scene()
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
    vm, fsm, scene = _make_scene()
    tvm = _setup_edge(scene, vm, fsm)
    edge_item = scene._edge_items[tvm]

    menu = QMenu()
    monkeypatch.setattr(menu, "exec", lambda _pos: None)

    scene._handle_transition_edge_menu(menu, edge_item, None, None)

    assert tvm in vm.transition_vms


def test_transition_menu_preview_for_attached_transfer(qapp, monkeypatch):
    """transfer가 붙은 전이의 메뉴에 컴파일 미리보기가 있고 그 스킬로 디스패치된다.

    트랜스퍼 스킬은 캔버스 노드가 아니라 엣지에 붙어 placement 우클릭 메뉴가
    닿지 않는다(사용자 보고) — 엣지 메뉴가 캔버스 쪽 진입점이다.
    """
    from daedalus.view.canvas import context_menus
    from tests.compiler.builders import make_transfer

    vm, fsm, scene = _make_scene()
    tvm = _setup_edge(scene, vm, fsm)
    transfer = make_transfer(name="scope-freeze")
    tvm.model.skill_ref = transfer
    edge_item = scene._edge_items[tvm]

    previewed = []
    monkeypatch.setattr(
        context_menus, "show_preview", lambda s, c: previewed.append(c)
    )

    menu = QMenu()
    def fake_exec(_pos):
        for act in menu.actions():
            if act.text().startswith("컴파일 미리보기"):
                return act
        return None
    monkeypatch.setattr(menu, "exec", fake_exec)

    scene._handle_transition_edge_menu(menu, edge_item, None, None)
    assert previewed == [transfer]


def test_transition_menu_no_preview_without_transfer(qapp, monkeypatch):
    """transfer가 없는 전이의 메뉴에는 미리보기 항목이 없다."""
    vm, fsm, scene = _make_scene()
    tvm = _setup_edge(scene, vm, fsm)
    edge_item = scene._edge_items[tvm]

    menu = QMenu()
    monkeypatch.setattr(menu, "exec", lambda _pos: None)
    scene._handle_transition_edge_menu(menu, edge_item, None, None)
    assert not any(a.text().startswith("컴파일 미리보기") for a in menu.actions())
