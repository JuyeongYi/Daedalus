"""WP-L: tool_shelf 직렬화 라운드트립 + 미지 kind 명시 실패."""
from __future__ import annotations

import dataclasses
import inspect
import json

import pytest

from daedalus.model.plugin.enums import SkillShell
from daedalus.model.plugin.tool import (
    TOOL_KIND_BY_NAME,
    TOOL_KINDS,
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


# ─────────────────── 종류 레지스트리 계약 (WP-11) ───────────────────


def _concrete_tool_classes() -> set[type]:
    found: set[type] = set()
    stack = [Tool]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub in found:
                continue
            found.add(sub)
            stack.append(sub)
    return {c for c in found if not inspect.isabstract(c) and c.__module__.startswith("daedalus.")}


def test_tool_kinds_cover_every_concrete_tool_class():
    """등록 표와 실제 클래스 집합은 **양방향으로** 같다 — 빠뜨리면 로드가 죽는다."""
    assert {spec.cls for spec in TOOL_KINDS} == _concrete_tool_classes()


def test_tool_kind_tag_matches_the_instance_kind():
    """표의 kind 태그와 인스턴스의 `kind`는 같은 사실이다(짝 계약)."""
    for spec in TOOL_KINDS:
        assert spec.cls(name="n", description="d").kind == spec.kind


def test_tool_kind_extra_fields_are_real_dataclass_fields():
    """선언한 고유 키가 실제 필드인지 — 오타는 저장 시점에야 터지면 늦다."""
    for spec in TOOL_KINDS:
        names = {f.name for f in dataclasses.fields(spec.cls)}
        for field_spec in spec.fields:
            assert field_spec.name in names, f"{spec.kind}: {field_spec.name}"


def test_tool_kind_by_name_is_read_only():
    """표를 런타임에 고쳐 종류를 몰래 늘리는 일이 없게 한다."""
    with pytest.raises(TypeError):
        TOOL_KIND_BY_NAME["x"] = None  # type: ignore[index]


def test_missing_optional_keys_fall_back_to_dataclass_defaults():
    """키 부재 = dataclass 기본값 — 기본값을 직렬화 쪽에 복제하지 않는다."""
    tool = _deser_tool({"kind": "user", "name": "n", "description": "d"})
    assert tool.body == ""
    assert tool.shell is SkillShell.BASH
