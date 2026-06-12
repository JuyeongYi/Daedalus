"""WP-Q: 프로젝트 캔버스(FsmScene)가 project.graph에 동기화 + 로드 재구성."""
from PyQt6.QtCore import QPointF

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.view.app import MainWindow
from daedalus.view.canvas.scene import FsmScene
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _mk_proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return ProceduralSkill(
        fsm=fsm, name=name, description="",
        transfer_on=[EventDef(name="done")],
    )


def test_drop_skill_syncs_to_project_graph(qapp):
    """drop_skill로 만든 노드가 project.graph.states에 들어간다."""
    skill = _mk_proc("proc")
    project = PluginProject(name="p", skills=[skill])
    vm = ProjectViewModel()
    scene = FsmScene(vm, skill_lookup=lambda n: skill if n == "proc" else None)
    scene.set_project(project)

    scene.drop_skill("proc", QPointF(10, 20))
    assert any(
        getattr(s, "skill_ref", None) is skill for s in project.graph.states
    )

    vm.command_stack.undo()
    assert not any(
        getattr(s, "skill_ref", None) is skill for s in project.graph.states
    )


def test_create_transition_syncs_to_project_graph(qapp):
    a = _mk_proc("a")
    b = _mk_proc("b")
    project = PluginProject(name="p", skills=[a, b])
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene.set_project(project)

    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    avm = StateViewModel(model=sa, x=0, y=0)
    bvm = StateViewModel(model=sb, x=200, y=0)
    vm.state_vms.extend([avm, bvm])

    model = Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    tvm = TransitionViewModel(model=model, source_vm=avm, target_vm=bvm)
    from daedalus.view.commands.transition_commands import CreateTransitionCmd
    vm.execute(CreateTransitionCmd(vm, tvm, fsm=scene._target_fsm))

    assert model in project.graph.transitions
    vm.command_stack.undo()
    assert model not in project.graph.transitions


def test_delete_placement_syncs_to_project_graph(qapp):
    a = _mk_proc("a")
    project = PluginProject(name="p", skills=[a])
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene.set_project(project)

    sa = SimpleState(name="a", skill_ref=a)
    project.graph.states.append(sa)
    avm = StateViewModel(model=sa, x=0, y=0)
    vm.state_vms.append(avm)

    scene._delete_state(avm)
    assert sa not in project.graph.states

    vm.command_stack.undo()
    assert sa in project.graph.states


def test_entry_point_not_deletable_on_project_canvas(qapp):
    """EntryPoint(시작점)는 프로젝트 캔버스에서 삭제 불가."""
    project = PluginProject(name="p")
    vm = ProjectViewModel()
    scene = FsmScene(vm)
    scene.set_project(project)

    entry = project.graph.initial_state
    assert isinstance(entry, EntryPoint)
    evm = StateViewModel(model=entry, x=0, y=0)
    vm.state_vms.append(evm)

    scene._delete_state(evm)
    # 모델에서 제거되지 않음
    assert entry in project.graph.states


def test_load_reconstructs_project_canvas(qapp):
    """set_project가 project.graph + graph_layout으로 캔버스 VM을 재구성한다."""
    a = _mk_proc("a")
    b = _mk_proc("b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    project.graph_layout[sa.id] = [100.0, 200.0]
    project.graph_layout[sb.id] = [300.0, 400.0]

    window = MainWindow()
    window.set_project(project)

    pvm = window._project_vm
    # EntryPoint + 2 placement = 3 노드 VM
    assert len(pvm.state_vms) == 3
    # 전이 1개 복원
    assert len(pvm.transition_vms) == 1
    # 저장된 좌표 적용
    sa_vm = next(v for v in pvm.state_vms if v.model is sa)
    assert (sa_vm.x, sa_vm.y) == (100.0, 200.0)
    window.close()


def test_save_graph_layout_records_coords(qapp):
    project = PluginProject(name="p")
    window = MainWindow()
    window.set_project(project)

    # 캔버스에 EntryPoint VM이 있고 좌표를 바꾼 뒤 저장 레이아웃 기록
    pvm = window._project_vm
    entry_vm = pvm.state_vms[0]
    entry_vm.x = 55.0
    entry_vm.y = 66.0
    window._save_graph_layout()
    assert project.graph_layout[entry_vm.model.id] == [55.0, 66.0]
    window.close()
