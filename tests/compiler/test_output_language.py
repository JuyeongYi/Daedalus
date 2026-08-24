"""컴파일 산출은 영어다 — 자동 단락에 한국어가 스미지 않게 하는 게이트 (A12).

**원칙:** 사용자가 입력한 값(body, description, when_to_use, 포트 description,
블랙보드 설명 …)은 그대로 나가고, **컴파일러가 생성하는 텍스트는 전부 영어**다.
소비자가 LLM이라 자동 단락의 토큰이 곧 비용이다.

그래서 이 파일의 픽스처는 **사용자 값을 전부 영어로** 채운다 — 산출에 한글이
하나라도 있으면 그것은 컴파일러가 만든 것이고, 새 자동 단락에 한국어가 새로
들어왔다는 뜻이다.
"""
from __future__ import annotations

import re

import pytest

from daedalus.compiler.emit import (
    compile_agent,
    compile_hooks_json,
    compile_plugin_manifest,
    compile_schemas_json,
    compile_skill,
)
from daedalus.compiler.project_compiler import compile_project
from daedalus.model.fsm.blackboard import Blackboard, DynamicClass, DynamicField
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import FieldType
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.plugin.tool import UserDefinedTool
from daedalus.model.project import PluginProject

#: 한글 음절 + 자모. 산출에 이것이 있으면 컴파일러가 만든 한국어다.
HANGUL = re.compile(r"[가-힣ㄱ-ㆎ]")


def _proc(name: str) -> ProceduralSkill:
    first = SimpleState(name="gather")
    choice = ChoiceState(name="decide")
    last = SimpleState(name="wrap-up")
    fsm = StateMachine(
        name=f"{name}-fsm", initial_state=first,
        states=[first, choice, last], final_states=[last],
    )
    fsm.transitions.extend([
        Transition(source=first, target=choice, trigger=CompletionEvent(name="ready")),
        Transition(source=choice, target=last),
    ])
    skill = ProceduralSkill(
        fsm=fsm, name=name, description="Collect input and produce a report",
    )
    skill.when_to_use = "the user asks for a report"
    skill.body = "Gather the facts, then write them down."
    return skill


@pytest.fixture
def english_project() -> PluginProject:
    """사용자 값이 전부 영어인 픽스처 — 남는 한글은 전부 컴파일러 소산이다."""
    alpha, beta = _proc("alpha"), _proc("beta")
    alpha.transfer_on = [EventDef(name="done", description="analysis finished")]
    alpha.call_agents = [
        EventDef(name="delegate", description="hand the file list to the worker"),
    ]
    alpha.fsm.states[0].reads = ["Task.title"]
    alpha.fsm.states[2].writes = ["Task.done"]
    alpha.config.allowed_tools = ["Read", "mcp__github__list_issues"]

    s = SimpleState(name="check")
    transfer = TransferSkill(
        fsm=StateMachine(name="tf", initial_state=s, states=[s]),
        name="validate", description="Check the payload against the schema",
    )
    knowledge = DeclarativeSkill(name="rules", description="Background rules")
    knowledge.body = "Follow the house style."
    doc = ReferenceSkill(name="handbook", description="Reference handbook")

    entry = EntryPoint(name="entry")
    agent = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=entry, states=[entry]),
        name="runner", description="Runs the heavy job",
        transfer_on=[EventDef(name="ok", description="job succeeded")],
    )
    agent.body = "Do the heavy lifting."
    agent.config.tools = ["Read", "mcp__github__list_issues"]
    agent.config.max_turns = 12
    agent.config.hooks = {"guard": {}}

    blackboard = Blackboard(class_definitions=[
        DynamicClass(
            name="Task", description="the unit of work",
            fields=[
                DynamicField(name="title", field_type=FieldType.STRING, required=True),
                DynamicField(name="done", field_type=FieldType.BOOL),
            ],
        ),
    ])

    project = PluginProject(
        name="demo", description="A demo plugin", version="1.0.0",
        skills=[alpha, beta, transfer, knowledge, doc],
        agents=[agent],
        blackboard=blackboard,
        tool_shelf=[
            UserDefinedTool(
                name="counter", description="Counts things", body="wc -l",
            ),
        ],
        hook_library=[
            HookDef(
                name="guard", description="Guard the edits",
                event=HookEvent.PRE_TOOL_USE, matcher="Edit",
                handlers=[CommandHook(script="echo guarding")],
            ),
        ],
    )
    na = SimpleState(name="alpha", skill_ref=alpha)
    nb = SimpleState(name="beta", skill_ref=beta)
    ng = SimpleState(name="runner", skill_ref=agent)
    project.graph.states.extend([na, nb, ng])
    project.graph.transitions.extend([
        Transition(
            source=na, target=nb, trigger=CompletionEvent(name="done"),
            skill_ref=transfer,
        ),
        Transition(source=na, target=ng, trigger=CompletionEvent(name="delegate")),
        Transition(source=ng, target=nb, trigger=CompletionEvent(name="ok")),
    ])
    return project


def _assert_english(text: str, what: str) -> None:
    found = sorted(set(HANGUL.findall(text)))
    if not found:
        return
    lines = [ln for ln in text.split("\n") if HANGUL.search(ln)]
    raise AssertionError(
        f"{what}의 산출에 한국어가 있습니다 — 컴파일러가 만드는 텍스트는 전부 "
        f"영어여야 합니다(A12).\n" + "\n".join(f"  {ln}" for ln in lines[:15])
    )


# --- 게이트 ---


def test_skill_outputs_are_english(english_project):
    for skill in english_project.skills:
        _assert_english(
            compile_skill(skill, project=english_project), f"스킬 '{skill.name}'"
        )


def test_agent_outputs_are_english(english_project):
    for agent in english_project.agents:
        _assert_english(
            compile_agent(agent, project=english_project), f"에이전트 '{agent.name}'"
        )


def test_terminal_skill_output_is_english(english_project):
    """outgoing 0개 배치는 "다음 단계" 대신 "작업 완료" 단락을 받는다."""
    beta = next(s for s in english_project.skills if s.name == "beta")
    text = compile_skill(beta, project=english_project)
    assert "## Finishing Up" in text
    _assert_english(text, "터미널 배치")


def test_transfer_skill_output_is_english(english_project):
    transfer = next(s for s in english_project.skills if s.name == "validate")
    text = compile_skill(transfer, project=english_project)
    assert "## Progress Record" in text
    _assert_english(text, "전이 스킬")


def test_whole_project_compile_is_english(english_project, tmp_path):
    """실제 컴파일 산출 파일 전체 — 단락 하나를 빠뜨리지 않는다."""
    result = compile_project(english_project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert result.written
    for path in result.written:
        _assert_english(path.read_text(encoding="utf-8"), str(path.name))


def test_local_build_compile_is_english(english_project, tmp_path):
    """LOCAL 빌드는 산출 경로와 에이전트 프론트매터가 다르다 — 따로 본다."""
    english_project.build_target = BuildTarget.LOCAL
    result = compile_project(english_project, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    for path in result.written:
        _assert_english(path.read_text(encoding="utf-8"), str(path.name))


def test_side_outputs_are_english(english_project):
    _assert_english(compile_plugin_manifest(english_project), "plugin.json")
    _assert_english(compile_schemas_json(english_project) or "", "schemas.json")
    _assert_english(compile_hooks_json(english_project) or "", "hooks.json")


# --- 사용자 값은 그대로 나간다 (영어화가 삼키지 않는다) ---


def test_user_korean_values_pass_through(english_project):
    """사용자가 넣은 한국어는 **그대로** 나가야 한다 — 영어화 대상이 아니다."""
    alpha = next(s for s in english_project.skills if s.name == "alpha")
    alpha.body = "한국어 본문이다."
    alpha.description = "한국어 설명"
    alpha.transfer_on[0].description = "한국어 포트 설명"

    text = compile_skill(alpha, project=english_project)
    assert "한국어 본문이다." in text
    assert "한국어 설명" in text
    assert "한국어 포트 설명" in text


def test_blackboard_class_description_passes_through(english_project):
    english_project.blackboard.class_definitions[0].description = "작업 단위"
    alpha = next(s for s in english_project.skills if s.name == "alpha")
    assert "작업 단위" in compile_skill(alpha, project=english_project)


# --- 결정성 (영어화가 순서를 흔들지 않았는지) ---


def test_output_is_still_deterministic(english_project):
    alpha = next(s for s in english_project.skills if s.name == "alpha")
    first = compile_skill(alpha, project=english_project)
    second = compile_skill(alpha, project=english_project)
    assert first == second
