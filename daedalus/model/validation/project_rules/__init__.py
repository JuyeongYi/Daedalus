# daedalus/model/validation/project_rules/
"""프로젝트 수준 규칙 — 여러 컴포넌트를 가로질러야 판정되는 검사들.

``_ProjectRules``는 ``Validator``가 상속하는 믹스인이다(WP-RF-3d 분해 — 이동만,
동작 불변). ``validate_project``가 여기 있고, 각 FSM의 머신 수준 검사는
``_MachineRules._validate_machine``에 위임한다.

**A6 분해:** 구 단일 모듈 ``project_rules.py``(1,090줄 — 위생 상한 1,200줄에
근접)를 규칙 그룹별 믹스인 패키지로 쪼갰다(이동만·동작 불변, WP-RF 관례).
이 ``__init__``은 **재-export 파사드**이자 오케스트레이터다 —
``from daedalus.model.validation.project_rules import CC_BUILTIN_TOOLS,
_strip_markdown_code, _ProjectRules`` 같은 기존 임포트가 전부 무수정 동작하고,
``Validator._check_*``/``_collect_*``/``_scan_*``/``_graph_has_placements``
이름도 그대로 살아 있다(각 그룹 믹스인이 실체를 소유).

구획:
  text.py           — 코드 스팬 제거(_strip_markdown_code)
  scan.py           — 공용 순회 헬퍼(graph_has_placements/project_machines/
                      scan_state_access/scan_transitions) — 그룹 모듈이 서로를
                      ``_ProjectRules.<헬퍼>``로 부르면 파사드와 순환이 되므로
                      실체는 모듈 함수이고 믹스인이 staticmethod로 재노출한다
  naming.py         — 이름 규약·문자열 참조
  tools.py          — tool_shelf + CC_BUILTIN_TOOLS
  hooks.py          — hook_library (참조·고아 검사 포함)
  blackboard.py     — 블랙보드 접근 선언·필드 타입
  body_variables.py — 본문 경로·인수 변수(치환되지 않는 토큰)
  build_target.py   — 마켓플레이스에서 무시되는 에이전트 설정
  workflow.py       — 전이 스킬 재사용·진입점 의미론
  workspace.py      — 작업 폴더 문서(.claude/CLAUDE.md·rules/)
"""
from __future__ import annotations

from daedalus.model.validation.machine_rules import _MachineRules
from daedalus.model.validation.project_rules.blackboard import _BlackboardRules
from daedalus.model.validation.project_rules.body_variables import _BodyVariableRules
from daedalus.model.validation.project_rules.build_target import _BuildTargetRules
from daedalus.model.validation.project_rules.hooks import _HookRules
from daedalus.model.validation.project_rules.naming import _NamingRules
from daedalus.model.validation.project_rules.scan import graph_has_placements
from daedalus.model.validation.project_rules.text import (
    _CODE_FENCE_RE,
    _INLINE_CODE_RE,
    _strip_markdown_code,
)
from daedalus.model.validation.project_rules.tools import (
    CC_BUILTIN_TOOLS,
    _ToolRules,
)
from daedalus.model.validation.project_rules.workflow import _WorkflowRules
from daedalus.model.validation.project_rules.workspace import _WorkspaceDocRules
from daedalus.model.validation.severity import ValidationError


class _ProjectRules(
    _NamingRules,
    _ToolRules,
    _HookRules,
    _BlackboardRules,
    _BodyVariableRules,
    _BuildTargetRules,
    _WorkflowRules,
    _WorkspaceDocRules,
):
    """프로젝트 수준 규칙 모음 (Validator 믹스인) — 그룹 믹스인 합성 + 오케스트레이터."""

    _graph_has_placements = staticmethod(graph_has_placements)

    @staticmethod
    def validate_project(
        project, known_hook_names: frozenset[str] | None = None
    ) -> list[ValidationError]:
        """프로젝트 전체 검증 — 모든 FSM의 머신 수준 규칙 + 프로젝트 수준 규칙.

        known_hook_names(A1, 선택): `config.hooks`가 참조해도 되는 훅 이름의 전체
        집합. 전역 훅(`~/.daedalus/hooks/`)이 도입되면서 "프로젝트 라이브러리에
        없다"가 곧 dangling이 아니게 됐는데, **검증기는 파일시스템을 읽지 않는다**
        (읽으면 같은 프로젝트의 검증 결과가 검증한 사람의 홈에 따라 달라진다).
        그래서 호출자가 해소된 이름 집합을 주입한다 — 생략하면 종전대로
        `project.hook_library`만 본다(하위 호환).
        """
        errors: list[ValidationError] = []
        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                errors.extend(_MachineRules._validate_machine(
                    fsm, path=(f"skill:{skill.name}",),
                ))
        for agent in project.agents:
            errors.extend(_MachineRules._validate_machine(
                agent.fsm, path=(f"agent:{agent.name}",),
            ))
        # 프로젝트 워크플로 그래프 — placement가 하나라도 있을 때만 머신 규칙 적용.
        # 빈 캔버스(EntryPoint 하나뿐)는 검증 스킵 (경고 폭주 방지).
        # unreachable_state는 스킵한다(WP-EP): CC 플러그인 의미론상 프로젝트
        # 그래프의 모든 배치는 user_invocable 스킬 등으로 독립 시작 가능해
        # "도달 불가"가 성립하지 않는다. 재귀(에이전트 sub_machine)에는 전파되지
        # 않으므로 에이전트 FSM 내부의 unreachable_state는 기존대로 검사된다.
        graph = getattr(project, "graph", None)
        if graph is not None and graph_has_placements(graph):
            errors.extend(_MachineRules._validate_machine(
                graph, path=("project",), skip_rules=frozenset({"unreachable_state"}),
            ))
        # 신규 프로젝트 수준 규칙
        errors.extend(_NamingRules._check_duplicate_component_name(project))
        errors.extend(_NamingRules._check_invalid_component_name(project))
        errors.extend(_NamingRules._check_invalid_project_name(project))
        errors.extend(_NamingRules._check_dangling_string_references(project))
        errors.extend(_NamingRules._check_wrapped_sources(project))
        errors.extend(_NamingRules._check_external_plugins(project))
        # 도구(tool_shelf) 규칙
        errors.extend(_ToolRules._check_duplicate_tool_name(project))
        errors.extend(_ToolRules._check_empty_tool_definition(project))
        errors.extend(_ToolRules._check_dangling_tool_refs(project))
        # 훅(hook_library) 규칙
        errors.extend(_HookRules._check_duplicate_hook_name(project))
        errors.extend(_HookRules._check_empty_hook_command(project))
        errors.extend(_HookRules._check_hook_matcher_event(project))
        errors.extend(
            _HookRules._check_dangling_hook_refs(project, known_hook_names)
        )
        errors.extend(_HookRules._check_orphan_hooks(project))
        # 블랙보드(blackboard) 규칙 — WP-BB
        errors.extend(_BlackboardRules._check_dangling_blackboard_refs(project))
        errors.extend(_BlackboardRules._check_orphan_blackboard_fields(project))
        errors.extend(_BlackboardRules._check_blackboard_field_types(project))
        # 빌드 타깃(build_target) 규칙 — WP-TG
        errors.extend(_BuildTargetRules._check_mcp_agent_in_marketplace_build(project))
        errors.extend(_BuildTargetRules._check_unsupported_agent_fields(project))
        errors.extend(_BodyVariableRules._check_plugin_root_in_local_build(project))
        errors.extend(_BodyVariableRules._check_skill_dir_token_in_agent(project))
        errors.extend(_BodyVariableRules._check_skill_only_variables(project))
        # 진입점 의미론 규칙 — A3
        errors.extend(_WorkflowRules._check_mid_chain_user_invocable(project))
        # 전이 스킬 재사용 금지 — A11
        errors.extend(_WorkflowRules._check_transfer_skill_reused(project))
        # 작업 폴더 문서 — WP-WD
        errors.extend(_WorkspaceDocRules._check_workspace_docs(project))
        return errors


__all__ = [
    "CC_BUILTIN_TOOLS",
    "_CODE_FENCE_RE",
    "_INLINE_CODE_RE",
    "_ProjectRules",
    "_strip_markdown_code",
]
