# tests/compiler/test_integration.py
"""통합 — 대표 프로젝트(스킬 2 + 에이전트 1 + 위임 1 + tool 1) 컴파일."""
from __future__ import annotations

from daedalus.compiler import compile_project
from daedalus.compiler.emit import compile_skill
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.plugin.tool import BuiltinTool, UserDefinedTool
from daedalus.model.project import PluginProject

from tests.compiler.builders import (
    make_agent,
    make_declarative,
    make_procedural,
    make_team_spawn,
)


def _representative_project():
    teammate = make_agent("helper-agent")
    deleg = make_team_spawn("spawn-helpers", teammate)

    # 위임 노드를 가진 procedural 스킬
    node = SimpleState(name="spawn-helpers", skill_ref=deleg)
    end = SimpleState(name="finish")
    sm = StateMachine(
        name="main_fsm", initial_state=node, states=[node, end], final_states=[end]
    )
    sm.transitions.append(
        Transition(source=node, target=end, trigger=CompletionEvent(name="done"))
    )
    main_skill = ProceduralSkill(
        fsm=sm,
        name="main-skill",
        description="Main workflow",
        when_to_use="orchestrating helpers",
        config=ProceduralSkillConfig(),
        body="# Instructions\n\nCoordinate.",
        transfer_on=[EventDef("done")],
    )
    kb = make_declarative("domain-kb")

    tool = UserDefinedTool(name="my-tool", description="custom", body="echo hi")

    return PluginProject(
        name="demo",
        skills=[main_skill, kb],
        agents=[teammate],
        delegations=[deleg],
        tool_shelf=[tool],
    )


def test_integration_writes_expected_files(tmp_path):
    project = _representative_project()
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]

    assert (tmp_path / "skills" / "main-skill" / "SKILL.md").exists()
    assert (tmp_path / "skills" / "domain-kb" / "SKILL.md").exists()
    assert (tmp_path / "agents" / "helper-agent.md").exists()


def test_integration_core_content(tmp_path):
    project = _representative_project()
    compile_project(project, tmp_path)

    main = (tmp_path / "skills" / "main-skill" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: main-skill" in main
    assert "## 위임 지침" in main
    assert "helper-agent" in main
    # tool_shelf 참조 단락
    assert "## 참조: 도구 선반" in main
    assert "my-tool" in main
    assert "echo hi" in main

    agent_md = (tmp_path / "agents" / "helper-agent.md").read_text(encoding="utf-8")
    assert "name: helper-agent" in agent_md


def test_integration_lf_and_no_bom(tmp_path):
    project = _representative_project()
    compile_project(project, tmp_path)
    raw = (tmp_path / "skills" / "main-skill" / "SKILL.md").read_bytes()
    assert b"\r\n" not in raw  # CRLF 없음
    assert not raw.startswith(b"\xef\xbb\xbf")  # BOM 없음


def test_recompile_is_deterministic(tmp_path):
    project = _representative_project()
    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    compile_project(project, out1)
    compile_project(project, out2)

    for rel in ["skills/main-skill/SKILL.md", "agents/helper-agent.md", "skills/domain-kb/SKILL.md"]:
        t1 = (out1 / rel).read_text(encoding="utf-8")
        t2 = (out2 / rel).read_text(encoding="utf-8")
        assert t1 == t2, f"{rel} 비결정적"


def test_local_skill_dir_naming(tmp_path):
    agent = make_agent("a1")
    local = make_procedural(name="local-proc")
    agent.skills = [local]
    project = PluginProject(name="demo", agents=[agent])
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    # 로컬 스킬 규칙: <agent>--<skill> (충돌 무결 아님 — 충돌은 게이트의 사전 경로 검사가 거부)
    assert (tmp_path / "skills" / "a1--local-proc" / "SKILL.md").exists()
    text = (tmp_path / "skills" / "a1--local-proc" / "SKILL.md").read_text(encoding="utf-8")
    # local_procedural 매트릭스: context fixed fork
    assert "context: fork" in text
