# tests/model/test_validation_facade.py
"""WP-RF-3d: validation.py → validation/ 패키지 분해의 재-export 파사드 완전성 고정.

분해 전 단일 모듈 ``model/validation.py``의 속성 집합(dir 기준, dunder 제외)과
``Validator``의 멤버 집합을 그대로 하드코딩해, 분해 후 패키지
``daedalus.model.validation``에서 전부 접근 가능함을 고정한다 — 기존 호출부·
테스트가 쓰는 ``from daedalus.model.validation import <이름>``과
``Validator._check_*`` 경로가 어떤 이름이든 깨지지 않는 것이 분해의 1차 게이트다.
"""
from __future__ import annotations

import daedalus.model.validation as validation
from daedalus.model.validation import Validator

# 분해 직전 validation.py의 dir() 스냅샷 (dunder 제외) — 2026-08-17 실측.
_PRE_SPLIT_ATTRS = [
    "BuildTarget",
    "CC_BUILTIN_TOOLS",
    "ChoiceState",
    "CompletionEvent",
    "CompositeEvaluation",
    "CompositeExecution",
    "CompositeState",
    "EntryPoint",
    "EvaluationStrategy",
    "ExecutionStrategy",
    "ExitPoint",
    "ParallelState",
    "PermissionMode",
    "SKIPPABLE_RULES",
    "State",
    "StateMachine",
    "TerminateState",
    "ToolEvaluation",
    "ToolExecution",
    "Transition",
    "ValidationError",
    "Validator",
    "VariableScope",
    "WARNING_RULES",
    "_CODE_FENCE_RE",
    "_INLINE_CODE_RE",
    "_strip_markdown_code",
    "annotations",
    "dataclass",
    "field",
    "re",
]

# 분해 직전 Validator의 멤버 스냅샷 (dunder 제외) — 외부·내부 호출부가 이 이름으로
# 부른다(예: compiler/emit/common.py의 Validator._graph_has_placements).
_PRE_SPLIT_VALIDATOR_MEMBERS = [
    "_COMPONENT_NAME_RE",
    "_STATE_ACTION_FIELDS",
    "_TRANSITION_ACTION_FIELDS",
    "_check_agent_to_agent",
    "_check_blackboard_field_types",
    "_check_choice_completeness",
    "_check_completion_events",
    "_check_dangling_blackboard_refs",
    "_check_dangling_hook_refs",
    "_check_dangling_string_references",
    "_check_dangling_tool_refs",
    "_check_duplicate_component_name",
    "_check_duplicate_hook_name",
    "_check_duplicate_skill_ref",
    "_check_duplicate_state_name",
    "_check_duplicate_tool_name",
    "_check_empty_hook_command",
    "_check_empty_tool_definition",
    "_check_final_in_states",
    "_check_hook_matcher_event",
    "_check_initial_in_states",
    "_check_invalid_component_name",
    "_check_invalid_data_map_source",
    "_check_invalid_project_name",
    "_check_mcp_agent_in_marketplace_build",
    "_check_nested_agents",
    "_check_orphan_blackboard_fields",
    "_check_parallel_join_count",
    "_check_plugin_root_in_local_build",
    "_check_pseudo_state_hooks",
    "_check_required_inputs",
    "_check_skill_dir_token_in_agent",
    "_check_transfer_on_not_empty",
    "_check_transition_endpoints",
    "_check_transition_type_consistency",
    "_check_trigger_unknown_event",
    "_check_unreachable_state",
    "_check_unsupported_agent_fields",
    "_collect_eval_tools",
    "_collect_exec_tools",
    "_collect_hook_refs",
    "_collect_machine_tool_refs",
    "_graph_has_placements",
    "_project_machines",
    "_scan_state_access",
    "_validate_machine",
    "validate",
    "validate_project",
]


def test_facade_exposes_all_pre_split_attributes():
    """분해 전 모듈의 모든 속성이 패키지 파사드에서도 접근 가능해야 한다."""
    missing = [name for name in _PRE_SPLIT_ATTRS if not hasattr(validation, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_validator_keeps_all_pre_split_members():
    """Validator의 멤버 이름이 하나도 사라지지 않아야 한다."""
    missing = [n for n in _PRE_SPLIT_VALIDATOR_MEMBERS if not hasattr(Validator, n)]
    assert not missing, f"Validator 멤버 누락: {missing}"


def test_facade_reexports_are_submodule_objects():
    """파사드의 이름이 각 구현 모듈의 객체와 동일해야 한다 (복제 아님)."""
    from daedalus.model.validation import machine_rules, project_rules, severity

    assert validation.ValidationError is severity.ValidationError
    assert validation.WARNING_RULES is severity.WARNING_RULES
    assert validation.SKIPPABLE_RULES is machine_rules.SKIPPABLE_RULES
    assert validation.CC_BUILTIN_TOOLS is project_rules.CC_BUILTIN_TOOLS
    assert validation._strip_markdown_code is project_rules._strip_markdown_code
    # Validator는 두 믹스인의 합성 — 메서드 실체가 각 그룹 모듈에 있어야 한다.
    assert Validator.validate is machine_rules._MachineRules.validate
    assert Validator.validate_project is project_rules._ProjectRules.validate_project
    assert (
        Validator._check_unreachable_state
        is machine_rules._MachineRules._check_unreachable_state
    )
    assert (
        Validator._check_dangling_tool_refs
        is project_rules._ProjectRules._check_dangling_tool_refs
    )


def test_validator_mixin_composition():
    """Validator가 두 규칙 그룹 믹스인을 상속한다 (합성 지점 고정)."""
    from daedalus.model.validation import machine_rules, project_rules

    assert issubclass(Validator, machine_rules._MachineRules)
    assert issubclass(Validator, project_rules._ProjectRules)


def test_state_action_fields_are_single_source():
    """액션 체인 필드 목록은 머신 규칙 모듈이 단일 진실 — 도구 수집도 이것을 본다."""
    from daedalus.model.validation import machine_rules

    assert Validator._STATE_ACTION_FIELDS is machine_rules._MachineRules._STATE_ACTION_FIELDS
    assert "on_entry" in Validator._STATE_ACTION_FIELDS
    assert "on_traverse" in Validator._TRANSITION_ACTION_FIELDS
