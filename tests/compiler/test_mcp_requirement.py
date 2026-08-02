# tests/compiler/test_mcp_requirement.py
"""WP-TM Part C: 컴파일러 요구 환경 자동 언급 (allowed_tools/tools의 mcp__ 접두 파싱)."""
from __future__ import annotations

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.model.plugin.config import AgentConfig, ProceduralSkillConfig
from daedalus.model.plugin.enums import ModelType
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_procedural


def test_skill_with_mcp_tools_gets_requirement_section():
    skill = make_procedural(
        name="a",
        config=ProceduralSkillConfig(
            model=ModelType.SONNET,
            allowed_tools=["Read", "mcp__playwright__browser_click"],
        ),
    )
    text = compile_skill(skill)
    assert "## 요구 환경" in text
    assert "`playwright`" in text


def test_skill_without_mcp_tools_no_section():
    skill = make_procedural(
        name="a",
        config=ProceduralSkillConfig(model=ModelType.SONNET, allowed_tools=["Read", "Bash"]),
    )
    text = compile_skill(skill)
    assert "## 요구 환경" not in text


def test_skill_mcp_requirement_section_before_next_steps():
    a = make_procedural(
        name="a",
        config=ProceduralSkillConfig(
            model=ModelType.SONNET,
            allowed_tools=["mcp__github__create_issue"],
        ),
    )
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.transition import Transition

    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(a, project=project)
    assert "## 요구 환경" in text
    assert "## 다음 단계" in text
    assert text.index("## 요구 환경") < text.index("## 다음 단계")


def test_skill_multiple_servers_sorted_deterministically():
    skill = make_procedural(
        name="a",
        config=ProceduralSkillConfig(
            model=ModelType.SONNET,
            allowed_tools=[
                "mcp__zeta__do_thing",
                "mcp__alpha__other_thing",
                "mcp__alpha__yet_another",
            ],
        ),
    )
    text = compile_skill(skill)
    idx_alpha = text.index("`alpha`")
    idx_zeta = text.index("`zeta`")
    assert idx_alpha < idx_zeta


def test_skill_requirement_section_is_deterministic_across_calls():
    skill = make_procedural(
        name="a",
        config=ProceduralSkillConfig(
            model=ModelType.SONNET,
            allowed_tools=["mcp__b__x", "mcp__a__y"],
        ),
    )
    text1 = compile_skill(skill)
    text2 = compile_skill(skill)
    assert text1 == text2


def test_local_skill_still_gets_requirement_section():
    """로컬 스킬(에이전트 소유)도 자기 config 기반이므로 단락을 받는다."""
    skill = make_procedural(
        name="local-a",
        config=ProceduralSkillConfig(
            model=ModelType.SONNET,
            allowed_tools=["mcp__playwright__browser_click"],
        ),
    )
    text = compile_skill(skill, local=True)
    assert "## 요구 환경" in text


def test_agent_tools_mcp_prefix_merges_into_settings_note():
    agent = make_agent("worker")
    agent.config = AgentConfig(model=ModelType.SONNET, tools=["mcp__github__create_issue"])
    text = compile_agent(agent)
    assert text.count("## 요구 환경") == 1
    assert "github" in text


def test_agent_tools_and_declared_mcp_servers_deduped_and_sorted():
    agent = make_agent("worker")
    agent.config = AgentConfig(
        model=ModelType.SONNET,
        mcp_servers=["github"],
        tools=["mcp__github__create_issue", "mcp__agora__dispatch"],
    )
    text = compile_agent(agent)
    section = text.split("## 요구 환경", 1)[1]
    assert text.count("## 요구 환경") == 1
    # MCP 서버 연결 줄 안에서는 github이 중복 없이 한 번만 등장(mcp_servers
    # 선언 + tools 파싱 결과가 병합·중복 제거된다)
    mcp_line = next(line for line in section.splitlines() if "MCP 서버 연결" in line)
    assert mcp_line.count("github") == 1
    idx_agora = mcp_line.index("agora")
    idx_github = mcp_line.index("github")
    assert idx_agora < idx_github


def test_agent_without_mcp_tools_no_section():
    agent = make_agent("worker")
    agent.config = AgentConfig(model=ModelType.SONNET, tools=["Read", "Bash"])
    text = compile_agent(agent)
    assert "## 요구 환경" not in text
