"""fork 에이전트 후보 — 종류가 정한다 (사용자 확정 2026-09-17/2026-09-19).

예전 판정은 "캔버스에 배치되지 않은 워크플로 에이전트"였다 — 배치를 지우면
조용히 겸직이 생겼다. 이제 fork 에이전트는 **별도 종류**다.

WP-EX(역할 고정)가 한 갈래를 더 걷었다: 사용 선언한 외부 플러그인의 에이전트를
`플러그인:이름` **문자열** 후보로 흘려 넣던 자리가 사라지고, 외부 에이전트도
`ExternalForkAgent`로 **등록한 뒤** 그 컴포넌트 이름을 고른다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import ExternalForkAgent, ForkAgent
from daedalus.model.plugin.config import ExternalForkAgentConfig
from daedalus.model.project import PluginProject
from daedalus.view.actions.fork_skill import fork_agent_choices, validate_fork_agent

from tests.compiler.builders import make_agent


def _project() -> PluginProject:
    worker = make_agent(name="worker")          # 배치된 워크플로 에이전트
    idle = make_agent(name="idle")              # 미배치 워크플로 에이전트
    helper = ForkAgent(name="helper", description="fork 실행 기반")
    critic = ExternalForkAgent(
        name="critic", description="외부 fork 실행 기반",
        config=ExternalForkAgentConfig(source="tools@market:reviewer"),
    )
    project = PluginProject(name="p", agents=[worker, idle, helper, critic])
    project.graph.states.append(SimpleState(name="worker", skill_ref=worker))
    return project


def test_builtins_first_then_fork_agents():
    values = [v for v, _ in fork_agent_choices(_project())]
    assert values[:3] == ["general-purpose", "Explore", "Plan"]
    assert "helper" in values
    # 워크플로 에이전트는 배치 여부와 무관하게 후보가 아니다 — 종류가 다르다.
    assert "worker" not in values
    assert "idle" not in values


def test_external_fork_agent_is_a_candidate_by_component_name():
    """외부 fork 실행 기반은 **등록한 컴포넌트 이름**으로 고른다 (WP-EX).

    산출의 `agent:`에 나가는 것은 source 원문이지만, 고르는 값은 컴포넌트
    이름이다 — 그래야 이름 변경·삭제·검증이 다른 컴포넌트와 같은 길을 탄다.
    """
    rows = dict(fork_agent_choices(_project()))
    assert "critic" in rows
    assert "tools@market:reviewer" in rows["critic"]
    # 원문 자체는 후보가 아니다 — 등록하지 않은 이름은 고를 수 없다.
    assert "tools@market:reviewer" not in rows


def test_choice_note_distinguishes_own_from_external():
    rows = dict(fork_agent_choices(_project()))
    assert rows["helper"] == "프로젝트 fork 에이전트"
    assert rows["critic"].startswith("외부 플러그인 fork 에이전트")


def test_external_fork_agent_without_source_still_listed():
    """source가 비어도 후보에서 사라지지 않는다 — 편집 중일 수 있다.

    조용히 목록에서 빼면 "왜 안 보이지"가 되고, 비었다는 사실은
    `external_source_missing` 경고가 말한다(원칙 5).
    """
    project = PluginProject(
        name="p", agents=[ExternalForkAgent(name="blank", description="d")],
    )
    rows = dict(fork_agent_choices(project))
    assert "(source 미지정)" in rows["blank"]


@pytest.mark.parametrize("name", ["worker", "idle"])
def test_workflow_agent_rejected_with_reason(name):
    with pytest.raises(ValueError, match="워크플로 에이전트"):
        validate_fork_agent(_project(), name)


def test_fork_agent_accepted():
    validate_fork_agent(_project(), "helper")  # 예외 없음
    validate_fork_agent(_project(), "critic")  # 등록된 외부 fork 에이전트


def test_raw_plugin_reference_is_rejected_with_the_registration_path():
    """`플러그인:이름` 원문은 거절하되 **등록하는 법**을 말한다 (원칙 5).

    받아 주면 그 외부 에이전트가 컴포넌트로 등록되지 않은 채 산출에만 나가고,
    사용 선언·역할 고정·검증이 전부 비켜 간다.
    """
    with pytest.raises(ValueError) as excinfo:
        validate_fork_agent(_project(), "other@mkt:helper")
    message = str(excinfo.value)
    assert "external_fork_agent" in message
    assert "other@mkt:helper" in message


def test_unknown_agent_rejected_with_choices():
    with pytest.raises(ValueError, match="helper"):
        validate_fork_agent(_project(), "Helper")
