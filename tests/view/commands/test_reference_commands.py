"""봉합 1: 참조 노드/링크 커맨드 회귀 테스트."""
from unittest.mock import MagicMock

from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ReferenceSkill
from daedalus.model.project import PluginProject
from daedalus.view.commands.reference_commands import (
    CreateRefCmd,
    CreateRefLinkCmd,
    DeleteRefCmd,
    DeleteRefLinkCmd,
    MoveRefCmd,
)
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
)


def _make_pvm_with_project() -> tuple[ProjectViewModel, PluginProject]:
    pvm = ProjectViewModel()
    project = PluginProject(name="p")
    return pvm, project


def _make_ref_skill(name: str = "ref_skill") -> ReferenceSkill:
    return ReferenceSkill(name=name, description="")


class TestCreateRefCmd:
    def test_execute_adds_to_pvm(self):
        pvm, project = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=10.0, y=20.0)
        sync = MagicMock()
        cmd = CreateRefCmd(pvm, rvm, project.reference_placements, sync_fn=sync)
        cmd.execute()
        assert rvm in pvm.reference_vms
        sync.assert_called()

    def test_undo_removes_from_pvm(self):
        pvm, project = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=10.0, y=20.0)
        sync = MagicMock()
        cmd = CreateRefCmd(pvm, rvm, project.reference_placements, sync_fn=sync)
        cmd.execute()
        cmd.undo()
        assert rvm not in pvm.reference_vms

    def test_description_contains_skill_name(self):
        pvm, project = _make_pvm_with_project()
        skill = _make_ref_skill("my_ref")
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        cmd = CreateRefCmd(pvm, rvm, project.reference_placements, sync_fn=lambda: None)
        assert "my_ref" in cmd.description


class TestDeleteRefCmd:
    def test_execute_removes_ref_and_links(self):
        pvm, project = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        pvm.reference_vms.append(rvm)
        pvm.reference_links.append(lvm)
        sync = MagicMock()
        cmd = DeleteRefCmd(pvm, rvm, sync_fn=sync)
        cmd.execute()
        assert rvm not in pvm.reference_vms
        assert lvm not in pvm.reference_links
        sync.assert_called()

    def test_undo_restores_ref_and_links(self):
        pvm, project = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        pvm.reference_vms.append(rvm)
        pvm.reference_links.append(lvm)
        sync = MagicMock()
        cmd = DeleteRefCmd(pvm, rvm, sync_fn=sync)
        cmd.execute()
        cmd.undo()
        assert rvm in pvm.reference_vms
        assert lvm in pvm.reference_links


class TestMoveRefCmd:
    def test_execute_updates_position(self):
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        sync = MagicMock()
        cmd = MoveRefCmd(rvm, old_x=0.0, old_y=0.0, new_x=50.0, new_y=70.0, sync_fn=sync)
        cmd.execute()
        assert rvm.x == 50.0
        assert rvm.y == 70.0
        sync.assert_called()

    def test_undo_restores_position_and_calls_sync(self):
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        sync = MagicMock()
        cmd = MoveRefCmd(rvm, old_x=0.0, old_y=0.0, new_x=50.0, new_y=70.0, sync_fn=sync)
        cmd.execute()
        sync.reset_mock()
        cmd.undo()
        assert rvm.x == 0.0
        assert rvm.y == 0.0
        sync.assert_called()

    def test_description_contains_model_name(self):
        skill = _make_ref_skill("r_skill")
        rvm = ReferenceViewModel(model=skill, x=0.0, y=0.0)
        cmd = MoveRefCmd(rvm, 0, 0, 1, 1, sync_fn=lambda: None)
        assert "r_skill" in cmd.description


class TestCreateRefLinkCmd:
    def test_execute_adds_link(self):
        pvm, _ = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        sync = MagicMock()
        cmd = CreateRefLinkCmd(pvm, lvm, sync_fn=sync)
        cmd.execute()
        assert lvm in pvm.reference_links
        sync.assert_called()

    def test_undo_removes_link(self):
        pvm, _ = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        sync = MagicMock()
        cmd = CreateRefLinkCmd(pvm, lvm, sync_fn=sync)
        cmd.execute()
        cmd.undo()
        assert lvm not in pvm.reference_links


class TestDeleteRefLinkCmd:
    def test_execute_removes_link(self):
        pvm, _ = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        pvm.reference_links.append(lvm)
        sync = MagicMock()
        cmd = DeleteRefLinkCmd(pvm, lvm, sync_fn=sync)
        cmd.execute()
        assert lvm not in pvm.reference_links
        sync.assert_called()

    def test_undo_restores_link(self):
        pvm, _ = _make_pvm_with_project()
        skill = _make_ref_skill()
        rvm = ReferenceViewModel(model=skill)
        svm = StateViewModel(model=SimpleState(name="s"))
        lvm = ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
        pvm.reference_links.append(lvm)
        sync = MagicMock()
        cmd = DeleteRefLinkCmd(pvm, lvm, sync_fn=sync)
        cmd.execute()
        cmd.undo()
        assert lvm in pvm.reference_links
