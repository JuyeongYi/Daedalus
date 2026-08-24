# daedalus/view/actions/references.py
"""참조 노드 액션 — 링크된 노드 조회 / 링크 추가 (A9-6, A9-7).

참조 노드는 상태가 아니라 **여러 상태가 공유하는 문서**라 링크가 4~5개만 돼도
캔버스에서 어디에 연결됐는지 눈으로 따라가기 어렵다. 그 조회와 추가를 UI 무관
함수로 모은다 — 캔버스 우클릭과 참조 스킬 에디터가 같은 것을 쓴다.
"""
from __future__ import annotations


def linked_state_vms(project_vm, ref_vm) -> list:
    """이 참조 노드에 연결된 상태 뷰모델 목록 (캔버스 순서 그대로)."""
    return [
        link.state_vm
        for link in project_vm.reference_links
        if link.reference_vm is ref_vm
    ]


def linkable_state_vms(project_vm, ref_vm) -> list:
    """아직 연결되지 않은 배치 노드 목록 — "링크 추가" 후보.

    **같은 스킬이 이미 걸린 상태는 뺀다**(캔버스 드래그의 중복 방지 규칙과 동일:
    `FsmScene.create_reference_link`가 같은 판정을 쓴다). 이미 연결된 것을
    후보로 내면 고르는 순간 아무 일도 일어나지 않는다.
    """
    ref_skill = ref_vm.model
    linked = {
        id(link.state_vm)
        for link in project_vm.reference_links
        if link.reference_vm.model is ref_skill
    }
    return [vm for vm in project_vm.state_vms if id(vm) not in linked]


def reference_vms_for(project_vm, skill: object) -> list:
    """이 참조 스킬이 캔버스에 놓인 인스턴스 전부.

    같은 스킬을 여러 번 놓을 수 있으므로 목록이다(그래서 MCP도 `index`로
    지목한다) — 에디터에서 "링크 추가"를 할 때 어느 인스턴스인지 정해야 한다.
    """
    return [vm for vm in project_vm.reference_vms if vm.model is skill]


def add_reference_link(scene, ref_vm, state_vm) -> None:
    """링크를 만든다 — **드래그와 같은 커맨드 경로**(`create_reference_link`).

    씬을 받는 유일한 액션이다: 참조 링크는 뷰모델 갱신 뒤 모델
    `reference_placements`를 다시 만드는 sync가 따라붙어야 하고, 그 sync 함수는
    씬이 쥐고 있다. 여기서 커맨드를 직접 만들면 그 배선을 복제하게 된다.
    """
    scene.create_reference_link(state_vm, ref_vm)
