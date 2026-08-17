"""WP-HOOK: hook_library 직렬화 라운드트립."""
from __future__ import annotations

import json

from daedalus.model.plugin.hook import (
    AgentHook,
    CommandHook,
    HookDef,
    HookEvent,
    HookShell,
    HttpHook,
    McpToolHook,
    PromptHook,
)
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _sample_library() -> list[HookDef]:
    return [
        HookDef(name="fmt", description="포맷", event=HookEvent.POST_TOOL_USE,
                matcher="Edit|Write",
                handlers=[CommandHook(script="fmt", timeout=30)]),
        HookDef(name="notify", description="알림", event=HookEvent.STOP,
                handlers=[CommandHook(script="notify")]),
    ]


def test_hook_library_roundtrip_json():
    proj = PluginProject(name="p", hook_library=_sample_library())
    blob = json.dumps(serialize_project(proj))
    out = deserialize_project(json.loads(blob))

    assert len(out.hook_library) == 2
    by_name = {h.name: h for h in out.hook_library}

    fmt = by_name["fmt"]
    assert fmt.event is HookEvent.POST_TOOL_USE
    assert fmt.matcher == "Edit|Write"
    assert fmt.handlers[0].script == "fmt"
    assert fmt.handlers[0].timeout == 30
    assert fmt.id == proj.hook_library[0].id  # id 보존
    assert fmt.handlers[0].id == proj.hook_library[0].handlers[0].id

    notify = by_name["notify"]
    assert notify.event is HookEvent.STOP
    assert notify.matcher == ""
    assert notify.handlers[0].timeout is None


def test_all_handler_types_roundtrip():
    """다섯 타입 전부 왕복해야 한다 — 하나라도 빠지면 저장 시 조용히 사라진다."""
    hooks = [
        HookDef(name="a", description="", handlers=[CommandHook(
            script="run", args=["-x"], shell=HookShell.BASH,
            run_async=True, async_rewake=True,
            condition="Bash(git *)", status_message="검사 중", timeout=7,
        )]),
        HookDef(name="b", description="", handlers=[PromptHook(
            prompt="p", model="haiku", continue_on_block=True)]),
        HookDef(name="c", description="", handlers=[AgentHook(prompt="q", model="opus")]),
        HookDef(name="d", description="", handlers=[HttpHook(
            url="https://x", headers={"H": "1"}, allowed_env_vars=["T"])]),
        HookDef(name="e", description="", handlers=[McpToolHook(
            server="s", tool="t", tool_input={"k": "v"})]),
    ]
    proj = PluginProject(name="p", hook_library=hooks)
    out = deserialize_project(json.loads(json.dumps(serialize_project(proj))))

    got = {h.name: h.handlers[0] for h in out.hook_library}
    assert got["a"].to_json() == hooks[0].handlers[0].to_json()
    assert got["a"].shell is HookShell.BASH
    assert got["b"].to_json() == hooks[1].handlers[0].to_json()
    assert got["c"].to_json() == hooks[2].handlers[0].to_json()
    assert got["d"].to_json() == hooks[3].handlers[0].to_json()
    assert got["e"].to_json() == hooks[4].handlers[0].to_json()


def test_multiple_handlers_roundtrip_in_order():
    proj = PluginProject(name="p", hook_library=[HookDef(
        name="multi", description="",
        handlers=[CommandHook(script="a"), AgentHook(prompt="b"), PromptHook(prompt="c")],
    )])
    out = deserialize_project(json.loads(json.dumps(serialize_project(proj))))
    assert [h.kind for h in out.hook_library[0].handlers] == ["command", "agent", "prompt"]


def test_legacy_command_hook_migrated_on_load():
    """구버전 파일(훅 하나 = 커맨드 하나)은 CommandHook 하나로 감싸진다."""
    proj = PluginProject(name="p", hook_library=_sample_library())
    data = json.loads(json.dumps(serialize_project(proj)))
    # 저장 파일을 구버전 형태로 되돌린다
    data["format"] = 1
    data["hook_library"][0].pop("handlers")
    data["hook_library"][0]["command"] = "legacy-fmt"
    data["hook_library"][0]["timeout"] = 11

    out = deserialize_project(data)
    handler = out.hook_library[0].handlers[0]
    assert handler.kind == "command"
    assert handler.script == "legacy-fmt"
    assert handler.timeout == 11


def test_legacy_hook_without_command_gets_no_handler():
    proj = PluginProject(name="p", hook_library=_sample_library())
    data = json.loads(json.dumps(serialize_project(proj)))
    data["format"] = 1
    data["hook_library"][0].pop("handlers")

    out = deserialize_project(data)
    assert out.hook_library[0].handlers == []


def test_unknown_handler_kind_is_skipped():
    """미래 버전의 핸들러 타입을 만나도 로드가 죽지 않는다."""
    proj = PluginProject(name="p", hook_library=_sample_library())
    data = json.loads(json.dumps(serialize_project(proj)))
    data["hook_library"][0]["handlers"].append({"kind": "quantum", "id": "x"})

    out = deserialize_project(data)
    assert [h.kind for h in out.hook_library[0].handlers] == ["command"]


def test_empty_hook_library_roundtrip():
    proj = PluginProject(name="p")
    out = deserialize_project(serialize_project(proj))
    assert out.hook_library == []


def test_config_hooks_roundtrip_preserves_keys():
    """config.hooks(이름 참조 dict)도 라운드트립된다."""
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.config import AgentConfig
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState

    s = SimpleState(name="s")
    fsm = StateMachine(name="f", states=[s], initial_state=s)
    cfg = AgentConfig()
    cfg.hooks = {"fmt": {}, "notify": {"timeout": 5}}
    ag = AgentDefinition(fsm=fsm, name="ag", description="d", config=cfg)
    proj = PluginProject(name="p", agents=[ag], hook_library=_sample_library())

    out = deserialize_project(json.loads(json.dumps(serialize_project(proj))))
    assert out.agents[0].config.hooks == {"fmt": {}, "notify": {"timeout": 5}}
