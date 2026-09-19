# tests/compiler/test_hooks.py
"""WP-HOOK: hooks.json 컴파일 + 프론트매터 hooks 표기."""
from __future__ import annotations

import json

from daedalus.compiler import compile_hooks_json, compile_project, compile_skill
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.project import PluginProject

from tests.compiler.builders import make_agent, make_declarative, make_procedural


def _library() -> list[HookDef]:
    return [
        HookDef(name="fmt-on-edit", description="포맷", event=HookEvent.POST_TOOL_USE,
                matcher="Edit|Write",
                handlers=[CommandHook(script="run-formatter", timeout=30)]),
        HookDef(name="notify-stop", description="알림", event=HookEvent.STOP,
                handlers=[CommandHook(script="notify")]),
        HookDef(name="guard-bash", description="차단", event=HookEvent.PRE_TOOL_USE,
                matcher="Bash", handlers=[CommandHook(script="guard")]),
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
    # **플러그인 훅은 전역이다** — 라이브러리의 훅은 컴포넌트 참조 여부와
    # 무관하게 전부 실린다(guard-bash는 아무도 참조하지 않지만 배출된다).
    assert set(hooks.keys()) == {"PreToolUse", "PostToolUse", "Stop"}

    # PostToolUse: matcher 있음 + timeout 있음
    post = hooks["PostToolUse"]
    assert post == [{
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/fmt-on-edit.sh", "timeout": 30}],
    }]

    # Stop: matcher 미지정 + timeout 없음
    stop = hooks["Stop"]
    assert stop == [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify-stop.sh"}]}]


def test_hooks_json_matcher_omitted_when_event_ignores_it():
    """matcher를 받지 않는 이벤트(스키마 명시)에서는 출력에서 생략된다."""
    lib = [HookDef(name="h", description="d", event=HookEvent.CWD_CHANGED,
                   matcher="Edit", handlers=[CommandHook(script="c")])]
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["h"])], hook_library=lib)
    obj = json.loads(compile_hooks_json(proj))
    assert "matcher" not in obj["hooks"]["CwdChanged"][0]


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


def test_project_hooks_emitted_without_any_reference():
    """부착하지 않은 프로젝트 훅도 배출된다 (2026-09-07 규격 확인).

    플러그인 훅은 활성화되면 자동으로 동작한다 — `config.hooks` 참조는 켜는
    조건이 아니다. 예전에는 참조된 것만 실어, 만들어 둔 훅이 산출에서 말없이
    사라졌다(사용자 보고).
    """
    proj = PluginProject(name="p", hook_library=_library())  # 참조 없음
    obj = json.loads(compile_hooks_json(proj))
    assert set(obj["hooks"].keys()) == {"PreToolUse", "PostToolUse", "Stop"}


def test_disabled_hook_is_not_emitted():
    """`enabled=False`인 훅은 hooks.json에도 스크립트에도 나가지 않는다.

    라이브러리는 "정의를 모아 두고 고르는 곳"이라 만들어 두고 아직 켜지 않은
    훅이 있을 수 있다(사용자 확정 2026-09-07).
    """
    from daedalus.compiler.emit import compile_hook_scripts

    lib = _library()
    lib[2].enabled = False  # guard-bash (PreToolUse)
    proj = PluginProject(name="p", hook_library=lib)

    obj = json.loads(compile_hooks_json(proj))
    assert set(obj["hooks"].keys()) == {"PostToolUse", "Stop"}
    assert "guard-bash.sh" not in [n for n, _ in compile_hook_scripts(proj)]


def test_disabled_hook_still_goes_to_agent_frontmatter():
    """전역 배출을 꺼도 **에이전트가 참조하면** 그 프론트매터에는 들어간다.

    `enabled`는 플러그인 전역 훅 스위치이고, 에이전트 프론트매터 훅은 그
    에이전트 안에서만 도는 별개 경로다(사용자 확정). 스크립트 파일도 함께
    나가야 한다 — 안 그러면 에이전트가 없는 파일을 실행한다.
    """
    from daedalus.compiler.emit import compile_agent, compile_hook_scripts
    from daedalus.model.plugin.enums import BuildTarget

    lib = _library()
    lib[2].enabled = False  # guard-bash
    agent = _agent_with_hooks(["guard-bash"])
    proj = PluginProject(
        name="p", agents=[agent], hook_library=lib,
        build_target=BuildTarget.LOCAL,  # 에이전트 hooks 프론트매터는 LOCAL 전용
    )

    # 전역 등록에는 없다
    text = compile_hooks_json(proj)
    assert text is None or "PreToolUse" not in json.loads(text)["hooks"]
    # 에이전트 프론트매터에는 있다
    assert "PreToolUse" in compile_agent(agent, project=proj)
    # 스크립트 파일도 함께 나간다
    assert "guard-bash.sh" in [n for n, _ in compile_hook_scripts(proj)]


def test_hooks_json_none_when_library_empty():
    """라이브러리가 비고 합성 훅도 없으면 파일을 만들지 않는다."""
    assert compile_hooks_json(PluginProject(name="p")) is None


def test_hooks_json_none_when_ref_dangling():
    """라이브러리에 없는 이름만 참조하면 출력 없음(교집합 비어있음).

    (dangling 참조는 `dangling_hook_ref` 경고가 따로 짚는다.)"""
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["ghost"])])
    assert compile_hooks_json(proj) is None


def test_hooks_json_same_event_multiple_hooks_library_order():
    """같은 이벤트의 복수 훅은 라이브러리 선언 순서로 정렬."""
    lib = [
        HookDef(name="a", description="d", event=HookEvent.PRE_TOOL_USE, matcher="Bash", handlers=[CommandHook(script="ca")]),
        HookDef(name="b", description="d", event=HookEvent.PRE_TOOL_USE, matcher="Read", handlers=[CommandHook(script="cb")]),
    ]
    # 에이전트는 역순으로 참조하지만 출력은 라이브러리 순서(a, b)
    proj = PluginProject(name="p", agents=[_agent_with_hooks(["b", "a"])], hook_library=lib)
    obj = json.loads(compile_hooks_json(proj))
    pre = obj["hooks"]["PreToolUse"]
    assert [g["hooks"][0]["command"].rsplit("/", 1)[-1] for g in pre] == ["a.sh", "b.sh"]


# ── 프론트매터 hooks 표기 ──

def test_skill_frontmatter_emits_hooks_block():
    """스킬 훅은 settings.json과 같은 3단 블록으로 프론트매터에 나간다 (2026-09-13).

    2026-09-07에는 "SKILL.md에 hooks 키가 없다"고 판단해 뺐으나 틀렸다 — 스키마에
    "Hooks registered while this skill is active"가 있고 로컬·플러그인 스킬 모두
    훅이 실제로 돈다(실측). 예전의 이름 flow-list(`hooks: [a, b]`)는 규격 모양이
    아니었으므로 되살리지 않는다.
    """
    skill = make_declarative("kb")
    skill.config.hooks = {"fmt-on-edit": {}}
    proj = PluginProject(name="p", skills=[skill], hook_library=_library())
    front = compile_skill(skill, project=proj).split("---")[1]
    assert "hooks:" in front
    assert "hooks: [" not in front  # 이름 목록이 아니다
    assert "type: command" in front
    assert "fmt-on-edit.sh" in front


def test_skill_hooks_need_scripts_in_marketplace_build_even_if_disabled():
    """스킬이 참조한 훅은 전역으로 꺼져 있어도 스크립트 파일이 필요하다 —
    두 빌드 타깃 모두(에이전트 참조와 달리 마켓 빌드에서도 스킬 훅은 돈다)."""
    from daedalus.compiler.emit.hooks import compile_hook_scripts

    library = _library()
    for hook in library:
        hook.enabled = False
    skill = make_declarative("kb")
    skill.config.hooks = {"fmt-on-edit": {}}
    proj = PluginProject(name="p", skills=[skill], hook_library=library)
    names = [name for name, _body in compile_hook_scripts(proj)]
    assert "fmt-on-edit.sh" in names


def test_reference_skill_hooks_need_scripts(monkeypatch):
    """SKILL.md를 내는 스킬은 **전부** 자기 훅 스크립트를 끌어온다 (D6).

    참조 스킬은 `skills/<이름>/SKILL.md`를 내고 그 프론트매터에 `hooks:`
    블록이 실린다(`component_hook_groups`) — 그런데 스크립트 배출 루프는
    `is_reference_usage`로 참조 스킬을 통째로 건너뛰어, **존재하지 않는
    스크립트를 가리키는 훅**이 산출됐다. 산출 판정의 실체는
    `emit.common.emits_output_file` 하나여야 한다(원칙 1).
    """
    from daedalus.compiler.emit.hooks import compile_hook_scripts
    from tests.compiler.builders import make_reference

    library = _library()
    for hook in library:
        hook.enabled = False  # 전역 배출 경로를 닫아 스킬 루프만 남긴다
    ref = make_reference("ref-doc")
    ref.config.hooks = {"guard-bash": {}}
    proj = PluginProject(name="p", skills=[ref], hook_library=library)

    text = compile_skill(ref, project=proj)
    assert "hooks:" in text  # 프론트매터에는 이미 실린다
    names = [name for name, _body in compile_hook_scripts(proj)]
    assert "guard-bash.sh" in names


def test_components_without_an_output_file_are_still_skipped():
    """산출 파일을 내지 않는 컴포넌트는 여전히 세지 않는다 (D6의 반대편).

    외부 플러그인 에이전트는 우리 산출 파일이 없으므로 그 훅은 어디서도 돌지
    않는다 — 스크립트를 내면 아무도 쓰지 않는 파일이 산출에 남는다.
    """
    from daedalus.compiler.emit.hooks import compile_hook_scripts
    from daedalus.model.plugin.agent import ExternalAgent
    from daedalus.model.plugin.config import ExternalAgentConfig

    library = _library()
    for hook in library:
        hook.enabled = False
    external = ExternalAgent(
        name="reviewer", description="d",
        config=ExternalAgentConfig(source="alpha@mkt:review"),
    )
    external.config.hooks = {"guard-bash": {}}
    proj = PluginProject(name="p", agents=[external], hook_library=library)

    assert compile_hook_scripts(proj) == []


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


def test_enabled_roundtrips_through_serialization():
    """빌드 포함 스위치는 저장/로드를 견딘다. 구버전 파일(키 부재)은 True."""
    from daedalus.model.serialize import deserialize_project, serialize_project

    lib = _library()
    lib[0].enabled = False
    proj = PluginProject(name="p", hook_library=lib)

    data = serialize_project(proj)
    loaded = deserialize_project(data)
    assert [h.enabled for h in loaded.hook_library] == [False, True, True]

    del data["hook_library"][0]["enabled"]  # 구버전 파일
    assert deserialize_project(data).hook_library[0].enabled is True
