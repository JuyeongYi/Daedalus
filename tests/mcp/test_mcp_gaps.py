"""MCP 표면의 구멍 메우기 — 훅·참조 노드·프로젝트 속성·호출 포트 제거.

실제로 그래프를 만들어 보다가 드러난 빈 자리들이다. 어느 것이든 "GUI에서는
되는데 AI는 못 한다"가 되면 협업이 한쪽에서만 성립하므로, 편집 도구는 반영뿐
아니라 **undo까지** 확인한다(test_mcp_tools.py와 같은 규약).
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.plugin.hook import HookEvent
from daedalus.model.plugin.skill import ProceduralSkill, ReferenceSkill
from daedalus.model.project import PluginProject


@pytest.fixture
def window(qapp):
    from daedalus.view.app import MainWindow

    s1 = SimpleState(name="Start")
    fsm = StateMachine(name="f", initial_state=s1, states=[s1], final_states=[s1])
    skill = ProceduralSkill(fsm=fsm, name="init", description="초기화")
    ref = ReferenceSkill(name="guide", description="참조 문서")
    project = PluginProject(name="p", skills=[skill, ref])

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


@pytest.fixture
def tools(window):
    from daedalus.mcp.tools import DaedalusTools

    return DaedalusTools(window)


# --- 에이전트 호출 포트 조회·제거 ---


def test_get_component_exposes_call_agents(tools):
    """포트를 만들어 놓고도 조회할 수 없으면 AI가 자기 상태를 못 본다."""
    tools.add_agent_call("init", "review")
    info = tools.get_component("init")
    assert [c["name"] for c in info["call_agents"]] == ["review"]


def test_remove_agent_call_removes_port(tools):
    tools.add_agent_call("init", "review")
    result = tools.remove_agent_call("init", "review")
    assert result["call_agents"] == []

    tools.undo()
    assert [e.name for e in tools._find_component("init").call_agents] == ["review"]


def test_remove_agent_call_reports_orphaned_transitions(tools):
    """포트를 지우면 그 포트를 쓰던 전이가 고아가 된다 — 조용히 두지 않는다."""
    tools.create_agent("worker")
    tools.place_component("init", 0, 0)
    tools.place_component("worker", 200, 0)
    tools.add_agent_call("init", "review")
    tools.connect_states("init", "worker", trigger="review")

    result = tools.remove_agent_call("init", "review")
    assert result["orphaned_transitions"] == [["init", "worker"]]


def test_remove_unknown_call_port_lists_existing(tools):
    tools.add_agent_call("init", "review")
    with pytest.raises(ValueError, match="review"):
        tools.remove_agent_call("init", "nope")


# --- 프로젝트 속성 ---


def test_set_project_properties_updates_manifest_fields(tools, window):
    result = tools.set_project_properties(
        name="ue-perf", description="언리얼 성능", version="1.2.0"
    )
    assert result["name"] == "ue-perf"
    assert window._project.version == "1.2.0"

    tools.undo()
    assert window._project.name == "p", "한 번의 undo로 전부 되돌아가야 한다"
    assert window._project.version == "0.1.0"


def test_set_project_properties_ignores_blank_fields(tools, window):
    tools.set_project_properties(version="2.0.0")
    assert window._project.name == "p", "빈 값은 건드리지 않는다"
    assert window._project.version == "2.0.0"


def test_set_project_properties_switches_build_target(tools, window):
    tools.set_project_properties(build_target="local")
    assert window._project.build_target is BuildTarget.LOCAL


def test_set_project_properties_rejects_unknown_target(tools):
    with pytest.raises(ValueError, match="marketplace"):
        tools.set_project_properties(build_target="nope")


def test_set_project_properties_no_args_is_noop(tools):
    result = tools.set_project_properties()
    assert result["changed"] == []


# --- 설명 / when_to_use ---


def test_set_component_description_is_undoable(tools):
    """이전에는 이 편집만 Ctrl+Z가 듣지 않았다."""
    tools.set_component_description("init", "새 설명")
    assert tools._find_component("init").description == "새 설명"

    tools.undo()
    assert tools._find_component("init").description == "초기화"


def test_set_component_when_to_use(tools):
    tools.set_component_when_to_use("init", "프로젝트를 처음 열 때")
    assert tools.get_component("init")["when_to_use"] == "프로젝트를 처음 열 때"

    tools.undo()
    assert tools.get_component("init")["when_to_use"] == ""


# --- 훅 라이브러리 ---


def test_create_hook_adds_to_library(tools, window):
    result = tools.create_hook(
        "guard-bash", event="PreToolUse", matcher="Bash",
        handlers=[{"type": "command", "command": "echo hi", "timeout": 5}],
    )
    assert result["event"] == "PreToolUse"
    library = window._project.hook_library
    assert [h.name for h in library] == ["guard-bash"]
    assert library[0].handlers[0].timeout == 5

    tools.undo()
    assert window._project.hook_library == []


def test_create_hook_command_shortcut(tools, window):
    """command 인자는 핸들러 하나짜리 훅을 만드는 지름길이다."""
    tools.create_hook("h", command="x")
    handler = window._project.hook_library[0].handlers[0]
    assert handler.kind == "command" and handler.script == "x"
    assert handler.timeout is None


def test_create_hook_rejects_duplicate_name(tools):
    tools.create_hook("h", command="x")
    with pytest.raises(ValueError, match="이미"):
        tools.create_hook("h", command="y")


def test_create_hook_rejects_unknown_event(tools):
    with pytest.raises(ValueError, match="SessionStart"):
        tools.create_hook("h", event="Nope")


def test_create_hook_warns_about_matcher_on_event_that_ignores_it(tools):
    """조용히 무시되면 사용자가 원인을 못 찾는다."""
    result = tools.create_hook("h", event="CwdChanged", matcher="Bash")
    assert "note" in result


def test_create_hook_with_handler_specs(tools, window):
    """CC 스키마 그대로의 핸들러 목록을 받는다 — command 훅만이 아니다."""
    tools.create_hook("h", event="Stop", handlers=[
        {"type": "agent", "prompt": "확인하라", "timeout": 60},
        {"type": "http", "url": "https://x", "statusMessage": "보내는 중"},
    ])
    hook = window._project.hook_library[0]
    assert [h.kind for h in hook.handlers] == ["agent", "http"]
    assert hook.handlers[0].to_json()["timeout"] == 60
    assert hook.handlers[1].to_json()["statusMessage"] == "보내는 중"


def test_create_hook_rejects_unknown_handler_type(tools):
    with pytest.raises(ValueError, match="mcp_tool"):
        tools.create_hook("h", handlers=[{"type": "quantum"}])


def test_create_hook_rejects_property_not_on_that_type(tools):
    """agent 훅에 command를 주면 조용히 무시되는 대신 거부한다."""
    with pytest.raises(ValueError, match="command"):
        tools.create_hook("h", handlers=[{"type": "agent", "command": "x"}])


def test_create_hook_without_handlers_notes_it(tools):
    result = tools.create_hook("h")
    assert "note" in result


def test_update_hook_changes_fields(tools, window):
    tools.create_hook("h", command="old", matcher="Bash")
    tools.update_hook(
        "h", handlers=[{"type": "command", "command": "new"}], event="PostToolUse",
    )

    hook = window._project.hook_library[0]
    assert hook.handlers[0].script == "new"
    assert hook.event is HookEvent.POST_TOOL_USE

    tools.undo()
    assert hook.handlers[0].script == "old"
    assert hook.event is HookEvent.PRE_TOOL_USE


def test_update_hook_clears_matcher_with_empty_string(tools, window):
    tools.create_hook("h", command="x", matcher="Bash")
    tools.update_hook("h", matcher="")
    assert window._project.hook_library[0].matcher == ""


def test_update_hook_omitted_handlers_are_untouched(tools, window):
    tools.create_hook("h", command="keep")
    tools.update_hook("h", matcher="Bash")
    assert window._project.hook_library[0].handlers[0].script == "keep"


def test_update_hook_unknown_name(tools):
    with pytest.raises(ValueError, match="없습니다"):
        tools.update_hook("nope", matcher="x")


# --- 훅 → 서브에이전트 프론트매터 ---


def test_hook_frontmatter_preview_emits_yaml(tools):
    tools.create_hook("guard", event="PreToolUse", matcher="Bash", command="./a.sh")
    out = tools.hook_frontmatter_preview(["guard"])
    assert out["yaml"].startswith("hooks:\n")
    assert "PreToolUse:" in out["yaml"]
    assert "- matcher: Bash" in out["yaml"]
    assert "- type: command" in out["yaml"]


def test_hook_frontmatter_preview_defaults_to_whole_library(tools):
    tools.create_hook("a", command="x")
    tools.create_hook("b", event="Stop", command="y")
    assert tools.hook_frontmatter_preview()["hooks"] == ["a", "b"]


def test_hook_frontmatter_preview_rejects_unknown_name(tools):
    with pytest.raises(ValueError, match="ghost"):
        tools.hook_frontmatter_preview(["ghost"])


def test_hook_frontmatter_preview_skips_handlerless_hooks(tools):
    tools.create_hook("empty")
    out = tools.hook_frontmatter_preview()
    assert out["yaml"] == ""


def test_list_hook_events_covers_schema(tools):
    out = tools.list_hook_events()
    assert len(out["events"]) == 31
    by_name = {e["name"]: e for e in out["events"]}
    assert by_name["PreToolUse"]["supports_matcher"] is True
    assert by_name["CwdChanged"]["supports_matcher"] is False
    assert out["handler_types"] == ["command", "prompt", "agent", "http", "mcp_tool"]


def test_delete_hook_removes_definition(tools, window):
    tools.create_hook("h", command="x")
    tools.delete_hook("h")
    assert window._project.hook_library == []

    tools.undo()
    assert [h.name for h in window._project.hook_library] == ["h"]


def test_delete_hook_reports_dangling_references(tools):
    tools.create_hook("h", command="x")
    tools.set_component_hooks("init", ["h"])
    result = tools.delete_hook("h")
    assert result["still_referenced_by"] == ["init"]


def test_set_component_hooks_records_reference(tools):
    tools.create_hook("h", command="x")
    tools.set_component_hooks("init", ["h"])
    assert tools._find_component("init").config.hooks == {"h": {}}

    tools.undo()
    # 선언 기본값은 {}가 아니라 None이다 — undo는 그 원래 값으로 되돌린다
    assert tools._find_component("init").config.hooks is None


def test_set_component_hooks_rejects_unknown_hook(tools):
    """오타는 컴파일까지 조용히 흘러가 경고로만 드러난다 — 여기서 막는다."""
    tools.create_hook("real", command="x")
    with pytest.raises(ValueError, match="real"):
        tools.set_component_hooks("init", ["typo"])


def test_set_component_hooks_accepts_global_hook(tools, tmp_path, monkeypatch):
    """전역 훅(A1) 이름도 유효하다 — 피커가 후보로 내는 이름을 도구가 거절하면
    둘이 다른 말을 하는 셈이다."""
    import json

    from daedalus.model.plugin import hook_store
    from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent

    directory = tmp_path / "globalhooks"
    directory.mkdir()
    monkeypatch.setattr(hook_store, "global_hooks_dir", lambda home_dir=None: directory)
    (directory / "shared.json").write_text(
        json.dumps(hook_store.hook_to_json(HookDef(
            name="shared", description="", event=HookEvent.PRE_TOOL_USE,
            handlers=[CommandHook(script="echo hi")],
        ))),
        encoding="utf-8",
    )

    tools.set_component_hooks("init", ["shared"])
    assert list(tools._find_component("init").config.hooks) == ["shared"]


def test_set_component_hooks_preserves_overrides(tools):
    tools.create_hook("a", command="x")
    tools.create_hook("b", command="y")
    tools.set_component_hooks("init", ["a"])
    tools._find_component("init").config.hooks["a"] = {"timeout": 9}

    tools.set_component_hooks("init", ["a", "b"])
    assert tools._find_component("init").config.hooks["a"] == {"timeout": 9}


def test_get_project_lists_hook_library(tools):
    tools.create_hook("h", command="x", event="SessionEnd")
    entry = tools.get_project()["hook_library"][0]
    assert entry["name"] == "h" and entry["event"] == "SessionEnd"
    assert entry["handler_count"] == 1


def test_get_project_hook_summary_omits_script_bodies(tools):
    """개요에 셸 스크립트 전문을 실으면 프로젝트를 볼 때마다 그 값을 다 낸다 (Q1)."""
    tools.create_hook("h", command="echo 매우-긴-스크립트", event="SessionEnd")
    entry = tools.get_project()["hook_library"][0]
    assert "scripts" not in entry and "handlers" not in entry


def test_get_hook_returns_full_definition(tools):
    tools.create_hook("h", command="echo hi", event="SessionEnd", matcher="")
    detail = tools.get_hook("h")
    # 개요 필드를 그대로 품고, 전문을 더한다
    assert detail["name"] == "h" and detail["handler_count"] == 1
    assert detail["handlers"][0]["type"] == "command"
    assert "echo hi" in "\n".join(detail["scripts"].values())


def test_get_hook_unknown_name(tools):
    with pytest.raises(ValueError, match="없습니다"):
        tools.get_hook("nope")


# --- 참조 노드 ---


def test_place_reference_creates_node(tools, window):
    result = tools.place_reference("guide", 100, 50)
    assert result["index"] == 0
    assert len(window._project_vm.reference_vms) == 1
    # 모델에도 동기화된다 (저장·컴파일의 단일 진실)
    assert [rp.skill_name for rp in window._project.reference_placements] == ["guide"]

    tools.undo()
    assert window._project_vm.reference_vms == []


def test_place_reference_allows_multiple_instances(tools):
    """참조 노드는 상태가 아니라 여러 상태가 공유하는 문서라 중복 배치가 정상이다."""
    tools.place_reference("guide", 0, 0)
    second = tools.place_reference("guide", 300, 0)
    assert second["index"] == 1
    assert len(tools.get_project()["references"]) == 2


def test_place_reference_rejects_non_reference_skill(tools):
    with pytest.raises(ValueError, match="place_component"):
        tools.place_reference("init")


def test_link_reference_connects_node(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    result = tools.link_reference("init", "guide")
    assert result["created"] is True
    assert tools.get_project()["references"][0]["linked_nodes"] == ["init"]

    tools.undo()
    assert window._project_vm.reference_links == []


def test_link_reference_is_idempotent(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")
    tools.link_reference("init", "guide")
    assert len(window._project_vm.reference_links) == 1


def test_unlink_reference_drops_link_but_keeps_node(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")

    tools.unlink_reference("init", "guide")
    assert window._project_vm.reference_links == []
    assert len(window._project_vm.reference_vms) == 1


def test_unlink_reference_without_link_errors(tools):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    with pytest.raises(ValueError, match="참조 연결이 없습니다"):
        tools.unlink_reference("init", "guide")


def test_unplace_reference_removes_node_and_links(tools, window):
    tools.place_component("init", 0, 0)
    tools.place_reference("guide", 200, 0)
    tools.link_reference("init", "guide")

    result = tools.unplace_reference("guide")
    assert result["removed_links"] == 1
    assert window._project_vm.reference_vms == []

    tools.undo()
    assert len(window._project_vm.reference_vms) == 1
    assert len(window._project_vm.reference_links) == 1, "링크도 함께 돌아와야 한다"


def test_unplace_reference_index_out_of_range(tools):
    tools.place_reference("guide", 0, 0)
    with pytest.raises(ValueError, match="1개뿐"):
        tools.unplace_reference("guide", index=3)


def test_link_reference_without_placed_reference_errors(tools):
    tools.place_component("init", 0, 0)
    with pytest.raises(ValueError, match="참조 노드가 없습니다"):
        tools.link_reference("init", "guide")


# --- 진행 훅 토글 (G4) ---


def test_set_project_properties_toggles_progress_hook(tools, window):
    assert window._project.emit_progress_hook is True

    result = tools.set_project_properties(emit_progress_hook=False)
    assert result["emit_progress_hook"] is False
    assert window._project.emit_progress_hook is False

    tools.undo()
    assert window._project.emit_progress_hook is True


def test_set_project_properties_progress_hook_none_is_untouched(tools, window):
    tools.set_project_properties(emit_progress_hook=False)
    tools.set_project_properties(name="renamed")
    assert window._project.emit_progress_hook is False, "None(생략)은 건드리지 않는다"


def test_set_project_properties_progress_hook_joins_macro_with_other_fields(tools, window):
    """다른 필드와 함께 오면 1 undo 단위로 묶인다."""
    tools.set_project_properties(version="9.9.9", emit_progress_hook=False)
    assert window._project.version == "9.9.9"
    assert window._project.emit_progress_hook is False

    tools.undo()
    assert window._project.version == "0.1.0"
    assert window._project.emit_progress_hook is True


# --- 진입점 프리셋 (G5) ---


def test_set_entry_preset_applies_and_undoes(tools, window):
    comp = tools._find_component("init")
    assert comp.config.user_invocable is None

    result = tools.set_entry_preset("init", "entry")
    assert result["changed"] is True
    assert result["preset"] == "entry"
    assert comp.config.user_invocable is True
    assert comp.config.disable_model_invocation is False

    tools.undo()
    assert comp.config.user_invocable is None
    assert comp.config.disable_model_invocation is None


def test_set_entry_preset_same_preset_is_noop(tools):
    tools.set_entry_preset("init", "entry")
    result = tools.set_entry_preset("init", "entry")
    assert result["changed"] is False
    assert result["before"] == "entry"


def test_set_entry_preset_rejects_unknown_preset(tools):
    with pytest.raises(ValueError, match="default"):
        tools.set_entry_preset("init", "nope")


def test_set_entry_preset_rejects_fixed_kind(tools):
    """ReferenceSkill은 user_invocable/disable_model_invocation이 고정이다."""
    with pytest.raises(ValueError, match="진입점 프리셋을 적용할 수 없습니다"):
        tools.set_entry_preset("guide", "entry")


def test_set_entry_preset_uses_same_realization_as_canvas(tools, window):
    """캔버스 메뉴·프론트매터 콤보와 같은 apply_entry_preset을 부른다 —
    current_entry_preset으로 되짚어도 같은 프리셋이 나와야 한다."""
    from daedalus.view.actions.entrypoint import EntryPreset, current_entry_preset

    tools.set_entry_preset("init", "user_only")
    comp = tools._find_component("init")
    assert current_entry_preset(comp) is EntryPreset.USER_ONLY


# --- 에이전트 호출 포트 일괄 교체 (G6) ---


def test_set_agent_calls_replaces_whole_list(tools, window):
    tools.add_agent_call("init", "legacy")
    result = tools.set_agent_calls(
        "init",
        [
            {"name": "review", "description": "코드 리뷰 위임", "color": "#ff8844"},
            {"name": "profile"},
        ],
    )
    assert result["call_agents"] == ["review", "profile"]
    comp = tools._find_component("init")
    assert [e.name for e in comp.call_agents] == ["review", "profile"]
    assert comp.call_agents[0].description == "코드 리뷰 위임"

    tools.undo()
    assert [e.name for e in tools._find_component("init").call_agents] == ["legacy"]


def test_set_agent_calls_rejects_duplicate_names(tools):
    with pytest.raises(ValueError, match="review"):
        tools.set_agent_calls("init", [{"name": "review"}, {"name": "review"}])


def test_set_agent_calls_rejects_non_procedural_skill(tools):
    with pytest.raises(ValueError, match="ProceduralSkill"):
        tools.set_agent_calls("guide", [{"name": "review"}])


def test_set_agent_calls_accepts_bare_strings(tools):
    result = tools.set_agent_calls("init", ["a", "b"])
    assert result["call_agents"] == ["a", "b"]


# --- 전역 훅 조회 + 프로젝트로 복사 (G7) ---


def _write_global_hook(tmp_path, monkeypatch, filename="shared", *, script="echo hi"):
    import json

    from daedalus.model.plugin import hook_store
    from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent

    directory = tmp_path / "globalhooks"
    directory.mkdir(exist_ok=True)
    monkeypatch.setattr(hook_store, "global_hooks_dir", lambda home_dir=None: directory)
    (directory / f"{filename}.json").write_text(
        json.dumps(hook_store.hook_to_json(HookDef(
            name=filename, description="공유 훅", event=HookEvent.PRE_TOOL_USE,
            handlers=[CommandHook(script=script)],
        ))),
        encoding="utf-8",
    )
    return directory


def test_get_project_lists_global_hooks(tools, tmp_path, monkeypatch):
    _write_global_hook(tmp_path, monkeypatch, "shared")
    info = tools.get_project()
    assert [h["name"] for h in info["global_hooks"]] == ["shared"]
    # 개요만 — 스크립트 본문/핸들러는 안 실린다(get_hook 전용, Q1과 같은 정책).
    assert "scripts" not in info["global_hooks"][0]


def test_get_project_hides_global_hook_shadowed_by_project(tools, tmp_path, monkeypatch):
    _write_global_hook(tmp_path, monkeypatch, "shared")
    tools.create_hook("shared", command="local override")
    info = tools.get_project()
    assert info["global_hooks"] == []
    assert [h["name"] for h in info["hook_library"]] == ["shared"]


def test_copy_global_hook_adds_and_undoes(tools, window, tmp_path, monkeypatch):
    _write_global_hook(tmp_path, monkeypatch, "shared", script="echo copied")
    result = tools.copy_global_hook("shared")
    assert result["name"] == "shared"
    library = window._project.hook_library
    assert [h.name for h in library] == ["shared"]
    assert library[0].handlers[0].script == "echo copied"

    tools.undo()
    assert window._project.hook_library == []


def test_copy_global_hook_unknown_name(tools, tmp_path, monkeypatch):
    _write_global_hook(tmp_path, monkeypatch, "shared")
    with pytest.raises(ValueError, match="shared"):
        tools.copy_global_hook("nope")


def test_copy_global_hook_rejects_when_already_in_project(tools, tmp_path, monkeypatch):
    _write_global_hook(tmp_path, monkeypatch, "shared")
    tools.create_hook("shared", command="local")
    with pytest.raises(ValueError, match="이미"):
        tools.copy_global_hook("shared")


# --- 훅 프리셋 생성 (G8) ---


def test_list_hook_presets_lists_builtin(tools):
    out = tools.list_hook_presets()
    names = [p["name"] for p in out["presets"]]
    assert "format-on-edit" in names
    entry = next(p for p in out["presets"] if p["name"] == "format-on-edit")
    assert entry["event"] == "PostToolUse"
    assert entry["handler_types"] == ["command"]


def test_create_hook_from_preset_copies_content(tools, window):
    result = tools.create_hook("my-formatter", preset="format-on-edit")
    assert result["event"] == "PostToolUse"
    hook = window._project.hook_library[0]
    assert hook.name == "my-formatter"
    assert hook.matcher == "Edit|Write"
    assert hook.handlers[0].kind == "command"

    tools.undo()
    assert window._project.hook_library == []


def test_create_hook_preset_rejects_unknown_name(tools):
    with pytest.raises(ValueError, match="알 수 없는 훅 프리셋"):
        tools.create_hook("h", preset="does-not-exist")


def test_create_hook_preset_rejects_mixing_with_handlers(tools):
    with pytest.raises(ValueError, match="preset"):
        tools.create_hook(
            "h", preset="format-on-edit",
            handlers=[{"type": "command", "command": "x"}],
        )


def test_create_hook_preset_rejects_mixing_with_matcher(tools):
    with pytest.raises(ValueError, match="preset"):
        tools.create_hook("h", preset="format-on-edit", matcher="Bash")


# --- 카탈로그 후보 조회 (G9) ---


def test_list_tool_candidates_includes_builtins_and_agents(tools):
    tools.create_agent("worker")
    out = tools.list_tool_candidates()
    assert "Read" in out["candidates"]  # CC_BUILTIN_TOOLS
    assert "Agent(worker)" in out["candidates"]


# --- config 비기본값만 (Q3) ---


def test_get_component_config_only_shows_non_default_values(tools):
    info = tools.get_component("init")
    # 아무것도 바꾸지 않았으면 전부 선언 기본값이라 비어 있어야 한다.
    assert info["config"] == {}


def test_get_component_config_shows_only_changed_fields(tools):
    tools.set_entry_preset("init", "entry")
    info = tools.get_component("init")
    assert info["config"] == {
        "user_invocable": True,
        "disable_model_invocation": False,
    }


# --- get_project 구획 선택 (Q4) ---


def test_get_project_sections_default_is_full(tools):
    """생략하면 기존 응답과 완전히 같은 키 집합이어야 한다(하위 호환)."""
    full = tools.get_project()
    assert set(full) == {
        "name", "description", "version", "build_target", "saved_path",
        "emit_progress_hook", "mcp_server_defs", "can_undo", "can_redo",
        "skills", "agents", "placements", "transitions", "references",
        "blackboard_classes", "hook_library", "global_hooks",
    }


def test_get_project_sections_filters_to_requested_groups(tools):
    result = tools.get_project(sections=["components"])
    assert set(result) == {"skills", "agents"}


def test_get_project_sections_combines_multiple_groups(tools):
    result = tools.get_project(sections=["meta", "hooks"])
    assert set(result) == {
        "name", "description", "version", "build_target", "saved_path",
        "emit_progress_hook", "mcp_server_defs", "can_undo", "can_redo",
        "hook_library", "global_hooks",
    }


def test_get_project_sections_rejects_unknown_name(tools):
    with pytest.raises(ValueError, match="nope"):
        tools.get_project(sections=["nope"])
