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
