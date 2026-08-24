"""HookLibraryPanel의 전역 훅 표시 — 읽기 전용 + 프로젝트로 복사 (A1).

전역 훅은 여기서 고치지 않는다. 전역 파일을 앱에서 직접 편집하게 하면 다른
프로젝트가 조용히 함께 바뀌고, 나중에 어디서 고쳤는지 알 길이 없다 —
프로젝트로 복사한 뒤 그 사본을 고친다.
"""
from __future__ import annotations

import json

import pytest

from daedalus.model.plugin import hook_store
from daedalus.model.plugin.hook import CommandHook, HookDef, HookEvent
from daedalus.model.project import PluginProject
from daedalus.view.editors.hook_panel import HookLibraryPanel


def _hook(name: str, script: str = "echo hi") -> HookDef:
    return HookDef(
        name=name, description="d", event=HookEvent.PRE_TOOL_USE,
        handlers=[CommandHook(script=script)],
    )


@pytest.fixture
def global_dir(tmp_path, monkeypatch):
    """전역 훅 폴더 — 루트 conftest의 격리를 이 테스트용 경로로 다시 고정."""
    directory = tmp_path / "globalhooks"
    directory.mkdir()
    monkeypatch.setattr(hook_store, "global_hooks_dir", lambda home_dir=None: directory)
    return directory


def _write_global(directory, name: str, script: str = "global-cmd") -> None:
    (directory / f"{name}.json").write_text(
        json.dumps(hook_store.hook_to_json(_hook(name, script)), ensure_ascii=False),
        encoding="utf-8",
    )


def _labels(panel: HookLibraryPanel) -> list[str]:
    return [panel._list.item(i).text() for i in range(panel._list.count())]


def test_global_hooks_appear_after_project_hooks(qapp, global_dir):
    _write_global(global_dir, "shared")
    panel = HookLibraryPanel()
    panel.set_project(PluginProject(name="p", hook_library=[_hook("local")]))

    labels = _labels(panel)
    assert len(labels) == 2
    assert labels[0].startswith("local")
    assert labels[1].startswith("🌐 shared")


def test_shadowed_global_is_hidden(qapp, global_dir):
    """동명 프로젝트 훅이 있으면 전역은 목록에서 뺀다 — 둘 다 보이면 어느 쪽이
    실제로 쓰이는지 화면만 봐서는 알 수 없다."""
    _write_global(global_dir, "fmt")
    panel = HookLibraryPanel()
    panel.set_project(PluginProject(name="p", hook_library=[_hook("fmt")]))

    labels = _labels(panel)
    assert len(labels) == 1
    assert not labels[0].startswith("🌐")


def test_selecting_global_locks_editing(qapp, global_dir):
    _write_global(global_dir, "shared")
    panel = HookLibraryPanel()
    panel.set_project(PluginProject(name="p", hook_library=[_hook("local")]))

    panel._list.setCurrentRow(1)  # 전역
    assert panel._current_is_global() is True
    assert panel._name.text() == "shared"
    assert panel._name.isEnabled() is False
    assert panel._remove_btn.isEnabled() is False
    assert panel._handler_add_btn.isEnabled() is False
    assert panel._copy_to_project_btn.isEnabled() is True

    panel._list.setCurrentRow(0)  # 프로젝트
    assert panel._current_is_global() is False
    assert panel._name.isEnabled() is True
    assert panel._remove_btn.isEnabled() is True
    assert panel._copy_to_project_btn.isEnabled() is False


def test_editing_a_global_hook_is_a_no_op(qapp, global_dir):
    """위젯이 잠겨 있어도 프로그램 경로로는 들어올 수 있다 — 모델을 지킨다."""
    _write_global(global_dir, "shared")
    project = PluginProject(name="p")
    panel = HookLibraryPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)

    hook = panel._current_hook()
    panel._name.setText("건드림")
    panel._save_head()
    panel._add_handler()

    assert hook.name == "shared"
    assert len(hook.handlers) == 1
    assert project.hook_library == []


def test_copy_to_project_keeps_name_and_deep_copies(qapp, global_dir):
    """이름을 유지해야 참조가 사본을 가리킨다(동명이면 프로젝트가 이긴다)."""
    _write_global(global_dir, "shared")
    project = PluginProject(name="p")
    panel = HookLibraryPanel()
    panel.set_project(project)
    panel._list.setCurrentRow(0)
    original = panel._current_hook()

    panel._copy_global_to_project()

    assert [h.name for h in project.hook_library] == ["shared"]
    copy = project.hook_library[0]
    assert copy is not original
    assert copy.handlers[0] is not original.handlers[0]
    assert copy.id != original.id

    # 사본을 고쳐도 전역 객체는 그대로다
    copy.handlers[0].script = "project-cmd"
    assert original.handlers[0].script == "global-cmd"

    # 복사 후에는 전역이 가려져 목록에 하나만 남고, 그것이 편집 가능한 사본이다
    labels = _labels(panel)
    assert len(labels) == 1
    assert not labels[0].startswith("🌐")
    assert panel._current_is_global() is False


def test_delete_removes_the_right_hook(qapp, global_dir):
    """전역이 섞인 목록에서도 인덱스 착오로 엉뚱한 훅을 지우지 않는다."""
    _write_global(global_dir, "shared")
    project = PluginProject(name="p", hook_library=[_hook("a"), _hook("b")])
    panel = HookLibraryPanel()
    panel.set_project(project)

    panel._list.setCurrentRow(1)  # 프로젝트 훅 'b'
    panel._delete_hook()
    assert [h.name for h in project.hook_library] == ["a"]

    panel._list.setCurrentRow(1)  # 이제 전역 'shared'
    panel._delete_hook()
    assert [h.name for h in project.hook_library] == ["a"]  # 전역은 못 지운다
