# tests/view/panels/test_property_panel.py
"""WP-BB Part C-1: PropertyPanel의 상태 접근 선언(reads/writes) TagInput."""
from __future__ import annotations

from daedalus.model.fsm.state import SimpleState
from daedalus.view.panels.property_panel import PropertyPanel
from daedalus.view.viewmodel.project_vm import ProjectViewModel
from daedalus.view.viewmodel.state_vm import StateViewModel
from daedalus.view.widgets.tag_input import TagInput, get_blackboard_candidates, set_blackboard_candidate_provider


def _panel_and_vm() -> tuple[PropertyPanel, ProjectViewModel]:
    vm = ProjectViewModel()
    panel = PropertyPanel(vm)
    return panel, vm


def _tag_inputs(panel: PropertyPanel) -> list[TagInput]:
    return panel.findChildren(TagInput)


def test_show_state_exposes_reads_writes_tag_inputs(qapp):
    panel, vm = _panel_and_vm()
    state = SimpleState(name="s", reads=["A"], writes=["B.field"])
    svm = StateViewModel(model=state, x=0, y=0)
    panel.show_state(svm)

    inputs = _tag_inputs(panel)
    assert len(inputs) == 2
    tags = {tuple(w.get_tags()) for w in inputs}
    assert ("A",) in tags
    assert ("B.field",) in tags


def test_editing_reads_tag_input_writes_back_to_model(qapp):
    panel, vm = _panel_and_vm()
    state = SimpleState(name="s")
    svm = StateViewModel(model=state, x=0, y=0)
    panel.show_state(svm)

    reads_input, writes_input = _tag_inputs(panel)
    reads_input.add_tag("TaskState")
    assert state.reads == ["TaskState"]


def test_editing_writes_tag_input_writes_back_to_model(qapp):
    panel, vm = _panel_and_vm()
    state = SimpleState(name="s")
    svm = StateViewModel(model=state, x=0, y=0)
    panel.show_state(svm)

    reads_input, writes_input = _tag_inputs(panel)
    writes_input.add_tag("TaskState.step")
    assert state.writes == ["TaskState.step"]


def test_editing_access_declaration_notifies_project_vm(qapp):
    panel, vm = _panel_and_vm()
    notified = []
    vm.add_listener(lambda: notified.append(1))

    state = SimpleState(name="s")
    svm = StateViewModel(model=state, x=0, y=0)
    panel.show_state(svm)

    reads_input, _ = _tag_inputs(panel)
    reads_input.add_tag("X")
    assert notified


def test_reads_writes_tag_input_uses_blackboard_candidates(qapp):
    try:
        set_blackboard_candidate_provider(lambda: ["TaskState", "TaskState.step"])
        panel, vm = _panel_and_vm()
        state = SimpleState(name="s")
        svm = StateViewModel(model=state, x=0, y=0)
        panel.show_state(svm)

        inputs = _tag_inputs(panel)
        for w in inputs:
            assert w.get_candidates() == ["TaskState", "TaskState.step"]
    finally:
        set_blackboard_candidate_provider(None)


def test_no_candidate_provider_gives_empty_candidates(qapp):
    set_blackboard_candidate_provider(None)
    assert get_blackboard_candidates() == []
