"""진입점 프리셋 — 공유 액션 함수 (A8).

**로직 테스트는 여기 하나뿐이다.** 캔버스 우클릭 메뉴와 스킬 에디터 콤보는
`apply_entry_preset`을 부르는 호출부일 뿐이므로, 그쪽 테스트는 "이 함수를
부르는가"만 확인한다(로직 중복 금지).
"""
from __future__ import annotations

import pytest

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.view.actions.entrypoint import (
    ENTRY_PRESETS,
    EntryPreset,
    apply_entry_preset,
    current_entry_preset,
    spec_for,
    supports_entry_presets,
)
from daedalus.view.viewmodel.project_vm import ProjectViewModel


def _proc(name: str = "worker") -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s], final_states=[s])
    return ProceduralSkill(fsm=fsm, name=name, description="d")


def _transfer() -> TransferSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name="f", initial_state=s, states=[s])
    return TransferSkill(fsm=fsm, name="t", description="d")


def _agent() -> AgentDefinition:
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="af", initial_state=entry, states=[entry])
    return AgentDefinition(
        fsm=fsm, name="a", description="d", transfer_on=[EventDef(name="done")],
    )


@pytest.fixture
def vm() -> ProjectViewModel:
    return ProjectViewModel()


# --- 노출 판정 ---


def test_procedural_and_declarative_support_presets():
    """두 필드가 매트릭스에서 OPTIONAL인 종류에만 노출한다."""
    assert supports_entry_presets(_proc()) is True
    assert supports_entry_presets(DeclarativeSkill(name="k", description="d")) is True


def test_fixed_kinds_do_not_support_presets():
    """FIXED 필드를 프리셋으로 덮으면 컴파일이 fixed_value를 강제해
    "설정했는데 아무 일도 없는" 상태가 된다."""
    assert supports_entry_presets(_transfer()) is False
    assert supports_entry_presets(ReferenceSkill(name="r", description="d")) is False


def test_agent_does_not_support_presets():
    """에이전트는 두 필드 자체가 없다."""
    assert supports_entry_presets(_agent()) is False


def test_empty_node_component_is_none_safe():
    assert supports_entry_presets(None) is False


# --- 현재 프리셋 판정 ---


def test_new_skill_is_default_preset():
    """tri-state 선언 기본값(None/None) = "일반 상태로"."""
    assert current_entry_preset(_proc()) is EntryPreset.DEFAULT


@pytest.mark.parametrize("preset", list(EntryPreset))
def test_apply_then_current_roundtrip(vm, preset):
    skill = _proc()
    apply_entry_preset(vm, skill, preset)
    assert current_entry_preset(skill) is preset


def test_partial_state_matches_no_preset():
    """반쪽만 지정된 조합은 어느 프리셋도 아니다 — 체크가 없는 것이 정직하다."""
    skill = _proc()
    skill.config.user_invocable = True
    skill.config.disable_model_invocation = None
    assert current_entry_preset(skill) is None


def test_current_preset_of_fixed_kind_is_none():
    assert current_entry_preset(_transfer()) is None


# --- 적용 ---


@pytest.mark.parametrize("preset", list(EntryPreset))
def test_preset_sets_both_fields(vm, preset):
    skill = _proc()
    spec = spec_for(preset)
    apply_entry_preset(vm, skill, preset)
    assert skill.config.user_invocable is spec.user_invocable
    assert skill.config.disable_model_invocation is spec.disable_model_invocation


def test_apply_is_one_undo_unit(vm):
    """두 필드가 1 undo 단위 — 한 필드씩 되돌아가면 중간에 의미 없는 조합
    (아무 데서도 못 부르는 노드)을 거친다."""
    skill = _proc()
    apply_entry_preset(vm, skill, EntryPreset.USER_ONLY)
    assert len(vm.command_stack.history) == 1

    vm.command_stack.undo()
    assert skill.config.user_invocable is None
    assert skill.config.disable_model_invocation is None


def test_redo_reapplies_both(vm):
    skill = _proc()
    apply_entry_preset(vm, skill, EntryPreset.PURE)
    vm.command_stack.undo()
    vm.command_stack.redo()
    assert skill.config.user_invocable is False
    assert skill.config.disable_model_invocation is False


def test_switching_presets_is_undoable_step_by_step(vm):
    skill = _proc()
    apply_entry_preset(vm, skill, EntryPreset.ENTRY)
    apply_entry_preset(vm, skill, EntryPreset.PURE)
    assert current_entry_preset(skill) is EntryPreset.PURE

    vm.command_stack.undo()
    assert current_entry_preset(skill) is EntryPreset.ENTRY
    vm.command_stack.undo()
    assert current_entry_preset(skill) is EntryPreset.DEFAULT


def test_applying_the_same_preset_is_a_no_op(vm):
    """값이 같은데 커맨드를 쌓으면 Ctrl+Z가 아무 변화 없는 단계를 센다."""
    skill = _proc()
    assert apply_entry_preset(vm, skill, EntryPreset.DEFAULT) is False
    assert vm.command_stack.history == []

    assert apply_entry_preset(vm, skill, EntryPreset.ENTRY) is True
    assert apply_entry_preset(vm, skill, EntryPreset.ENTRY) is False
    assert len(vm.command_stack.history) == 1


def test_apply_refuses_unsupported_component(vm):
    transfer = _transfer()
    assert apply_entry_preset(vm, transfer, EntryPreset.ENTRY) is False
    assert vm.command_stack.history == []


# --- 프리셋 표 자체 ---


def test_preset_table_covers_every_member():
    """프리셋 멤버가 늘면 표도 늘어야 한다 — 메뉴/콤보가 이 표를 순회한다."""
    assert {spec.preset for spec in ENTRY_PRESETS} == set(EntryPreset)
    assert len(ENTRY_PRESETS) == len(EntryPreset)


def test_preset_value_sets_are_distinct():
    """네 프리셋의 (user_invocable, disable) 조합이 서로 달라야 current 판정이
    유일하다."""
    combos = {
        (spec.user_invocable, spec.disable_model_invocation)
        for spec in ENTRY_PRESETS
    }
    assert len(combos) == len(ENTRY_PRESETS)
