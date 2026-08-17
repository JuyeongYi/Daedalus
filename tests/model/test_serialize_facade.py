# tests/model/test_serialize_facade.py
"""WP-SZ: serialize.py → serialize/ 패키지 분해의 재-export 파사드 완전성 고정.

분해 전 단일 모듈 ``model/serialize.py``의 속성 집합(dir 기준, dunder 제외)을
그대로 하드코딩해, 분해 후 패키지 ``daedalus.model.serialize``에서 전부 접근
가능함을 고정한다 — 기존 호출부·테스트가 쓰는
``from daedalus.model.serialize import <이름>`` 경로가 어떤 이름이든 깨지지
않는 것이 분해의 1차 게이트다(``_ser_tool``/``_deser_tool`` 처럼 언더스코어
헬퍼를 직접 임포트하는 테스트가 실제로 있다).
"""
from __future__ import annotations

import daedalus.model.serialize as serialize

# 분해 직전 serialize.py의 dir() 스냅샷 (dunder 제외) — 2026-08-18 실측, 138개.
_PRE_SPLIT_ATTRS = [
    "Action",
    "AgentColor",
    "AgentConfig",
    "AgentDefinition",
    "AgentIsolation",
    "Any",
    "Blackboard",
    "BlackboardTrigger",
    "BuildTarget",
    "BuiltinTool",
    "ChoiceState",
    "CollectionType",
    "CompletionEvent",
    "CompositeEvaluation",
    "CompositeExecution",
    "CompositeState",
    "ConflictResolution",
    "DeclarativeSkill",
    "DeclarativeSkillConfig",
    "DynamicClass",
    "DynamicField",
    "EffortLevel",
    "EntryPoint",
    "EvaluationStrategy",
    "Event",
    "EventDef",
    "ExecutionPolicy",
    "ExecutionStrategy",
    "ExitPoint",
    "ExpressionEvaluation",
    "FORMAT_VERSION",
    "FieldType",
    "Guard",
    "HookDef",
    "HookEvent",
    "JoinStrategy",
    "LLMEvaluation",
    "LLMExecution",
    "MCPEvaluation",
    "MCPExecution",
    "MCPTool",
    "MemoryScope",
    "ModelType",
    "ParallelState",
    "PermissionMode",
    "PluginProject",
    "ProceduralSkill",
    "ProceduralSkillConfig",
    "ReferencePlacement",
    "ReferenceSkill",
    "ReferenceSkillConfig",
    "Region",
    "Section",
    "SimpleState",
    "SkillContext",
    "SkillShell",
    "State",
    "StateMachine",
    "TerminateState",
    "Tool",
    "ToolEvaluation",
    "ToolExecution",
    "TransferSkill",
    "TransferSkillConfig",
    "Transition",
    "TransitionType",
    "UserDefinedTool",
    "Variable",
    "VariableScope",
    "_EVAL_BUILDERS",
    "_EXEC_BUILDERS",
    "_KNOWN_STATE_KINDS",
    "_KNOWN_TOOL_KINDS",
    "_Registry",
    "_apply_state_common",
    "_deser_action",
    "_deser_actions",
    "_deser_agent",
    "_deser_blackboard",
    "_deser_body",
    "_deser_config",
    "_deser_dynamic_class",
    "_deser_dynamic_field",
    "_deser_eval",
    "_deser_event",
    "_deser_eventdef",
    "_deser_exec",
    "_deser_guard",
    "_deser_hook",
    "_deser_hook_handler",
    "_deser_machine",
    "_deser_policy",
    "_deser_ref_placement",
    "_deser_region",
    "_deser_section",
    "_deser_skill",
    "_deser_state",
    "_deser_tool",
    "_deser_transition",
    "_deser_variable",
    "_enum_opt",
    "_enum_val",
    "_make_project_graph",
    "_migrate_v1",
    "_new_id",
    "_promote_local_skills",
    "_ser_action",
    "_ser_actions",
    "_ser_agent",
    "_ser_blackboard",
    "_ser_config",
    "_ser_dynamic_class",
    "_ser_dynamic_field",
    "_ser_eval",
    "_ser_event",
    "_ser_eventdef",
    "_ser_exec",
    "_ser_guard",
    "_ser_hook",
    "_ser_hook_handler",
    "_ser_machine",
    "_ser_policy",
    "_ser_ref_placement",
    "_ser_region",
    "_ser_skill",
    "_ser_state",
    "_ser_state_common",
    "_ser_tool",
    "_ser_transition",
    "_ser_variable",
    "_to_enum",
    "_v1_all_machines",
    "_v1_scrub_number",
    "annotations",
    "copy",
    "deserialize_project",
    "render_markdown",
    "serialize_project",
]


def test_facade_exposes_all_pre_split_attributes():
    """분해 전 모듈의 모든 속성이 패키지 파사드에서도 접근 가능해야 한다."""
    missing = [name for name in _PRE_SPLIT_ATTRS if not hasattr(serialize, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_facade_reexports_are_submodule_objects():
    """파사드의 이름이 각 구현 모듈의 객체와 동일해야 한다 (복제 아님)."""
    from daedalus.model.serialize import deser, migrate, ser

    assert serialize.serialize_project is ser.serialize_project
    assert serialize.deserialize_project is deser.deserialize_project
    assert serialize._migrate_v1 is migrate._migrate_v1
    assert serialize._promote_local_skills is migrate._promote_local_skills
    assert serialize._ser_tool is ser._ser_tool
    assert serialize._deser_tool is deser._deser_tool
    assert serialize._Registry is deser._Registry
    # FORMAT_VERSION은 쓰는 쪽(ser)이 단일 진실 — 읽는 쪽/마이그레이션이 그것을 본다.
    assert serialize.FORMAT_VERSION is ser.FORMAT_VERSION
    assert deser.FORMAT_VERSION is ser.FORMAT_VERSION
    assert migrate.FORMAT_VERSION is ser.FORMAT_VERSION


def test_dependency_direction_is_acyclic():
    """의존 방향 ser ← migrate ← deser 고정 — 역방향 임포트는 순환을 만든다."""
    import ast
    from pathlib import Path

    pkg = Path(serialize.__file__).parent

    def imported_siblings(name: str) -> set[str]:
        tree = ast.parse((pkg / name).read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("daedalus.model.serialize"):
                    found.add(node.module.rsplit(".", 1)[-1])
        return found

    assert imported_siblings("ser.py") == set()
    assert imported_siblings("migrate.py") == {"ser"}
    assert imported_siblings("deser.py") == {"ser", "migrate"}


def test_split_modules_are_within_soft_budget():
    """분해 목표 — 각 모듈 800줄 이하 (하드 상한 1,200은 위생 테스트가 강제)."""
    from pathlib import Path

    pkg = Path(serialize.__file__).parent
    oversized = {
        p.name: len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(pkg.glob("*.py"))
        if len(p.read_text(encoding="utf-8").splitlines()) > 800
    }
    assert not oversized, f"분해 목표(800줄) 초과: {oversized}"
