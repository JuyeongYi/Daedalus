"""전역 훅 저장소 — `~/.daedalus/hooks/*.json` 로딩과 2단 병합 (A1).

훅은 프로젝트를 넘어 재사용된다. 카탈로그(도구 후보)와 같은 의미론 —
전역 + 프로젝트, 이름 충돌 시 프로젝트 우선 — 을 여기서 고정한다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent, PromptHook
from daedalus.model.plugin.hook_store import (
    global_hooks_dir,
    hook_to_json,
    load_global_hooks,
    resolve_hooks,
)
from daedalus.model.project import PluginProject


def _hook(name: str, *, event=HookEvent.PRE_TOOL_USE, script="echo hi") -> HookDef:
    return HookDef(
        name=name, description="d", event=event, matcher="Edit",
        handlers=[CommandHook(script=script)],
    )


@pytest.fixture
def home(tmp_path):
    """전역 훅 폴더를 가진 가짜 홈."""
    (tmp_path / ".daedalus" / "hooks").mkdir(parents=True)
    return tmp_path


def _write(home, name: str, hook: HookDef) -> None:
    path = global_hooks_dir(home) / f"{name}.json"
    path.write_text(json.dumps(hook_to_json(hook), ensure_ascii=False), encoding="utf-8")


# --- 로딩 ---


def test_missing_dir_is_empty(tmp_path):
    """폴더가 없어도 죽지 않는다 — 전역 훅을 안 쓰는 것이 기본값이다."""
    assert load_global_hooks(tmp_path) == []


def test_loads_hook_with_handlers(home):
    _write(home, "fmt", _hook("무시되는-이름", script="prettier --write"))
    (loaded,) = load_global_hooks(home)
    assert loaded.name == "fmt"  # 파일명 stem이 이름의 단일 진실
    assert loaded.event is HookEvent.PRE_TOOL_USE
    assert loaded.matcher == "Edit"
    assert [h.script for h in loaded.handlers] == ["prettier --write"]


def test_handler_types_survive(home):
    """kind 태그 다형성이 유지된다 — 커맨드 훅만 되는 저장소가 아니다."""
    hook = HookDef(
        name="review", description="", event=HookEvent.STOP,
        handlers=[CommandHook(script="a"), PromptHook(prompt="검토하라")],
    )
    _write(home, "review", hook)
    (loaded,) = load_global_hooks(home)
    assert [type(h).__name__ for h in loaded.handlers] == ["CommandHook", "PromptHook"]
    assert loaded.handlers[1].prompt == "검토하라"


def test_filename_order_is_deterministic(home):
    for name in ("zeta", "alpha", "mid"):
        _write(home, name, _hook(name))
    assert [h.name for h in load_global_hooks(home)] == ["alpha", "mid", "zeta"]


def test_broken_file_is_skipped(home, capsys):
    """파일 하나가 깨졌다고 앱이 뜨지 않으면 안 된다 (카탈로그 관례)."""
    _write(home, "good", _hook("good"))
    (global_hooks_dir(home) / "broken.json").write_text("{ not json", encoding="utf-8")
    (global_hooks_dir(home) / "array.json").write_text("[1, 2]", encoding="utf-8")

    assert [h.name for h in load_global_hooks(home)] == ["good"]
    assert "broken.json" in capsys.readouterr().err


def test_non_json_files_ignored(home):
    _write(home, "good", _hook("good"))
    (global_hooks_dir(home) / "notes.txt").write_text("...", encoding="utf-8")
    assert [h.name for h in load_global_hooks(home)] == ["good"]


# --- 병합 ---


def test_project_hook_wins_over_global(home):
    _write(home, "fmt", _hook("fmt", script="global-cmd"))
    project = PluginProject(name="p", hook_library=[_hook("fmt", script="project-cmd")])

    resolved = resolve_hooks(project, home)
    assert set(resolved) == {"fmt"}
    assert resolved["fmt"].handlers[0].script == "project-cmd"


def test_both_scopes_are_visible(home):
    _write(home, "shared", _hook("shared"))
    project = PluginProject(name="p", hook_library=[_hook("local-only")])

    resolved = resolve_hooks(project, home)
    assert set(resolved) == {"shared", "local-only"}


def test_resolve_without_globals_is_just_the_project(tmp_path):
    """전역이 없으면 프로젝트 라이브러리 그대로 — 기존 동작과 같다."""
    project = PluginProject(name="p", hook_library=[_hook("a"), _hook("b")])
    resolved = resolve_hooks(project, tmp_path)
    assert list(resolved) == ["a", "b"]


# --- 파일 형상 ---


def test_hook_to_json_drops_identity(home):
    """이름과 id는 파일에 나가지 않는다 — 이름은 파일명이, id는 프로젝트가 정한다."""
    data = hook_to_json(_hook("fmt"))
    assert "name" not in data
    assert "id" not in data
    assert all("id" not in h for h in data["handlers"])
    assert data["event"] == HookEvent.PRE_TOOL_USE.value


def test_roundtrip_through_file(home):
    """프로젝트 훅을 파일로 내보내고 다시 읽으면 같은 훅이다."""
    original = HookDef(
        name="check", description="검사", event=HookEvent.POST_TOOL_USE,
        matcher="Write", handlers=[CommandHook(script="ruff check", timeout=30)],
    )
    _write(home, "check", original)
    (loaded,) = load_global_hooks(home)

    assert loaded.name == original.name
    assert loaded.description == original.description
    assert loaded.event is original.event
    assert loaded.matcher == original.matcher
    assert loaded.handlers[0].script == "ruff check"
    assert loaded.handlers[0].timeout == 30
