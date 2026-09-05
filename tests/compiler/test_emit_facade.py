# tests/compiler/test_emit_facade.py
"""WP-RF-3a: emit.py → emit/ 패키지 분해의 재-export 파사드 완전성 고정.

분해 전 단일 모듈 ``compiler/emit.py``의 속성 집합(dir 기준, dunder 제외)을
그대로 하드코딩해, 분해 후 패키지 ``daedalus.compiler.emit``에서 전부 임포트
가능함을 고정한다 — 기존 테스트·호출부가 쓰는 ``from daedalus.compiler.emit
import <이름>`` 경로가 어떤 이름이든 깨지지 않는 것이 분해의 1차 게이트다.
"""
from __future__ import annotations

import daedalus.compiler.emit as emit

# 분해 직전 emit.py의 dir() 스냅샷 (dunder 제외) — 2026-08-17 실측.
# 이후 **실제로 삭제된** 이름은 여기서도 뺀다(파사드가 죽은 코드를 붙잡고 있으면
# 안 된다): substitute_local_file_refs/_LOCAL_FILE_REF_FROM/_LOCAL_FILE_REF_TO는
# 프로덕션 호출이 0이 되어 2026-09-06에 제거됐다.
_PRE_SPLIT_ATTRS = [
    "AGENT_FIELD_MATRIX",
    "AgentDefinition",
    "AgentField",
    "Any",
    "ChoiceState",
    "CompletionEvent",
    "ComponentConfig",
    "CompositeEvaluation",
    "CompositeState",
    "DeclarativeSkill",
    "EntryPoint",
    "Enum",
    "EvaluationStrategy",
    "ExitPoint",
    "ExpressionEvaluation",
    "FieldEmit",
    "FieldRule",
    "FieldVisibility",
    "Guard",
    "HOOK_SCRIPT_DIR",
    "HOOK_SCRIPT_REF_PREFIX",
    "HookDef",
    "HookEvent",
    "LLMEvaluation",
    "MCPEvaluation",
    "ModelType",
    "ParallelState",
    "ProceduralSkill",
    "ReferenceSkill",
    "SKILL_FIELD_MATRIX",
    "SimpleState",
    "Skill",
    "SkillField",
    "State",
    "StateMachine",
    "TerminateState",
    "ToolEvaluation",
    "TransferSkill",
    "_DC_MISSING",
    "_MISSING",
    "_Missing",
    "_PROGRESS_SCRIPT_NAME",
    "_PROGRESS_SCRIPT_REF",
    "_PROGRESS_SESSION_START_COMMAND",
    "_PROGRESS_MANUAL_FALLBACK",
    "_YAML_RESERVED",
    "_agent_hook_groups",
    "_agent_mcp_server_names",
    "_agent_outputs_section",
    "_agent_skills_list",
    "_blackboard_section",
    "_body_block",
    "_build_target",
    "_call_contract_section",
    "_class_to_json_schema",
    "_collect_referenced_hook_names",
    "_collect_state_access",
    "_component_access_union",
    "_compose_description",
    "_config_default",
    "_describe_access",
    "_describe_agent_fsm",
    "_describe_evaluation",
    "_describe_fsm",
    "_describe_guard",
    "_describe_join",
    "_describe_node_action",
    "_describe_trigger",
    "_emit_agent_field",
    "_emit_skill_field",
    "_entry_context_section",
    "_entry_incoming_transitions",
    "_entry_item_line",
    "_entry_source_ref_name",
    "_enum_value",
    "_field_to_json_schema",
    "_format_kv",
    "_frontmatter_block",
    "_frontmatter_lines_agent",
    "_frontmatter_lines_skill",
    "_fsm_procedure_blocks",
    "_graph_placements",
    "_graph_placements_any",
    "_invocation_section_agent",
    "_invoke_phrase",
    "_is_local_build",
    "_join_blocks",
    "_local_settings_frontmatter_lines",
    "_mcp_requirement_section_skill",
    "_mcp_servers_from_tools",
    "_next_step_condition",
    "_next_step_invoke_line",
    "_next_steps_section",
    "_ordered_states",
    "_progress_hook_entry",
    "_progress_cli",
    "_progress_terminal_section",
    "_progress_update_note",
    "_resume_preamble_section",
    "_transfer_progress_note",
    "_script_text",
    "_settings_note_agent",
    "_should_emit_progress_hook",
    "_skill_kind_key",
    "_state_label",
    "_tool_shelf_section",
    "_transition_condition",
    "_yaml_block_lines",
    "_yaml_list",
    "_yaml_scalar",
    "annotations",
    "compile_agent",
    "compile_hook_scripts",
    "compile_hooks_json",
    "compile_plugin_manifest",
    "compile_schemas_json",
    "compile_skill",
    "dc_fields",
    "expand_root_token",
    "json",
    "referenced_mcp_servers",
]


def test_facade_exposes_all_pre_split_attributes():
    """분해 전 모듈의 모든 속성이 패키지 파사드에서도 접근 가능해야 한다."""
    missing = [name for name in _PRE_SPLIT_ATTRS if not hasattr(emit, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_facade_reexports_are_submodule_objects():
    """파사드의 이름이 각 구현 모듈의 객체와 동일해야 한다 (복제 아님)."""
    from daedalus.compiler.emit import agent, frontmatter, hooks, manifest, sections, skill

    assert emit.compile_skill is skill.compile_skill
    assert emit.compile_agent is agent.compile_agent
    assert emit.compile_hooks_json is hooks.compile_hooks_json
    assert emit.compile_hook_scripts is hooks.compile_hook_scripts
    assert emit.compile_plugin_manifest is manifest.compile_plugin_manifest
    assert emit.compile_schemas_json is manifest.compile_schemas_json
    assert emit.referenced_mcp_servers is sections.referenced_mcp_servers
    assert emit._yaml_block_lines is frontmatter._yaml_block_lines
    # sentinel 단일성 — _MISSING이 모듈마다 딴 객체면 config 기본값 비교가 깨진다
    from daedalus.compiler.emit import common

    assert emit._MISSING is common._MISSING
