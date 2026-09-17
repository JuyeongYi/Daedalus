"""fork 에이전트 후보 — 종류가 정한다 (사용자 확정 2026-09-17).

예전 판정은 "캔버스에 배치되지 않은 워크플로 에이전트"였다 — 배치를 지우면
조용히 겸직이 생겼다. 이제 fork 에이전트는 **별도 종류**다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import ForkAgent
from daedalus.model.project import PluginProject
from daedalus.view.actions.fork_skill import fork_agent_choices, validate_fork_agent

from tests.compiler.builders import make_agent


def _project() -> PluginProject:
    worker = make_agent(name="worker")          # 배치된 워크플로 에이전트
    idle = make_agent(name="idle")              # 미배치 워크플로 에이전트
    helper = ForkAgent(name="helper", description="fork 실행 기반")
    project = PluginProject(name="p", agents=[worker, idle, helper])
    project.graph.states.append(SimpleState(name="worker", skill_ref=worker))
    return project


def test_builtins_first_then_fork_agents():
    values = [v for v, _ in fork_agent_choices(_project())]
    assert values[:3] == ["general-purpose", "Explore", "Plan"]
    assert "helper" in values
    # 워크플로 에이전트는 배치 여부와 무관하게 후보가 아니다 — 종류가 다르다.
    assert "worker" not in values
    assert "idle" not in values


@pytest.mark.parametrize("name", ["worker", "idle"])
def test_workflow_agent_rejected_with_reason(name):
    with pytest.raises(ValueError, match="워크플로 에이전트"):
        validate_fork_agent(_project(), name)


def test_fork_agent_accepted():
    validate_fork_agent(_project(), "helper")  # 예외 없음


def test_unknown_agent_rejected_with_choices():
    with pytest.raises(ValueError, match="helper"):
        validate_fork_agent(_project(), "Helper")
