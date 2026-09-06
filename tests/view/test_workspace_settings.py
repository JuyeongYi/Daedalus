# tests/view/test_workspace_settings.py
"""작업 폴더 settings (WP-WS) — 모델 왕복·베이크·설정 탭·LOCAL 전용 표시·MCP."""
from __future__ import annotations

import json

import pytest

from daedalus.model.plugin.enums import BuildTarget
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator


# ─────────────────────────── 모델 왕복 ───────────────────────────


def test_workspace_settings_roundtrip():
    project = PluginProject(
        name="p", build_target=BuildTarget.LOCAL,
        workspace_settings={"permissions": {"deny": ["Read(state/**)"]}, "model": "opus"},
    )
    loaded = deserialize_project(serialize_project(project))
    assert loaded.workspace_settings == project.workspace_settings


def test_workspace_settings_missing_key_defaults_empty():
    data = serialize_project(PluginProject(name="p"))
    data.pop("workspace_settings")
    assert deserialize_project(data).workspace_settings == {}


# ─────────────────────────── 검증 규칙 ───────────────────────────


def test_settings_in_marketplace_build_warns():
    project = PluginProject(
        name="p", build_target=BuildTarget.MARKETPLACE,
        workspace_settings={"model": "opus"},
    )
    rules = [e.rule for e in Validator.validate_project(project)]
    assert "workspace_settings_in_marketplace_build" in rules


def test_settings_local_or_empty_no_warning():
    for project in (
        PluginProject(name="p", build_target=BuildTarget.LOCAL,
                      workspace_settings={"model": "opus"}),
        PluginProject(name="p", build_target=BuildTarget.MARKETPLACE),
    ):
        rules = [e.rule for e in Validator.validate_project(project)]
        assert "workspace_settings_in_marketplace_build" not in rules


# ─────────────────────── 베이크 (wire_workspace) ───────────────────────


def test_bake_deep_merges_and_is_idempotent(tmp_path):
    from daedalus.compiler.wiring import wire_workspace

    settings_path = tmp_path / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "permissions": {"deny": ["Bash(rm *)"], "allow": ["Read"]},
        "model": "sonnet",
    }), encoding="utf-8")

    extra = {
        "permissions": {"deny": ["Read(state/**)", "Bash(rm *)"]},
        "model": "opus",
        "hooks": {"PreToolUse": []},  # 무시돼야 한다 — 훅 정본은 hook_library
    }
    wire_workspace(tmp_path, extra_settings=extra)
    obj = json.loads(settings_path.read_text(encoding="utf-8"))
    # 깊은 병합: deny는 없는 원소만 추가(순서 보존), allow(수기)는 불가침
    assert obj["permissions"]["deny"] == ["Bash(rm *)", "Read(state/**)"]
    assert obj["permissions"]["allow"] == ["Read"]
    assert obj["model"] == "opus"  # 스칼라는 갱신
    assert "hooks" not in obj  # hooks 키 무시

    before = settings_path.read_bytes()
    wire_workspace(tmp_path, extra_settings=extra)  # 멱등
    assert settings_path.read_bytes() == before


def test_local_compile_bakes_settings(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(
        name="p", build_target=BuildTarget.LOCAL,
        workspace_settings={"permissions": {"deny": ["Edit(state/**)"]}},
    )
    result = compile_project(project, tmp_path)
    assert not result.errors
    obj = json.loads(
        (tmp_path / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    assert obj["permissions"]["deny"] == ["Edit(state/**)"]


def test_marketplace_compile_does_not_bake(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(
        name="p", build_target=BuildTarget.MARKETPLACE,
        workspace_settings={"model": "opus"},
    )
    compile_project(project, tmp_path)
    assert not (tmp_path / ".claude" / "settings.local.json").exists()


def test_dry_run_reports_but_writes_nothing(tmp_path):
    from daedalus.compiler.project_compiler import compile_project

    project = PluginProject(
        name="p", build_target=BuildTarget.LOCAL,
        workspace_settings={"model": "opus"},
    )
    compile_project(project, tmp_path, dry_run=True)
    assert not (tmp_path / ".claude").exists()


# ─────────────────────────── 설정 탭 (GUI) ───────────────────────────

pytest.importorskip(
    "qclaudecodesettingeditorwidget", reason="external/ 서브모듈 미설치"
)


@pytest.fixture
def make_panel(qapp):
    """패널 팩토리 + 정리 — 위젯의 0ms 디바운스 타이머(singleShot →
    _flush_change)가 **위젯 파괴 후** 발화하면 stale PropertyRow 접근으로
    죽는다(업스트림 수명 버그 — 실제 앱에서는 패널이 탭에 부모로 붙어 상주라
    안 터진다). 테스트에서는 패널이 살아 있는 동안 이벤트를 배수해 타이머를
    소진시킨 뒤 버린다.
    """
    panels: list = []

    def _make(project):
        from daedalus.view.editors.workspace_settings_panel import (
            WorkspaceSettingsPanel,
        )

        calls: list[str] = []
        panel = WorkspaceSettingsPanel(
            on_notify_fn=lambda scope="structure": calls.append(scope)
        )
        panel.set_project(project)
        panel.ensure_editor()  # 지연 생성 — 실제 앱에서는 탭 표시(showEvent)가 만든다
        panels.append(panel)
        return panel, calls

    yield _make
    qapp.processEvents()  # 대기 중 디바운스 타이머를 위젯 생전에 소진
    for panel in panels:
        panel.deleteLater()
    qapp.processEvents()


def test_panel_loads_and_saves_settings(make_panel):
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL,
                            workspace_settings={"model": "opus"})
    panel, calls = make_panel(project)
    assert panel.current_settings() == {"model": "opus"}
    # 위젯 편집 시뮬레이션 — 프로그램적 setter는 settingChanged를 내지
    # 않으므로 UI 편집이 타는 저장 경로를 명시 호출로 검증한다.
    panel._editor.setSettingValue("model", "sonnet")
    panel._on_setting_changed()
    assert project.workspace_settings["model"] == "sonnet"
    assert "content" in calls


def test_panel_strips_hooks_on_save(make_panel, monkeypatch):
    """위젯이 hooks를 돌려주더라도 모델에는 싣지 않는다 (방어적 strip).

    새 위젯 버전은 숨긴 카테고리 키 입력을 HiddenKeyError로 거부하므로
    (노출 정책 API 우회 차단), hooks가 위젯을 **통과해 나오는** 경로를
    monkeypatch로 재현한다 — strip은 위젯 정책과 독립적인 이중 방어다.
    """
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    panel, _ = make_panel(project)
    monkeypatch.setattr(
        panel._editor, "settings",
        lambda: {"hooks": {"PreToolUse": []}, "model": "opus"},
    )
    panel._on_setting_changed()
    assert "hooks" not in project.workspace_settings
    assert project.workspace_settings.get("model") == "opus"


def test_panel_hooks_category_hidden(make_panel):
    """훅 카테고리는 편집 표면에서 제외된다 (사용자 확정 — 훅 정본은 hook_library)."""
    from qclaudecodesettingeditorwidget.categories import Category

    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    panel, _ = make_panel(project)
    assert not (panel._editor._categories & Category.HOOKS)


def test_marketplace_notice_flag(make_panel):
    project = PluginProject(name="p", build_target=BuildTarget.MARKETPLACE)
    panel, _ = make_panel(project)
    assert panel._notice.isVisibleTo(panel)
    panel.set_project(PluginProject(name="p", build_target=BuildTarget.LOCAL))
    assert not panel._notice.isVisibleTo(panel)


# ─────────────────────── LOCAL 전용 탭 표시 ───────────────────────


def test_local_only_tabs_hidden_for_marketplace(qapp):
    from daedalus.view.app import _LOCAL_ONLY_TAB_INDEXES, MainWindow

    window = MainWindow()
    window.load_project(PluginProject(name="p", build_target=BuildTarget.MARKETPLACE))
    bar = window._tabs.tabBar()
    for index in _LOCAL_ONLY_TAB_INDEXES:
        assert not bar.isTabVisible(index)
    # FSM·블랙보드·훅 탭은 그대로
    for index in (0, 1, 2):
        assert bar.isTabVisible(index)
    window.close()


def test_local_only_tabs_visible_for_local_and_follow_target_change(qapp):
    from daedalus.view.app import _LOCAL_ONLY_TAB_INDEXES, MainWindow

    window = MainWindow()
    project = PluginProject(name="p", build_target=BuildTarget.LOCAL)
    window.load_project(project)
    bar = window._tabs.tabBar()
    for index in _LOCAL_ONLY_TAB_INDEXES:
        assert bar.isTabVisible(index)
    # 빌드 타깃 변경(속성 다이얼로그/MCP 경로의 notify)이 표시를 따라간다
    project.build_target = BuildTarget.MARKETPLACE
    window._project_vm.notify()
    for index in _LOCAL_ONLY_TAB_INDEXES:
        assert not bar.isTabVisible(index)
    window.close()


# ─────────────────────────── MCP 패리티 ───────────────────────────


def test_mcp_set_and_get_workspace_settings(qapp):
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.app import MainWindow

    window = MainWindow()
    window.load_project(PluginProject(name="p", build_target=BuildTarget.LOCAL))
    tools = DaedalusTools(window)

    result = tools.set_workspace_settings(
        {"permissions": {"deny": ["Read(state/**)"]}}
    )
    assert result["settings"]["permissions"]["deny"] == ["Read(state/**)"]
    assert (
        window._project.workspace_settings["permissions"]["deny"]
        == ["Read(state/**)"]
    )
    got = tools.get_workspace_settings()
    assert got["settings"] == window._project.workspace_settings
    assert got["build_target"] == "local"

    tools.undo()
    assert window._project.workspace_settings == {}
    window.close()


def test_mcp_set_workspace_settings_rejects_hooks(qapp):
    from daedalus.mcp.tools import DaedalusTools
    from daedalus.view.app import MainWindow

    window = MainWindow()
    window.load_project(PluginProject(name="p"))
    tools = DaedalusTools(window)
    with pytest.raises(ValueError, match="hook_library"):
        tools.set_workspace_settings({"hooks": {}})
    window.close()


def test_mcp_tools_registered():
    from daedalus.mcp.service import TOOL_NAMES

    assert "get_workspace_settings" in TOOL_NAMES
    assert "set_workspace_settings" in TOOL_NAMES
