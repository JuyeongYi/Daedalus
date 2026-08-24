"""진입점 프리셋의 두 호출부 — 캔버스 우클릭 / 스킬 에디터 (A8).

**로직은 여기서 검사하지 않는다**(tests/view/actions/test_entrypoint_presets.py).
여기서 고정하는 것은 두 표면이 **같은 함수를 부르는가**와, 프리셋을 지원하지
않는 대상에 UI를 만들지 않는가다 — 한쪽에 로직을 넣고 다른 쪽이 흉내 내면
"같은 조작인데 어디서 했느냐에 따라 결과가 다른" 상태가 된다.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox, QMenu

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill, TransferSkill
from daedalus.model.project import PluginProject
from daedalus.view.actions.entrypoint import EntryPreset, current_entry_preset
from daedalus.view.app import MainWindow


def _proc(name: str = "worker") -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def _agent() -> AgentDefinition:
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="af", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name="worker-agent", description="d",
        transfer_on=[EventDef(name="done")],
    )


@pytest.fixture
def window(qapp):
    skill = _proc()
    transfer = TransferSkill(
        fsm=StateMachine(
            name="tf", initial_state=SimpleState(name="s"),
            states=[SimpleState(name="s")],
        ),
        name="tr", description="d",
    )
    project = PluginProject(name="p", skills=[skill, transfer], agents=[_agent()])
    project.graph.states.append(SimpleState(name="worker", skill_ref=skill))
    project.graph.states.append(SimpleState(name="tr", skill_ref=transfer))
    project.graph.states.append(SimpleState(name="agent", skill_ref=project.agents[0]))
    project.graph.states.append(SimpleState(name="empty"))

    win = MainWindow()
    win.set_project(project)
    yield win
    win.close()


def _state_vm(window, node_name: str):
    return next(
        vm for vm in window._project_vm.state_vms if vm.model.name == node_name
    )


# --- 캔버스 우클릭 ---


def test_menu_offers_four_presets(window):
    scene = window._fsm_scene
    menu = QMenu()
    mapping = scene._add_entry_preset_menu(menu, _state_vm(window, "worker"))
    assert set(mapping.values()) == set(EntryPreset)
    assert len(mapping) == 4
    menu.deleteLater()


def test_menu_checks_the_current_preset(window):
    scene = window._fsm_scene
    state_vm = _state_vm(window, "worker")
    state_vm.model.skill_ref.config.user_invocable = True
    state_vm.model.skill_ref.config.disable_model_invocation = True

    menu = QMenu()
    mapping = scene._add_entry_preset_menu(menu, state_vm)
    checked = [preset for act, preset in mapping.items() if act.isChecked()]
    assert checked == [EntryPreset.USER_ONLY]
    menu.deleteLater()


@pytest.mark.parametrize("node", ["tr", "agent", "empty"])
def test_menu_absent_for_unsupported_nodes(window, node):
    """눌러도 아무 일도 일어나지 않는 항목은 없느니만 못하다."""
    scene = window._fsm_scene
    menu = QMenu()
    assert scene._add_entry_preset_menu(menu, _state_vm(window, node)) == {}
    menu.deleteLater()


def test_menu_handler_calls_shared_action(window, monkeypatch):
    calls: list = []
    import daedalus.view.actions.entrypoint as entrypoint

    monkeypatch.setattr(
        entrypoint, "apply_entry_preset",
        lambda vm, comp, preset: calls.append((vm, comp, preset)) or True,
    )
    scene = window._fsm_scene
    state_vm = _state_vm(window, "worker")
    scene._apply_entry_preset(state_vm, EntryPreset.PURE)

    assert len(calls) == 1
    vm, comp, preset = calls[0]
    assert vm is window._project_vm
    assert comp is state_vm.model.skill_ref
    assert preset is EntryPreset.PURE


def test_menu_action_actually_applies(window):
    """몽키패치 없이 한 번 — 공유 함수가 실제로 배선돼 있는지 확인."""
    scene = window._fsm_scene
    state_vm = _state_vm(window, "worker")
    scene._apply_entry_preset(state_vm, EntryPreset.PURE)
    assert current_entry_preset(state_vm.model.skill_ref) is EntryPreset.PURE
    assert window._project_vm.command_stack.can_undo


# --- 스킬 에디터 ---


def _entry_combo(panel) -> QComboBox | None:
    return panel._entry_preset_combo


def test_editor_has_preset_combo(window):
    from daedalus.view.editors.skill_editor import SkillEditor

    skill = window._project.skills[0]
    editor = SkillEditor(
        skill, on_notify_fn=window._project_vm.notify, project_vm=window._project_vm,
    )
    combo = _entry_combo(editor._editor._fm)
    assert combo is not None
    # "(직접 지정)" + 프리셋 4종
    assert combo.count() == 5
    editor.close()


def test_editor_combo_absent_for_fixed_kind(window):
    from daedalus.view.editors.skill_editor import SkillEditor

    transfer = window._project.skills[1]
    editor = SkillEditor(transfer, project_vm=window._project_vm)
    assert _entry_combo(editor._editor._fm) is None
    editor.close()


def test_editor_combo_absent_without_command_stack(window):
    """스택이 없으면 undo 가능한 편집을 할 수 없으므로 UI를 내지 않는다."""
    from daedalus.view.editors.skill_editor import SkillEditor

    editor = SkillEditor(window._project.skills[0])
    assert _entry_combo(editor._editor._fm) is None
    editor.close()


def test_editor_combo_calls_shared_action(window, monkeypatch):
    from daedalus.view.editors.skill_editor import SkillEditor

    skill = window._project.skills[0]
    editor = SkillEditor(skill, project_vm=window._project_vm)
    combo = _entry_combo(editor._editor._fm)
    assert combo is not None

    calls: list = []
    import daedalus.view.actions.entrypoint as entrypoint

    monkeypatch.setattr(
        entrypoint, "apply_entry_preset",
        lambda vm, comp, preset: calls.append((vm, comp, preset)) or True,
    )
    combo.setCurrentIndex(combo.findData(EntryPreset.USER_ONLY))

    assert len(calls) == 1
    assert calls[0][0] is window._project_vm
    assert calls[0][1] is skill
    assert calls[0][2] is EntryPreset.USER_ONLY
    editor.close()


def test_editor_combo_reflects_current_and_syncs_rows(window):
    """콤보로 고르면 개별 체크 행도 새 값을 보인다 — 둘이 다른 값을 말하면
    어느 쪽이 진실인지 알 수 없다."""
    from daedalus.model.plugin.enums import SkillField
    from daedalus.view.editors.skill_editor import SkillEditor, _OptionalRow

    skill = window._project.skills[0]
    editor = SkillEditor(skill, project_vm=window._project_vm)
    panel = editor._editor._fm
    combo = _entry_combo(panel)

    combo.setCurrentIndex(combo.findData(EntryPreset.PURE))
    assert skill.config.user_invocable is False
    assert skill.config.disable_model_invocation is False

    widget = panel._field_widgets[SkillField.USER_INVOCABLE]
    row = widget.parent()
    assert isinstance(row, _OptionalRow)
    assert row.is_checked() is True   # 명시 False도 "지정"이다
    assert widget.isChecked() is False

    combo.setCurrentIndex(combo.findData(EntryPreset.DEFAULT))
    assert skill.config.user_invocable is None
    assert row.is_checked() is False  # 미지정 → 체크 해제
    editor.close()


def test_editor_combo_loads_current_preset(window):
    from daedalus.view.editors.skill_editor import SkillEditor

    skill = window._project.skills[0]
    skill.config.user_invocable = True
    skill.config.disable_model_invocation = False
    editor = SkillEditor(skill, project_vm=window._project_vm)
    combo = _entry_combo(editor._editor._fm)
    assert combo.currentData() is EntryPreset.ENTRY
    editor.close()


def test_editor_combo_shows_no_preset_for_partial_state(window):
    from daedalus.view.editors.skill_editor import SkillEditor

    skill = window._project.skills[0]
    skill.config.user_invocable = True
    skill.config.disable_model_invocation = None
    editor = SkillEditor(skill, project_vm=window._project_vm)
    combo = _entry_combo(editor._editor._fm)
    assert combo.currentIndex() == 0
    assert combo.currentData() is None
    editor.close()
