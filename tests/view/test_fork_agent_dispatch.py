"""fork 에이전트 디스패치 스윕 — 버킷·미리보기·탭·MCP (2026-09-17).

ForkAgent가 "에이전트 컴포넌트 전반" 경로에서 스킬 경로로 새면 저장·미리보기가
죽는다(원칙 1·5). `_bucket`은 두 종류를 `project.agents`로 보내는 **단 하나의**
판정이다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.agent import ForkAgent
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


def test_created_fork_agent_lands_in_the_agents_bucket(tools, window):
    tools.create_agent("helper", kind="fork_agent")
    comp = next(a for a in window._project.agents if a.name == "helper")
    assert isinstance(comp, ForkAgent)
    assert not any(s.name == "helper" for s in window._project.skills)


def test_delete_and_undo_restore_the_same_bucket(tools, window):
    tools.create_agent("helper", kind="fork_agent")
    comp = next(a for a in window._project.agents if a.name == "helper")
    tools.delete_component("helper")
    assert comp not in window._project.agents
    tools.undo()
    assert comp in window._project.agents
    assert comp not in window._project.skills


def test_fork_agent_rejects_placement_coordinates(tools):
    with pytest.raises(ValueError, match="배치되지 않습니다"):
        tools.create_agent("helper", kind="fork_agent", x=10.0, y=20.0)


def test_unknown_agent_kind_is_rejected(tools):
    with pytest.raises(ValueError, match="fork_agent"):
        tools.create_agent("helper", kind="nonsense")


def test_preview_uses_the_agent_compiler_and_path(window):
    from daedalus.view.actions.preview import preview_text, preview_title

    agent = ForkAgent(name="helper", description="d", body="Do the work.")
    window._register_component(agent)
    title = preview_title(agent)
    assert title == "컴파일 미리보기 — agents/helper.md"
    text = preview_text(agent, project=window._project)
    assert "name: helper" in text
    assert "Do the work." in text


def test_compile_preview_returns_agent_text(tools, window):
    tools.create_agent("helper", kind="fork_agent")
    out = tools.compile_preview("helper")
    assert out["kind"] == "fork_agent"
    assert "name: helper" in out["text"]


def test_list_component_fields_uses_the_fork_agent_matrix(tools):
    tools.create_agent("helper", kind="fork_agent")
    fields = {f["field"] for f in tools.list_component_fields("helper")["fields"]}
    assert "tools" in fields
    # fork 에이전트 표에는 이 두 행이 없다.
    assert "background" not in fields
    assert "isolation" not in fields


def test_editor_tab_opens_with_the_fork_agent_prefix(window):
    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    window._open_component(agent)
    titles = [window._tabs.tabText(i) for i in range(window._tabs.count())]
    assert "🧩 helper" in titles


def test_registry_lists_fork_agents_in_their_own_section(window):
    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    panel = window._registry_panel
    panel.set_project(window._project)
    section = panel._sections["fork_agent"]
    labels = [section._list.item(i).text() for i in range(section._list.count())]
    assert any("helper" in label for label in labels)
    assert panel._sections["agent"]._list.count() == 0
