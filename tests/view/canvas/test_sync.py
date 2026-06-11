"""canvas/sync.sync_refs_to_model — Qt 무관 모델 동기화 단위 테스트."""
from __future__ import annotations

from daedalus.model.plugin.skill import ReferenceSkill
from daedalus.model.fsm.state import SimpleState
from daedalus.view.canvas.sync import sync_refs_to_model
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import (
    ReferenceLinkViewModel,
    ReferenceViewModel,
    StateViewModel,
)


def test_sync_empty_clears_placements():
    pvm = ProjectViewModel()
    placements = ["stale"]
    sync_refs_to_model(pvm, placements)
    assert placements == []


def test_sync_records_position_and_connections():
    pvm = ProjectViewModel()
    ref = ReferenceSkill(name="DocRef", description="")
    rvm = ReferenceViewModel(model=ref, x=12.0, y=34.0)
    pvm.reference_vms.append(rvm)

    state = SimpleState(name="UsesDoc")
    svm = StateViewModel(model=state, x=0, y=0)
    pvm.state_vms.append(svm)
    pvm.reference_links.append(
        ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
    )

    placements: list = []
    sync_refs_to_model(pvm, placements)

    assert len(placements) == 1
    p = placements[0]
    assert p.skill_name == "DocRef"
    assert (p.x, p.y) == (12.0, 34.0)
    assert p.connected_states == ["UsesDoc"]


def test_sync_unconnected_ref_has_empty_connections():
    pvm = ProjectViewModel()
    ref = ReferenceSkill(name="Lonely", description="")
    pvm.reference_vms.append(ReferenceViewModel(model=ref, x=1, y=2))

    placements: list = []
    sync_refs_to_model(pvm, placements)

    assert len(placements) == 1
    assert placements[0].connected_states == []


def test_sync_replaces_existing_placements():
    """동기화는 기존 placements를 비우고 재구성한다 (스테일 누적 방지)."""
    pvm = ProjectViewModel()
    ref = ReferenceSkill(name="R", description="")
    pvm.reference_vms.append(ReferenceViewModel(model=ref, x=0, y=0))

    placements: list = []
    sync_refs_to_model(pvm, placements)
    sync_refs_to_model(pvm, placements)  # 두 번째 호출

    assert len(placements) == 1, "재호출 시 중복 누적되면 안 된다"
