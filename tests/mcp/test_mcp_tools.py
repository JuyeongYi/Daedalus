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


# --- 컴포넌트 생성/이름변경 (WP-CE 1차) ---


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("procedural", "procedural_skill"),
        ("declarative", "declarative_skill"),
        ("transfer", "transfer_skill"),
        ("reference", "reference_skill"),
    ],
)
def test_create_skill_each_kind(tools, window, kind, expected):
    tools.create_skill(f"s-{kind}", kind=kind)
    comp = next(s for s in window._project.skills if s.name == f"s-{kind}")
    assert comp.kind == expected


def test_create_skill_is_undoable(tools, window):
    tools.create_skill("temp", kind="declarative")
    assert any(s.name == "temp" for s in window._project.skills)

    tools.undo()
    assert not any(s.name == "temp" for s in window._project.skills)


def test_created_procedural_skill_gets_blackboard_parent(tools, window):
    """생성 경로가 블랙보드 스코핑을 배선해야 한다."""
    tools.create_skill("with-fsm", kind="procedural")
    comp = next(s for s in window._project.skills if s.name == "with-fsm")
    assert comp.fsm.blackboard.parent is window._project.blackboard


def test_create_agent_has_entry_and_exit(tools, window):
    tools.create_agent("worker", description="작업자")
    agent = next(a for a in window._project.agents if a.name == "worker")
    names = {s.name for s in agent.fsm.states}
    assert "entry" in names and "done" in names

    tools.undo()
    assert not any(a.name == "worker" for a in window._project.agents)


def test_create_skill_rejects_duplicate_name(tools):
    with pytest.raises(ValueError, match="이미"):
        tools.create_skill("init", kind="declarative")


def test_create_skill_rejects_unknown_kind(tools):
    with pytest.raises(ValueError, match="알 수 없는"):
        tools.create_skill("x", kind="nonsense")


def test_rename_component_updates_references_and_undoes(tools, window):
    """문자열 참조까지 대칭으로 되돌아와야 한다."""
    agent_skill = next(s for s in window._project.skills if s.name == "init")
    tools.create_agent("helper")
    agent_skill.config.agent = "helper"

    tools.rename_component("helper", "assistant")
    assert agent_skill.config.agent == "assistant"

    tools.undo()
    assert agent_skill.config.agent == "helper"


def test_rename_to_existing_name_rejected(tools):
    with pytest.raises(ValueError, match="이미"):
        tools.rename_component("init", "rules")


def test_set_component_description(tools, window):
    tools.set_component_description("rules", "새 설명")
    comp = next(s for s in window._project.skills if s.name == "rules")
    assert comp.description == "새 설명"


# --- 포트/전이 의미론 (WP-CE) ---


def test_set_transfer_on_defines_output_ports(tools, window):
    tools.set_transfer_on(
        "init",
        [{"name": "ok", "description": "성공"}, {"name": "fail", "color": "#ff4444"}],
    )
    comp = next(s for s in window._project.skills if s.name == "init")
    assert [e.name for e in comp.transfer_on] == ["ok", "fail"]
    assert comp.transfer_on[0].description == "성공"
    assert comp.transfer_on[1].color == "#ff4444"

    # ProceduralSkill의 기본 transfer_on은 [EventDef("done")] — undo는 그 기본값으로 돌아간다
    tools.undo()
    assert [e.name for e in comp.transfer_on] == ["done"]


def test_set_transfer_on_accepts_bare_strings(tools, window):
    tools.set_transfer_on("init", ["a", "b"])
    comp = next(s for s in window._project.skills if s.name == "init")
    assert [e.name for e in comp.transfer_on] == ["a", "b"]


def test_set_entry_paths_defines_input_ports(tools, window):
    tools.set_entry_paths("rules", [{"name": "from-init"}])
    comp = next(s for s in window._project.skills if s.name == "rules")
    assert [e.name for e in comp.entry_paths] == ["from-init"]


def test_connect_states_with_trigger_and_guard(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b", trigger="gpu", guard="GPU 시간이 최대일 때")

    tvm = window._project_vm.transition_vms[0]
    assert tvm.model.trigger.name == "gpu"
    assert tvm.model.guard.evaluation.prompt == "GPU 시간이 최대일 때"


def test_set_transition_updates_existing_edge(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b")
    tools.set_transition("a", "b", trigger="done", target_port="main")

    trans = window._project_vm.transition_vms[0].model
    assert trans.trigger.name == "done"
    assert trans.target_port == "main"

    # 한 undo로 두 속성이 함께 되돌아온다 (MacroCommand)
    tools.undo()
    assert trans.trigger is None
    assert trans.target_port == ""


def test_set_transition_none_leaves_untouched(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b", trigger="keep")
    tools.set_transition("a", "b", target_port="p")

    trans = window._project_vm.transition_vms[0].model
    assert trans.trigger.name == "keep"  # None이었으므로 유지
    assert trans.target_port == "p"


def test_set_transition_empty_string_clears(tools, window):
    tools.create_state("a")
    tools.create_state("b")
    tools.connect_states("a", "b", trigger="gone")
    tools.set_transition("a", "b", trigger="")

    assert window._project_vm.transition_vms[0].model.trigger is None


# --- 블랙보드 ---


def test_create_blackboard_class(tools, window):
    tools.create_blackboard_class(
        "PerfMeasurement",
        description="측정치",
        fields=[
            {"name": "frame_ms", "type": "float", "required": True},
            {"name": "draw_calls", "type": "int"},
        ],
    )
    classes = window._project.blackboard.class_definitions
    assert [c.name for c in classes] == ["PerfMeasurement"]
    assert [f.name for f in classes[0].fields] == ["frame_ms", "draw_calls"]
    assert classes[0].fields[0].required is True

    tools.undo()
    assert window._project.blackboard.class_definitions == []


def test_create_blackboard_class_rejects_container_type(tools):
    """블랙보드 필드는 스칼라 4종만 — 컨테이너는 collection이 전담한다."""
    with pytest.raises(ValueError, match="쓸 수 없습니다"):
        tools.create_blackboard_class("X", fields=[{"name": "f", "type": "list"}])


def test_create_blackboard_class_accepts_collection(tools, window):
    from daedalus.model.fsm.blackboard import CollectionType

    tools.create_blackboard_class(
        "X", fields=[{"name": "tags", "type": "string", "collection": "list"}]
    )
    cls = window._project.blackboard.class_definitions[0]
    assert cls.fields[0].collection is CollectionType.LIST


def test_create_blackboard_class_rejects_duplicate(tools):
    tools.create_blackboard_class("Dup")
    with pytest.raises(ValueError, match="이미"):
        tools.create_blackboard_class("Dup")


def test_set_state_access_declares_reads_writes(tools, window):
    tools.create_state("n")
    tools.set_state_access("n", reads=["PerfTarget"], writes=["PerfMeasurement.frame_ms"])

    state = window._project_vm.get_state_vm("n").model
    assert state.reads == ["PerfTarget"]
    assert state.writes == ["PerfMeasurement.frame_ms"]

    tools.undo()
    assert state.reads == [] and state.writes == []


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
