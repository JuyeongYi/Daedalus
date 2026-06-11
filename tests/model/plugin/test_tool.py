"""WP-L: Tool 계층 (BuiltinTool/MCPTool/UserDefinedTool) 단위 테스트."""
from __future__ import annotations

import pytest

from daedalus.model.plugin.enums import SkillShell
from daedalus.model.plugin.tool import (
    BuiltinTool,
    MCPTool,
    Tool,
    UserDefinedTool,
)


def test_builtin_tool_kind():
    t = BuiltinTool(name="Read", description="파일 읽기")
    assert t.kind == "builtin"
    assert t.allowed_arguments_note == ""


def test_mcp_tool_kind():
    t = MCPTool(name="pw-click", description="클릭", server="playwright", tool_name="browser_click")
    assert t.kind == "mcp"
    assert t.server == "playwright"
    assert t.tool_name == "browser_click"


def test_user_defined_tool_kind_and_defaults():
    t = UserDefinedTool(name="git-commit", description="커밋", body="git commit -m x")
    assert t.kind == "user"
    assert t.body == "git commit -m x"
    assert t.shell is SkillShell.BASH


def test_user_defined_tool_shell_override():
    t = UserDefinedTool(
        name="deploy", description="배포", body="./deploy.ps1",
        shell=SkillShell.POWERSHELL,
    )
    assert t.shell is SkillShell.POWERSHELL


def test_tool_abc_not_instantiable():
    """Tool은 ABC — kind가 추상이라 직접 인스턴스화 불가."""
    with pytest.raises(TypeError):
        Tool(name="x", description="y")  # type: ignore[abstract]


def test_tool_id_unique():
    a = BuiltinTool(name="Read", description="a")
    b = BuiltinTool(name="Read", description="a")
    assert a.id and b.id
    assert a.id != b.id


def test_tool_id_excluded_from_equality():
    """id는 compare=False — 값 동등성에서 제외."""
    a = BuiltinTool(name="Read", description="a")
    b = BuiltinTool(name="Read", description="a")
    assert a == b  # id만 다르고 나머지 동일 → 동등


def test_tool_id_kw_only():
    """id는 kw_only — 위치 인수로 새지 않는다."""
    t = MCPTool("nm", "desc", "srv", "tn")
    assert t.name == "nm"
    assert t.id  # 자동 생성
