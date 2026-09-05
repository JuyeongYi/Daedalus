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
    """제공자가 사는 유일한 이유 — HOOKS 필드의 자동완성 후보다."""
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.editors.skill_editor import _FrontmatterPanel
    from daedalus.view.widgets.tag_input import set_hook_name_provider

    from tests.compiler.builders import make_procedural

    set_hook_name_provider(lambda: ["lint", "fmt"])
    try:
        panel = _FrontmatterPanel(make_procedural())
        widget = panel._field_widgets[SkillField.HOOKS]
        assert widget.get_candidates() == ["lint", "fmt"]
    finally:
        set_hook_name_provider(None)
