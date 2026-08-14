"""MCP 표면의 구멍 메우기 — 훅·참조 노드·프로젝트 속성·호출 포트 제거.

실제로 그래프를 만들어 보다가 드러난 빈 자리들이다. 어느 것이든 "GUI에서는
되는데 AI는 못 한다"가 되면 협업이 한쪽에서만 성립하므로, 편집 도구는 반영뿐
아니라 **undo까지** 확인한다(test_mcp_tools.py와 같은 규약).
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import HookEvent
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    ref = ReferenceSkill(name="guide", description="참조 문서")
    project = PluginProject(name="p", skills=[skill, ref])

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- 에이전트 호출 포트 조회·제거 ---


def test_get_component_exposes_call_agents(tools):
    """포트를 만들어 놓고도 조회할 수 없으면 AI가 자기 상태를 못 본다."""
    tools.add_agent_call("init", "review")
    info = tools.get_component("init")
    assert [c["name"] for c in info["call_agents"]] == ["review"]


def test_remove_agent_call_removes_port(tools):
    tools.add_agent_call("init", "review")
    result = tools.remove_agent_call("init", "review")
    assert result["call_agents"] == []

    tools.undo()
    assert [e.name for e in tools._find_component("init").call_agents] == ["review"]


def test_remove_agent_call_reports_orphaned_transitions(tools):
    """포트를 지우면 그 포트를 쓰던 전이가 고아가 된다 — 조용히 두지 않는다."""
    tools.create_agent("worker")
    tools.place_component("init", 0, 0)
    tools.place_component("worker", 200, 0)
    tools.add_agent_call("init", "review")
    tools.connect_states("init", "worker", trigger="review")

    result = tools.remove_agent_call("init", "review")
    assert result["orphaned_transitions"] == [["init", "worker"]]


def test_remove_unknown_call_port_lists_existing(tools):
    tools.add_agent_call("init", "review")
    with pytest.raises(ValueError, match="review"):
        tools.remove_agent_call("init", "nope")


# --- 프로젝트 속성 ---


def test_set_project_properties_updates_manifest_fields(tools, window):
    result = tools.set_project_properties(
        name="ue-perf", description="언리얼 성능", version="1.2.0"
    )
    assert result["name"] == "ue-perf"
    assert window._project.version == "1.2.0"

    tools.undo()
    assert window._project.name == "p", "한 번의 undo로 전부 되돌아가야 한다"
    assert window._project.version == "0.1.0"


def test_set_project_properties_ignores_blank_fields(tools, window):
    tools.set_project_properties(version="2.0.0")
    assert window._project.name == "p", "빈 값은 건드리지 않는다"
    assert window._project.version == "2.0.0"


def test_set_project_properties_switches_build_target(tools, window):
    tools.set_project_properties(build_target="local")
    assert window._project.build_target is BuildTarget.LOCAL


def test_set_project_properties_rejects_unknown_target(tools):
    with pytest.raises(ValueError, match="marketplace"):
        tools.set_project_properties(build_target="nope")


def test_set_project_properties_no_args_is_noop(tools):
    result = tools.set_project_properties()
    assert result["changed"] == []


# --- 설명 / when_to_use ---


def test_set_component_description_is_undoable(tools):
    """이전에는 이 편집만 Ctrl+Z가 듣지 않았다."""
    tools.set_component_description("init", "새 설명")
    assert tools._find_component("init").description == "새 설명"

    tools.undo()
    assert tools._find_component("init").description == "초기화"


def test_set_component_when_to_use(tools):
    tools.set_component_when_to_use("init", "프로젝트를 처음 열 때")
    assert tools.get_component("init")["when_to_use"] == "프로젝트를 처음 열 때"

    tools.undo()
    assert tools.get_component("init")["when_to_use"] == ""


# --- 훅 라이브러리 ---


def test_create_hook_adds_to_library(tools, window):
    result = tools.create_hook(
        "guard-bash", event="PreToolUse", command="echo hi", matcher="Bash", timeout=5
    )
    assert result["event"] == "PreToolUse"
    library = window._project.hook_library
    assert [h.name for h in library] == ["guard-bash"]
    assert library[0].timeout == 5

    tools.undo()
    assert window._project.hook_library == []


def test_create_hook_zero_timeout_means_unset(tools, window):
    tools.create_hook("h", command="x")
    assert window._project.hook_library[0].timeout is None


def test_create_hook_rejects_duplicate_name(tools):
    tools.create_hook("h", command="x")
    with pytest.raises(ValueError, match="이미"):
        tools.create_hook("h", command="y")


def test_create_hook_rejects_unknown_event(tools):
    with pytest.raises(ValueError, match="SessionStart"):
        tools.create_hook("h", event="Nope")


def test_create_hook_warns_about_matcher_on_non_tool_event(tools):
    """matcher는 Pre/PostToolUse 전용 — 조용히 무시되면 사용자가 원인을 못 찾는다."""
    result = tools.create_hook("h", event="SessionStart", matcher="Bash")
    assert "note" in result


def test_update_hook_changes_fields(tools, window):
    tools.create_hook("h", command="old", matcher="Bash")
    tools.update_hook("h", command="new", event="PostToolUse")

    hook = window._project.hook_library[0]
    assert hook.command == "new"
    assert hook.event is HookEvent.POST_TOOL_USE

    tools.undo()
    assert hook.command == "old"
    assert hook.event is HookEvent.PRE_TOOL_USE


def test_update_hook_clears_matcher_with_empty_string(tools, window):
    tools.create_hook("h", command="x", matcher="Bash")
    tools.update_hook("h", matcher="")
    assert window._project.hook_library[0].matcher == ""


def test_update_hook_blank_command_is_untouched(tools, window):
    tools.create_hook("h", command="keep")
    tools.update_hook("h", matcher="Bash")
    assert window._project.hook_library[0].command == "keep"


def test_update_hook_unknown_name(tools):
    with pytest.raises(ValueError, match="없습니다"):
        tools.update_hook("nope", command="x")


def test_delete_hook_removes_definition(tools, window):
    tools.create_hook("h", command="x")
    tools.delete_hook("h")
    assert window._project.hook_library == []

    tools.undo()
    assert [h.name for h in window._project.hook_library] == ["h"]


def test_delete_hook_reports_dangling_references(tools):
    tools.create_hook("h", command="x")
    tools.set_component_hooks("init", ["h"])
    result = tools.delete_hook("h")
    assert result["still_referenced_by"] == ["init"]


def test_set_component_hooks_records_reference(tools):
    tools.create_hook("h", command="x")
    tools.set_component_hooks("init", ["h"])
    assert tools._find_component("init").config.hooks == {"h": {}}

    tools.undo()
    # 선언 기본값은 {}가 아니라 None이다 — undo는 그 원래 값으로 되돌린다
    assert tools._find_component("init").config.hooks is None


def test_set_component_hooks_rejects_unknown_hook(tools):
    """오타는 컴파일까지 조용히 흘러가 경고로만 드러난다 — 여기서 막는다."""
    tools.create_hook("real", command="x")
    with pytest.raises(ValueError, match="real"):
        tools.set_component_hooks("init", ["typo"])


def test_set_component_hooks_preserves_overrides(tools):
    tools.create_hook("a", command="x")
    tools.create_hook("b", command="y")
    tools.set_component_hooks("init", ["a"])
    tools._find_component("init").config.hooks["a"] = {"timeout": 9}

    tools.set_component_hooks("init", ["a", "b"])
    assert tools._find_component("init").config.hooks["a"] == {"timeout": 9}


def test_get_project_lists_hook_library(tools):
    tools.create_hook("h", command="x", event="SessionEnd")
    entry = tools.get_project()["hook_library"][0]
    assert entry["name"] == "h" and entry["event"] == "SessionEnd"


# --- 참조 노드 ---


def test_place_reference_creates_node(tools, window):
    result = tools.place_reference("guide", 100, 50)
    assert result["index"] == 0
    assert len(window._project_vm.reference_vms) == 1
    # 모델에도 동기화된다 (저장·컴파일의 단일 진실)
    assert [rp.skill_name for rp in window._project.reference_placements] == ["guide"]

    tools.undo()
    assert window._project_vm.reference_vms == []


def test_place_reference_allows_multiple_instances(tools):
    """참조 노드는 상태가 아니라 여러 상태가 공유하는 문서라 중복 배치가 정상이다."""
    tools.place_reference("guide", 0, 0)
    second = tools.place_reference("guide", 300, 0)
    assert second["index"] == 1
    assert len(tools.get_project()["references"]) == 2


def test_place_reference_rejects_non_reference_skill(tools):
    with pytest.raises(ValueError, match="place_component"):
        tools.place_reference("init")


def test_link_reference_connects_node(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    result = tools.link_reference("init", "guide")
    assert result["created"] is True
    assert tools.get_project()["references"][0]["linked_nodes"] == ["init"]

    tools.undo()
    assert window._project_vm.reference_links == []


def test_link_reference_is_idempotent(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")
    tools.link_reference("init", "guide")
    assert len(window._project_vm.reference_links) == 1


def test_unlink_reference_drops_link_but_keeps_node(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")

    tools.unlink_reference("init", "guide")
    assert window._project_vm.reference_links == []
    assert len(window._project_vm.reference_vms) == 1


def test_unlink_reference_without_link_errors(tools):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    with pytest.raises(ValueError, match="참조 연결이 없습니다"):
        tools.unlink_reference("init", "guide")


def test_unplace_reference_removes_node_and_links(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")

    result = tools.unplace_reference("guide")
    assert result["removed_links"] == 1
    assert window._project_vm.reference_vms == []

    tools.undo()
    assert len(window._project_vm.reference_vms) == 1
    assert len(window._project_vm.reference_links) == 1, "링크도 함께 돌아와야 한다"


def test_unplace_reference_index_out_of_range(tools):
    tools.place_reference("guide", 0, 0)
    with pytest.raises(ValueError, match="1개뿐"):
        tools.unplace_reference("guide", index=3)


def test_link_reference_without_placed_reference_errors(tools):
    tools.place_component("init", 0, 0)
    with pytest.raises(ValueError, match="참조 노드가 없습니다"):
        tools.link_reference("init", "guide")
