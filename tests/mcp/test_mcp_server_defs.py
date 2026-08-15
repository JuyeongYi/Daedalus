"""MCP 서버 정의 등록 (set_mcp_server_def, WP-MW).

컴포넌트는 서버를 이름으로만 참조한다 — 정의(이름 → .mcp.json 객체)가 없으면
LOCAL 컴파일이 설치 배선을 할 수 없어 missing_mcp_server_def 경고가 난다.
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


_DEF = {"type": "http", "url": "http://127.0.0.1:8787/mcp"}


def test_add_and_read_back(tools, window):
    out = tools.set_mcp_server_def("daedalus", dict(_DEF))
    assert out["action"] == "added"
    assert window._project.mcp_server_defs == {"daedalus": _DEF}
    assert tools.get_project()["mcp_server_defs"] == {"daedalus": _DEF}


def test_update_existing(tools, window):
    tools.set_mcp_server_def("daedalus", dict(_DEF))
    out = tools.set_mcp_server_def("daedalus", {"command": "daedalus-stdio"})
    assert out["action"] == "updated"
    assert window._project.mcp_server_defs["daedalus"] == {"command": "daedalus-stdio"}


def test_remove_with_empty_config(tools, window):
    tools.set_mcp_server_def("daedalus", dict(_DEF))
    out = tools.set_mcp_server_def("daedalus", None)
    assert out["action"] == "removed"
    assert window._project.mcp_server_defs == {}


def test_remove_unknown_is_rejected(tools):
    with pytest.raises(ValueError, match="정의가 없습니다"):
        tools.set_mcp_server_def("nope", None)


def test_undoable(tools, window):
    tools.set_mcp_server_def("daedalus", dict(_DEF))
    tools.undo()
    assert window._project.mcp_server_defs == {}
    tools.redo()
    assert window._project.mcp_server_defs == {"daedalus": _DEF}


def test_round_trips_through_serialization(tools, window):
    from daedalus.model.serialize import deserialize_project, serialize_project

    tools.set_mcp_server_def("daedalus", dict(_DEF))
    loaded = deserialize_project(serialize_project(window._project))
    assert loaded.mcp_server_defs == {"daedalus": _DEF}


def test_legacy_file_without_key_loads_empty():
    from daedalus.model.serialize import deserialize_project, serialize_project

    data = serialize_project(PluginProject(name="p"))
    del data["mcp_server_defs"]
    assert deserialize_project(data).mcp_server_defs == {}


def test_tool_is_exposed():
    from daedalus.mcp.service import TOOL_NAMES

    assert "set_mcp_server_def" in TOOL_NAMES
