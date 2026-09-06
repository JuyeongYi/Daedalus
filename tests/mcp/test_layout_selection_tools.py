"""레이아웃·선택 도구 (G13·G10·G16).

- `move_reference`는 `move_state`의 짝이다 — 참조 노드만 좌표를 못 고치던 갭.
- `set_transition_waypoints`는 엣지 경유점(WP-ER)의 **교체 1종**이다. 캔버스는
  하나씩 추가·드래그하지만 MCP로 좌표를 한 점씩 넣는 것은 의미가 없다.
- `focus_node`/`select_nodes`는 `get_selection`의 쓰기 짝이고 **undo 대상이
  아니다** — 선택은 편집이 아니라 "무엇을 보고 있는가"다.
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    project = PluginProject(
        name="p",
        skills=[
            ProceduralSkill(fsm=fsm, name="init", description="초기화"),
            ProceduralSkill(
                fsm=StateMachine(
                    name="g", initial_state=s1, states=[s1], final_states=[s1]
                ),
                name="wrap",
                description="마무리",
            ),
            ReferenceSkill(name="guide", description="참조 문서"),
        ],
    )
    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


@pytest.fixture
def linked(tools):
    tools.place_component("init", 0, 0)
    tools.place_component("wrap", 300, 0)
    tools.connect_states("init", "wrap")
    return tools


# --- G13: move_reference ---


def test_move_reference_moves_and_syncs_model(tools):
    tools.place_reference("guide", 10, 10)
    result = tools.move_reference("guide", 120, 60)
    assert result["to"] == [120.0, 60.0]

    rvm = tools._find_ref_vm("guide")
    assert (rvm.x, rvm.y) == (120.0, 60.0)
    placement = tools._project.reference_placements[0]
    assert (placement.x, placement.y) == (120.0, 60.0)


def test_move_reference_is_undoable(tools):
    tools.place_reference("guide", 10, 10)
    tools.move_reference("guide", 120, 60)
    tools.undo()
    rvm = tools._find_ref_vm("guide")
    assert (rvm.x, rvm.y) == (10.0, 10.0)


def test_move_reference_picks_by_index(tools):
    tools.place_reference("guide", 0, 0)
    tools.place_reference("guide", 50, 50)
    tools.move_reference("guide", 900, 900, index=1)
    assert (tools._find_ref_vm("guide", 0).x, tools._find_ref_vm("guide", 0).y) == (0.0, 0.0)
    assert tools._find_ref_vm("guide", 1).x == 900.0


def test_move_reference_rejects_missing_node(tools):
    with pytest.raises(ValueError, match="참조 노드가 없습니다"):
        tools.move_reference("guide", 1, 1)


# --- G10: set_transition_waypoints ---


def test_set_waypoints_replaces_whole_list(linked):
    linked.set_transition_waypoints("init", "wrap", [[10, 20], [30, 40]])
    tvm = linked._find_transition_vm("init", "wrap")
    assert tvm.waypoints == [(10.0, 20.0), (30.0, 40.0)]

    result = linked.set_transition_waypoints("init", "wrap", [[99, 99]])
    assert result["waypoints"] == [[99.0, 99.0]]
    assert result["removed"] == 2


def test_set_waypoints_empty_clears(linked):
    linked.set_transition_waypoints("init", "wrap", [[10, 20]])
    linked.set_transition_waypoints("init", "wrap")
    assert linked._find_transition_vm("init", "wrap").waypoints == []


def test_set_waypoints_is_one_undo_unit(linked):
    linked.set_transition_waypoints("init", "wrap", [[10, 20], [30, 40]])
    linked.undo()
    assert linked._find_transition_vm("init", "wrap").waypoints == []

    linked.set_transition_waypoints("init", "wrap", [[1, 1]])
    linked.set_transition_waypoints("init", "wrap", [[2, 2], [3, 3]])
    linked.undo()  # 교체 전체가 1 undo — 지우기+추가가 따로 되돌아가지 않는다
    assert linked._find_transition_vm("init", "wrap").waypoints == [(1.0, 1.0)]


def test_set_waypoints_reported_by_get_project(linked):
    linked.set_transition_waypoints("init", "wrap", [[10, 20], [30, 40]])
    canvas = linked.get_project(sections=["canvas"])
    assert canvas["transitions"][0]["waypoint_count"] == 2


def test_set_waypoints_rejects_malformed_point(linked):
    with pytest.raises(ValueError, match=r"points\[1\]"):
        linked.set_transition_waypoints("init", "wrap", [[1, 2], [3]])
    assert linked._find_transition_vm("init", "wrap").waypoints == []


def test_set_waypoints_noop_leaves_history_clean(linked):
    before = len(linked._window._active_stack.history)
    linked.set_transition_waypoints("init", "wrap")
    assert len(linked._window._active_stack.history) == before


# --- G16: focus_node / select_nodes ---


def test_focus_node_selects_single_node(linked):
    result = linked.focus_node("wrap")
    assert result["focused"] == "wrap"
    assert linked.get_selection()["selected_nodes"] == [
        {"node": "wrap", "component": "wrap", "kind": "procedural_skill"}
    ]


def test_focus_node_is_not_undoable(linked):
    before = len(linked._window._active_stack.history)
    linked.focus_node("wrap")
    assert len(linked._window._active_stack.history) == before


def test_select_nodes_selects_many(linked):
    result = linked.select_nodes(["init", "wrap"])
    assert result["count"] == 2
    names = {n["node"] for n in linked.get_selection()["selected_nodes"]}
    assert names == {"init", "wrap"}


def test_select_nodes_empty_clears_selection(linked):
    linked.select_nodes(["init"])
    linked.select_nodes([])
    assert linked.get_selection()["empty"] is True


def test_select_nodes_rejects_unknown_name_without_partial_selection(linked):
    with pytest.raises(ValueError, match="nope"):
        linked.select_nodes(["init", "nope"])
    assert linked.get_selection()["empty"] is True
