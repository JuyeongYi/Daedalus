# daedalus/view/graph_io.py
"""프로젝트 그래프 ↔ 캔버스 VM 왕복 (WP-RF-3e 관례).

`MainWindow`의 협력 객체다(Mixin 아님). 담당은 두 방향뿐이다:

- `load_project_graph()` — `project.graph` + `graph_layout`/`edge_layout` →
  캔버스 VM(state_vms/transition_vms/reference_vms/reference_links) 재구성.
- `save_graph_layout()` — 캔버스 VM 좌표 → `project.graph_layout`/`edge_layout`.

상태(`_project`/`_project_vm`)의 단일 진실은 계속 윈도우이고, 이 객체는
그것을 복제하지 않고 `self._w.<attr>`로 직접 읽고 쓴다.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 타입 전용
    from daedalus.view.app import MainWindow


class GraphIO:
    """프로젝트 그래프 로드/레이아웃 저장을 담당하는 MainWindow 협력 객체."""

    def __init__(self, window: MainWindow) -> None:
        self._w = window

    def load_project_graph(self) -> None:
        """project.graph + graph_layout으로부터 캔버스 VM(state_vms/transition_vms)을
        재구성한다. 기존 VM은 비우고 새로 채운다 (중복 방지). notify로 캔버스 갱신.

        WP-EP: CC 플러그인에는 단일 진입점이 없다(user_invocable 스킬은 전부
        독립 시작 가능) — 합성 EntryPoint("start")는 모델(graph.initial_state)에는
        여전히 존재하지만 프로젝트 캔버스에는 **그리지 않는다**. EntryPoint에
        닿는 전이(구버전 파일의 시작 전이 포함)도 VM이 없으므로 자연히 스킵된다
        (경고 없음). 에이전트 캔버스는 이 WP의 영향을 받지 않는다.
        """
        from daedalus.model.fsm.pseudo import EntryPoint
        from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel

        w = self._w
        if w._project is None:
            return
        graph = w._project.graph

        # 기존 캔버스 VM 비우기 (set_project 재호출 시 중복 누적 방지)
        w._project_vm.state_vms.clear()
        w._project_vm.transition_vms.clear()

        placements = [s for s in graph.states if not isinstance(s, EntryPoint)]

        saved = w._project.graph_layout  # 키: state.id (안정 식별자)
        x = 0.0
        vm_map: dict[str, StateViewModel] = {}
        for state in placements:
            if state.id in saved:
                sx, sy = saved[state.id]
                vm = StateViewModel(model=state, x=sx, y=sy)
            else:
                vm = StateViewModel(model=state, x=x, y=100.0)
            w._project_vm.state_vms.append(vm)
            vm_map[state.id] = vm
            x += 220.0

        saved_edges = w._project.edge_layout  # 키: Transition.id (WP-ER)
        for trans in graph.transitions:
            # source/target이 EntryPoint면 vm_map에 없어 자연히 스킵된다.
            src_vm = vm_map.get(trans.source.id)
            tgt_vm = vm_map.get(trans.target.id)
            if src_vm and tgt_vm:
                waypoints = [(x, y) for x, y in saved_edges.get(trans.id, [])]
                tvm = TransitionViewModel(
                    model=trans, source_vm=src_vm, target_vm=tgt_vm,
                    waypoints=waypoints,
                )
                w._project_vm.transition_vms.append(tvm)

        # 참조 노드 복원 — 선재 결함 수정: 참조 배치는 저장(라이브 sync)만 되고
        # 로드 복원 경로가 없어 캔버스에서 사라졌고, 이후 참조 편집 시
        # sync_refs_to_model이 (빈 VM 기준으로) 로드분을 통째로 소실시켰다.
        from daedalus.view.viewmodel.state_vm import (
            ReferenceLinkViewModel,
            ReferenceViewModel,
        )
        w._project_vm.reference_vms.clear()
        w._project_vm.reference_links.clear()
        skills_by_name = {s.name: s for s in w._project.skills}
        vms_by_name = {svm.model.name: svm for svm in w._project_vm.state_vms}
        for rp in getattr(w._project, "reference_placements", None) or []:
            ref_skill = skills_by_name.get(rp.skill_name)
            if ref_skill is None:
                continue  # dangling_string_reference가 F7에서 짚는다
            rvm = ReferenceViewModel(model=ref_skill, x=rp.x, y=rp.y)
            w._project_vm.reference_vms.append(rvm)
            for state_name in rp.connected_states:
                svm = vms_by_name.get(state_name)
                if svm is not None:
                    w._project_vm.reference_links.append(
                        ReferenceLinkViewModel(state_vm=svm, reference_vm=rvm)
                    )
        w._project_vm.notify()

    def save_graph_layout(self) -> None:
        """캔버스 노드 위치를 project.graph_layout에 기록. 키는 state.id.

        WP-ER: 엣지 경유점(waypoint)도 함께 project.edge_layout에 기록한다.
        키는 Transition.id.
        """
        w = self._w
        if w._project is None:
            return
        layout: dict[str, list[float]] = {}
        for svm in w._project_vm.state_vms:
            layout[svm.model.id] = [svm.x, svm.y]
        w._project.graph_layout = layout

        edge_layout: dict[str, list[list[float]]] = {}
        for tvm in w._project_vm.transition_vms:
            if tvm.waypoints:
                edge_layout[tvm.model.id] = [list(pt) for pt in tvm.waypoints]
        w._project.edge_layout = edge_layout
