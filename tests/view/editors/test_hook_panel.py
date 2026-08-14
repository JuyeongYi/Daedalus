"""훅 라이브러리 상주 탭 (WP-HK).

모달 다이얼로그를 대체한 탭이다. CC 훅은 이벤트 31종 × 핸들러 5종의 3단
구조라, 편집기가 그 구조를 그대로 다룰 수 있는지가 이 테스트의 관심사다.
"""
from __future__ import annotations

import pytest

from daedalus.model.plugin.hook import (
    AgentHook,
    CommandHook,
    HookDef,
    HookEvent,
    HookShell,
    HttpHook,
    McpToolHook,
)
from daedalus.model.project import PluginProject
from daedalus.view.app import _HOOK_TAB_INDEX, MainWindow
from daedalus.view.editors.hook_panel import HookLibraryPanel, event_label


@pytest.fixture
def panel(qapp):
    p = HookLibraryPanel()
    p.set_project(PluginProject(name="p"))
    return p


def _hook(name="h", **kw) -> HookDef:
    return HookDef(
        name=name,
        description=kw.get("description", ""),
        event=kw.get("event", HookEvent.PRE_TOOL_USE),
        matcher=kw.get("matcher", ""),
        handlers=kw.get("handlers", [CommandHook(script="./a.sh")]),
    )


# --- 상주 탭 배선 ---


def test_hook_tab_exists_and_is_not_closable(qapp):
    window = MainWindow()
    try:
        assert isinstance(window._tabs.widget(_HOOK_TAB_INDEX), HookLibraryPanel)
        before = window._tabs.count()
        window._close_tab(_HOOK_TAB_INDEX)
        assert window._tabs.count() == before, "고정 탭은 닫히면 안 된다"
    finally:
        window.close()


def test_menu_action_focuses_the_tab(qapp):
    window = MainWindow()
    try:
        window._tabs.setCurrentIndex(0)
        window._open_hook_library()
        assert window._tabs.currentIndex() == _HOOK_TAB_INDEX
    finally:
        window.close()


def test_set_project_binds_library(qapp):
    window = MainWindow()
    try:
        project = PluginProject(name="p", hook_library=[_hook("a"), _hook("b")])
        window.set_project(project)
        assert window._hook_panel._list.count() == 2
    finally:
        window.close()


# --- 목록 ---


def test_add_hook_appends_to_library(panel):
    panel._add_hook()
    assert len(panel._project.hook_library) == 1
    # 빈 훅이 아니라 커맨드 핸들러 하나로 시작한다 — 바로 쓸 수 있게
    assert panel._project.hook_library[0].handlers[0].kind == "command"


def test_add_hook_avoids_duplicate_names(panel):
    panel._add_hook()
    panel._add_hook()
    names = [h.name for h in panel._project.hook_library]
    assert len(set(names)) == 2, "같은 이름이 둘이면 duplicate_hook_name 에러가 난다"


def test_delete_hook_removes_selected(panel):
    panel._project.hook_library.extend([_hook("a"), _hook("b")])
    panel._reload_list()
    panel._list.setCurrentRow(0)
    panel._delete_hook()
    assert [h.name for h in panel._project.hook_library] == ["b"]


def test_list_marks_hook_without_handlers(panel):
    panel._project.hook_library.append(_hook("empty", handlers=[]))
    panel._reload_list()
    assert "⚠" in panel._list.item(0).text()


def test_add_from_preset_copies_not_shares(panel, monkeypatch):
    from daedalus.model.plugin import hook_presets

    monkeypatch.setattr(
        "daedalus.view.editors.hook_panel.QInputDialog.getItem",
        lambda *a, **k: (hook_presets.BUILTIN_HOOK_PRESETS[0].name, True),
    )
    panel._add_from_preset()
    added = panel._project.hook_library[0]
    src = hook_presets.BUILTIN_HOOK_PRESETS[0]
    assert added.id != src.id
    assert added.handlers[0] is not src.handlers[0]


# --- 훅 헤더 편집 ---


def test_event_change_writes_back(panel):
    panel._project.hook_library.append(_hook("a"))
    panel._reload_list()
    panel._event.setCurrentIndex(list(HookEvent).index(HookEvent.SESSION_END))
    assert panel._project.hook_library[0].event is HookEvent.SESSION_END


def test_matcher_disabled_for_events_that_ignore_it(panel):
    panel._project.hook_library.append(_hook("a", event=HookEvent.CWD_CHANGED))
    panel._reload_list()
    assert not panel._matcher.isEnabled()
    assert "matcher를 받지 않습니다" in panel._matcher_note.text()


def test_matcher_enabled_for_events_that_accept_it(panel):
    panel._project.hook_library.append(_hook("a", event=HookEvent.STOP))
    panel._reload_list()
    assert panel._matcher.isEnabled()
    assert panel._matcher_note.text() == ""


def test_stale_matcher_on_unsupported_event_is_flagged(panel):
    """이미 값이 들어 있으면 그냥 잠그는 것으로 부족하다 — 무시된다고 알려야 한다."""
    panel._project.hook_library.append(
        _hook("a", event=HookEvent.TASK_CREATED, matcher="x")
    )
    panel._reload_list()
    assert "무시" in panel._matcher_note.text()


def test_event_label_marks_special_events():
    assert "matcher 없음" in event_label(HookEvent.CWD_CHANGED)
    assert "미문서화" in event_label(HookEvent.SETUP)
    assert event_label(HookEvent.PRE_TOOL_USE) == "PreToolUse"


# --- 핸들러 편집 ---


def test_handler_list_shows_all_handlers(panel):
    panel._project.hook_library.append(
        _hook("a", handlers=[CommandHook(script="x"), AgentHook(prompt="y")])
    )
    panel._reload_list()
    assert panel._handler_list.count() == 2
    assert "command" in panel._handler_list.item(0).text()
    assert "agent" in panel._handler_list.item(1).text()


@pytest.mark.parametrize(
    "kind", ["command", "prompt", "agent", "http", "mcp_tool"]
)
def test_add_handler_of_each_type(panel, kind):
    """다섯 타입 전부 UI에서 만들 수 있어야 한다."""
    from daedalus.model.plugin.hook import HOOK_HANDLER_LABELS

    panel._project.hook_library.append(_hook("a", handlers=[]))
    panel._reload_list()
    panel._handler_type.setCurrentIndex([k for k, _ in HOOK_HANDLER_LABELS].index(kind))
    panel._add_handler()
    assert panel._project.hook_library[0].handlers[0].kind == kind


def test_delete_handler(panel):
    panel._project.hook_library.append(
        _hook("a", handlers=[CommandHook(script="x"), AgentHook(prompt="y")])
    )
    panel._reload_list()
    panel._handler_list.setCurrentRow(0)
    panel._delete_handler()
    assert [h.kind for h in panel._project.hook_library[0].handlers] == ["agent"]


def test_handler_form_writes_back_command_fields(panel):
    panel._project.hook_library.append(_hook("a", handlers=[CommandHook()]))
    panel._reload_list()

    form = panel._handler_form
    assert form is not None
    form._script.setPlainText("./run.sh")
    form._timeout.setValue(12)
    form._condition.setText("Bash(git *)")
    form._status.setText("검사 중")
    form._shell.setCurrentIndex(list(HookShell).index(HookShell.POWERSHELL))
    form._run_async.setChecked(True)

    handler = panel._project.hook_library[0].handlers[0]
    assert handler.script == "./run.sh"
    assert handler.timeout == 12
    assert handler.condition == "Bash(git *)"
    assert handler.status_message == "검사 중"
    assert handler.shell is HookShell.POWERSHELL
    assert handler.run_async is True


def test_handler_form_writes_back_http_fields(panel):
    panel._project.hook_library.append(_hook("a", handlers=[HttpHook()]))
    panel._reload_list()

    form = panel._handler_form
    form._url.setText("https://x/y")
    form._headers.setPlainText("X-Token: abc\nAccept: json")
    form._env.setText("TOKEN SECRET")

    handler = panel._project.hook_library[0].handlers[0]
    assert handler.url == "https://x/y"
    assert handler.headers == {"X-Token": "abc", "Accept": "json"}
    assert handler.allowed_env_vars == ["TOKEN", "SECRET"]


def test_handler_form_writes_back_mcp_fields(panel):
    panel._project.hook_library.append(_hook("a", handlers=[McpToolHook()]))
    panel._reload_list()

    form = panel._handler_form
    form._server.setText("slack")
    form._tool.setText("post")
    form._input.setPlainText("channel: #dev")

    handler = panel._project.hook_library[0].handlers[0]
    assert handler.server == "slack"
    assert handler.tool == "post"
    assert handler.tool_input == {"channel": "#dev"}


def test_handler_form_is_never_a_toplevel_window(panel):
    """부모 없는 QWidget은 최상위 윈도우다 — 레이아웃에 붙기 전 한 프레임 동안
    빈 창이 깜빡였다(핸들러를 전환할 때마다 보였다)."""
    panel._project.hook_library.append(_hook("a", handlers=[CommandHook(script="x")]))
    panel._reload_list()

    form = panel._handler_form
    assert form is not None
    assert form.parent() is not None
    assert not form.isWindow()


def test_handler_toolbar_sits_above_the_list(panel):
    """조작 줄이 목록 아래에 있으면 무엇을 추가하는 버튼인지 한 번 더 훑어야 한다."""
    box_layout = panel._handlers_box.layout()
    order = [box_layout.itemAt(i) for i in range(box_layout.count())]
    toolbar_index = next(
        i for i, item in enumerate(order)
        if item.layout() is not None and item.layout().indexOf(panel._handler_type) >= 0
    )
    list_index = next(
        i for i, item in enumerate(order) if item.widget() is panel._handler_list
    )
    assert toolbar_index < list_index


def test_handler_area_absorbs_extra_space(panel):
    """스페이서가 없으면 훅이 없을 때 위젯들이 위아래로 흩어진다."""
    box_layout = panel._handlers_box.layout()
    holder_index = next(
        i for i in range(box_layout.count())
        if box_layout.itemAt(i).layout() is panel._handler_form_holder
    )
    assert box_layout.stretch(holder_index) == 1


def test_switching_handler_rebuilds_form(panel):
    """타입마다 필드가 달라 폼을 갈아끼운다 — 이전 타입의 위젯이 남으면 안 된다."""
    panel._project.hook_library.append(
        _hook("a", handlers=[CommandHook(script="x"), HttpHook(url="https://y")])
    )
    panel._reload_list()

    panel._handler_list.setCurrentRow(0)
    assert hasattr(panel._handler_form, "_script")
    panel._handler_list.setCurrentRow(1)
    assert hasattr(panel._handler_form, "_url")
    assert not hasattr(panel._handler_form, "_script")


# --- 프론트매터 내보내기 ---


def test_copy_frontmatter_puts_yaml_on_clipboard(panel, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    panel._project.hook_library.append(
        _hook("a", event=HookEvent.PRE_TOOL_USE, matcher="Bash")
    )
    panel._reload_list()
    panel._copy_frontmatter()

    text = QApplication.clipboard().text()
    assert text.startswith("hooks:\n")
    assert "PreToolUse:" in text
    assert "- matcher: Bash" in text
    assert "- type: command" in text


def test_copy_hooks_json_puts_json_on_clipboard(panel, monkeypatch):
    import json

    from PySide6.QtWidgets import QApplication, QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    panel._project.hook_library.append(_hook("a"))
    panel._reload_list()
    panel._copy_hooks_json()

    obj = json.loads(QApplication.clipboard().text())
    assert obj["hooks"]["PreToolUse"][0]["hooks"][0]["type"] == "command"


def test_copy_refuses_when_no_handlers(panel, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    seen = {}
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: seen.setdefault("called", True)
    )
    QApplication.clipboard().setText("SENTINEL")
    panel._project.hook_library.append(_hook("a", handlers=[]))
    panel._reload_list()
    panel._copy_frontmatter()

    assert seen.get("called")
    assert QApplication.clipboard().text() == "SENTINEL", "빈 훅을 복사하면 안 된다"
