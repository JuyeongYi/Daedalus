# tests/compiler/test_hooks.py
"""WP-HOOK: hooks.json 컴파일 + 프론트매터 hooks 표기."""
from __future__ import annotations

import json

from daedalus.compiler import compile_hooks_json, compile_project, compile_skill
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_declarative, make_procedural


def _library() -> list[HookDef]:
    return [
        HookDef(name="fmt-on-edit", description="포맷", event=HookEvent.POST_TOOL_USE,
                matcher="Edit|Write", command="run-formatter", timeout=30),
        HookDef(name="notify-stop", description="알림", event=HookEvent.STOP,
                command="notify"),
        HookDef(name="guard-bash", description="차단", event=HookEvent.PRE_TOOL_USE,
                matcher="Bash", command="guard"),
    ]


def _agent_with_hooks(names) -> object:
    ag = make_agent("worker")
    ag.config.hooks = {n: {} for n in names}
    return ag


# ── compile_hooks_json: 스키마 ──

def test_hooks_json_schema_roundtrip():
    proj = PluginProject(
        name="p",
        agents=[_agent_with_hooks(["fmt-on-edit", "notify-stop"])],
        hook_library=_library(),
    )
    text = compile_hooks_json(proj)
    assert text is not None
    obj = json.loads(text)  # JSON 왕복 가능

    assert "hooks" in obj
    hooks = obj["hooks"]
    assert set(hooks.keys()) == {"PostToolUse", "Stop"}

    # PostToolUse: matcher 있음 + timeout 있음
    post = hooks["PostToolUse"]
    assert post == [{
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": "run-formatter", "timeout": 30}],
    }]

    # Stop: matcher 없음(도구 이벤트 아님) + timeout 없음
    stop = hooks["Stop"]
    assert stop == [{"hooks": [{"type": "command", "command": "notify"}]}]


def test_hooks_json_matcher_only_on_tool_events():
    """STOP 이벤트 훅에 (실수로) matcher가 있어도 출력에서 생략된다."""
    lib = [HookDef(name="h", description="d", event=HookEvent.STOP,
                   matcher="Edit", command="c")]
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["h"])], hook_library=lib)
    obj = json.loads(compile_hooks_json(proj))
    assert "matcher" not in obj["hooks"]["Stop"][0]


def test_hooks_json_event_key_order_deterministic():
    """이벤트 키는 HookEvent 선언 순서 — PreToolUse가 PostToolUse보다 먼저."""
    proj = PluginProject(
        name="p",
        agents=[_agent_with_hooks(["notify-stop", "guard-bash", "fmt-on-edit"])],
        hook_library=_library(),
    )
    obj = json.loads(compile_hooks_json(proj))
    keys = list(obj["hooks"].keys())
    assert keys == ["PreToolUse", "PostToolUse", "Stop"]


def test_hooks_json_none_when_no_refs():
    proj = PluginProject(name="p", hook_library=_library())  # 참조 없음
    assert compile_hooks_json(proj) is None


def test_hooks_json_none_when_ref_dangling():
    """라이브러리에 없는 이름만 참조하면 출력 없음(교집합 비어있음)."""
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["ghost"])])
    assert compile_hooks_json(proj) is None


def test_hooks_json_same_event_multiple_hooks_library_order():
    """같은 이벤트의 복수 훅은 라이브러리 선언 순서로 정렬."""
    lib = [
        HookDef(name="a", description="d", event=HookEvent.PRE_TOOL_USE, matcher="Bash", command="ca"),
        HookDef(name="b", description="d", event=HookEvent.PRE_TOOL_USE, matcher="Read", command="cb"),
    ]
    # 에이전트는 역순으로 참조하지만 출력은 라이브러리 순서(a, b)
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["b", "a"])], hook_library=lib)
    obj = json.loads(compile_hooks_json(proj))
    pre = obj["hooks"]["PreToolUse"]
    assert [g["hooks"][0]["command"] for g in pre] == ["ca", "cb"]


# ── 프론트매터 hooks 표기 ──

def test_frontmatter_hooks_name_list():
    """스킬 프론트매터 hooks는 참조 이름 flow-list로 표기."""
    skill = make_declarative("kb")
    skill.config.hooks = {"fmt-on-edit": {}, "notify-stop": {}}
    text = compile_skill(skill)
    assert "hooks: [fmt-on-edit, notify-stop]" in text


def test_frontmatter_hooks_omitted_when_empty():
    skill = make_declarative("kb")
    skill.config.hooks = None
    text = compile_skill(skill)
    assert "hooks:" not in text


# ── compile_project: 파일 생성 ──

def test_compile_project_writes_hooks_json(tmp_path):
    proj = PluginProject(
        name="p",
        agents=[_agent_with_hooks(["fmt-on-edit"])],
        hook_library=_library(),
    )
    result = compile_project(proj, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    hj = tmp_path / "hooks" / "hooks.json"
    assert hj.exists()
    raw = hj.read_bytes()
    obj = json.loads(raw.decode("utf-8"))
    assert "PostToolUse" in obj["hooks"]
    # LF 보장 (CRLF 없음) + UTF-8
    assert b"\r" not in raw


def test_compile_project_no_hooks_json_when_no_refs(tmp_path):
    proj = PluginProject(name="p", skills=[make_procedural(name="s")])
    result = compile_project(proj, tmp_path)
    assert result.ok
    assert not (tmp_path / "hooks" / "hooks.json").exists()


def test_dangling_hook_ref_warns_but_compiles(tmp_path):
    """dangling_hook_ref는 경고 — 컴파일 거부 아님."""
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["ghost"])])
    result = compile_project(proj, tmp_path)
    assert result.ok, [e.message for e in result.errors]
    assert "dangling_hook_ref" in {w.rule for w in result.warnings}
