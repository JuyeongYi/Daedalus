"""WP-Q: 프로젝트 캔버스(FsmScene)가 project.graph에 동기화 + 로드 재구성."""
from PySide6.QtCore import QPointF

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


def test_entry_point_delete_guard_in_scene(qapp):
    """FsmScene._delete_state의 EntryPoint 방어 — 프로젝트 캔버스에는 이제
    EntryPoint VM이 없지만(WP-EP), 같은 방어를 공유하는 AgentFsmScene(에이전트
    캔버스의 진짜 EntryPoint)을 위해 공용 경로의 방어를 잠근다."""
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
    """set_project가 project.graph + graph_layout으로 캔버스 VM을 재구성한다.

    WP-EP: EntryPoint(워크플로 시작점)는 캔버스에 그리지 않는다 — placement만 VM화.
    """
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
    # EntryPoint는 비노출 — 2 placement만 VM화
    assert len(pvm.state_vms) == 2
    assert not any(isinstance(v.model, EntryPoint) for v in pvm.state_vms)
    # 전이 1개 복원
    assert len(pvm.transition_vms) == 1
    # 저장된 좌표 적용
    sa_vm = next(v for v in pvm.state_vms if v.model is sa)
    assert (sa_vm.x, sa_vm.y) == (100.0, 200.0)
    window.close()


def test_save_graph_layout_records_coords(qapp):
    """WP-EP: EntryPoint는 캔버스 VM이 없으므로 graph_layout에 저장되지 않는다."""
    a = _mk_proc("a")
    project = PluginProject(name="p", skills=[a])
    sa = SimpleState(name="a", skill_ref=a)
    project.graph.states.append(sa)

    window = MainWindow()
    window.set_project(project)

    pvm = window._project_vm
    a_vm = pvm.state_vms[0]
    a_vm.x = 55.0
    a_vm.y = 66.0
    window._save_graph_layout()
    assert project.graph_layout[a_vm.model.id] == [55.0, 66.0]
    # EntryPoint의 state.id 키가 없다
    entry_id = project.graph.initial_state.id
    assert entry_id not in project.graph_layout
    window.close()


def test_demo_project_load_has_no_entry_point_vm(qapp):
    """WP-EP: __main__._demo_project()(개발용 데모 프로젝트) 로드 후에도
    캔버스 VM 목록에 EntryPoint가 없다.
    """
    from daedalus.__main__ import _demo_project

    window = MainWindow()
    window.set_project(_demo_project())
    pvm = window._project_vm
    assert not any(isinstance(v.model, EntryPoint) for v in pvm.state_vms)
    window.close()


def test_roundtrip_project_load_has_no_entry_point_vm(qapp):
    """WP-EP: 직렬화→역직렬화 왕복 프로젝트 로드 후에도 캔버스 VM에
    EntryPoint가 없다 (placement는 그대로 복원됨).
    """
    import json

    from daedalus.model.serialize import deserialize_project, serialize_project

    a = _mk_proc("a")
    b = _mk_proc("b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )

    p2 = deserialize_project(json.loads(json.dumps(serialize_project(project))))

    window = MainWindow()
    window.set_project(p2)
    pvm = window._project_vm
    assert not any(isinstance(v.model, EntryPoint) for v in pvm.state_vms)
    # placement 2개 + 전이 1개는 그대로 복원된다
    assert len(pvm.state_vms) == 2
    assert len(pvm.transition_vms) == 1
    window.close()


def test_old_version_start_transition_not_rendered_but_preserved(qapp):
    """구버전 직렬화 dict(EntryPoint→스킬 시작 전이 포함) 로드 시 예외/경고 없이
    성공하고, 그 전이는 캔버스에 렌더되지 않으며 저장 왕복 후에도 모델에
    EntryPoint가 보존된다.
    """
    import json

    from daedalus.model.serialize import deserialize_project, serialize_project

    a = _mk_proc("a")
    project = PluginProject(name="p", skills=[a])
    sa = SimpleState(name="a", skill_ref=a)
    project.graph.states.append(sa)
    entry = project.graph.initial_state
    project.graph.transitions.append(
        Transition(source=entry, target=sa, trigger=CompletionEvent(name="done"))
    )

    data = json.loads(json.dumps(serialize_project(project)))
    warns: list[str] = []
    p2 = deserialize_project(data, collect_warnings=warns)
    assert warns == []

    # 모델에는 시작 전이가 보존된다
    assert len(p2.graph.transitions) == 1
    assert isinstance(p2.graph.transitions[0].source, EntryPoint)

    # 캔버스에는 렌더되지 않는다 (EntryPoint VM 없음 → 그 전이 VM도 없음)
    window = MainWindow()
    window.set_project(p2)
    pvm = window._project_vm
    assert not any(isinstance(v.model, EntryPoint) for v in pvm.state_vms)
    assert len(pvm.transition_vms) == 0

    # 저장 왕복 후에도 모델에 EntryPoint + 시작 전이가 보존된다
    window._save_graph_layout()
    data2 = json.loads(json.dumps(serialize_project(p2)))
    p3 = deserialize_project(data2)
    assert isinstance(p3.graph.initial_state, EntryPoint)
    assert len(p3.graph.transitions) == 1
    window.close()
