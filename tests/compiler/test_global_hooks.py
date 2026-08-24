"""전역 훅(A1)이 컴파일·검증에 어떻게 합류하는가.

핵심 계약은 **주입**이다 — 컴파일러와 검증기는 파일시스템을 읽지 않고,
호출자가 해소한 dict/이름 집합을 받는다. 그래서 여기서는 파일을 깔지 않고
해소된 값을 직접 넘겨 그 계약을 고정한다(파일 로딩 자체는
`tests/model/plugin/test_hook_store.py`가 본다).
"""
from __future__ import annotations

import json

from daedalus.compiler.emit import compile_hook_scripts, compile_hooks_json
from daedalus.compiler.project_compiler import compile_project
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator


def _hook(name: str, script: str = "echo hi") -> HookDef:
    return HookDef(
        name=name, description="", event=HookEvent.PRE_TOOL_USE, matcher="Edit",
        handlers=[CommandHook(script=script)],
    )


def _project_referencing(hook_name: str, library=()) -> PluginProject:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name="worker", description="d")
    skill.config.hooks = {hook_name: {}}
    return PluginProject(name="p", skills=[skill], hook_library=list(library))


# --- 컴파일 ---


def test_global_only_hook_compiles_when_injected():
    """프로젝트 라이브러리에 없어도 주입된 훅이면 hooks.json에 실린다."""
    project = _project_referencing("fmt")
    resolved = {"fmt": _hook("fmt", "prettier --write")}

    text = compile_hooks_json(project, resolved)
    assert text is not None
    hooks = json.loads(text)["hooks"]
    assert "PreToolUse" in hooks

    scripts = dict(compile_hook_scripts(project, resolved))
    assert any("prettier --write" in body for body in scripts.values())


def test_without_injection_global_hook_is_absent():
    """주입하지 않으면 종전대로 프로젝트 라이브러리만 본다 (하위 호환 게이트)."""
    project = _project_referencing("fmt")
    text = compile_hooks_json(project)
    assert text is None  # 참조는 있지만 정의가 없어 배출할 것이 없다


def test_project_hook_wins_in_compile():
    """동명이면 프로젝트 정의가 산출에 나간다 — resolve_hooks의 우선순위 그대로."""
    project = _project_referencing("fmt", library=[_hook("fmt", "project-cmd")])
    resolved = {"fmt": project.hook_library[0]}  # resolve_hooks가 만들어 주는 것

    scripts = dict(compile_hook_scripts(project, resolved))
    assert any("project-cmd" in body for body in scripts.values())
    assert not any("global-cmd" in body for body in scripts.values())


def test_injection_does_not_change_output_without_globals():
    """전역이 없으면 산출이 바이트 단위로 불변이다."""
    project = _project_referencing("fmt", library=[_hook("fmt")])
    baseline = compile_hooks_json(project)
    injected = compile_hooks_json(project, {h.name: h for h in project.hook_library})
    assert injected == baseline


def test_compile_project_writes_global_hook(tmp_path):
    project = _project_referencing("fmt")
    result = compile_project(
        project, tmp_path, resolved_hooks={"fmt": _hook("fmt", "prettier --write")},
    )
    assert result.ok, [e.message for e in result.errors]
    hooks_json = tmp_path / "hooks" / "hooks.json"
    assert hooks_json.exists()
    assert "PreToolUse" in json.loads(hooks_json.read_text(encoding="utf-8"))["hooks"]


# --- 검증 ---


def test_dangling_hook_ref_without_known_names():
    """이름 집합을 주지 않으면 전역 훅 참조가 dangling으로 보인다(종전 동작)."""
    project = _project_referencing("fmt")
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "dangling_hook_ref" in rules


def test_known_hook_names_silences_the_warning():
    project = _project_referencing("fmt")
    rules = [
        e.rule
        for e in Validator.validate_project(project, known_hook_names=frozenset({"fmt"}))
    ]
    assert "dangling_hook_ref" not in rules


def test_typo_still_warns_with_known_names():
    """전역을 알려 줘도 없는 이름은 여전히 경고다 — 오타가 조용히 통과하면 안 된다."""
    project = _project_referencing("fmtt")
    rules = [
        e.rule
        for e in Validator.validate_project(project, known_hook_names=frozenset({"fmt"}))
    ]
    assert "dangling_hook_ref" in rules


def test_compile_gate_uses_resolved_names(tmp_path):
    """컴파일 경고에도 전역 훅 참조가 dangling으로 나오지 않는다."""
    project = _project_referencing("fmt")
    result = compile_project(
        project, tmp_path, resolved_hooks={"fmt": _hook("fmt")},
    )
    assert "dangling_hook_ref" not in [w.rule for w in result.warnings]
