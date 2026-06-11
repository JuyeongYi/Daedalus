"""봉합 2: AgentFsmScene transfer skill append 커맨드화 회귀 테스트."""
from unittest.mock import patch

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import TransferSkill
from daedalus.view.commands.transition_commands import AddSkillToListCmd
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


def _make_transfer_skill(name: str = "ts") -> TransferSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)
    return TransferSkill(fsm=fsm, name=name, description="")


class TestAddSkillToListCmd:
    def test_execute_adds_skill(self):
        skills: list = []
        skill = _make_transfer_skill("ts1")
        cmd = AddSkillToListCmd(skills, skill)
        cmd.execute()
        assert any(s is skill for s in skills)

    def test_undo_removes_by_identity(self):
        """값 동등성 같은 스킬이 여럿 있어도 identity 기준으로 정확히 1개만 제거."""
        skills: list = []
        skill_a = _make_transfer_skill("ts")
        skill_b = _make_transfer_skill("ts")  # 이름 같음 — 다른 인스턴스
        cmd = AddSkillToListCmd(skills, skill_a)
        cmd.execute()
        skills.append(skill_b)  # 수동으로 같은 이름 스킬 추가
        assert len(skills) == 2
        cmd.undo()
        # skill_a만 제거, skill_b는 잔류
        assert not any(s is skill_a for s in skills)
        assert any(s is skill_b for s in skills)

    def test_execute_idempotent(self):
        """같은 인스턴스를 두 번 execute해도 1개만 존재."""
        skills: list = []
        skill = _make_transfer_skill("ts")
        cmd = AddSkillToListCmd(skills, skill)
        cmd.execute()
        cmd.execute()
        assert sum(1 for s in skills if s is skill) == 1


def _make_agent_scene():
    from daedalus.view.canvas.scene import AgentFsmScene

    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    agent_fsm = StateMachine(
        name="agent_fsm",
        states=[entry, done],
        initial_state=entry,
        final_states=[done],
    )
    agent_skills: list = []
    vm = ProjectViewModel()
    scene = AgentFsmScene(vm, agent_fsm=agent_fsm, agent_skills=agent_skills)
    return vm, agent_fsm, agent_skills, scene


def test_agent_scene_create_transfer_skill_undo_no_orphan(qapp):
    """에이전트 씬에서 transfer skill 생성 → undo → _agent_skills에 잔류 없음."""
    vm, agent_fsm, agent_skills, scene = _make_agent_scene()

    entry, done = agent_fsm.states[0], agent_fsm.states[1]
    model = Transition(source=entry, target=done, trigger=CompletionEvent(name="done"))
    agent_fsm.transitions.append(model)
    evm = StateViewModel(model=entry, x=0, y=0)
    dvm = StateViewModel(model=done, x=100, y=0)
    vm.state_vms.extend([evm, dvm])
    tvm = TransitionViewModel(model=model, source_vm=evm, target_vm=dvm)
    vm.transition_vms.append(tvm)

    with patch(
        "daedalus.view.canvas.scene.QInputDialog.getText",
        return_value=("local_ts", True),
    ):
        scene._create_and_assign_transfer_skill(tvm)

    assert any(getattr(s, "name", None) == "local_ts" for s in agent_skills)
    assert tvm.model.skill_ref is not None

    vm.command_stack.undo()
    assert not any(
        getattr(s, "name", None) == "local_ts" for s in agent_skills
    ), "undo 후 _agent_skills에 고아 스킬이 잔류하면 안 된다"
    assert tvm.model.skill_ref is None
