"""블랙보드 도구 권한 유도와 `.mcp.json` 배선 (WP-BM 단계 2).

노드의 reads/writes 선언이 **프론트매터 권한**으로 번역되는 것이 이 WP의 이점의
실체다 — 캔버스의 📖/✏ 뱃지와 산출 권한이 같은 사실을 말한다(원칙 1). 여기서
고정하는 것:

1. 선언 → 도구의 대응(읽기만 / 쓰기 / 진행 기록)과 **좁게 주기**.
2. 표면별 합류 규칙 — 스킬 `allowed-tools`는 권한 부여라 합치고, 에이전트
   `tools`는 제한 목록이라 **목록이 있을 때만** 합친다.
3. fork의 비대칭 — fork 스킬 파일은 도구를 부여하지 못하므로 그 fork 에이전트가
   대신 진다. 외부 fork 에이전트는 파일이 없어 못 지고, 그 자리를 경고가 말한다.
4. 빌드 타깃이 도구 이름과 `.mcp.json` 자리를 가른다(실측 2026-09-20).
"""
from __future__ import annotations

import json

import pytest

from daedalus.compiler.emit import compile_agent, compile_skill
from daedalus.compiler.emit.blackboard_tools import (
    bb_schemas_arg,
    bb_server_entry,
    bb_server_name,
    bb_server_needed,
    bb_tool,
    bb_tool_prefix,
    bb_tools_for,
)
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition, ExternalForkAgent, ForkAgent
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.skill import (
    ProceduralSkill,
    SyncForkSkill,
    TransferSkill,
)
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator

PLUGIN = "p"
_M = "mcp__plugin_p_bb-p__"  # MARKETPLACE 도구 접두 (실측 — 플러그인 네임스페이스)
_L = "mcp__bb-p__"           # LOCAL 도구 접두 (작업 폴더 .mcp.json)


def _fsm(name: str = "m") -> StateMachine:
    entry = EntryPoint(name="start")
    return StateMachine(name=name, initial_state=entry, states=[entry])


def _blackboard() -> Blackboard:
    return Blackboard(class_definitions=[
        DynamicClass(
            name="TaskState",
            description="progress",
            fields=[DynamicField(name="step", field_type=FieldType.STRING)],
        ),
    ])


def _project(*, blackboard: bool = True, target=BuildTarget.MARKETPLACE) -> PluginProject:
    project = PluginProject(name=PLUGIN, description="demo")
    project.build_target = target
    if blackboard:
        project.blackboard = _blackboard()
    return project


def _skill(name: str) -> ProceduralSkill:
    skill = ProceduralSkill(
        fsm=_fsm(name), name=name, description=f"{name} step.", body="Do it."
    )
    skill.transfer_on = [EventDef(name="done")]
    return skill


def _place(project, skill, *, reads=(), writes=(), with_next=True) -> SimpleState:
    """스킬을 그래프에 놓고 접근을 선언한다. `with_next`면 나가는 전이도 만든다."""
    node = SimpleState(
        name=skill.name, skill_ref=skill, reads=list(reads), writes=list(writes)
    )
    project.skills.append(skill)
    project.graph.states.append(node)
    if with_next:
        tail = _skill(f"{skill.name}-next")
        project.skills.append(tail)
        tail_node = SimpleState(name=tail.name, skill_ref=tail)
        project.graph.states.append(tail_node)
        project.graph.transitions.append(Transition(
            source=node, target=tail_node, trigger=EventDef(name="done"),
        ))
    return node


# ─────────────────────────── 이름·배선 값 ───────────────────────────


def test_server_name_is_bb_plus_plugin():
    assert bb_server_name(_project()) == "bb-p"


@pytest.mark.parametrize(
    "target,prefix", [(BuildTarget.MARKETPLACE, _M), (BuildTarget.LOCAL, _L)]
)
def test_tool_prefix_follows_the_build_target(target, prefix):
    """플러그인이 제공한 서버는 CC가 네임스페이스를 붙인다 (실측 2026-09-20)."""
    project = _project(target=target)
    assert bb_tool_prefix(project) == prefix
    assert bb_tool(project, "read") == f"{prefix}read"


def test_unknown_tool_name_is_refused_loudly():
    with pytest.raises(ValueError, match="없는 도구"):
        bb_tool(_project(), "delete_everything")


@pytest.mark.parametrize(
    "target,expected",
    [
        (BuildTarget.MARKETPLACE, "${CLAUDE_PLUGIN_ROOT}/schemas/p.json"),
        (BuildTarget.LOCAL, "schemas/p.json"),
    ],
)
def test_schemas_argument_follows_the_build_target(target, expected):
    project = _project(target=target)
    assert bb_schemas_arg(project) == expected
    assert bb_server_entry(project) == {
        "command": "daedalus-bb", "args": ["--schemas", expected],
    }


# ─────────────────────────── 선언 → 도구 ───────────────────────────


def test_reads_only_grants_read_and_list():
    project = _project()
    skill = _skill("collect")
    _place(project, skill, reads=["TaskState"], with_next=False)
    assert bb_tools_for(skill, project) == [
        f"{_M}list", f"{_M}read", f"{_M}progress_read", f"{_M}progress_set",
    ]


def test_writes_grant_the_write_side_too():
    project = _project()
    skill = _skill("collect")
    _place(project, skill, writes=["TaskState.step"], with_next=False)
    granted = bb_tools_for(skill, project)
    assert f"{_M}write" in granted and f"{_M}init" in granted
    assert f"{_M}validate" in granted
    assert f"{_M}read" not in granted  # 쓰기만 선언했으면 읽기는 주지 않는다


def test_no_declaration_grants_only_the_progress_tools_when_placed():
    """배치만 돼 있으면 진행 기록 도구뿐이다 — 상태 도구는 선언이 있어야 한다."""
    project = _project()
    skill = _skill("collect")
    _place(project, skill, with_next=False)
    assert bb_tools_for(skill, project) == [
        f"{_M}progress_read", f"{_M}progress_set",
    ]


def test_unplaced_skill_gets_nothing():
    project = _project()
    skill = _skill("idle")
    project.skills.append(skill)
    assert bb_tools_for(skill, project) == []


def test_declared_access_without_a_blackboard_grants_no_state_tools():
    """클래스 정의가 없으면 읽고 쓸 상태 자체가 없다."""
    project = _project(blackboard=False)
    skill = _skill("collect")
    _place(project, skill, reads=["TaskState"], with_next=False)
    assert bb_tools_for(skill, project) == [
        f"{_M}progress_read", f"{_M}progress_set",
    ]


def test_transfer_skill_gets_progress_set_but_not_progress_read():
    """전이 스킬은 `note`만 남긴다 — 재개 프리앰블이 없으니 읽기도 없다."""
    project = _project()
    step = _skill("collect")
    _place(project, step, with_next=False)
    edge = TransferSkill(
        fsm=_fsm("e"), name="edge", description="Edge step.", body="Prep."
    )
    project.skills.append(edge)
    assert bb_tools_for(edge, project) == [f"{_M}progress_set"]


def test_workflow_agent_does_not_own_the_progress_record():
    project = _project()
    agent = AgentDefinition(fsm=_fsm("a"), name="worker", description="Worker.")
    agent.transfer_on = [EventDef(name="done")]
    project.agents.append(agent)
    project.graph.states.append(SimpleState(name="worker", skill_ref=agent))
    assert bb_tools_for(agent, project) == []


def test_tools_are_ordered_by_the_server_tool_order():
    """산출은 결정적이다 — 집합 순회 순서가 새지 않는다(원칙 6)."""
    from daedalus.cli.mcp_server import TOOL_NAMES

    project = _project()
    skill = _skill("collect")
    _place(project, skill, reads=["TaskState"], writes=["TaskState.step"],
           with_next=False)
    granted = [t.removeprefix(_M) for t in bb_tools_for(skill, project)]
    assert granted == [n for n in TOOL_NAMES if n in set(granted)]


# ─────────────────────────── fork의 비대칭 ───────────────────────────


def _fork_pair(project, *, base, reads=("TaskState",)):
    fork = SyncForkSkill(
        fsm=_fsm("f"), name="scout", description="Scout.", body="Look."
    )
    fork.config.agent = base.name
    fork.transfer_on = [EventDef(name="ok")]
    _place(project, fork, reads=reads, with_next=False)
    project.agents.append(base)
    return fork


def test_fork_skill_file_grants_nothing_and_its_agent_grants_instead():
    project = _project()
    base = ForkAgent(name="base", description="Fork base.", body="Work.")
    fork = _fork_pair(project, base=base)
    # fork 스킬의 SKILL.md는 서브에이전트의 도구를 늘리지 못한다.
    assert bb_tools_for(fork, project) == []
    # 권한을 실을 수 있는 유일한 파일이 대신 진다.
    assert bb_tools_for(base, project) == [
        f"{_M}list", f"{_M}read", f"{_M}progress_read",
    ]


def test_fork_agent_never_gets_progress_set():
    """fork는 진행 기록을 쓰지 않는다 — 보고를 받은 메인이 쓴다."""
    project = _project()
    base = ForkAgent(name="base", description="Fork base.", body="Work.")
    _fork_pair(project, base=base)
    assert f"{_M}progress_set" not in bb_tools_for(base, project)


def test_external_fork_agent_cannot_carry_the_grant_and_validation_says_so():
    project = _project()
    base = ExternalForkAgent(name="critic", description="External critic.")
    base.source = "ext-pack:critic"
    _fork_pair(project, base=base)
    assert bb_tools_for(base, project) == []  # 산출 파일이 없다

    findings = Validator().validate_project(project)
    unreachable = [f for f in findings if f.rule == "bb_tools_unreachable"]
    assert len(unreachable) == 1
    assert unreachable[0].source == "scout"
    assert unreachable[0].is_warning


def test_a_fork_without_blackboard_access_raises_no_warning():
    """경고는 "블랙보드를 쓰는데 실을 자리가 없다"일 때만 난다."""
    project = _project()
    base = ExternalForkAgent(name="critic", description="External critic.")
    base.source = "ext-pack:critic"
    _fork_pair(project, base=base, reads=())
    findings = Validator().validate_project(project)
    assert not [f for f in findings if f.rule == "bb_tools_unreachable"]


# ─────────────────────────── 프론트매터 합류 ───────────────────────────


def test_skill_allowed_tools_merges_with_the_declared_list():
    project = _project()
    skill = _skill("collect")
    skill.config.allowed_tools = ["Read", "Write"]
    _place(project, skill, reads=["TaskState"], with_next=False)
    line = next(
        ln for ln in compile_skill(skill, project=project).splitlines()
        if ln.startswith("allowed-tools:")
    )
    assert line.startswith("allowed-tools: [Read, Write, ")
    assert f"{_M}read" in line


def test_agent_tools_none_is_left_alone():
    """`tools`가 없으면 전부 상속이다 — 목록을 만들면 그 순간 나머지가 막힌다."""
    project = _project()
    base = ForkAgent(name="base", description="Fork base.", body="Work.")
    _fork_pair(project, base=base)
    assert base.config.tools is None
    assert not [
        ln for ln in compile_agent(base, project=project).splitlines()
        if ln.startswith("tools:")
    ]


def test_agent_tools_list_merges():
    project = _project()
    base = ForkAgent(name="base", description="Fork base.", body="Work.")
    base.config.tools = ["Read"]
    _fork_pair(project, base=base)
    line = next(
        ln for ln in compile_agent(base, project=project).splitlines()
        if ln.startswith("tools:")
    )
    assert line.startswith("tools: [Read, ")
    assert f"{_M}read" in line


def test_local_build_agent_declares_the_server_in_mcp_servers():
    """LOCAL에서는 `mcpServers`가 프론트매터로 나간다 — 도구와 같은 유도를 탄다."""
    project = _project(target=BuildTarget.LOCAL)
    base = ForkAgent(name="base", description="Fork base.", body="Work.")
    base.config.tools = ["Read"]
    _fork_pair(project, base=base)
    text = compile_agent(base, project=project)
    assert f"{_L}read" in text
    assert "mcpServers:" in text
    assert "  - bb-p" in text


# ─────────────────────────── `.mcp.json` 배선 ───────────────────────────


def test_server_is_needed_only_when_some_file_carries_a_grant():
    empty = _project()
    assert bb_server_needed(empty) is False
    project = _project()
    _place(project, _skill("collect"), with_next=False)
    assert bb_server_needed(project) is True


def test_marketplace_build_ships_the_server_in_the_plugin_mcp_json(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = _project()
    _place(project, _skill("collect"), reads=["TaskState"], with_next=False)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    payload = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert payload == {"mcpServers": {"bb-p": {
        "command": "daedalus-bb",
        "args": ["--schemas", "${CLAUDE_PLUGIN_ROOT}/schemas/p.json"],
    }}}


def test_local_build_merges_the_server_into_the_workspace_mcp_json(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"mine": {"command": "x"}}}), encoding="utf-8"
    )
    project = _project(target=BuildTarget.LOCAL)
    _place(project, _skill("collect"), reads=["TaskState"], with_next=False)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    servers = json.loads(
        (tmp_path / ".mcp.json").read_text(encoding="utf-8")
    )["mcpServers"]
    assert servers["mine"] == {"command": "x"}  # 남의 항목은 그대로
    assert servers["bb-p"]["args"] == ["--schemas", "schemas/p.json"]


def test_no_mcp_json_when_nothing_carries_a_grant(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = _project()
    project.skills.append(_skill("idle"))
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert not (tmp_path / ".mcp.json").exists()


@pytest.mark.parametrize(
    "target", [BuildTarget.MARKETPLACE, BuildTarget.LOCAL]
)
def test_a_user_server_taking_the_name_warns_instead_of_being_overwritten(
    tmp_path, target
):
    from daedalus.compiler.project_compiler import compile_project

    project = _project(target=target)
    project.mcp_server_defs = {"bb-p": {"command": "mine"}}
    _place(project, _skill("collect"), reads=["TaskState"], with_next=False)
    result = compile_project(project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert any(w.rule == "bb_server_name_taken" for w in result.warnings)
