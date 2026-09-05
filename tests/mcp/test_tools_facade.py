# tests/mcp/test_tools_facade.py
"""WP-RF-3b: mcp/tools.py → mcp/tools/ 패키지 분해의 재-export 파사드 완전성 고정.

분해 전 단일 모듈 ``mcp/tools.py``의 속성 집합(dir 기준, dunder 제외)과
``DaedalusTools``의 멤버 집합을 그대로 하드코딩해, 분해 후 패키지
``daedalus.mcp.tools``에서 전부 접근 가능함을 고정한다 — SDK가 메서드
docstring·시그니처로 입력 스키마를 만들므로(service._wrap의 functools.wraps
경로) 메서드 표면이 그대로 보존되는 것이 분해의 1차 게이트다.
"""
from __future__ import annotations

import daedalus.mcp.tools as tools

# 분해 직전 tools.py의 dir() 스냅샷 (dunder 제외) — 2026-08-17 실측.
_PRE_SPLIT_MODULE_ATTRS = [
    "Any",
    "DaedalusTools",
    "_MAX_BODY_PREVIEW",
    "annotations",
    "os",
]

# 분해 직전 DaedalusTools의 멤버 스냅샷 (vars 기준, dunder 제외) — 75종.
# 이후 **실제로 삭제된** 멤버는 여기서도 뺀다: _all_hook_owners는 _BaseTools의
# _components와 본문이 같은 사본이라 2026-09-06에 제거됐다(호출부는 _components로).
_PRE_SPLIT_CLASS_MEMBERS = [
    "_body_text",
    "_build_hook_handler",
    "_coerce_field_value",
    "_component_kind",
    "_components",
    "_config_field_types",
    "_find_component",
    "_find_hook",
    "_find_ref_vm",
    "_find_state_vm",
    "_find_transition_vm",
    "_hook_summary",
    "_make_event_defs",
    "_make_guard",
    "_make_trigger",
    "_placement_summary",
    "_project",
    "_reference_summary",
    "_refresh_hook_ui",
    "_reject_duplicate_name",
    "_scene",
    "_scope",
    "_skill_matrix_key",
    "_status_text",
    "_transition_summary",
    "_vm",
    "add_agent_call",
    "compile_preview",
    "connect_states",
    "create_agent",
    "create_blackboard_class",
    "create_hook",
    "create_skill",
    "create_state",
    "delete_hook",
    "delete_state",
    "disconnect_states",
    "export_package",
    "get_body_outline",
    "get_body_section",
    "get_component",
    "get_history",
    "get_project",
    "get_selection",
    "hook_frontmatter_preview",
    "link_reference",
    "list_component_fields",
    "list_hook_events",
    "list_recent_projects",
    "move_state",
    "open_project",
    "place_component",
    "place_reference",
    "redo",
    "remove_agent_call",
    "rename_component",
    "rename_state",
    "save_project",
    "set_body_section",
    "set_component_body",
    "set_component_description",
    "set_component_field",
    "set_component_hooks",
    "set_component_when_to_use",
    "set_mcp_server_def",
    "set_project_properties",
    "set_state_access",
    "set_transfer_on",
    "set_transition",
    "undo",
    "unlink_reference",
    "unplace_reference",
    "update_hook",
    "validate_project",
]


def test_facade_exposes_all_pre_split_attributes():
    """분해 전 모듈의 모든 속성이 패키지 파사드에서도 접근 가능해야 한다."""
    missing = [name for name in _PRE_SPLIT_MODULE_ATTRS if not hasattr(tools, name)]
    assert not missing, f"파사드 누락 이름: {missing}"


def test_composed_class_has_all_pre_split_members():
    """합성 클래스가 분해 전 클래스의 멤버 전부를 갖는다."""
    missing = [
        name
        for name in _PRE_SPLIT_CLASS_MEMBERS
        if not hasattr(tools.DaedalusTools, name)
    ]
    assert not missing, f"멤버 누락: {missing}"


def test_composed_class_members_come_from_mixins():
    """파사드의 클래스가 각 도메인 믹스인의 메서드와 동일 객체다 (복제 아님)."""
    from daedalus.mcp.tools import (
        blackboard,
        body,
        canvas,
        hooks,
        ports,
        props,
        query,
        session,
    )

    cls = tools.DaedalusTools
    assert cls.get_project is query.QueryTools.get_project
    assert cls.save_project is session.SessionTools.save_project
    assert cls.connect_states is canvas.CanvasTools.connect_states
    assert cls.set_transfer_on is ports.PortTools.set_transfer_on
    assert cls.create_blackboard_class is blackboard.BlackboardTools.create_blackboard_class
    assert cls.create_hook is hooks.HookTools.create_hook
    assert cls.set_component_body is body.BodyTools.set_component_body
    assert cls.set_project_properties is props.PropsTools.set_project_properties
    assert cls._find_component is tools._base._BaseTools._find_component


def test_tool_methods_keep_docstring_and_signature():
    """SDK 입력 스키마의 원료 — TOOL_NAMES의 모든 도구가 docstring을 가진 메서드다."""
    import inspect

    from daedalus.mcp.service import TOOL_NAMES

    for name in TOOL_NAMES:
        fn = getattr(tools.DaedalusTools, name, None)
        assert fn is not None, f"TOOL_NAMES의 '{name}'이 DaedalusTools에 없다"
        assert callable(fn), f"'{name}'이 callable이 아니다"
        # redo만 분해 전부터 docstring이 없다 — 새 결손이 생기지 않는 것을 고정.
        if name != "redo":
            assert fn.__doc__, f"'{name}'의 docstring이 사라졌다 (SDK 스키마 원료)"
        sig = inspect.signature(fn)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        assert all(
            p.kind is not inspect.Parameter.VAR_KEYWORD for p in params
        ), f"'{name}'이 **kwargs로만 노출되면 SDK가 인자를 만들 수 없다"
