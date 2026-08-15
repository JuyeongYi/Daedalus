# tests/model/test_validation_build_target.py
"""WP-TG Part D: 빌드 타깃 인지 검증 규칙 2종."""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import DeclarativeSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator


def _mcp_agent(name: str = "worker", *, via_tools: bool = True, via_servers: bool = False):
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name=f"{name}_fsm", initial_state=entry, states=[entry, done], final_states=[done],
    )
    config = AgentConfig(
        tools=["mcp__playwright__browser_click"] if via_tools else [],
        mcp_servers=["playwright"] if via_servers else None,
    )
    return AgentDefinition(fsm=fsm, name=name, description="", config=config)


# ─────────────────────── mcp_agent_in_marketplace_build ───────────────────────


def test_mcp_agent_warns_in_marketplace_build_via_tools():
    project = PluginProject(
        name="p", agents=[_mcp_agent(via_tools=True)], build_target=BuildTarget.MARKETPLACE,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "mcp_agent_in_marketplace_build"]
    assert named
    assert all(f.is_warning for f in named)


def test_mcp_agent_warns_in_marketplace_build_via_mcp_servers():
    project = PluginProject(
        name="p",
        agents=[_mcp_agent(via_tools=False, via_servers=True)],
        build_target=BuildTarget.MARKETPLACE,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "mcp_agent_in_marketplace_build"]
    assert named


def test_mcp_agent_no_warning_in_local_build():
    """LOCAL 빌드면 에이전트가 MCP를 써도 경고 없음."""
    project = PluginProject(
        name="p", agents=[_mcp_agent(via_tools=True)], build_target=BuildTarget.LOCAL,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "mcp_agent_in_marketplace_build"]
    assert named == []


def test_non_mcp_agent_no_warning_in_marketplace_build():
    """MCP를 쓰지 않는 에이전트는 마켓플레이스 빌드에서도 경고 없음."""
    project = PluginProject(
        name="p",
        agents=[_mcp_agent(via_tools=False, via_servers=False)],
        build_target=BuildTarget.MARKETPLACE,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "mcp_agent_in_marketplace_build"]
    assert named == []


# ─────────────────────── plugin_root_in_local_build ───────────────────────


def _skill_with_body(body: str) -> DeclarativeSkill:
    return DeclarativeSkill(name="doc-skill", description="d", body=body)


def test_plugin_root_non_files_usage_warns_in_local_build():
    body = "설정 스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
    project = PluginProject(
        name="p", skills=[_skill_with_body(body)], build_target=BuildTarget.LOCAL,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "plugin_root_in_local_build"]
    assert named
    assert all(f.is_warning for f in named)


def test_neutral_root_token_no_warning_in_local_build():
    """타깃 중립 ${ROOT}는 어느 빌드에서도 정상이다 (WP-RT)."""
    body = "참조: ${ROOT}/files/doc.txt"
    project = PluginProject(
        name="p", skills=[_skill_with_body(body)], build_target=BuildTarget.LOCAL,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "plugin_root_in_local_build"]
    assert named == []


def test_plugin_root_non_files_usage_no_warning_in_marketplace_build():
    """MARKETPLACE 빌드에서는 이 규칙 자체가 발화하지 않는다(경로가 유효하므로)."""
    body = "설정 스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
    project = PluginProject(
        name="p", skills=[_skill_with_body(body)], build_target=BuildTarget.MARKETPLACE,
    )
    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "plugin_root_in_local_build"]
    assert named == []


def test_plugin_root_checks_agent_and_local_skill_bodies():
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="worker_fsm", initial_state=entry, states=[entry, done], final_states=[done],
    )
    agent = AgentDefinition(
        fsm=fsm, name="worker", description="",
        body="에이전트 스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/agent-setup.sh",
    )
    local_skill = _skill_with_body(
        "로컬 스크립트: ${CLAUDE_PLUGIN_ROOT}/scripts/local-setup.sh"
    )
    local_skill.name = "local-helper"
    agent.skills = [local_skill]
    project = PluginProject(name="p", agents=[agent], build_target=BuildTarget.LOCAL)

    findings = Validator.validate_project(project)
    named = [f for f in findings if f.rule == "plugin_root_in_local_build"]
    labels = {f.source for f in named}
    assert labels == {
        "에이전트 'worker'",
        "에이전트 'worker'의 로컬 스킬 'local-helper'",
    }


def test_retired_contract_cards_not_scanned():
    """WP-CT — 계약 카드는 산출에 반영되지 않으므로 더 이상 검사하지 않는다.
    카드 속 죽은 경로가 경고를 내면 고칠 수 없는 경고가 영구히 남는다."""
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.section import Section
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.enums import BuildTarget
    from daedalus.model.project import PluginProject
    from daedalus.model.validation import Validator

    s = SimpleState(name="a")
    agent = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=s, states=[s], final_states=[s]),
        name="worker", description="d", body="본문\n",
    )
    agent.caller_contracts.append(
        Section(title="caller: x", content="스크립트: ${CLAUDE_PLUGIN_ROOT}/bin/run.sh")
    )
    project = PluginProject(name="p", agents=[agent], build_target=BuildTarget.LOCAL)
    errors = Validator.validate_project(project)
    assert not any(e.rule == "plugin_root_in_local_build" for e in errors)


