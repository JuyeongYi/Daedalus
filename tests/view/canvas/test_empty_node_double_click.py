"""빈 상태 노드 더블클릭 (컴포넌트가 붙지 않은 노드).

컴포넌트가 붙은 노드는 더블클릭하면 편집기가 열린다. 빈 노드는 열 편집기가
없어 아무 반응도 없었는데, 사용자에게는 고장으로 읽힌다 — 빈 노드에서 유일하게
편집할 것인 이름을 연다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel


@pytest.fixture
def scene(qapp):
    vm = ProjectViewModel()
    sc = FsmScene(vm)
    sc.set_project(PluginProject(name="p"))
    return sc


def _add(scene, name, skill_ref=None):
    svm = StateViewModel(model=SimpleState(name=name, skill_ref=skill_ref), x=0, y=0)
    scene._project_vm.state_vms.append(svm)
    scene._project_vm.notify()
    return svm


def _node_for(scene, svm):
    from daedalus.view.canvas.node_item import StateNodeItem

    return next(
        i for i in scene.items()
        if isinstance(i, StateNodeItem) and i.state_vm is svm
    )


def test_empty_node_opens_rename(scene, monkeypatch):
    svm = _add(scene, "survey")
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        lambda *a, **k: ("renamed", True),
    )
    scene.handle_node_double_clicked(_node_for(scene, svm))
    assert svm.model.name == "renamed"


def test_rename_is_undoable(scene, monkeypatch):
    svm = _add(scene, "survey")
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        lambda *a, **k: ("renamed", True),
    )
    scene.handle_node_double_clicked(_node_for(scene, svm))
    scene._project_vm.command_stack.undo()
    assert svm.model.name == "survey"


def test_cancel_leaves_name(scene, monkeypatch):
    svm = _add(scene, "survey")
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        lambda *a, **k: ("whatever", False),
    )
    scene.handle_node_double_clicked(_node_for(scene, svm))
    assert svm.model.name == "survey"


def test_duplicate_name_rejected(scene, monkeypatch):
    """같은 머신에 동명 상태가 둘이면 서로를 가린다(duplicate_state_name)."""
    _add(scene, "taken")
    svm = _add(scene, "survey")
    warned = {}
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        lambda *a, **k: ("taken", True),
    )
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QMessageBox.warning",
        lambda *a, **k: warned.setdefault("shown", True),
    )
    scene.handle_node_double_clicked(_node_for(scene, svm))
    assert svm.model.name == "survey"
    assert warned.get("shown")


def test_component_node_still_opens_editor(scene, monkeypatch):
    """컴포넌트가 붙은 노드는 종전대로 편집기 시그널을 낸다."""
    s = SimpleState(name="x")
    skill = ProceduralSkill(
        fsm=StateMachine(name="f", initial_state=s, states=[s]),
        name="init", description="",
    )
    svm = _add(scene, "init", skill_ref=skill)

    emitted = []
    scene.node_double_clicked.connect(emitted.append)
    monkeypatch.setattr(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        lambda *a, **k: pytest.fail("컴포넌트 노드는 이름 변경이 아니라 편집기를 연다"),
    )
    scene.handle_node_double_clicked(_node_for(scene, svm))
    assert emitted == [skill]
