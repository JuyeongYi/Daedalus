"""fork 에이전트 MCP 패리티 조회 (WP-F, 2026-09-18).

GUI에 새로 생긴 "사용하는 fork 스킬" 패널에는 대응하는 **읽기**가 있어야
한다(원칙 2) — `delete_component`의 `still_referenced_by`는 지워야만 보이므로
조회의 대체가 되지 않는다. 목록의 실체는 `model/plugin/placement.
fork_skills_using` 하나다(편집기·삭제 확인·산출과 공용, 원칙 1).

`get_project`의 에이전트 행에 실리는 `kind`도 같은 이유다 — 워크플로 에이전트와
fork 에이전트는 배치·포트·프론트매터 표가 달라, 목록에서 구분되지 않으면
호출자가 잘못 배선한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    win = MainWindow()
    win.set_project(PluginProject(name="p"))
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


def test_get_project_agent_rows_carry_kind(tools):
    tools.create_agent("worker")
    tools.create_agent("helper", kind="fork_agent")

    rows = {
        a["name"]: a["kind"]
        for a in tools.get_project(sections=["components"])["agents"]
    }
    assert rows == {"worker": "agent", "helper": "fork_agent"}


def test_get_component_lists_fork_skills_using_the_agent(tools):
    tools.create_agent("helper", kind="fork_agent")
    tools.create_skill("scout", kind="sync_fork", fork_agent="helper")
    tools.create_skill("audit", kind="async_fork", fork_agent="helper")
    tools.create_skill("other", kind="sync_fork")

    info = tools.get_component("helper")
    assert info["kind"] == "fork_agent"
    assert info["used_by_fork_skills"] == ["audit", "scout"]


def test_get_component_reports_an_unused_fork_agent_as_empty(tools):
    tools.create_agent("helper", kind="fork_agent")
    assert tools.get_component("helper")["used_by_fork_skills"] == []


def test_workflow_agent_has_no_fork_usage_key(tools):
    """역참조는 fork 에이전트의 개념이다 — 워크플로 에이전트에는 실리지 않는다."""
    tools.create_agent("worker")
    assert "used_by_fork_skills" not in tools.get_component("worker")


def test_read_matches_the_delete_report(tools):
    """쓰기(삭제 보고)와 읽기가 같은 목록을 말한다 — 유도가 하나다."""
    tools.create_agent("helper", kind="fork_agent")
    tools.create_skill("scout", kind="sync_fork", fork_agent="helper")

    read = tools.get_component("helper")["used_by_fork_skills"]
    assert tools.delete_component("helper")["still_referenced_by"] == [
        f"skill:{name}.agent" for name in read
    ]
