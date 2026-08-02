# tests/compiler/test_agent.py
"""에이전트 .md 컴파일 — INVOCATION 안내, SETTINGS 언급, FSM 출구."""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent
from daedalus.model.plugin.config import AgentConfig
from daedalus.model.plugin.enums import AgentIsolation, ModelType

from tests.compiler.builders import make_agent


def test_agent_invocation_section_lists_non_default_invocation_fields():
    agent = make_agent()
    agent.config = AgentConfig(
        model=ModelType.SONNET,
        max_turns=10,
        background=True,
        isolation=AgentIsolation.WORKTREE,
    )
    text = compile_agent(agent)
    assert "## 호출 파라미터" in text
    assert "max-turns`: 10" in text
    assert "background`: True" in text
    assert "isolation`: worktree" in text


def test_agent_invocation_section_omitted_when_all_default():
    agent = make_agent()
    agent.config = AgentConfig(model=ModelType.SONNET)  # max_turns None, background False, isolation NONE
    text = compile_agent(agent)
    assert "## 호출 파라미터" not in text


def test_agent_settings_note_mentions_mcp_and_hooks():
    agent = make_agent()
    agent.config = AgentConfig(
        model=ModelType.SONNET,
        mcp_servers=["agora", "github"],
        hooks={"PreToolUse": []},
    )
    text = compile_agent(agent)
    assert "## 요구 환경" in text
    assert "agora" in text
    assert "github" in text
    assert "hooks.json" in text


def test_agent_settings_note_omitted_when_none():
    agent = make_agent()
    text = compile_agent(agent)
    assert "## 요구 환경" not in text


def test_agent_fsm_internal_workflow_and_exits():
    agent = make_agent()
    text = compile_agent(agent)
    assert "## 내부 워크플로" in text
    assert "**work**" in text
    assert "## 출구" in text
    assert "`done`" in text


def test_agent_sections_emitted():
    agent = make_agent()
    text = compile_agent(agent)
    assert "# instruction" in text
    assert "Do agent work." in text


def test_agent_fsm_shows_access_declarations():
    """WP-BB Part D-1: 에이전트 내부 워크플로 서술에도 접근 선언이 붙는다."""
    agent = make_agent()
    work = next(s for s in agent.fsm.states if s.name == "work")
    work.reads = ["TaskState"]
    work.writes = ["ReviewFindings.files"]
    text = compile_agent(agent)
    assert "(읽기: `TaskState` / 쓰기: `ReviewFindings.files`)" in text


def test_agent_fsm_no_access_declaration_no_suffix():
    agent = make_agent()
    text = compile_agent(agent)
    assert "읽기:" not in text
    assert "쓰기:" not in text
