# daedalus/compiler/emit/
"""model → 마크다운 텍스트 생성 (순수 — 파일시스템·Qt 무관).

여기서는 문자열만 만든다. 파일 쓰기·게이트는 project_compiler.py가 담당한다.
출력은 결정적이다 (같은 모델 → 같은 문자열, LF 줄바꿈).

WP-RF-3a: 구 단일 모듈 ``compiler/emit.py``를 패키지로 분해했다 (이동만, 동작
불변). 이 ``__init__``은 **재-export 파사드**다 — 분해 전 모듈의 모든 속성
(public + 테스트가 쓰는 _언더스코어 헬퍼 + 부수 임포트)을 그대로 제공하므로
``from daedalus.compiler.emit import compile_skill, _blackboard_section`` 같은
기존 임포트가 전부 무수정으로 동작한다.

구획:
  common.py      — 공용 헬퍼 (enum 값·config 기본값·본문 블록·블록 결합·
                   빌드 타깃 판정·그래프 placement 판정)
  frontmatter.py — 프론트매터 렌더 (YAML 스칼라/리스트/블록 + 스킬 프론트매터)
  sections.py    — 공용 단락 (가드/트리거·FSM 절차 서술·요구 환경(MCP)·
                   블랙보드·tool_shelf)
  skill.py       — SKILL.md 조립 (다음 단계·작업 재개·진입 맥락 + compile_skill)
  agent.py       — 에이전트 .md 조립 (출구·호출 계약·skills 합류·호출 파라미터
                   + compile_agent)
  hooks.py       — hooks.json·훅 스크립트 (compile_hooks_json/compile_hook_scripts)
  manifest.py    — plugin.json·schemas.json·경로 변수 확장

확정 정책 (WP-compiler-v0):
  1. 프론트매터: 해당 kind 매트릭스에서 emit==FRONTMATTER인 필드만. 키는
     frontmatter_key. FIXED는 fixed_value 강제. model==INHERIT는 키 생략.
     OPTIONAL 필드 값이 선언 기본값과 같으면 생략. enum은 .value.
  2. when_to_use: description과 합류 — "<description> Use when <when_to_use>".
  3. 본문: body(단일 마크다운 문자열)을 그대로 배출(공백뿐이면 블록 생략, WP-SB).
  4. ProceduralSkill FSM → 사람이 읽는 절차 단락.
  5. tool_shelf: 참조 문서 단락.
"""
from __future__ import annotations

# ── 분해 전 모듈의 부수 임포트 (파사드 완전성 — dir 기준 public 집합 보존) ──
import json
from dataclasses import MISSING as _DC_MISSING
from dataclasses import fields as dc_fields
from enum import Enum
from typing import Any

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    SimpleState,
    State,
)
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    EvaluationStrategy,
    ExpressionEvaluation,
    LLMEvaluation,
    MCPEvaluation,
    ToolEvaluation,
)
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.enums import (
    AgentField,
    FieldEmit,
    FieldVisibility,
    ModelType,
    SkillField,
)
from daedalus.model.plugin.field_matrix import (
    AGENT_FIELD_MATRIX,
    SKILL_FIELD_MATRIX,
    FieldRule,
)
from daedalus.model.plugin.hook import (
    HOOK_SCRIPT_DIR,
    HOOK_SCRIPT_REF_PREFIX,
    HookDef,
    HookEvent,
)
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    Skill,
    TransferSkill,
)

# ── 분해된 구현 재-export ──
from daedalus.compiler.emit.common import (
    _MISSING,
    _Missing,
    _body_block,
    _build_target,
    _config_default,
    _enum_value,
    _graph_placements,
    _graph_placements_any,
    _is_local_build,
    _join_blocks,
)
from daedalus.compiler.emit.frontmatter import (
    _YAML_RESERVED,
    _compose_description,
    _emit_skill_field,
    _format_kv,
    _frontmatter_block,
    _frontmatter_lines_skill,
    _yaml_block_lines,
    _yaml_list,
    _yaml_scalar,
)
from daedalus.compiler.emit.sections import (
    _blackboard_section,
    _collect_state_access,
    _component_access_union,
    _describe_access,
    _describe_evaluation,
    _describe_fsm,
    _describe_guard,
    _describe_join,
    _describe_node_action,
    _describe_trigger,
    _fsm_procedure_blocks,
    _mcp_requirement_section_skill,
    _mcp_servers_from_tools,
    _ordered_states,
    _state_label,
    _tool_shelf_section,
    _transition_condition,
    referenced_mcp_servers,
)
from daedalus.compiler.emit.skill import (
    _PROGRESS_UPDATE_NOTE,
    _TRANSFER_PROGRESS_NOTE,
    _entry_context_section,
    _entry_incoming_transitions,
    _entry_item_line,
    _entry_source_ref_name,
    _invoke_phrase,
    _next_step_condition,
    _next_step_invoke_line,
    _next_steps_section,
    _progress_terminal_section,
    _resume_preamble_section,
    _skill_kind_key,
    compile_skill,
)
from daedalus.compiler.emit.agent import (
    _agent_hook_groups,
    _agent_mcp_server_names,
    _agent_outputs_section,
    _agent_skills_list,
    _call_contract_section,
    _describe_agent_fsm,
    _emit_agent_field,
    _frontmatter_lines_agent,
    _invocation_section_agent,
    _local_settings_frontmatter_lines,
    _settings_note_agent,
    compile_agent,
)
from daedalus.compiler.emit.hooks import (
    _PROGRESS_SCRIPT_NAME,
    _PROGRESS_SCRIPT_REF,
    _PROGRESS_SESSION_START_COMMAND,
    _collect_referenced_hook_names,
    _progress_hook_entry,
    _script_text,
    _should_emit_progress_hook,
    compile_hook_scripts,
    compile_hooks_json,
)
from daedalus.compiler.emit.manifest import (
    _LOCAL_FILE_REF_FROM,
    _LOCAL_FILE_REF_TO,
    _class_to_json_schema,
    _field_to_json_schema,
    compile_plugin_manifest,
    compile_schemas_json,
    expand_root_token,
    substitute_local_file_refs,
)
