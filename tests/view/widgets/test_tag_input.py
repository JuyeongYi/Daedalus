# tests/view/widgets/test_tag_input.py
from __future__ import annotations


def test_tag_input_empty(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    assert w.get_tags() == []


def test_tag_input_set_tags(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep", "Bash"])
    assert w.get_tags() == ["Read", "Grep", "Bash"]


def test_tag_input_add_tag(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.add_tag("Read")
    w.add_tag("Grep")
    assert w.get_tags() == ["Read", "Grep"]


def test_tag_input_no_duplicates(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.add_tag("Read")
    w.add_tag("Read")
    assert w.get_tags() == ["Read"]


def test_tag_input_remove_tag(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep", "Bash"])
    w.remove_tag("Grep")
    assert w.get_tags() == ["Read", "Bash"]


def test_tag_input_changed_signal(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    called = []
    w.tags_changed.connect(lambda: called.append(1))
    w.add_tag("Read")
    assert len(called) == 1


def test_tag_input_set_candidates_stores_list(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_candidates(["Read", "Bash", "mcp__playwright__browser_click"])
    assert w.get_candidates() == ["Read", "Bash", "mcp__playwright__browser_click"]


def test_tag_input_completer_attached_and_filters_case_insensitive(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_candidates(["Bash(git *)", "Read", "mcp__playwright__browser_click"])
    completer = w._input.completer()
    assert completer is not None

    completer.setCompletionPrefix("bash")
    assert completer.completionCount() == 1

    completer.setCompletionPrefix("MCP__")
    assert completer.completionCount() == 1


def test_tag_input_set_candidates_replaces_previous_completer(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_candidates(["Read"])
    w.set_candidates(["Write", "Edit"])
    assert w.get_candidates() == ["Write", "Edit"]
    completer = w._input.completer()
    completer.setCompletionPrefix("Read")
    assert completer.completionCount() == 0


def test_tool_candidate_provider_default_empty(qapp):
    from daedalus.view.widgets.tag_input import get_tool_candidates, set_tool_candidate_provider
    set_tool_candidate_provider(None)
    assert get_tool_candidates() == []


def test_tool_candidate_provider_registered(qapp):
    from daedalus.view.widgets.tag_input import get_tool_candidates, set_tool_candidate_provider
    set_tool_candidate_provider(lambda: ["Read", "Agent(worker)"])
    try:
        assert get_tool_candidates() == ["Read", "Agent(worker)"]
    finally:
        set_tool_candidate_provider(None)


# 훅 이름 후보 — 구 preset_picker.py에서 옮겨 온 제공자(항목 4).
# 체크리스트 위젯(HookPresetPicker)이 TagInput으로 대체되면서 그 모듈에 남은 것이
# 이 제공자뿐이라, 후보를 실제로 쓰는 위젯 옆으로 옮겼다.


def test_hook_name_provider_default_empty(qapp):
    from daedalus.view.widgets.tag_input import get_hook_names, set_hook_name_provider
    set_hook_name_provider(None)
    assert get_hook_names() == []


def test_hook_name_provider_registered(qapp):
    from daedalus.view.widgets.tag_input import get_hook_names, set_hook_name_provider
    set_hook_name_provider(lambda: ["lint", "fmt"])
    try:
        assert get_hook_names() == ["lint", "fmt"]
    finally:
        set_hook_name_provider(None)


def test_hook_names_feed_the_hooks_taginput_candidates(qapp):
    """제공자가 사는 유일한 이유 — HOOKS 필드의 자동완성 후보다.

    HOOKS는 **에이전트 전용**이다(스킬 프론트매터에는 hooks 키가 없다 —
    2026-09-07 규격 확인).
    """
    from daedalus.model.plugin.enums import AgentField
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.view.widgets.tag_input import set_hook_name_provider

    from tests.compiler.builders import make_agent

    set_hook_name_provider(lambda: ["lint", "fmt"])
    try:
        panel = _FrontmatterPanel(make_agent("worker"))
        widget = panel._field_widgets[AgentField.HOOKS]
        assert widget.get_candidates() == ["lint", "fmt"]
    finally:
        set_hook_name_provider(None)


# 칩 제자리 편집 — QLabel → QLineEdit 전환 (사용자 요청: "이미 추가된 거
# 수정하기 어렵다"). 편집 커밋은 editingFinished(Enter/포커스 아웃)이고,
# 유효성 판정(빈 값·중복 → 되돌림)은 TagInput이 한다.


def _chips(w):
    from daedalus.view.widgets.tag_input import _TagChip
    return [c for c in w._chips_widget.findChildren(_TagChip)]


def _chip_named(w, name):
    return next(c for c in _chips(w) if c.name == name)


def test_chip_edit_commits_in_place(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep", "Bash"])
    called = []
    w.tags_changed.connect(lambda: called.append(1))

    chip = _chip_named(w, "Grep")
    chip._edit.setText("Glob")
    chip._edit.editingFinished.emit()

    assert w.get_tags() == ["Read", "Glob", "Bash"]  # 순서 보존
    assert chip.name == "Glob"
    assert len(called) == 1


def test_chip_edit_empty_reverts(qapp):
    """빈 값은 삭제가 아니라 되돌림 — 삭제는 x 버튼의 몫."""
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read"])
    chip = _chip_named(w, "Read")
    chip._edit.setText("   ")
    chip._edit.editingFinished.emit()
    assert w.get_tags() == ["Read"]
    assert chip._edit.text() == "Read"


def test_chip_edit_duplicate_reverts(qapp):
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep"])
    chip = _chip_named(w, "Grep")
    chip._edit.setText("Read")
    chip._edit.editingFinished.emit()
    assert w.get_tags() == ["Read", "Grep"]
    assert chip._edit.text() == "Grep"


def test_chip_edit_unchanged_is_noop(qapp):
    """editingFinished가 Enter+포커스 아웃으로 연달아 와도 신호가 중복되지 않는다."""
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read"])
    called = []
    w.tags_changed.connect(lambda: called.append(1))
    chip = _chip_named(w, "Read")
    chip._edit.editingFinished.emit()
    assert called == []


def test_chip_edit_then_remove_uses_new_name(qapp):
    """편집 후 x 버튼이 옛 이름을 지우려다 실패하면 안 된다."""
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read", "Grep"])
    chip = _chip_named(w, "Grep")
    chip._edit.setText("Glob")
    chip._edit.editingFinished.emit()
    chip.remove_requested.emit(chip.name)
    assert w.get_tags() == ["Read"]


def test_chip_gets_completer_from_candidates(qapp):
    """칩 편집도 상단 입력과 같은 자동완성 후보를 받는다."""
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_candidates(["Read", "Bash(git *)"])
    w.set_tags(["Read"])
    chip = _chip_named(w, "Read")
    completer = chip._edit.completer()
    assert completer is not None
    completer.setCompletionPrefix("bash")
    assert completer.completionCount() == 1


def test_set_candidates_refreshes_existing_chips(qapp):
    """태그가 먼저 있고 후보가 나중에 와도 칩이 자동완성을 받는다."""
    from daedalus.view.widgets.tag_input import TagInput
    w = TagInput()
    w.set_tags(["Read"])
    w.set_candidates(["Read", "Write"])
    chip = _chip_named(w, "Read")
    assert chip._edit.completer() is not None
