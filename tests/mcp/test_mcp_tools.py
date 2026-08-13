"""앱 내장 MCP 도구 (WP-MCP).

도구를 ``DaedalusTools``로 직접 호출해 검증한다 — HTTP 서버를 띄우지 않으므로
포트를 잡지 않고 빠르다. 프로토콜 계층(실제 MCP 클라이언트 접속 → 도구 호출)은
별도로 수동 E2E로 확인했고, 여기서는 **도구가 실제 모델/캔버스에 무엇을 하는지**를
고정한다.

편집 도구의 핵심 계약은 "즉시 반영되고 undo로 되돌릴 수 있다"이므로, 반영만
확인하고 끝내지 않고 반드시 undo까지 확인한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    doc = DeclarativeSkill(name="rules", description="규칙", body="원본 본문")
    project = PluginProject(name="p", skills=[skill, doc])

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- 읽기 ---


def test_get_project_reports_components(tools):
    info = tools.get_project()
    assert info["name"] == "p"
    assert {s["name"] for s in info["skills"]} == {"init", "rules"}
    assert info["can_undo"] is False


def test_get_selection_empty_when_nothing_selected(tools):
    sel = tools.get_selection()
    assert sel["empty"] is True
    assert sel["selected_nodes"] == []


def test_get_component_returns_body(tools):
    info = tools.get_component("rules")
    assert info["body"] == "원본 본문"
    assert info["kind"] == "declarative_skill"


def test_get_component_unknown_name_lists_candidates(tools):
    with pytest.raises(ValueError, match="init"):
        tools.get_component("nope")


def test_validate_project_counts_severities(tools):
    result = tools.validate_project()
    assert "error_count" in result
    assert isinstance(result["issues"], list)


def test_compile_preview_emits_frontmatter(tools):
    result = tools.compile_preview("rules")
    assert result["text"].startswith("---")


# --- 편집: 반영 + undo ---


def test_place_component_adds_node_and_undo_removes_it(tools, window):
    tools.place_component("init", x=10, y=20)
    assert any(s.model.name == "init" for s in window._project_vm.state_vms)
    # 백킹 머신(project.graph)에도 들어가야 저장·컴파일에 잡힌다
    assert any(getattr(s, "skill_ref", None) is not None for s in window._project.graph.states)

    tools.undo()
    assert not any(s.model.name == "init" for s in window._project_vm.state_vms)


def test_create_move_and_undo_restores_position(tools, window):
    tools.create_state("n1", x=0, y=0)
    tools.move_state("n1", x=100, y=200)
    vm = window._project_vm.get_state_vm("n1")
    assert (vm.x, vm.y) == (100.0, 200.0)

    tools.undo()
    assert (vm.x, vm.y) == (0.0, 0.0)


def test_connect_and_disconnect_states(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b")
    assert len(window._project_vm.transition_vms) == 1

    tools.disconnect_states("a", "b")
    assert window._project_vm.transition_vms == []

    tools.undo()
    assert len(window._project_vm.transition_vms) == 1


def test_delete_state_removes_attached_transitions_in_one_undo(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b")

    result = tools.delete_state("a")
    assert result["removed_transitions"] == 1
    assert window._project_vm.transition_vms == []

    # 노드와 전이가 한 undo 단위로 함께 복원돼야 한다
    tools.undo()
    assert window._project_vm.get_state_vm("a") is not None
    assert len(window._project_vm.transition_vms) == 1


def test_rename_state(tools, window):
    tools.create_state("old")
    tools.rename_state("old", "new")
    assert window._project_vm.get_state_vm("new") is not None
    tools.undo()
    assert window._project_vm.get_state_vm("old") is not None


def test_connect_unknown_state_raises(tools):
    tools.create_state("a")
    with pytest.raises(ValueError, match="nope"):
        tools.connect_states("a", "nope")


# --- 본문: 캔버스가 아니라 본문 문서 undo 스택으로 간다 (WP-BU 연동) ---


def test_set_component_body_updates_model_and_document(tools, window):
    from daedalus.view.editors import body_documents

    tools.set_component_body("rules", "새 본문")
    comp = next(s for s in window._project.skills if s.name == "rules")
    assert comp.body == "새 본문"

    doc = body_documents.registry().document_for(comp)
    assert doc.toPlainText() == "새 본문"
    # 본문 편집은 캔버스 스택이 아니라 문서 스택에 올라간다
    assert doc.isUndoAvailable()
    assert window._project_vm.command_stack.can_undo is False


# --- 이력 ---


def test_get_history_lists_recent_commands(tools):
    tools.create_state("a")
    tools.create_state("b")
    history = tools.get_history()
    assert len(history["entries"]) == 2
    assert "create_state" in history["entries"][-1]["script"]
    assert history["can_undo"] is True


def test_redo_after_undo(tools, window):
    tools.create_state("a")
    tools.undo()
    assert window._project_vm.get_state_vm("a") is None
    tools.redo()
    assert window._project_vm.get_state_vm("a") is not None


def test_undo_on_empty_stack_is_noop(tools):
    result = tools.undo()
    assert result["undone"] is None


def test_tools_without_project_raise(qapp):
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.app import MainWindow

    win = MainWindow()
    try:
        with pytest.raises(RuntimeError, match="프로젝트"):
            DaedalusTools(win).get_project()
    finally:
        win.close()
