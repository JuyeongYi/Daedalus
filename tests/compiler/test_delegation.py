# tests/compiler/test_delegation.py
"""위임 노드 컴파일 — 3종 × EXPLICIT/GUIDED + wait/forget."""
from __future__ import annotations

from daedalus.compiler.emit import compile_skill
from daedalus.model.plugin.delegation import CompositionMode, DispatchMode, WaitMode

from tests.compiler.builders import (
    make_agent,
    make_agora_dispatch,
    make_delegation_skill,
    make_dynamic_workflow,
    make_team_spawn,
)


def _compile_with(deleg):
    return compile_skill(make_delegation_skill(deleg), project=None)


# ─────────────────────── 공통 전제 ───────────────────────


def test_delegation_preamble_present():
    teammate = make_agent("rev")
    deleg = make_team_spawn("build-team", teammate)
    text = _compile_with(deleg)
    assert "## 위임 전제 조건" in text
    assert "TeamCreate" in text
    assert "Workflow" in text
    assert ".mcp.json" in text
    assert "X-Agora-Instance-Id" in text


# ─────────────────────── TeamSpawn ───────────────────────


def test_team_spawn_explicit_lists_teammates():
    teammate = make_agent("reviewer-agent")
    deleg = make_team_spawn("build-team", teammate, composition=CompositionMode.EXPLICIT)
    text = _compile_with(deleg)
    assert "TeamCreate로 팀을 만들고" in text
    assert "에이전트 'reviewer-agent' × 2" in text
    assert "reviewer" in text  # role_note


def test_team_spawn_guided_has_guidance_prompt_and_hint_label():
    teammate = make_agent("reviewer-agent")
    deleg = make_team_spawn(
        "build-team", teammate, composition=CompositionMode.GUIDED,
        guidance="prefer senior agents",
    )
    text = _compile_with(deleg)
    assert "스스로 판단해 팀을 구성" in text
    assert "출발점(힌트)" in text
    assert "보충 지침: prefer senior agents" in text


def test_team_spawn_wait_vs_forget():
    teammate = make_agent("rev")
    wait = make_team_spawn("t1", teammate, wait_mode=WaitMode.WAIT)
    forget = make_team_spawn("t2", teammate, wait_mode=WaitMode.FIRE_AND_FORGET)
    assert "완료를 기다려" in _compile_with(wait)
    assert "즉시 다음 단계로" in _compile_with(forget)


# ─────────────────────── DynamicWorkflow ───────────────────────


def test_dynamic_workflow_explicit_objective_and_phases():
    deleg = make_dynamic_workflow("wf", composition=CompositionMode.EXPLICIT)
    text = _compile_with(deleg)
    assert "Workflow 도구로" in text
    assert "ship the feature" in text
    assert "design" in text


def test_dynamic_workflow_explicit_phase_agent_type():
    agent = make_agent("designer")
    deleg = make_dynamic_workflow("wf", phase_agent=agent)
    text = _compile_with(deleg)
    assert "designer" in text
    assert "agentType" in text


def test_dynamic_workflow_guided():
    deleg = make_dynamic_workflow(
        "wf", composition=CompositionMode.GUIDED, guidance="keep it small",
    )
    text = _compile_with(deleg)
    assert "스스로 설계해" in text
    assert "힌트" in text
    assert "보충 지침: keep it small" in text


# ─────────────────────── AgoraDispatch ───────────────────────


def test_agora_dispatch_explicit():
    deleg = make_agora_dispatch("send", mode=DispatchMode.DISPATCH)
    text = _compile_with(deleg)
    assert "agora.dispatch" in text
    assert "task.assign" in text
    assert "inst-1" in text
    assert "include the spec" in text  # payload_note


def test_agora_broadcast():
    deleg = make_agora_dispatch("send", mode=DispatchMode.BROADCAST)
    text = _compile_with(deleg)
    assert "agora.broadcast" in text
    assert "전원" in text


def test_agora_guided_keeps_msgtype_target():
    deleg = make_agora_dispatch("send", composition=CompositionMode.GUIDED)
    text = _compile_with(deleg)
    # GUIDED여도 msgtype/target은 명시
    assert "task.assign" in text
    assert "본문 맥락에서 구성" in text


def test_agora_wait_uses_flush():
    deleg = make_agora_dispatch("send", wait_mode=WaitMode.WAIT)
    text = _compile_with(deleg)
    assert "agora.flush" in text
