"""참조 노드 액션 — 링크 조회 / 후보 산출 (A9-6, A9-7) 공유 함수."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.view.actions.references import (
    linkable_state_vms,
    linked_state_vms,
    reference_vms_for,
)
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
)


def _proc(name: str) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


@pytest.fixture
def vm():
    project_vm = ProjectViewModel()
    for name in ("a", "b", "c"):
        skill = _proc(name)
        project_vm.state_vms.append(
            StateViewModel(model=SimpleState(name=name, skill_ref=skill))
        )
    return project_vm


@pytest.fixture
def ref(vm):
    doc = ReferenceSkill(name="doc", description="d")
    rvm = ReferenceViewModel(model=doc)
    vm.reference_vms.append(rvm)
    return rvm


def _link(vm, ref_vm, name: str):
    state_vm = next(s for s in vm.state_vms if s.model.name == name)
    vm.reference_links.append(
        ReferenceLinkViewModel(state_vm=state_vm, reference_vm=ref_vm)
    )
    return state_vm


def test_linked_is_empty_without_links(vm, ref):
    assert linked_state_vms(vm, ref) == []


def test_linked_lists_only_this_reference(vm, ref):
    other = ReferenceViewModel(model=ReferenceSkill(name="other", description="d"))
    vm.reference_vms.append(other)
    _link(vm, ref, "a")
    _link(vm, other, "b")

    assert [s.model.name for s in linked_state_vms(vm, ref)] == ["a"]


def test_linkable_excludes_already_linked(vm, ref):
    """이미 연결된 것을 후보로 내면 고르는 순간 아무 일도 일어나지 않는다."""
    _link(vm, ref, "a")
    assert [s.model.name for s in linkable_state_vms(vm, ref)] == ["b", "c"]


def test_linkable_excludes_links_through_other_instances(vm, ref):
    """같은 스킬이 두 번 놓였고 다른 인스턴스에 이미 걸렸으면 후보가 아니다.

    캔버스 드래그의 중복 방지(`create_reference_link`)가 **스킬 기준**으로
    판정하므로 후보 산출도 같아야 한다.
    """
    twin = ReferenceViewModel(model=ref.model)
    vm.reference_vms.append(twin)
    _link(vm, twin, "a")
    assert [s.model.name for s in linkable_state_vms(vm, ref)] == ["b", "c"]


def test_linkable_all_when_nothing_linked(vm, ref):
    assert len(linkable_state_vms(vm, ref)) == 3


def test_reference_vms_for_finds_every_instance(vm, ref):
    twin = ReferenceViewModel(model=ref.model)
    vm.reference_vms.append(twin)
    other = ReferenceViewModel(model=ReferenceSkill(name="other", description="d"))
    vm.reference_vms.append(other)

    found = reference_vms_for(vm, ref.model)
    assert len(found) == 2
    assert all(r.model is ref.model for r in found)


def test_reference_vms_for_unplaced_skill(vm):
    assert reference_vms_for(vm, ReferenceSkill(name="nope", description="d")) == []
