"""ValidationError.is_warning / WARNING_RULES 완전성 테스트 (WP-J)."""
from __future__ import annotations

import pytest

from daedalus.model.validation import ValidationError, WARNING_RULES, Validator
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import SimpleState
from daedalus.model.project import PluginProject


# 에러로 분류되어야 하는 규칙 목록
_ERROR_RULES = frozenset({
    "initial_state_in_states",
    "final_states_in_states",
    "no_nested_agent",
    "no_agent_to_agent",
    "no_duplicate_skill_ref",
    "transfer_on_not_empty",
    "transition_endpoint_not_in_states",
    "duplicate_component_name",
})

# 경고로 분류되어야 하는 규칙 목록 (WARNING_RULES와 동일)
_WARN_RULES = frozenset({
    "missing_required_input",
    "pseudo_state_hooks",
    "completion_event_on_composite",
    "empty_delegation",
    "forget_completion_mismatch",
    "duplicate_state_name",
    "unreachable_state",
    "invalid_data_map_source",
    "trigger_unknown_event",
    "dangling_teammate_ref",
    "dangling_string_reference",
    "invalid_component_name",
})


def test_warning_rules_completeness():
    """WARNING_RULES가 경고 규칙 집합과 동일하다."""
    assert WARNING_RULES == _WARN_RULES


def test_error_and_warning_rules_are_disjoint():
    """에러 규칙과 경고 규칙이 겹치지 않는다 (invalid_component_name 제외)."""
    overlap = _ERROR_RULES & WARNING_RULES
    assert not overlap, f"에러/경고 규칙 중복: {overlap}"


@pytest.mark.parametrize("rule", sorted(_ERROR_RULES))
def test_error_rule_is_not_warning(rule: str):
    """에러 등급 규칙은 is_warning이 False다."""
    err = ValidationError(rule=rule, message="test msg", source="s")
    assert not err.is_warning, f"규칙 '{rule}'은 에러여야 한다"


@pytest.mark.parametrize("rule", sorted(_WARN_RULES - {"invalid_component_name"}))
def test_warning_rule_is_warning(rule: str):
    """경고 등급 규칙은 is_warning이 True다."""
    err = ValidationError(rule=rule, message="test msg", source="s")
    assert err.is_warning, f"규칙 '{rule}'은 경고여야 한다"


def test_invalid_component_name_empty_is_error():
    """invalid_component_name + '비어 있습니다' 메시지 → 에러."""
    err = ValidationError(
        rule="invalid_component_name",
        message="컴포넌트 이름이 비어 있습니다.",
        source="",
    )
    assert not err.is_warning


def test_invalid_component_name_mismatch_is_warning():
    """invalid_component_name + 일반 불일치 메시지 → 경고."""
    err = ValidationError(
        rule="invalid_component_name",
        message="컴포넌트 이름 'MySkill'이 명명 규약에 맞지 않습니다.",
        source="MySkill",
    )
    assert err.is_warning
