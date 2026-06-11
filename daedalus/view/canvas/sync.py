# daedalus/view/canvas/sync.py
"""뷰 모델 → 도메인 모델 동기화 로직.

씬(scene.py)에서 분리한 모델 동기화 묶음. 씬은 위임 호출만 하고,
실제 좌표/연결 정보의 모델 반영은 여기에 모은다. Qt 위젯에 의존하지
않으므로(ProjectViewModel + placements 리스트만 사용) 단위 테스트가 쉽다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daedalus.view.viewmodel.project_vm import ProjectViewModel


def sync_refs_to_model(project_vm: ProjectViewModel, placements: list) -> None:
    """참조 노드의 위치 + 연결 정보를 placements 리스트에 반영한다.

    placements를 비우고 현재 reference_vms / reference_links로 재구성한다.
    (project 또는 agent의 reference_placements 리스트를 그대로 받는다.)
    """
    from daedalus.model.project import ReferencePlacement

    placements.clear()
    for rvm in project_vm.reference_vms:
        skill_name = getattr(rvm.model, "name", "")
        connected = [
            link.state_vm.model.name
            for link in project_vm.reference_links
            if link.reference_vm is rvm
        ]
        placements.append(ReferencePlacement(
            skill_name=skill_name, x=rvm.x, y=rvm.y,
            connected_states=connected,
        ))
