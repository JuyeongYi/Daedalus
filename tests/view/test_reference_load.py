# tests/view/test_reference_load.py
"""참조 배치(reference_placements) 로드 복원 — 선재 결함 회귀 잠금.

참조 노드는 씬 편집 시 라이브 sync로 저장만 되고 로드 복원 경로가 없어,
캔버스에서 사라진 뒤 참조 편집 시 sync_refs_to_model이 (빈 VM 기준으로)
로드된 배치를 통째로 소실시켰다.
"""
from __future__ import annotations

import json

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject, ReferencePlacement
from daedalus.model.serialize import serialize_project
from daedalus.view.app import MainWindow


def _make_project() -> PluginProject:
    s = SimpleState(name="s")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name="alpha", description="d")
    ref = ReferenceSkill(name="guide", description="참조 문서")
    project = PluginProject(name="p", skills=[skill, ref])
    project.graph.states.append(SimpleState(name="alpha", skill_ref=skill))
    project.reference_placements.append(ReferencePlacement(
        skill_name="guide", x=100.0, y=-50.0, connected_states=["alpha"],
    ))
    return project


def test_set_project_restores_reference_vms(qapp):
    w = MainWindow()
    w.set_project(_make_project())
    assert len(w._project_vm.reference_vms) == 1
    rvm = w._project_vm.reference_vms[0]
    assert rvm.model.name == "guide"
    assert (rvm.x, rvm.y) == (100.0, -50.0)
    assert len(w._project_vm.reference_links) == 1
    assert w._project_vm.reference_links[0].state_vm.model.name == "alpha"


def test_reference_placements_survive_open_save_round_trip(qapp, tmp_path):
    """열기 → 저장 왕복에서 참조 배치가 소실되지 않는다."""
    src = tmp_path / "p.daedalus.json"
    src.write_text(
        json.dumps(serialize_project(_make_project()), ensure_ascii=False),
        encoding="utf-8",
    )
    w = MainWindow()
    w.open_path(str(src))
    dst = tmp_path / "p2.daedalus.json"
    w._save_to_path(str(dst))
    data = json.loads(dst.read_text(encoding="utf-8"))
    refs = data.get("reference_placements", [])
    assert len(refs) == 1
    assert refs[0]["skill_name"] == "guide"
    assert refs[0]["connected_states"] == ["alpha"]


def test_dangling_reference_placement_skipped(qapp):
    """실존하지 않는 skill_name 배치는 조용히 스킵 (F7 dangling이 짚는다)."""
    project = _make_project()
    project.reference_placements.append(ReferencePlacement(
        skill_name="no-such", x=0.0, y=0.0, connected_states=[],
    ))
    w = MainWindow()
    w.set_project(project)
    assert len(w._project_vm.reference_vms) == 1
