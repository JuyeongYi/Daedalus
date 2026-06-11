"""WP-HOOK: hook_library 직렬화 라운드트립."""
from __future__ import annotations

import json

from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project


def _sample_library() -> list[HookDef]:
    return [
        HookDef(name="fmt", description="포맷", event=HookEvent.POST_TOOL_USE,
                matcher="Edit|Write", command="fmt", timeout=30),
        HookDef(name="notify", description="알림", event=HookEvent.STOP,
                command="notify"),
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
    assert fmt.command == "fmt"
    assert fmt.timeout == 30
    assert fmt.id == proj.hook_library[0].id  # id 보존

    notify = by_name["notify"]
    assert notify.event is HookEvent.STOP
    assert notify.matcher == ""
    assert notify.timeout is None


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
