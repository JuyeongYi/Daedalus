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


def test_fork_agent_has_no_output_ports_in_mcp(tools):
    """fork 에이전트에 출력 포트를 쓰려 하면 거절한다.

    `SetAttrCmd`는 `getattr(..., None)` 폴백이라 가드가 없으면 없는 필드가
    인스턴스 속성으로 생기고, 성공 응답이 돌아간 뒤 저장 한 번에 사라진다
    (원칙 5). 유령 속성은 편집기·MCP의 `hasattr` 게이트도 무력화한다.
    """
    tools.create_agent("helper", kind="fork_agent")
    with pytest.raises(ValueError, match="출력 포트를 갖지 않습니다"):
        tools.set_transfer_on("helper", [{"name": "done"}])
    agent = next(a for a in tools._project.agents if a.name == "helper")
    assert not hasattr(agent, "transfer_on")


def test_fork_agent_editor_shows_no_port_panels(window):
    """편집기의 종류 판정은 클래스다 — hasattr는 유령 속성 하나에 속는다."""
    from daedalus.view.editors.agent_editor import AgentEditor

    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    editor = AgentEditor(agent, project=window._project)
    assert editor._is_workflow is False
    assert editor._transfer_on_panel is None
    assert editor._call_agents_panel is None


# ---------------------------------------------------------------------------
# 삭제 확인 — 참조를 몰래 지우지 않고 보고한다 (원칙 5)
# ---------------------------------------------------------------------------

def _make_fork_skill(name: str, agent_name: str):
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.plugin.config import SyncForkSkillConfig
    from daedalus.model.plugin.skill import SyncForkSkill

    s = SimpleState(name="s")
    return SyncForkSkill(
        fsm=StateMachine(name=f"{name}_fsm", states=[s], initial_state=s),
        name=name, description="d", config=SyncForkSkillConfig(agent=agent_name),
    )


@pytest.fixture
def delete_dialog(monkeypatch):
    """삭제 확인 다이얼로그 봉합선 — 메시지를 붙잡고 '아니오'를 돌려준다.

    헤드리스에서 모달이 뜨면 스위트가 멈춘다. 답을 바꾸려면 `answer`에 넣는다.
    """
    from PySide6.QtWidgets import QMessageBox

    from daedalus.view import component_actions as mod

    seen: dict = {"messages": [], "answer": QMessageBox.StandardButton.No}

    def _question(_parent, _title, text, *args, **kwargs):
        seen["messages"].append(text)
        return seen["answer"]

    monkeypatch.setattr(mod.QMessageBox, "question", staticmethod(_question))
    return seen


def test_delete_dialog_reports_fork_skills_using_the_agent(window, delete_dialog):
    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    window._register_component(_make_fork_skill("scout", "helper"))

    window._component_actions.on_delete_component(agent)

    message = delete_dialog["messages"][0]
    assert "fork 스킬 'scout'" in message
    # '아니오'를 골랐으니 아무것도 지워지지 않는다.
    assert agent in window._project.agents


def test_delete_dialog_omits_the_section_when_nobody_uses_it(window, delete_dialog):
    from PySide6.QtWidgets import QMessageBox

    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    delete_dialog["answer"] = QMessageBox.StandardButton.Yes

    window._component_actions.on_delete_component(agent)

    assert "fork 스킬" not in delete_dialog["messages"][0]
    assert agent not in window._project.agents


def test_delete_dialog_report_matches_the_shared_derivation(window, delete_dialog):
    """화면·산출·MCP가 같은 목록을 말한다 — 유도 함수가 하나다(원칙 1)."""
    from daedalus.model.plugin.placement import fork_skills_using

    agent = ForkAgent(name="helper", description="d")
    window._register_component(agent)
    for name in ("audit", "scout"):
        window._register_component(_make_fork_skill(name, "helper"))

    window._component_actions.on_delete_component(agent)

    message = delete_dialog["messages"][0]
    assert fork_skills_using(agent, window._project) == ["audit", "scout"]
    for name in ("audit", "scout"):
        assert f"fork 스킬 '{name}'" in message
