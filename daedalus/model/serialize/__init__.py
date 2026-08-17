# daedalus/model/serialize/
"""프로젝트 모델 ↔ JSON 호환 dict 직렬화 계층 (순수 모델 — Qt 무관).

원칙
----
- **소유 객체는 인라인, 참조는 ID 문자열로 평탄화한다.**
  - 참조 필드: ``Transition.source/target`` (state id), ``SimpleState.skill_ref``
    (component id), ``Transition.skill_ref`` (transfer skill id),
    ``StateMachine.initial_state/final_states`` (state id) 등.
- 다형성은 각 클래스의 ``kind`` property를 태그로 재사용한다. State 계열은
  kind property가 있으므로 그대로 사용한다.
- enum 은 ``.value`` 로 직렬화하고 역직렬화 시 enum 타입으로 복원한다.
- ``Blackboard.parent`` 는 ID 가 아니라 **소유 구조로 재연결**한다
  (sub_machine 역직렬화 시 부모 blackboard 를 구조적으로 다시 연결).

역직렬화는 2-pass 다:
  1. 객체 생성 + id→객체 레지스트리 구축
  2. 참조 해소 (state/skill/agent id → 실제 객체)

dangling id 는 ValueError 가 아니라 None 처리하고 경고를 수집한다.

포맷 버전 (v2)
--------------
- ``serialize_project`` 는 항상 ``"format": 2`` 를 쓴다.
- ``deserialize_project`` 는 format 1(또는 키 부재 구버전)을 받으면
  ``_migrate_v1`` 한 함수로 집약된 **단방향 마이그레이션**을 태운 뒤 v2 로
  읽는다 (왕복 보존 없음 — 열면 v2 로 저장된다). 미지의 상위 format 은 명시
  에러다.

WP-SZ: 구 단일 모듈 ``model/serialize.py``(1,437줄)를 패키지로 분해했다
(이동만, 동작 불변). 이 ``__init__`` 은 **재-export 파사드**다 — 분해 전 모듈의
모든 속성(public + 테스트가 쓰는 _언더스코어 헬퍼 + 부수 임포트)을 그대로
제공하므로 ``from daedalus.model.serialize import serialize_project, _ser_tool``
같은 기존 임포트가 전부 무수정으로 동작한다.

구획:
  ser.py     — 정방향(serialize_project + _ser_* 전부) + ``FORMAT_VERSION``
  migrate.py — format 1 → 2 단방향 마이그레이션(_migrate_v1 + 승계·승격·스크럽)
  deser.py   — 역방향(2-pass deserialize_project + _deser_* + _Registry)

의존 방향은 ``ser ← migrate ← deser`` 단방향이다 (순환 없음).
"""
from __future__ import annotations

# ── 분해 전 모듈의 부수 임포트 (파사드 완전성 — dir 기준 속성 집합 보존) ──
import copy
from typing import Any

from daedalus.model.fsm.action import Action
from daedalus.model.fsm.blackboard import (
    Blackboard,
    CollectionType,
    DynamicClass,
    DynamicField,
)
from daedalus.model.fsm.event import (
    BlackboardTrigger,
    CompletionEvent,
    Event,
)
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import (
    ChoiceState,
    EntryPoint,
    ExitPoint,
    TerminateState,
)
from daedalus.model.fsm.section import EventDef, Section, render_markdown
from daedalus.model.fsm.state import (
    CompositeState,
    ParallelState,
    Region,
    SimpleState,
    State,
)
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ExpressionEvaluation,
    LLMEvaluation,
    LLMExecution,
    MCPEvaluation,
    MCPExecution,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.transition import Transition, TransitionType
from daedalus.model.fsm.variable import (
    ConflictResolution,
    FieldType,
    Variable,
    VariableScope,
)
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.config import (
    AgentConfig,
    DeclarativeSkillConfig,
    ProceduralSkillConfig,
    ReferenceSkillConfig,
    TransferSkillConfig,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    BuildTarget,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillContext,
    SkillShell,
)
from daedalus.model.plugin.hook import HookDef, HookEvent
from daedalus.model.plugin.policy import ExecutionPolicy
from daedalus.model.plugin.skill import (
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    TransferSkill,
)
from daedalus.model.plugin.tool import (
    BuiltinTool,
    MCPTool,
    Tool,
    UserDefinedTool,
)
from daedalus.model.project import (
    PluginProject,
    ReferencePlacement,
    _make_project_graph,
)

# ── 분해된 구현 재-export ──
from daedalus.model.serialize.ser import (
    FORMAT_VERSION,
    _KNOWN_STATE_KINDS,
    _KNOWN_TOOL_KINDS,
    _enum_opt,
    _enum_val,
    _ser_action,
    _ser_actions,
    _ser_agent,
    _ser_blackboard,
    _ser_config,
    _ser_dynamic_class,
    _ser_dynamic_field,
    _ser_eval,
    _ser_event,
    _ser_eventdef,
    _ser_exec,
    _ser_guard,
    _ser_hook,
    _ser_hook_handler,
    _ser_machine,
    _ser_policy,
    _ser_ref_placement,
    _ser_region,
    _ser_skill,
    _ser_state,
    _ser_state_common,
    _ser_tool,
    _ser_transition,
    _ser_variable,
    serialize_project,
)
from daedalus.model.serialize.migrate import (
    _deser_section,
    _migrate_v1,
    _promote_local_skills,
    _v1_all_machines,
    _v1_scrub_number,
)
from daedalus.model.serialize.deser import (
    _EVAL_BUILDERS,
    _EXEC_BUILDERS,
    _Registry,
    _apply_state_common,
    _deser_action,
    _deser_actions,
    _deser_agent,
    _deser_blackboard,
    _deser_body,
    _deser_config,
    _deser_dynamic_class,
    _deser_dynamic_field,
    _deser_eval,
    _deser_event,
    _deser_eventdef,
    _deser_exec,
    _deser_guard,
    _deser_hook,
    _deser_hook_handler,
    _deser_machine,
    _deser_policy,
    _deser_ref_placement,
    _deser_region,
    _deser_skill,
    _deser_state,
    _deser_tool,
    _deser_transition,
    _deser_variable,
    _new_id,
    _to_enum,
    deserialize_project,
)
