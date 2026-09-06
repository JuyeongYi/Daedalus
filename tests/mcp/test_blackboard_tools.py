"""블랙보드 편집 패리티 (G1·G2) — 클래스 수정·삭제·개명 + 필드 단위 편집.

GUI 블랙보드 탭은 클래스 삭제·개명·설명 수정·필드 추가/수정/삭제가 전부
되는데 MCP는 `create_blackboard_class` 하나뿐이었다(패리티 원칙 위반).
편집 도구는 반영뿐 아니라 **undo까지**, 그리고 화면(패널·자동완성 후보)이
따라오는지까지 확인한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    project = PluginProject(name="p", skills=[skill])

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


@pytest.fixture
def perf(tools):
    """PerfMeasurement 클래스 + 그것을 읽고 쓰는 캔버스 노드 하나."""
    tools.create_blackboard_class(
        "PerfMeasurement",
        description="측정치",
        fields=[
            {"name": "frame_ms", "type": "float", "required": True},
            {"name": "draw_calls", "type": "int"},
        ],
    )
    tools.create_state("measure")
    tools.set_state_access(
        "measure",
        reads=["PerfMeasurement"],
        writes=["PerfMeasurement.frame_ms", "Other.x"],
    )
    return tools


# --- G1: 클래스 수정 ---


def test_update_blackboard_class_renames_and_follows_references(perf, window):
    """개명은 상태 reads/writes의 문자열 참조를 따라간다 (rename_component 관례)."""
    result = perf.update_blackboard_class("PerfMeasurement", new_name="Perf")

    cls = window._project.blackboard.class_definitions[0]
    assert cls.name == "Perf"
    state = window._project_vm.get_state_vm("measure").model
    assert state.reads == ["Perf"]
    # 무관한 클래스 참조는 건드리지 않는다
    assert state.writes == ["Perf.frame_ms", "Other.x"]
    assert {u["node"] for u in result["updated_references"]} == {"measure"}


def test_update_blackboard_class_rename_is_one_undo_step(perf, window):
    """이름과 참조가 따로 되돌아가면 중간에 참조가 깨진 상태를 거친다."""
    perf.update_blackboard_class("PerfMeasurement", new_name="Perf")
    perf.undo()

    cls = window._project.blackboard.class_definitions[0]
    state = window._project_vm.get_state_vm("measure").model
    assert cls.name == "PerfMeasurement"
    assert state.reads == ["PerfMeasurement"]
    assert state.writes == ["PerfMeasurement.frame_ms", "Other.x"]


def test_update_blackboard_class_sets_description(perf, window):
    perf.update_blackboard_class("PerfMeasurement", description="새 설명")
    assert window._project.blackboard.class_definitions[0].description == "새 설명"

    perf.undo()
    assert window._project.blackboard.class_definitions[0].description == "측정치"


def test_update_blackboard_class_clears_description_with_empty_string(perf, window):
    perf.update_blackboard_class("PerfMeasurement", description="")
    assert window._project.blackboard.class_definitions[0].description == ""


def test_update_blackboard_class_none_means_untouched(perf, window):
    """빈 커맨드를 쌓으면 Ctrl+Z가 아무 일도 안 하는 단계를 센다."""
    before = len(window._active_stack.history)
    result = perf.update_blackboard_class("PerfMeasurement")

    assert result["changed"] == []
    assert window._project.blackboard.class_definitions[0].description == "측정치"
    assert len(window._active_stack.history) == before


def test_update_blackboard_class_rejects_duplicate_name(perf):
    perf.create_blackboard_class("Other")
    with pytest.raises(ValueError, match="이미 있습니다"):
        perf.update_blackboard_class("PerfMeasurement", new_name="Other")


def test_update_blackboard_class_rejects_blank_name(perf):
    with pytest.raises(ValueError, match="비울 수 없습니다"):
        perf.update_blackboard_class("PerfMeasurement", new_name="   ")


def test_update_blackboard_class_unknown_lists_available(tools):
    tools.create_blackboard_class("Known")
    with pytest.raises(ValueError, match="Known"):
        tools.update_blackboard_class("Nope", description="x")


# --- G1: 클래스 삭제 ---


def test_delete_blackboard_class_reports_referrers_without_touching_them(perf, window):
    """삭제는 참조를 지우지 않는다 — delete_hook·delete_component와 같은 정책."""
    result = perf.delete_blackboard_class("PerfMeasurement")

    assert result["deleted"] == "PerfMeasurement"
    assert result["still_referenced_by"] == ["measure"]
    assert window._project.blackboard.class_definitions == []
    state = window._project_vm.get_state_vm("measure").model
    assert state.reads == ["PerfMeasurement"]


def test_delete_blackboard_class_undo_restores_position(tools, window):
    tools.create_blackboard_class("A")
    tools.create_blackboard_class("B")
    tools.create_blackboard_class("C")
    tools.delete_blackboard_class("B")
    assert [c.name for c in window._project.blackboard.class_definitions] == ["A", "C"]

    tools.undo()
    assert [c.name for c in window._project.blackboard.class_definitions] == [
        "A",
        "B",
        "C",
    ]


def test_deleted_class_reference_becomes_validation_warning(perf, window):
    """보고만 하고 두는 참조는 F7이 이어서 짚는다."""
    from daedalus.model.validation import Validator

    perf.delete_blackboard_class("PerfMeasurement")
    errors = Validator().validate_project(window._project)
    assert any(e.rule == "dangling_blackboard_ref" for e in errors)


# --- G2: 필드 단위 편집 ---


def test_set_blackboard_fields_replaces_whole_list(perf, window):
    from daedalus.model.fsm.blackboard import CollectionType
    from daedalus.model.fsm.variable import FieldType

    perf.set_blackboard_fields(
        "PerfMeasurement",
        fields=[
            {"name": "frame_ms", "type": "float", "required": True},
            {"name": "tags", "type": "string", "collection": "list"},
        ],
    )
    cls = window._project.blackboard.class_definitions[0]
    assert [f.name for f in cls.fields] == ["frame_ms", "tags"]
    assert cls.fields[1].collection is CollectionType.LIST
    assert cls.fields[1].field_type is FieldType.STRING


def test_set_blackboard_fields_is_undoable(perf, window):
    perf.set_blackboard_fields("PerfMeasurement", fields=[{"name": "only", "type": "string"}])
    perf.undo()

    cls = window._project.blackboard.class_definitions[0]
    assert [f.name for f in cls.fields] == ["frame_ms", "draw_calls"]


def test_set_blackboard_fields_reports_dropped_references(perf):
    """빠진 필드를 가리키던 노드를 알려 준다 — 교체는 개명을 알 수 없다."""
    result = perf.set_blackboard_fields(
        "PerfMeasurement", fields=[{"name": "draw_calls", "type": "int"}]
    )
    assert result["dropped_fields"] == ["frame_ms"]
    assert result["dropped_field_references"] == [
        {"field": "PerfMeasurement.frame_ms", "nodes": ["measure"]}
    ]


def test_set_blackboard_fields_shares_type_validation(perf):
    """create_blackboard_class와 같은 판정 — 컨테이너 타입은 collection이 전담."""
    with pytest.raises(ValueError, match="쓸 수 없습니다"):
        perf.set_blackboard_fields("PerfMeasurement", fields=[{"name": "f", "type": "list"}])


def test_set_blackboard_fields_rejects_duplicate_field_name(perf):
    with pytest.raises(ValueError, match="중복"):
        perf.set_blackboard_fields(
            "PerfMeasurement",
            fields=[{"name": "a", "type": "string"}, {"name": "a", "type": "int"}],
        )


def test_set_blackboard_fields_can_clear(perf, window):
    perf.set_blackboard_fields("PerfMeasurement", fields=[])
    assert window._project.blackboard.class_definitions[0].fields == []


# --- 화면이 따라오는가 ---


def test_panel_follows_mcp_class_rename(perf, window):
    perf.update_blackboard_class("PerfMeasurement", new_name="Perf")

    panel = window._blackboard_panel
    labels = [panel._list.item(i).text() for i in range(panel._list.count())]
    assert labels == ["Perf"]


def test_panel_field_table_follows_mcp_field_edit(perf, window):
    """목록만 새로 그리면 같은 행이 선택된 채라 테이블이 스테일로 남는다."""
    panel = window._blackboard_panel
    panel._list.setCurrentRow(0)

    perf.set_blackboard_fields(
        "PerfMeasurement", fields=[{"name": "renamed_only", "type": "string"}]
    )

    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 0).text() == "renamed_only"


def test_panel_description_follows_mcp_edit(perf, window):
    window._blackboard_panel._list.setCurrentRow(0)
    perf.update_blackboard_class("PerfMeasurement", description="바깥에서 바꿈")
    assert window._blackboard_panel._desc_edit.text() == "바깥에서 바꿈"


def test_tag_input_candidates_follow_mcp_edits(perf):
    """reads/writes 자동완성 후보는 provider가 호출 시점에 다시 만든다."""
    from daedalus.view.widgets.tag_input import get_blackboard_candidates

    perf.update_blackboard_class("PerfMeasurement", new_name="Perf")
    perf.set_blackboard_fields("Perf", fields=[{"name": "frame_ms", "type": "float"}])

    assert get_blackboard_candidates() == ["Perf", "Perf.frame_ms"]


# --- GUI 쪽도 같은 판정을 쓴다 ---


def test_gui_rename_follows_references_too(window, monkeypatch):
    """같은 조작이 표면에 따라 다른 결과를 내면 안 된다 (MCP와 같은 모델 헬퍼)."""
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.editors import blackboard_editor as be

    tools = DaedalusTools(window)
    tools.create_blackboard_class("PerfMeasurement")
    tools.create_state("measure")
    tools.set_state_access("measure", reads=["PerfMeasurement.frame_ms"])

    panel = window._blackboard_panel
    panel._list.setCurrentRow(0)
    monkeypatch.setattr(be.QInputDialog, "getText", staticmethod(lambda *a, **k: ("Perf", True)))
    panel._on_rename_class(panel._list.item(0))

    state = window._project_vm.get_state_vm("measure").model
    assert state.reads == ["Perf.frame_ms"]
    assert window._project.blackboard.class_definitions[0].name == "Perf"


# --- 도구 등록 ---


def test_new_tools_are_registered_in_service():
    """등록을 빠뜨리면 메서드는 있는데 CC에서는 보이지 않는다."""
    from daedalus.mcp.service import TOOL_NAMES

    for name in (
        "update_blackboard_class",
        "delete_blackboard_class",
        "set_blackboard_fields",
    ):
        assert name in TOOL_NAMES
