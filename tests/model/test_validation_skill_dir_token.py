"""skill_dir_token_in_agent — 에이전트 본문의 ${CLAUDE_SKILL_DIR} 경고 (WP-SF).

이 변수는 스킬 전용이다(CC 공식 치환 표) — 에이전트는 단일 .md라 자기
디렉토리가 없어 치환되지 않는다.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import DeclarativeSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator

_TOKEN = "${CLAUDE_SKILL_DIR}"


def _agent(body: str) -> AgentDefinition:
    entry = EntryPoint(name="start")
    fsm = StateMachine(name="f", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name="worker", description="d", body=body,
        transfer_on=[EventDef(name="done")],
    )


def _rules(project) -> list[str]:
    return [
        e.rule for e in Validator.validate_project(project)
        if e.rule == "skill_dir_token_in_agent"
    ]


def test_token_in_agent_body_warns():
    project = PluginProject(name="p", agents=[_agent(f"파일: {_TOKEN}/data.md")])
    assert _rules(project) == ["skill_dir_token_in_agent"]


def test_token_in_code_is_not_flagged():
    """규격 설명 문서의 코드 표기 언급은 짚지 않는다 (plugin_root 규칙과 동일)."""
    body = f"변수 설명: `{_TOKEN}` 는 스킬 전용이다.\n\n```\n{_TOKEN}/x\n```"
    project = PluginProject(name="p", agents=[_agent(body)])
    assert _rules(project) == []


def test_token_in_skill_body_is_fine():
    """스킬 본문의 이 토큰은 정상 — 이 규칙의 대상이 아니다."""
    skill = DeclarativeSkill(name="kb", description="d", body=f"{_TOKEN}/ref.md")
    project = PluginProject(name="p", skills=[skill])
    assert _rules(project) == []


def test_warning_severity():
    project = PluginProject(name="p", agents=[_agent(f"{_TOKEN}/x")])
    findings = [
        e for e in Validator.validate_project(project)
        if e.rule == "skill_dir_token_in_agent"
    ]
    assert findings and all(e.is_warning for e in findings)
