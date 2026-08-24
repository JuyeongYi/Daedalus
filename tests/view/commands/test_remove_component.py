"""RemoveComponentCmd — 컴포넌트 삭제의 undo/redo (A2).

삭제는 그래프 placement·연결 전이·참조 배치·다른 FSM의 skill_ref까지 훑어
정리하므로, 되돌리기가 부분적이면 없느니만 못하다. 여기서 고정하는 것은
**삭제 → undo가 그 전부를 되돌리는가**다.

검증은 뷰 화면이 아니라 **모델 + 뷰모델**로 한다 — 캔버스 아이템은 notify 이후
재구성되므로 중간 상태를 보면 고장이 있어도 통과한다.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject, ReferencePlacement
from daedalus.view.app import MainWindow
from daedalus.view.commands.component_commands import RemoveComponentCmd


def _proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}-fsm", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def _agent(name: str) -> AgentDefinition:
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name=f"{name}-fsm", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name=name, description="d", transfer_on=[EventDef(name="done")],
    )


def _chained_project() -> tuple[PluginProject, ProceduralSkill, ProceduralSkill]:
    """a → b 두 배치와 그 사이 전이 하나를 가진 프로젝트."""
    a, b = _proc("alpha"), _proc("beta")
    project = PluginProject(name="p", skills=[a, b])
    na = SimpleState(name="alpha", skill_ref=a)
    nb = SimpleState(name="beta", skill_ref=b)
    project.graph.states.extend([na, nb])
    project.graph.transitions.append(Transition(source=na, target=nb))
    return project, a, b


def _placement_names(project: PluginProject) -> list[str]:
    return [
        s.name for s in project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is not None
    ]


# --- 모델 수준 (윈도우 없이) ---


def test_delete_and_undo_restores_graph(qapp):
    """배치·전이·목록이 전부 돌아온다."""
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    assert len(vm.state_vms) == 2
    assert len(vm.transition_vms) == 1

    cmd = RemoveComponentCmd(project, vm, alpha)
    vm.execute(cmd)

    assert alpha not in project.skills
    assert _placement_names(project) == ["beta"]
    assert project.graph.transitions == []
    assert len(vm.state_vms) == 1
    assert len(vm.transition_vms) == 0

    vm.command_stack.undo()

    assert any(s is alpha for s in project.skills)
    assert sorted(_placement_names(project)) == ["alpha", "beta"]
    assert len(project.graph.transitions) == 1
    assert len(vm.state_vms) == 2
    assert len(vm.transition_vms) == 1
    window.close()


def test_undo_restores_component_position_in_list(qapp):
    """목록 안 위치까지 되돌아온다 — 순서가 컴파일 산출 순서를 좌우한다."""
    a, b, c = _proc("a"), _proc("b"), _proc("c")
    project = PluginProject(name="p", skills=[a, b, c])
    window = MainWindow()
    window.set_project(project)

    window._project_vm.execute(RemoveComponentCmd(project, window._project_vm, b))
    assert [s.name for s in project.skills] == ["a", "c"]

    window._project_vm.command_stack.undo()
    assert [s.name for s in project.skills] == ["a", "b", "c"]
    window.close()


def test_undo_restores_transition_viewmodel_identity(qapp):
    """되돌아온 전이 VM이 되돌아온 노드 VM을 가리킨다.

    모델만 복원하고 VM을 새로 만들면 전이 VM의 source_vm/target_vm이 캔버스에
    없는 유령 노드를 가리켜 엣지가 허공에 그려진다.
    """
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    vm.execute(RemoveComponentCmd(project, vm, alpha))
    vm.command_stack.undo()

    tvm = vm.transition_vms[0]
    assert any(svm is tvm.source_vm for svm in vm.state_vms)
    assert any(svm is tvm.target_vm for svm in vm.state_vms)
    window.close()


def test_undo_restores_node_position(qapp):
    """노드 좌표가 보존된다 (VM identity 보존의 실효)."""
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    target = next(s for s in vm.state_vms if s.model.skill_ref is alpha)
    target.x, target.y = 321.0, 654.0

    vm.execute(RemoveComponentCmd(project, vm, alpha))
    vm.command_stack.undo()

    restored = next(s for s in vm.state_vms if s.model.skill_ref is alpha)
    assert (restored.x, restored.y) == (321.0, 654.0)
    window.close()


def test_undo_restores_reference_placement_and_links(qapp):
    """참조 노드 배치와 연결 링크가 돌아온다."""
    from daedalus.view.viewmodel.state_vm import (
        ReferenceLinkViewModel,
        ReferenceViewModel,
    )

    host = _proc("host")
    ref = ReferenceSkill(name="doc", description="d")
    project = PluginProject(name="p", skills=[host, ref])
    node = SimpleState(name="host", skill_ref=host)
    project.graph.states.append(node)
    project.reference_placements.append(
        ReferencePlacement(skill_name="doc", x=10.0, y=20.0, connected_states=["host"])
    )

    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm
    assert len(vm.reference_vms) == 1
    assert len(vm.reference_links) == 1

    vm.execute(RemoveComponentCmd(project, vm, ref))
    assert project.reference_placements == []
    assert vm.reference_vms == []
    assert vm.reference_links == []
    assert ref not in project.skills

    vm.command_stack.undo()
    assert len(vm.reference_vms) == 1
    assert len(vm.reference_links) == 1
    assert len(project.reference_placements) == 1
    placement = project.reference_placements[0]
    assert placement.skill_name == "doc"
    assert placement.connected_states == ["host"]
    assert (placement.x, placement.y) == (10.0, 20.0)
    window.close()


def test_undo_restores_nullified_skill_refs(qapp):
    """다른 FSM 안에서 None으로 바뀐 skill_ref가 원래 컴포넌트로 돌아온다."""
    target = _proc("target")
    host = _proc("host")
    inner = SimpleState(name="inner", skill_ref=target)
    host.fsm.states.append(inner)
    project = PluginProject(name="p", skills=[host, target])

    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    vm.execute(RemoveComponentCmd(project, vm, target))
    assert inner.skill_ref is None

    vm.command_stack.undo()
    assert inner.skill_ref is target
    window.close()


def test_agent_delete_and_undo(qapp):
    """에이전트도 같은 커맨드로 처리된다 (버킷이 agents로 갈릴 뿐)."""
    agent = _agent("worker")
    project = PluginProject(name="p", agents=[agent])
    project.graph.states.append(SimpleState(name="worker", skill_ref=agent))

    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    vm.execute(RemoveComponentCmd(project, vm, agent))
    assert project.agents == []
    assert _placement_names(project) == []

    vm.command_stack.undo()
    assert project.agents == [agent]
    assert _placement_names(project) == ["worker"]
    window.close()


def test_redo_deletes_again(qapp):
    """undo 뒤 redo가 같은 삭제를 다시 수행한다."""
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    vm.execute(RemoveComponentCmd(project, vm, alpha))
    vm.command_stack.undo()
    vm.command_stack.redo()

    assert alpha not in project.skills
    assert _placement_names(project) == ["beta"]
    assert project.graph.transitions == []
    assert len(vm.state_vms) == 1
    assert len(vm.transition_vms) == 0
    window.close()


def test_single_undo_unit(qapp):
    """삭제 전체가 1 undo 단위다 — 여러 번 Ctrl+Z를 눌러야 하면 실격이다."""
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    vm = window._project_vm

    before = len(vm.command_stack.history)
    vm.execute(RemoveComponentCmd(project, vm, alpha))
    assert len(vm.command_stack.history) == before + 1
    window.close()


# --- 윈도우 경로 ---


def test_window_delete_component_uses_command(qapp):
    """MainWindow.delete_component가 커맨드 스택을 거쳐 되돌릴 수 있다."""
    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)

    window.delete_component(alpha)
    assert alpha not in project.skills
    assert window._project_vm.command_stack.can_undo

    window._undo()
    assert any(s is alpha for s in project.skills)
    window.close()


def test_window_delete_closes_open_tab(qapp):
    """열려 있던 편집 탭은 닫힌다 (기존 동작 유지)."""
    from daedalus.view.app import _FIXED_TAB_INDEXES

    project, alpha, _beta = _chained_project()
    window = MainWindow()
    window.set_project(project)
    window._open_component(alpha)
    assert window._tabs.count() == len(_FIXED_TAB_INDEXES) + 1

    window.delete_component(alpha)
    assert window._tabs.count() == len(_FIXED_TAB_INDEXES)
    assert alpha.id not in window._open_tabs
    window.close()
