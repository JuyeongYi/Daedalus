"""WP-L: tool_shelf 직렬화 라운드트립 + 미지 kind 명시 실패."""
from __future__ import annotations

import json

import pytest

from daedalus.model.plugin.enums import SkillShell
from daedalus.model.plugin.tool import (
    BuiltinTool,
    MCPTool,
    Tool,
    UserDefinedTool,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import (
    _deser_tool,
    _ser_tool,
    deserialize_project,
    serialize_project,
)


def _sample_shelf() -> list[Tool]:
    return [
        BuiltinTool(name="Read", description="파일 읽기", allowed_arguments_note="any path"),
        MCPTool(name="pw-click", description="클릭", server="playwright", tool_name="browser_click"),
        UserDefinedTool(
            name="git-commit", description="커밋", body="git commit -m msg",
            shell=SkillShell.POWERSHELL,
        ),
    ]


def test_tool_shelf_roundtrip_json():
    proj = PluginProject(name="p", tool_shelf=_sample_shelf())
    blob = json.dumps(serialize_project(proj))
    out = deserialize_project(json.loads(blob))

    assert len(out.tool_shelf) == 3
    by_name = {t.name: t for t in out.tool_shelf}

    rd = by_name["Read"]
    assert isinstance(rd, BuiltinTool)
    assert rd.allowed_arguments_note == "any path"
    assert rd.id == proj.tool_shelf[0].id  # id 보존

    mc = by_name["pw-click"]
    assert isinstance(mc, MCPTool)
    assert (mc.server, mc.tool_name) == ("playwright", "browser_click")

    ud = by_name["git-commit"]
    assert isinstance(ud, UserDefinedTool)
    assert ud.body == "git commit -m msg"
    assert ud.shell is SkillShell.POWERSHELL


def test_empty_tool_shelf_roundtrip():
    proj = PluginProject(name="p")
    out = deserialize_project(serialize_project(proj))
    assert out.tool_shelf == []


def test_ser_tool_unknown_kind_raises():
    class WeirdTool(Tool):
        @property
        def kind(self) -> str:
            return "weird"

    with pytest.raises(TypeError, match="직렬화 미지원 Tool kind"):
        _ser_tool(WeirdTool(name="x", description="y"))


def test_deser_tool_unknown_kind_raises():
    with pytest.raises(ValueError, match="역직렬화 미지원 Tool kind"):
        _deser_tool({"kind": "weird", "name": "x", "description": "y"})
