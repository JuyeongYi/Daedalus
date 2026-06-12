from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.validation import Validator
from daedalus.view.commands.state_commands import (
    CreateStateCmd,
    DeleteStateCmd,
    MoveStateCmd,
    RenameStateCmd,
)
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel


def _make_pvm_with_state(name: str = "S") -> tuple[ProjectViewModel, StateViewModel]:
    pvm = ProjectViewModel()
    vm = StateViewModel(model=SimpleState(name=name))
    pvm.add_state_vm(vm)
    return pvm, vm


class TestCreateStateCmd:
    def test_execute_adds_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        assert vm in pvm.state_vms

    def test_undo_removes_state(self):
        pvm = ProjectViewModel()
        vm = StateViewModel(model=SimpleState(name="New"))
        cmd = CreateStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm not in pvm.state_vms

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = CreateStateCmd(ProjectViewModel(), vm)
        assert "Idle" in cmd.description


class TestDeleteStateCmd:
    def test_execute_removes_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        assert vm not in pvm.state_vms

    def test_undo_restores_state(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        cmd.execute()
        cmd.undo()
        assert vm in pvm.state_vms

    def test_description(self):
        pvm, vm = _make_pvm_with_state("X")
        cmd = DeleteStateCmd(pvm, vm)
        assert "X" in cmd.description


class TestMoveStateCmd:
    def test_execute_updates_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        assert vm.x == 100.0
        assert vm.y == 200.0

    def test_undo_restores_position(self):
        vm = StateViewModel(model=SimpleState(name="S"), x=0.0, y=0.0)
        cmd = MoveStateCmd(vm, old_x=0.0, old_y=0.0, new_x=100.0, new_y=200.0)
        cmd.execute()
        cmd.undo()
        assert vm.x == 0.0
        assert vm.y == 0.0

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Idle"))
        cmd = MoveStateCmd(vm, 0, 0, 1, 1)
        assert "Idle" in cmd.description


class TestRenameStateCmd:
    def test_execute_changes_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        assert vm.model.name == "New"

    def test_undo_restores_name(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, old_name="Old", new_name="New")
        cmd.execute()
        cmd.undo()
        assert vm.model.name == "Old"

    def test_description(self):
        vm = StateViewModel(model=SimpleState(name="Old"))
        cmd = RenameStateCmd(vm, "Old", "New")
        assert "Old" in cmd.description and "New" in cmd.description


# --- FSM 동기화 테스트 ---


def _make_fsm() -> StateMachine:
    start = SimpleState(name="start")
    return StateMachine(name="fsm", states=[start], initial_state=start)


def test_create_state_cmd_syncs_fsm():
    vm = ProjectViewModel()
    fsm = _make_fsm()
    state = SimpleState(name="new_state")
    svm = StateViewModel(model=state, x=0, y=0)
    cmd = CreateStateCmd(vm, svm, fsm=fsm)

    cmd.execute()
    assert state in fsm.states
    assert svm in vm.state_vms

    cmd.undo()
    assert state not in fsm.states
    assert svm not in vm.state_vms


def test_create_state_cmd_without_fsm_keeps_legacy_behavior():
    vm = ProjectViewModel()
    state = SimpleState(name="new_state")
    svm = StateViewModel(model=state, x=0, y=0)
    cmd = CreateStateCmd(vm, svm)  # fsm 미전달 — 프로젝트 캔버스 경로

    cmd.execute()
    assert svm in vm.state_vms
    cmd.undo()
    assert svm not in vm.state_vms


def test_delete_state_cmd_syncs_fsm():
    vm = ProjectViewModel()
    fsm = _make_fsm()
    state = SimpleState(name="victim")
    fsm.states.append(state)
    svm = StateViewModel(model=state, x=0, y=0)
    vm.state_vms.append(svm)
    cmd = DeleteStateCmd(vm, svm, fsm=fsm)

    cmd.execute()
    assert state not in fsm.states
    assert svm not in vm.state_vms

    cmd.undo()
    assert state in fsm.states
    assert svm in vm.state_vms


def test_create_state_cmd_execute_is_idempotent_on_fsm():
    """redo 시 fsm.states에 중복 추가되지 않아야 한다."""
    vm = ProjectViewModel()
    fsm = _make_fsm()
    state = SimpleState(name="s")
    svm = StateViewModel(model=state, x=0, y=0)
    cmd = CreateStateCmd(vm, svm, fsm=fsm)
    cmd.execute()
    cmd.undo()
    cmd.execute()  # redo
    assert sum(1 for s in fsm.states if s is state) == 1


# --- WP-R: final_states / initial_state 정리 테스트 ---


def _make_fsm_with_final() -> tuple[StateMachine, SimpleState, SimpleState]:
    """start(initial) + end(final) 을 가진 FSM 반환."""
    start = SimpleState(name="start")
    end = SimpleState(name="end")
    fsm = StateMachine(name="fsm", states=[start, end], initial_state=start, final_states=[end])
    return fsm, start, end


def test_delete_final_state_removes_from_final_states():
    """final 상태 삭제 시 fsm.final_states에서도 제거된다."""
    pvm = ProjectViewModel()
    fsm, start, end = _make_fsm_with_final()
    end_vm = StateViewModel(model=end, x=0, y=0)
    pvm.state_vms.append(end_vm)

    cmd = DeleteStateCmd(pvm, end_vm, fsm=fsm)
    cmd.execute()

    assert end not in fsm.states
    assert end not in fsm.final_states


def test_delete_final_state_undo_restores_final_states():
    """final 상태 삭제 후 undo 시 fsm.final_states에 원복된다."""
    pvm = ProjectViewModel()
    fsm, start, end = _make_fsm_with_final()
    end_vm = StateViewModel(model=end, x=0, y=0)
    pvm.state_vms.append(end_vm)

    cmd = DeleteStateCmd(pvm, end_vm, fsm=fsm)
    cmd.execute()
    cmd.undo()

    assert end in fsm.states
    assert end in fsm.final_states


def test_delete_final_state_undo_restores_index():
    """final_states 내 원래 위치(인덱스)가 undo로 복원된다."""
    pvm = ProjectViewModel()
    start = SimpleState(name="start")
    end1 = SimpleState(name="end1")
    end2 = SimpleState(name="end2")
    fsm = StateMachine(
        name="fsm",
        states=[start, end1, end2],
        initial_state=start,
        final_states=[end1, end2],
    )
    end1_vm = StateViewModel(model=end1, x=0, y=0)
    pvm.state_vms.extend([end1_vm, StateViewModel(model=end2, x=0, y=0)])

    # end1(인덱스 0) 삭제 후 undo
    cmd = DeleteStateCmd(pvm, end1_vm, fsm=fsm)
    cmd.execute()
    assert fsm.final_states == [end2]
    cmd.undo()
    # 원래 인덱스 0에 복원
    assert fsm.final_states[0] is end1
    assert fsm.final_states[1] is end2


def test_delete_initial_state_undo_restores_initial():
    """initial_state 삭제 후 undo 시 initial_state가 원복된다."""
    pvm = ProjectViewModel()
    start = SimpleState(name="start")
    end = SimpleState(name="end")
    fsm = StateMachine(name="fsm", states=[start, end], initial_state=start, final_states=[end])
    start_vm = StateViewModel(model=start, x=0, y=0)
    pvm.state_vms.append(start_vm)

    cmd = DeleteStateCmd(pvm, start_vm, fsm=fsm)
    cmd.execute()
    # initial_state는 여전히 start를 가리키지만 states에서 제거됨 — dangling
    assert start not in fsm.states
    # undo로 원복
    cmd.undo()
    assert start in fsm.states
    assert fsm.initial_state is start


def test_delete_final_state_no_more_validator_error():
    """final 상태 삭제 후 Validator가 final_states_in_states 에러를 내지 않는다."""
    pvm = ProjectViewModel()
    fsm, start, end = _make_fsm_with_final()
    end_vm = StateViewModel(model=end, x=0, y=0)
    pvm.state_vms.append(end_vm)

    cmd = DeleteStateCmd(pvm, end_vm, fsm=fsm)
    cmd.execute()

    errors = Validator.validate(fsm)
    final_errors = [e for e in errors if e.rule == "final_states_in_states"]
    assert final_errors == [], f"예상치 못한 final_states_in_states 에러: {final_errors}"


def test_delete_non_final_state_no_effect_on_final_states():
    """final이 아닌 상태 삭제는 final_states에 영향을 주지 않는다."""
    pvm = ProjectViewModel()
    fsm, start, end = _make_fsm_with_final()
    mid = SimpleState(name="mid")
    fsm.states.append(mid)
    mid_vm = StateViewModel(model=mid, x=0, y=0)
    pvm.state_vms.append(mid_vm)

    cmd = DeleteStateCmd(pvm, mid_vm, fsm=fsm)
    cmd.execute()

    assert mid not in fsm.states
    assert end in fsm.final_states  # 영향 없음
