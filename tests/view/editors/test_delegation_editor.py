"""DelegationEditor 폼 생성 + 필드 왕복 + GUIDED 토글 테스트."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.delegation import (
    AgoraDispatchDef,
    CompositionMode,
    DispatchMode,
    DynamicWorkflowDef,
    PhaseSpec,
    TeamSpawnDef,
    TeammateSpec,
    WaitMode,
)
from daedalus.model.project import PluginProject
from daedalus.view.editors.delegation_editor import (
    DelegationEditor,
    _CommonHeader,
    _TeamSpawnBody,
    _DynamicWorkflowBody,
    _AgoraDispatchBody,
)


def _make_project() -> PluginProject:
    entry = EntryPoint(name="e")
    done = ExitPoint(name="done")
    fsm = StateMachine(name="f", states=[entry, done], initial_state=entry, final_states=[done])
    agent = AgentDefinition(fsm=fsm, name="worker", description="")
    return PluginProject(name="p", agents=[agent])


# ─────────────────────── CommonHeader ───────────────────────

def test_common_header_creates_ok(qapp):
    d = TeamSpawnDef(name="t", description="")
    header = _CommonHeader(d)
    assert header is not None


def test_common_header_wait_mode_writeback(qapp):
    """콤보 변경 시 모델에 즉시 기록된다."""
    d = TeamSpawnDef(name="t", description="")
    header = _CommonHeader(d)
    # FIRE_AND_FORGET로 변경
    header._wait_combo.setCurrentIndex(1)
    assert d.wait_mode is WaitMode.FIRE_AND_FORGET


def test_common_header_composition_writeback(qapp):
    """composition 콤보 변경 시 모델에 기록된다."""
    d = DynamicWorkflowDef(name="w", description="")
    header = _CommonHeader(d)
    header._comp_combo.setCurrentIndex(1)  # GUIDED
    assert d.composition is CompositionMode.GUIDED


def test_common_header_guided_enables_guidance(qapp):
    """GUIDED 선택 시 guidance 텍스트 위젯이 활성화된다."""
    d = TeamSpawnDef(name="t", description="")
    header = _CommonHeader(d)
    # 초기 상태: EXPLICIT → guidance 비활성
    header._comp_combo.setCurrentIndex(0)  # EXPLICIT
    assert not header._guidance_edit.isEnabled()
    # GUIDED → 활성
    header._comp_combo.setCurrentIndex(1)  # GUIDED
    assert header._guidance_edit.isEnabled()


def test_common_header_guidance_writeback(qapp):
    """guidance 텍스트 입력 시 모델에 기록된다."""
    d = TeamSpawnDef(name="t", description="", composition=CompositionMode.GUIDED)
    header = _CommonHeader(d)
    header._guidance_edit.setPlainText("힌트 텍스트")
    assert d.guidance == "힌트 텍스트"


# ─────────────────────── TeamSpawnBody ───────────────────────

def test_team_spawn_body_creates_ok(qapp):
    d = TeamSpawnDef(name="t", description="")
    project = _make_project()
    body = _TeamSpawnBody(d, project, lambda: None)
    assert body is not None


def test_team_spawn_body_add_teammate(qapp):
    """팀원 추가 버튼 → teammates에 스펙 추가."""
    d = TeamSpawnDef(name="t", description="")
    project = _make_project()
    body = _TeamSpawnBody(d, project, lambda: None)
    body._add_teammate()
    assert len(d.teammates) == 1


def test_team_spawn_body_count_writeback(qapp):
    """count 스핀 변경 → spec.count 기록."""
    agent = _make_project().agents[0]
    spec = TeammateSpec(agent_ref=agent, count=1)
    d = TeamSpawnDef(name="t", description="", teammates=[spec])
    project = _make_project()
    project.agents = [agent]
    body = _TeamSpawnBody(d, project, lambda: None)
    body._rows[0]._count_spin.setValue(5)
    assert d.teammates[0].count == 5


def test_team_spawn_body_composition_label_changes(qapp):
    """on_composition_changed(True) 시 라벨이 '힌트' 문구로 바뀐다."""
    d = TeamSpawnDef(name="t", description="")
    body = _TeamSpawnBody(d, None, lambda: None)
    body.on_composition_changed(True)
    assert "힌트" in body._label.text()
    body.on_composition_changed(False)
    assert "힌트" not in body._label.text()


# ─────────────────────── DynamicWorkflowBody ───────────────────────

def test_dynamic_workflow_body_objective_writeback(qapp):
    """objective 텍스트 변경 → 모델 기록."""
    d = DynamicWorkflowDef(name="w", description="")
    body = _DynamicWorkflowBody(d, None, lambda: None)
    body._objective_edit.setPlainText("저장소 감사")
    assert d.objective == "저장소 감사"


def test_dynamic_workflow_body_add_phase(qapp):
    """단계 추가 → phases에 스펙 추가."""
    d = DynamicWorkflowDef(name="w", description="")
    body = _DynamicWorkflowBody(d, None, lambda: None)
    body._add_phase()
    assert len(d.phases) == 1


def test_dynamic_workflow_body_composition_label_changes(qapp):
    """on_composition_changed(True) 시 라벨이 '힌트' 문구로 바뀐다."""
    d = DynamicWorkflowDef(name="w", description="")
    body = _DynamicWorkflowBody(d, None, lambda: None)
    body.on_composition_changed(True)
    assert "힌트" in body._objective_label.text() or "힌트" in body._phases_label.text()


# ─────────────────────── AgoraDispatchBody ───────────────────────

def test_agora_dispatch_body_msgtype_writeback(qapp):
    """msgtype 라인에딧 변경 → 모델 기록."""
    d = AgoraDispatchDef(name="a", description="")
    body = _AgoraDispatchBody(d, None, lambda: None)
    body._msgtype_edit.setText("task_request")
    assert d.msgtype == "task_request"


def test_agora_dispatch_body_mode_writeback(qapp):
    """mode 콤보 변경 → 모델 기록."""
    d = AgoraDispatchDef(name="a", description="")
    body = _AgoraDispatchBody(d, None, lambda: None)
    body._mode_combo.setCurrentIndex(1)  # broadcast
    assert d.mode is DispatchMode.BROADCAST


def test_agora_dispatch_body_target_writeback(qapp):
    """target 라인에딧 변경 → 모델 기록."""
    d = AgoraDispatchDef(name="a", description="")
    body = _AgoraDispatchBody(d, None, lambda: None)
    body._target_edit.setText("my-instance")
    assert d.target == "my-instance"


# ─────────────────────── DelegationEditor (통합) ───────────────────────

def test_delegation_editor_team_spawn_creates(qapp):
    """TeamSpawnDef → DelegationEditor 생성."""
    d = TeamSpawnDef(name="t", description="")
    editor = DelegationEditor(d, project=_make_project())
    assert editor is not None


def test_delegation_editor_dynamic_workflow_creates(qapp):
    d = DynamicWorkflowDef(name="w", description="")
    editor = DelegationEditor(d, project=_make_project())
    assert editor is not None


def test_delegation_editor_agora_dispatch_creates(qapp):
    d = AgoraDispatchDef(name="a", description="")
    editor = DelegationEditor(d, project=_make_project())
    assert editor is not None


def test_delegation_editor_notify_called(qapp):
    """모델 변경 시 on_notify_fn이 호출된다."""
    calls = []
    d = TeamSpawnDef(name="t", description="")
    editor = DelegationEditor(d, on_notify_fn=lambda: calls.append(1))
    editor._header._wait_combo.setCurrentIndex(1)  # 변경
    assert len(calls) >= 1


def test_delegation_editor_guided_toggle_updates_body(qapp):
    """GUIDED 토글 시 body 라벨이 갱신된다."""
    d = TeamSpawnDef(name="t", description="")
    editor = DelegationEditor(d, project=_make_project())
    body = editor._body
    assert body is not None
    # GUIDED로 전환
    editor._header._comp_combo.setCurrentIndex(1)
    assert "힌트" in body._label.text()
    # EXPLICIT으로 복귀
    editor._header._comp_combo.setCurrentIndex(0)
    assert "힌트" not in body._label.text()
