"""fork 에이전트 후보 — 세 종류, 배치된 프로젝트 에이전트 제외 (2026-09-13)."""
from __future__ import annotations

import pytest

from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject
from daedalus.view.actions.fork_skill import fork_agent_choices, validate_fork_agent

from tests.compiler.builders import make_agent


def _project() -> PluginProject:
    helper, worker = make_agent(name="helper"), make_agent(name="worker")
    project = PluginProject(name="p", agents=[worker, helper])
    project.graph.states.append(SimpleState(name="worker", skill_ref=worker))
    return project


def test_builtins_first_then_unplaced_project_agents():
    values = [v for v, _ in fork_agent_choices(_project())]
    assert values[:3] == ["general-purpose", "Explore", "Plan"]
    assert "helper" in values
    assert "worker" not in values


def test_placed_agent_rejected_with_reason():
    with pytest.raises(ValueError, match="배치"):
        validate_fork_agent(_project(), "worker")


def test_unknown_agent_rejected_with_choices():
    with pytest.raises(ValueError, match="helper"):
        validate_fork_agent(_project(), "Helper")
