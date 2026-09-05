# daedalus/model/validation/project_rules.py
"""프로젝트 수준 규칙 — 여러 컴포넌트를 가로질러야 판정되는 검사들.

``_ProjectRules``는 ``Validator``가 상속하는 믹스인이다(WP-RF-3d 분해 — 이동만,
동작 불변). ``validate_project``가 여기 있고, 각 FSM의 머신 수준 검사는
``_MachineRules._validate_machine``에 위임한다.
"""
from __future__ import annotations

import re

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.walk import iter_states, iter_transitions
from daedalus.model.plugin.enums import BuildTarget, PermissionMode
from daedalus.model.validation.machine_rules import _MachineRules
from daedalus.model.validation.severity import ValidationError


# CC 내장 도구 이름 집합 — tool_shelf에 선언하지 않아도 ToolEvaluation/ToolExecution이
# 직접 참조할 수 있는 도구들. dangling_tool_ref 검사 시 shelf와 합쳐 유효 집합을 이룬다.
# (2026-06 기준 CC 1급 도구 + 본 환경 PowerShell. MCP 도구는 mcp__로 시작하므로 별도.)
CC_BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebFetch", "WebSearch", "Agent", "Task",
    "TodoWrite", "NotebookEdit", "SlashCommand", "PowerShell",
})


_CODE_FENCE_RE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_markdown_code(text: str) -> str:
    """마크다운 본문에서 코드로 표시된 부분을 지운다.

    본문을 문자열로 훑는 규칙이 **문서가 무언가를 설명하려고 인용한 것**까지
    실사용으로 오인하지 않게 한다. 코드 펜스를 먼저 지우는 순서가 중요하다 —
    펜스 안의 백틱이 인라인 코드로 잘못 짝지어지는 것을 막는다.
    """
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", text))


class _ProjectRules:
    """프로젝트 수준 규칙 모음 (Validator 믹스인)."""

    @staticmethod
    def _graph_has_placements(graph: StateMachine) -> bool:
        """프로젝트 그래프에 EntryPoint 외 노드(placement)가 하나라도 있으면 True.

        빈 그래프(시작점만)는 검증을 스킵해 경고 폭주를 막는다.
        """
        return any(not isinstance(s, EntryPoint) for s in graph.states)

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
        if graph is not None and _ProjectRules._graph_has_placements(graph):
            errors.extend(_MachineRules._validate_machine(
                graph, path=("project",), skip_rules=frozenset({"unreachable_state"}),
            ))
        # 신규 프로젝트 수준 규칙
        errors.extend(_ProjectRules._check_duplicate_component_name(project))
        errors.extend(_ProjectRules._check_invalid_component_name(project))
        errors.extend(_ProjectRules._check_invalid_project_name(project))
        errors.extend(_ProjectRules._check_dangling_string_references(project))
        # 도구(tool_shelf) 규칙
        errors.extend(_ProjectRules._check_duplicate_tool_name(project))
        errors.extend(_ProjectRules._check_empty_tool_definition(project))
        errors.extend(_ProjectRules._check_dangling_tool_refs(project))
        # 훅(hook_library) 규칙
        errors.extend(_ProjectRules._check_duplicate_hook_name(project))
        errors.extend(_ProjectRules._check_empty_hook_command(project))
        errors.extend(_ProjectRules._check_hook_matcher_event(project))
        errors.extend(
            _ProjectRules._check_dangling_hook_refs(project, known_hook_names)
        )
        # 블랙보드(blackboard) 규칙 — WP-BB
        errors.extend(_ProjectRules._check_dangling_blackboard_refs(project))
        errors.extend(_ProjectRules._check_orphan_blackboard_fields(project))
        errors.extend(_ProjectRules._check_blackboard_field_types(project))
        # 빌드 타깃(build_target) 규칙 — WP-TG
        errors.extend(_ProjectRules._check_mcp_agent_in_marketplace_build(project))
        errors.extend(_ProjectRules._check_unsupported_agent_fields(project))
        errors.extend(_ProjectRules._check_plugin_root_in_local_build(project))
        errors.extend(_ProjectRules._check_skill_dir_token_in_agent(project))
        # 진입점 의미론 규칙 — A3
        errors.extend(_ProjectRules._check_mid_chain_user_invocable(project))
        # 전이 스킬 재사용 금지 — A11
        errors.extend(_ProjectRules._check_transfer_skill_reused(project))
        # 작업 폴더 문서 — WP-WD
        errors.extend(_ProjectRules._check_workspace_docs(project))
        return errors

    @staticmethod
    def _check_workspace_docs(project) -> list[ValidationError]:
        """작업 폴더 문서 규칙 3종 (WP-WD).

        - duplicate_rule_name: 같은 이름의 규칙 둘 — 이름이 곧 파일명이라 에러다.
        - invalid_rule_name: 파일명 규약 불일치 — 편집 중에는 경고이고, 컴파일
          게이트가 에러로 승격한다(컴포넌트 이름과 같은 관례).
        - workspace_doc_in_marketplace_build: 마켓플레이스 플러그인은 작업 폴더에
          쓸 수 없어 배출되지 않는다. **내용이 있을 때만** 경고한다 — 빈 문서는
          배출할 것이 없으므로 잃는 것도 없다.
        """
        errors: list[ValidationError] = []
        rules = list(getattr(project, "rules", None) or [])

        seen: dict[str, int] = {}
        for doc in rules:
            seen[doc.name] = seen.get(doc.name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                errors.append(ValidationError(
                    rule="duplicate_rule_name",
                    message=(
                        f"규칙 문서 이름 '{name}'이 {count}번 쓰였습니다. 이름이 곧 "
                        f".claude/rules/<이름>.md 파일명이라 서로 덮어씁니다."
                    ),
                    source=name,
                    subject=project,
                ))

        for doc in rules:
            if not _ProjectRules._COMPONENT_NAME_RE.match(doc.name or ""):
                errors.append(ValidationError(
                    rule="invalid_rule_name",
                    message=(
                        f"규칙 문서 이름 '{doc.name}'이 규약 "
                        f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다. 이름이 산출 "
                        f"파일명이 됩니다."
                    ),
                    source=doc.name,
                    subject=doc,
                ))

        if getattr(project, "build_target", None) is not BuildTarget.LOCAL:
            claude_md = getattr(project, "claude_md", None)
            filled = [doc for doc in rules if doc.has_content()]
            if claude_md is not None and claude_md.has_content():
                filled = [claude_md] + filled
            if filled:
                errors.append(ValidationError(
                    rule="workspace_doc_in_marketplace_build",
                    message=(
                        f"작업 폴더 문서 {len(filled)}건이 있지만 빌드 타깃이 "
                        f"마켓플레이스라 배출되지 않습니다 — 플러그인은 설치 대상 "
                        f"작업 폴더의 .claude/에 쓸 수 없습니다. 로컬 플러그인으로 "
                        f"바꾸거나 내용을 스킬 본문으로 옮기세요."
                    ),
                    source=project.name,
                    subject=project,
                ))
        return errors

    @staticmethod
    def _check_blackboard_field_types(project) -> list[ValidationError]:
        """invalid_blackboard_field_type — 블랙보드 필드 타입이 허용 집합
        (BLACKBOARD_FIELD_TYPES — 스칼라 원소 타입 4종) 밖이면 경고 (WP-BT).

        구버전 파일의 list/json/any/number 필드를 F7이 짚어 준다 (로드·컴파일은
        계속 동작 — 경고 등급). 컨테이너 형상은 CollectionType이 전담한다.
        """
        from daedalus.model.fsm.blackboard import BLACKBOARD_FIELD_TYPES

        errors: list[ValidationError] = []
        classes = getattr(project.blackboard, "class_definitions", None) or []
        for cls in classes:
            for fld in cls.fields:
                if fld.field_type not in BLACKBOARD_FIELD_TYPES:
                    errors.append(ValidationError(
                        rule="invalid_blackboard_field_type",
                        message=(
                            f"블랙보드 필드 '{cls.name}.{fld.name}'의 타입 "
                            f"'{fld.field_type.value}'은 더 이상 허용되지 않습니다 — "
                            f"스칼라 타입(string/int/float/bool) + 컬렉션 조합을 쓰세요."
                        ),
                        source=f"{cls.name}.{fld.name}",
                        subject=fld,
                    ))
        return errors

    # ------------------------------------------------------------------
    # 도구(tool_shelf) 규칙 + 참조 수집 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_eval_tools(ev: EvaluationStrategy | None) -> list[str]:
        """EvaluationStrategy(중첩 CompositeEvaluation 포함)에서 비어있지 않은
        ToolEvaluation.tool 이름을 수집한다.

        MCPEvaluation은 **의도적으로 제외** — MCPEvaluation.tool은 shelf의
        Tool.name이 아니라 MCP 서버 내 도구명이며, 참조 단위가 server+tool
        조합이라 dangling 검증은 Tier 2(MCP 서버 레지스트리)에서 별도 처리한다.
        """
        if ev is None:
            return []
        names: list[str] = []
        if isinstance(ev, ToolEvaluation):
            if ev.tool:
                names.append(ev.tool)
        elif isinstance(ev, CompositeEvaluation):
            for child in ev.children:
                names.extend(_ProjectRules._collect_eval_tools(child))
        return names

    @staticmethod
    def _collect_exec_tools(ex: ExecutionStrategy | None) -> list[str]:
        """ExecutionStrategy(중첩 CompositeExecution 포함)에서 비어있지 않은
        ToolExecution.tool 이름을 수집한다.

        MCPExecution은 **의도적으로 제외** — _collect_eval_tools와 동일 사유
        (server+tool 조합이 참조 단위, Tier 2에서 별도 처리).
        """
        if ex is None:
            return []
        names: list[str] = []
        if isinstance(ex, ToolExecution):
            if ex.tool:
                names.append(ex.tool)
        elif isinstance(ex, CompositeExecution):
            for child in ex.children:
                names.extend(_ProjectRules._collect_exec_tools(child))
        return names

    @staticmethod
    def _collect_machine_tool_refs(sm: StateMachine) -> list[str]:
        """머신 전체(상태 액션 체인 + 전이 가드/액션 체인)에서 참조하는 도구 이름을
        재귀적으로 수집한다. sub_machine(CompositeState)·Region도 내려간다.

        도구 참조 출처:
          - State 라이프사이클 훅 + custom_events의 Action.execution (ToolExecution)
          - Transition 가드 evaluation (ToolEvaluation) + 액션 체인 + custom_events
        """
        names: list[str] = []

        def _actions(lst) -> None:
            for a in (lst or []):
                names.extend(_ProjectRules._collect_exec_tools(a.execution))

        for state in iter_states(sm):
            for fname in _MachineRules._STATE_ACTION_FIELDS:
                _actions(getattr(state, fname, None))
            for lst in getattr(state, "custom_events", {}).values():
                _actions(lst)

        for t in iter_transitions(sm):
            if t.guard is not None:
                names.extend(_ProjectRules._collect_eval_tools(t.guard.evaluation))
            for fname in _MachineRules._TRANSITION_ACTION_FIELDS:
                _actions(getattr(t, fname, None))
            for lst in getattr(t, "custom_events", {}).values():
                _actions(lst)

        return names

    @staticmethod
    def _project_machines(project):
        """프로젝트의 모든 최상위 FSM(skill.fsm / agent.fsm)을 (label, sm)로 yield."""
        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                yield (f"skill:{skill.name}", fsm)
        for agent in project.agents:
            yield (f"agent:{agent.name}", agent.fsm)

    @staticmethod
    def _check_duplicate_tool_name(project) -> list[ValidationError]:
        """duplicate_tool_name — tool_shelf 내 동명 Tool 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        for tool in getattr(project, "tool_shelf", []):
            if tool.name in seen:
                errors.append(ValidationError(
                    rule="duplicate_tool_name",
                    message=(
                        f"tool_shelf에 도구 이름 '{tool.name}'이 중복됩니다. "
                        f"이름 참조가 모호해집니다."
                    ),
                    source=tool.name,
                    subject=tool,
                ))
            else:
                seen[tool.name] = tool
        return errors

    @staticmethod
    def _check_empty_tool_definition(project) -> list[ValidationError]:
        """empty_tool_definition — UserDefinedTool 본문(body) 빈 값 등 내용 누락 경고."""
        from daedalus.model.plugin.tool import MCPTool, UserDefinedTool
        errors: list[ValidationError] = []
        for tool in getattr(project, "tool_shelf", []):
            empty_msg = None
            if isinstance(tool, UserDefinedTool) and not tool.body.strip():
                empty_msg = f"사용자 정의 도구 '{tool.name}'의 본문이 비어 있습니다."
            elif isinstance(tool, MCPTool) and (not tool.server or not tool.tool_name):
                empty_msg = f"MCP 도구 '{tool.name}'의 server/tool_name이 비어 있습니다."
            if empty_msg:
                errors.append(ValidationError(
                    rule="empty_tool_definition",
                    message=empty_msg,
                    source=tool.name,
                    subject=tool,
                ))
        return errors

    @staticmethod
    def _check_dangling_tool_refs(project) -> list[ValidationError]:
        """dangling_tool_ref — FSM이 참조하는 도구 이름이 tool_shelf와 CC 내장 도구
        집합 어디에도 없으면 경고. 빈 문자열 참조는 미지정으로 간주(스킵)."""
        shelf_names = {t.name for t in getattr(project, "tool_shelf", [])}
        valid = shelf_names | CC_BUILTIN_TOOLS
        errors: list[ValidationError] = []
        for label, fsm in _ProjectRules._project_machines(project):
            for name in _ProjectRules._collect_machine_tool_refs(fsm):
                if name not in valid:
                    errors.append(ValidationError(
                        rule="dangling_tool_ref",
                        message=(
                            f"{label}: FSM이 참조하는 도구 '{name}'이 tool_shelf와 "
                            f"CC 내장 도구 어디에도 없습니다."
                        ),
                        source=name,
                        subject=fsm,
                        path=(label,),
                    ))
        return errors

    # ------------------------------------------------------------------
    # 훅(hook_library) 규칙 + 참조 수집 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_hook_refs(project):
        """config.hooks 키(훅 이름 참조)를 (label, name, subject)로 yield.

        스킬/에이전트의 config.hooks를 모두 훑는다.
        """
        for skill in getattr(project, "skills", []):
            cfg = getattr(skill, "config", None)
            hooks = getattr(cfg, "hooks", None)
            if isinstance(hooks, dict):
                for name in hooks:
                    yield (f"skill:{skill.name}", name, skill)
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            hooks = getattr(cfg, "hooks", None)
            if isinstance(hooks, dict):
                for name in hooks:
                    yield (f"agent:{agent.name}", name, agent)

    @staticmethod
    def _check_duplicate_hook_name(project) -> list[ValidationError]:
        """duplicate_hook_name — hook_library 내 동명 HookDef 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if hook.name in seen:
                errors.append(ValidationError(
                    rule="duplicate_hook_name",
                    message=(
                        f"hook_library에 훅 이름 '{hook.name}'이 중복됩니다. "
                        f"이름 참조가 모호해집니다."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
            else:
                seen[hook.name] = hook
        return errors

    @staticmethod
    def _check_empty_hook_command(project) -> list[ValidationError]:
        """empty_hook_command — 훅에 핸들러가 없거나, 핸들러의 필수 값이 비면 경고.

        WP-HK로 훅이 핸들러 목록을 갖게 되면서 "빈 값" 판정이 타입마다 달라졌다
        (command 훅은 command, http 훅은 url, …). 각 핸들러가 무엇이 필수인지
        아는 유일한 곳은 자기 자신이므로 `summary()`가 비었는지로 판정한다 —
        핸들러 타입이 늘어도 이 규칙은 그대로 따라간다.
        """
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if not hook.handlers:
                errors.append(ValidationError(
                    rule="empty_hook_command",
                    message=f"훅 '{hook.name}'에 핸들러가 없습니다 — 아무 일도 하지 않습니다.",
                    source=hook.name,
                    subject=hook,
                ))
                continue
            for handler in hook.handlers:
                if handler.summary().startswith("("):  # "(커맨드 없음)" 등
                    errors.append(ValidationError(
                        rule="empty_hook_command",
                        message=(
                            f"훅 '{hook.name}'의 {handler.kind} 핸들러에 "
                            f"필수 값이 비어 있습니다."
                        ),
                        source=hook.name,
                        subject=hook,
                    ))
        return errors

    @staticmethod
    def _check_hook_matcher_event(project) -> list[ValidationError]:
        """hook_matcher_without_tool_event — matcher를 받지 않는 이벤트에 matcher가
        있으면 경고.

        규칙 이름은 예전(도구 이벤트 전용이라고 보던 시절) 그대로 두지만, 판정은
        스키마 기준이다 — CC 이벤트 대부분이 matcher를 받고, 받지 않는 것은
        `NO_MATCHER_EVENTS`에 모아 두었다.
        """
        from daedalus.model.plugin.hook import (
            MATCHER_EVENTS,
            mcp_matcher_matches_nothing,
        )
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if not hook.matcher.strip():
                continue
            if hook.event not in MATCHER_EVENTS:
                errors.append(ValidationError(
                    rule="hook_matcher_without_tool_event",
                    message=(
                        f"훅 '{hook.name}'의 matcher '{hook.matcher}'는 "
                        f"event '{hook.event.value}'에서 무시됩니다 — "
                        f"이 이벤트는 matcher를 받지 않습니다."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
            elif mcp_matcher_matches_nothing(hook.matcher):
                errors.append(ValidationError(
                    rule="hook_matcher_matches_nothing",
                    message=(
                        f"훅 '{hook.name}'의 matcher '{hook.matcher}'는 어떤 MCP "
                        f"도구와도 맞지 않습니다 — 서버 이름까지만 쓰면 정규식이 "
                        f"아니라 정확한 문자열로 비교됩니다. 서버 전체를 잡으려면 "
                        f"'{hook.matcher.strip()}__.*'처럼 도구 부분을 붙이세요."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
        return errors

    @staticmethod
    def _check_dangling_hook_refs(
        project, known_hook_names: frozenset[str] | None = None
    ) -> list[ValidationError]:
        """dangling_hook_ref — config.hooks 키가 알려진 훅 이름에 없으면 경고.

        known_hook_names가 주어지면 그것이 유효 집합이다(전역 훅 포함, A1).
        생략하면 `project.hook_library`만 — validate_project docstring 참조.
        """
        lib_names = (
            set(known_hook_names)
            if known_hook_names is not None
            else {h.name for h in getattr(project, "hook_library", [])}
        )
        errors: list[ValidationError] = []
        for label, name, subject in _ProjectRules._collect_hook_refs(project):
            if name not in lib_names:
                errors.append(ValidationError(
                    rule="dangling_hook_ref",
                    message=(
                        f"{label}: config.hooks가 참조하는 훅 '{name}'이 "
                        f"훅 라이브러리(프로젝트·전역)에 없습니다."
                    ),
                    source=name,
                    subject=subject,
                    path=(label,),
                ))
        return errors

    @staticmethod
    def _check_duplicate_component_name(project) -> list[ValidationError]:
        """duplicate_component_name — skills/agents 전체에서 동명 컴포넌트 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        all_components = [
            *project.skills,
            *project.agents,
        ]
        for comp in all_components:
            name = getattr(comp, "name", None)
            if name is None:
                continue
            if name in seen:
                errors.append(ValidationError(
                    rule="duplicate_component_name",
                    message=(
                        f"프로젝트에 이름 '{name}'이 중복됩니다. "
                        f"컴파일 시 디렉토리/파일명 충돌이 발생합니다."
                    ),
                    source=name,
                    subject=comp,
                ))
            else:
                seen[name] = comp
        return errors

    _COMPONENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

    @staticmethod
    def _check_invalid_component_name(project) -> list[ValidationError]:
        """invalid_component_name — 이름이 ^[a-z0-9][a-z0-9-]*$ 불일치 시 경고. 빈 이름은 에러."""
        all_components = [
            *project.skills,
            *project.agents,
        ]
        errors: list[ValidationError] = []
        for comp in all_components:
            name = getattr(comp, "name", None)
            if name is None:
                continue
            if name == "":
                errors.append(ValidationError(
                    rule="invalid_component_name",
                    message="컴포넌트 이름이 비어 있습니다.",
                    source="",
                    subject=comp,
                ))
            elif not _ProjectRules._COMPONENT_NAME_RE.match(name):
                errors.append(ValidationError(
                    rule="invalid_component_name",
                    message=(
                        f"컴포넌트 이름 '{name}'이 명명 규약 "
                        f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다."
                    ),
                    source=name,
                    subject=comp,
                ))
        return errors

    @staticmethod
    def _check_invalid_project_name(project) -> list[ValidationError]:
        """invalid_component_name — 프로젝트 이름도 컴포넌트와 동일 규약 적용.

        프로젝트 이름은 plugin.json의 name(플러그인 식별자)이 되므로 컴포넌트
        이름과 같은 등급(빈 이름=에러, 규약 불일치=경고)으로 검사한다.
        다른 프로젝트 수준 규칙(duplicate_component_name 등)에는 프로젝트 이름을
        끌어들이지 않는다 — 이름 규약 검사만.
        """
        name = getattr(project, "name", None)
        if name is None:
            return []
        if name == "":
            return [ValidationError(
                rule="invalid_component_name",
                message="프로젝트 이름이 비어 있습니다.",
                source="",
                subject=project,
                path=("project",),
            )]
        if not _ProjectRules._COMPONENT_NAME_RE.match(name):
            return [ValidationError(
                rule="invalid_component_name",
                message=(
                    f"프로젝트 이름 '{name}'이 명명 규약 "
                    f"'^[a-z0-9][a-z0-9-]*$'에 맞지 않습니다."
                ),
                source=name,
                subject=project,
                path=("project",),
            )]
        return []

    @staticmethod
    def _check_dangling_string_references(project) -> list[ValidationError]:
        """dangling_string_reference — ProceduralSkillConfig.agent / AgentConfig.skills /
        reference_placements.skill_name의 문자열 참조 실존 검사."""
        from daedalus.model.plugin.config import ProceduralSkillConfig, AgentConfig
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.model.plugin.agent import AgentDefinition

        errors: list[ValidationError] = []

        # 전역 이름 맵
        global_skill_names = {s.name for s in project.skills}
        global_agent_names = {a.name for a in project.agents}

        # ProceduralSkillConfig.agent 검사
        for skill in project.skills:
            if not isinstance(skill, ProceduralSkill):
                continue
            cfg = skill.config
            if isinstance(cfg, ProceduralSkillConfig) and cfg.agent:
                if cfg.agent not in global_agent_names:
                    errors.append(ValidationError(
                        rule="dangling_string_reference",
                        message=(
                            f"스킬 '{skill.name}'의 config.agent '{cfg.agent}'가 "
                            f"프로젝트 agents에 없습니다."
                        ),
                        source=skill.name,
                        subject=skill,
                    ))

        # AgentConfig.skills 검사 (전역 스킬 이름)
        for agent in project.agents:
            cfg = agent.config
            if not isinstance(cfg, AgentConfig):
                continue
            for skill_name in cfg.skills:
                if skill_name not in global_skill_names:
                    errors.append(ValidationError(
                        rule="dangling_string_reference",
                        message=(
                            f"에이전트 '{agent.name}'의 config.skills '{skill_name}'이 "
                            f"프로젝트 skills에 없습니다."
                        ),
                        source=agent.name,
                        subject=agent,
                    ))

        # reference_placements.skill_name 검사
        for placement in project.reference_placements:
            if placement.skill_name not in global_skill_names:
                errors.append(ValidationError(
                    rule="dangling_string_reference",
                    message=(
                        f"reference_placement의 skill_name '{placement.skill_name}'이 "
                        f"프로젝트 skills에 없습니다."
                    ),
                    source=placement.skill_name,
                    subject=placement,
                ))

        return errors

    # ------------------------------------------------------------------
    # 블랙보드(blackboard) 규칙 2종 — WP-BB Part E
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_state_access(sm: StateMachine, visit) -> None:
        """머신(재귀 — sub_machine/Region 포함)의 모든 상태에 visit(state)를 적용한다.

        dangling_blackboard_ref/orphan_blackboard_field가 공유하는 순회 로직.
        재귀 골격 자체는 ``model/fsm/walk.iter_states``가 단일 진실이다.
        """
        for state in iter_states(sm):
            visit(state)

    @staticmethod
    def _check_dangling_blackboard_refs(project) -> list[ValidationError]:
        """dangling_blackboard_ref — 상태 reads/writes의 "Class"/"Class.field" 문자열
        참조가 프로젝트 최상위 블랙보드 class_definitions에 실존하는지 검사.

        미존재 → 경고(subject=해당 상태). 빈 문자열은 스킵. 모든 머신(skill.fsm/
        agent.fsm, 재귀)과 프로젝트 그래프의 상태를 검사한다.
        """
        classes = getattr(project.blackboard, "class_definitions", None) or []
        known_classes = {c.name for c in classes}
        known_fields = {f"{c.name}.{fld.name}" for c in classes for fld in c.fields}

        errors: list[ValidationError] = []

        def _make_checker(path: tuple[str, ...]):
            def _visit(state) -> None:
                for ref in list(getattr(state, "reads", None) or []) + list(
                    getattr(state, "writes", None) or []
                ):
                    if not ref:
                        continue
                    valid = ref in known_fields if "." in ref else ref in known_classes
                    if not valid:
                        errors.append(ValidationError(
                            rule="dangling_blackboard_ref",
                            message=(
                                f"상태 '{state.name}'의 블랙보드 참조 '{ref}'이 "
                                f"프로젝트 블랙보드에 없습니다."
                            ),
                            source=state.name,
                            subject=state,
                            path=path,
                        ))
            return _visit

        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                _ProjectRules._scan_state_access(fsm, _make_checker((f"skill:{skill.name}",)))
        for agent in project.agents:
            _ProjectRules._scan_state_access(agent.fsm, _make_checker((f"agent:{agent.name}",)))
        graph = getattr(project, "graph", None)
        if graph is not None:
            _ProjectRules._scan_state_access(graph, _make_checker(("project",)))

        return errors

    @staticmethod
    def _check_orphan_blackboard_fields(project) -> list[ValidationError]:
        """orphan_blackboard_field — 어떤 상태의 reads/writes에도 등장하지 않는
        블랙보드 필드를 경고. 클래스 전체 참조("Class")는 그 클래스의 모든 필드를
        커버한 것으로 간주한다. 프로젝트 전체에 접근 선언이 하나도 없으면 스킵
        (선언 기능 미사용 프로젝트에 경고 폭주 방지)."""
        classes = getattr(project.blackboard, "class_definitions", None) or []
        if not classes:
            return []

        declared: set[str] = set()

        def _collect(state) -> None:
            declared.update(getattr(state, "reads", None) or [])
            declared.update(getattr(state, "writes", None) or [])

        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                _ProjectRules._scan_state_access(fsm, _collect)
        for agent in project.agents:
            _ProjectRules._scan_state_access(agent.fsm, _collect)
        graph = getattr(project, "graph", None)
        if graph is not None:
            _ProjectRules._scan_state_access(graph, _collect)

        if not declared:
            return []  # 접근 선언 기능 자체를 쓰지 않는 프로젝트 — 스킵

        errors: list[ValidationError] = []
        for cls in classes:
            if cls.name in declared:
                continue  # 클래스 전체 참조 — 모든 필드 커버
            for fld in cls.fields:
                field_ref = f"{cls.name}.{fld.name}"
                if field_ref in declared:
                    continue
                errors.append(ValidationError(
                    rule="orphan_blackboard_field",
                    message=(
                        f"블랙보드 필드 '{field_ref}'을 참조하는 상태(reads/writes)가 "
                        f"없습니다."
                    ),
                    source=field_ref,
                    subject=fld,
                ))
        return errors

    # ------------------------------------------------------------------
    # 빌드 타깃(build_target) 규칙 2종 — WP-TG Part D
    # ------------------------------------------------------------------

    @staticmethod
    def _check_mcp_agent_in_marketplace_build(project) -> list[ValidationError]:
        """mcp_agent_in_marketplace_build — build_target=MARKETPLACE인데 에이전트가
        MCP를 사용(config.tools의 mcp__ 접두 또는 mcp_servers 선언)하면 경고.

        CC는 마켓플레이스 플러그인으로 배포되는 에이전트의 MCP 사용을 지원하지
        않는다(mcpServers 등 프론트매터 미지원) — 로컬 플러그인 빌드로 전환하거나
        MCP 사용을 제거하라고 안내한다. LOCAL 빌드면 이 제약이 없으므로 무경고.
        """
        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.MARKETPLACE:
            return []
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            tools = getattr(cfg, "tools", None) or []
            mcp_servers = getattr(cfg, "mcp_servers", None) or []
            has_mcp_tool = any(
                isinstance(t, str) and t.startswith("mcp__") for t in tools
            )
            if has_mcp_tool or mcp_servers:
                errors.append(ValidationError(
                    rule="mcp_agent_in_marketplace_build",
                    message=(
                        f"에이전트 '{agent.name}'이 MCP를 사용하지만 빌드 타깃이 "
                        f"마켓플레이스 플러그인입니다 — CC는 플러그인 배포 "
                        f"에이전트의 MCP 사용을 지원하지 않습니다. 로컬 플러그인 "
                        f"빌드로 전환하거나 MCP 사용을 제거하세요."
                    ),
                    source=agent.name,
                    subject=agent,
                    path=(f"agent:{agent.name}",),
                ))
        return errors

    @staticmethod
    def _check_unsupported_agent_fields(project) -> list[ValidationError]:
        """unsupported_agent_field_in_marketplace_build — MARKETPLACE 빌드인데
        에이전트가 `hooks` 또는 기본값 아닌 `permissionMode`를 쓰면 경고 (WP-LA).

        CC는 **보안상 플러그인 서브에이전트의 `hooks`/`mcpServers`/
        `permissionMode` 프론트매터를 무시한다** — 값이 나가긴 해도 아무 일도
        일어나지 않으므로, 설계자가 걸어 둔 제약이 조용히 사라진다. MCP는 이미
        `mcp_agent_in_marketplace_build`가 짚으므로 여기서는 나머지 둘만 본다
        (같은 에이전트에 경고가 둘 겹치지 않게).
        """
        from daedalus.model.plugin.enums import AgentField
        from daedalus.model.plugin.field_matrix import agent_field_supported

        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.MARKETPLACE:
            return []
        # MCP(mcp_servers)는 아래 규칙에서 제외한다 — 같은 에이전트에 경고가 둘
        # 겹치지 않도록 mcp_agent_in_marketplace_build가 전담한다.
        checked = [AgentField.HOOKS, AgentField.PERMISSION_MODE]
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            cfg = getattr(agent, "config", None)
            unsupported: list[str] = []
            for afield in checked:
                if agent_field_supported(afield, build_target):
                    continue  # 지원되면 문제 없음(집합이 바뀌면 자동으로 따라간다)
                if afield is AgentField.HOOKS and getattr(cfg, "hooks", None):
                    unsupported.append("hooks")
                elif afield is AgentField.PERMISSION_MODE:
                    mode = getattr(cfg, "permission_mode", None)
                    if mode is not None and mode is not PermissionMode.DEFAULT:
                        unsupported.append(f"permissionMode({mode.value})")
            if not unsupported:
                continue
            errors.append(ValidationError(
                rule="unsupported_agent_field_in_marketplace_build",
                message=(
                    f"에이전트 '{agent.name}'의 {', '.join(unsupported)}는 "
                    f"마켓플레이스 플러그인에서 무시됩니다 — CC는 보안상 플러그인 "
                    f"서브에이전트의 hooks/mcpServers/permissionMode 프론트매터를 "
                    f"적용하지 않습니다. 로컬 플러그인 빌드로 전환하세요."
                ),
                source=agent.name,
                subject=agent,
                path=(f"agent:{agent.name}",),
            ))
        return errors

    @staticmethod
    def _check_plugin_root_in_local_build(project) -> list[ValidationError]:
        """plugin_root_in_local_build — build_target=LOCAL인데 스킬/에이전트
        본문에 **플러그인 전용 변수**가 남아 있으면 경고.

        CC는 `${CLAUDE_PLUGIN_ROOT}`와 `${CLAUDE_PLUGIN_DATA}`를 **플러그인
        스킬에서만 치환한다**(공식 skills 문서의 치환 표). 프로젝트 설치 빌드는
        플러그인이 아니므로 이 변수들이 리터럴 문자열 그대로 남는다.

        WP-RT 이후 files/ 참조는 타깃 중립 ``${ROOT}/files/``를 쓰므로 files/
        예외 처리는 없다 — 본문에 CC 원시 플러그인 변수가 보이면 그대로 문제다.

        단 **코드로 표시된 부분은 검사하지 않는다**(백틱 인라인 코드, 코드 펜스).
        규격을 설명하는 문서 스킬은 이 변수 이름을 언급할 수밖에 없는데, 그것을
        "죽은 경로"로 짚으면 고칠 수 없는 경고가 영구히 남는다. 실제 경로로 쓰는
        경우는 `${ROOT}`를 쓰는 것이 규약이므로 이 좁힘으로 잃는 것이 없다.
        """
        from daedalus.model.plugin.variables import PLUGIN_ONLY_VARIABLES

        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.LOCAL:
            return []
        errors: list[ValidationError] = []

        def _scan(label: str, subject: object, body: str, path: tuple[str, ...]) -> None:
            remaining = _strip_markdown_code(body or "")
            for var in PLUGIN_ONLY_VARIABLES:
                if var in remaining:
                    errors.append(ValidationError(
                        rule="plugin_root_in_local_build",
                        message=(
                            f"{label}의 본문에 '{var}'가 남아 있습니다 — 이 변수는 "
                            f"플러그인 스킬에서만 치환되므로, 프로젝트 설치 빌드에서는 "
                            f"문자열 그대로 남습니다. "
                            f"'${{CLAUDE_PROJECT_DIR}}'나 '${{CLAUDE_SKILL_DIR}}'를 쓰세요."
                        ),
                        source=label,
                        subject=subject,
                        path=path,
                    ))

        for skill in getattr(project, "skills", []):
            _scan(
                f"스킬 '{skill.name}'", skill, getattr(skill, "body", ""),
                (f"skill:{skill.name}",),
            )
        for agent in getattr(project, "agents", []):
            _scan(
                f"에이전트 '{agent.name}'", agent, getattr(agent, "body", ""),
                (f"agent:{agent.name}",),
            )
        return errors

    @staticmethod
    def _check_skill_dir_token_in_agent(project) -> list[ValidationError]:
        """skill_dir_token_in_agent — 에이전트 본문에 `${CLAUDE_SKILL_DIR}`가
        있으면 경고 (WP-SF).

        CC의 이 변수는 **스킬 전용**이다(공식 skills 문서의 치환 표 — 에이전트는
        단일 .md라 자기 디렉토리 개념 자체가 없다). 에이전트 .md에 남으면
        치환되지 않고 리터럴 문자열로 남는다. 파일을 주려면 스킬에 실어
        에이전트 skills 프론트매터로 전달하거나(WP-AS 자동 합류), 공용 files/를
        `${ROOT}/files/…`로 참조하라.

        코드로 표시된 부분(백틱·펜스)은 검사하지 않는다 —
        `plugin_root_in_local_build`와 같은 이유(규격 설명 문서의 언급까지
        짚으면 고칠 수 없는 경고가 남는다). 빌드 타깃 무관 — 양쪽 다 안 된다.
        """
        token = "${CLAUDE_SKILL_DIR}"
        errors: list[ValidationError] = []
        for agent in getattr(project, "agents", []):
            remaining = _strip_markdown_code(getattr(agent, "body", "") or "")
            if token in remaining:
                errors.append(ValidationError(
                    rule="skill_dir_token_in_agent",
                    message=(
                        f"에이전트 '{agent.name}'의 본문에 '{token}'가 있습니다 — "
                        f"이 변수는 스킬에서만 치환됩니다(에이전트는 전용 디렉토리가 "
                        f"없습니다). 파일은 스킬에 동봉해 skills 프론트매터로 "
                        f"전달하거나 공용 files/를 '${{ROOT}}/files/…'로 참조하세요."
                    ),
                    source=agent.name,
                    subject=agent,
                    path=(f"agent:{agent.name}",),
                ))
        return errors

    @staticmethod
    def _scan_transitions(sm: StateMachine, visit) -> None:
        """머신(재귀 — sub_machine/Region 포함)의 모든 전이에 visit(transition)를 적용.

        `_scan_state_access`의 전이판이다 — 같은 재귀 범위를 두 번 적으면
        한쪽만 고쳐졌을 때 규칙마다 보는 그래프가 달라진다. 그래서 재귀 골격은
        ``model/fsm/walk.iter_transitions``가 단일 진실이다.
        """
        for trans in iter_transitions(sm):
            visit(trans)

    @staticmethod
    def _check_transfer_skill_reused(project) -> list[ValidationError]:
        """transfer_skill_reused — 한 TransferSkill이 2개 이상 전이에 붙으면 에러 (A11).

        **프레이밍(사용자 확정): TransferSkill은 전이 위에 놓인 1:1 중간 상태다.**
        A→B 전이에 T가 붙으면 의미론은 A→T→B이고, T는 입력 하나(그 전이)·출력
        하나(계속 진행)뿐인 통과 노드다. 그래서 재사용 금지는 특별 규칙이 아니라
        `no_duplicate_skill_ref`와 **같은 논리**다 — 하나의 상태가 두 자리에
        동시에 있을 수 없다.

        모델 구조는 그대로다(`Transition.skill_ref`) — 이건 산출 의미론과 검증의
        프레이밍이지 그래프에 실제 중간 노드를 만든다는 뜻이 아니다.

        순회 범위는 프로젝트 그래프 + 각 스킬/에이전트 FSM(재귀)이다 —
        `dangling_tool_ref`/블랙보드 규칙과 같은 범위.
        """
        from daedalus.model.plugin.skill import TransferSkill

        # id(스킬) → (스킬, [경로 표지…]) — 어디에 붙었는지 알려 줘야 고칠 수 있다.
        uses: dict[int, tuple[object, list[str]]] = {}

        def _make_visitor(label: str):
            def _visit(trans) -> None:
                ref = getattr(trans, "skill_ref", None)
                if not isinstance(ref, TransferSkill):
                    return
                entry = uses.setdefault(id(ref), (ref, []))
                src = getattr(getattr(trans, "source", None), "name", "?")
                tgt = getattr(getattr(trans, "target", None), "name", "?")
                entry[1].append(f"{label}: {src}→{tgt}")
            return _visit

        graph = getattr(project, "graph", None)
        if graph is not None:
            _ProjectRules._scan_transitions(graph, _make_visitor("project"))
        for label, sm in _ProjectRules._project_machines(project):
            _ProjectRules._scan_transitions(sm, _make_visitor(label))

        errors: list[ValidationError] = []
        for _key, (skill, places) in uses.items():
            if len(places) < 2:
                continue
            errors.append(ValidationError(
                rule="transfer_skill_reused",
                message=(
                    f"전이 스킬 '{skill.name}'이 전이 {len(places)}곳에 붙어 "
                    f"있습니다 ({', '.join(places)}). 전이 스킬은 그 전이 위에 "
                    f"놓인 중간 상태이므로 전이 하나에만 속합니다 — 하나의 상태가 "
                    f"두 자리에 동시에 있을 수 없다는 점에서 "
                    f"no_duplicate_skill_ref와 같은 논리입니다. 전이마다 따로 "
                    f"만드세요. 같은 지침이 여러 전이에 필요하면 그 내용을 "
                    f"Declarative 스킬로 만들어 각 전이 스킬이 참조하게 하세요."
                ),
                source=skill.name,
                subject=skill,
            ))
        return errors

    @staticmethod
    def _check_mid_chain_user_invocable(project) -> list[ValidationError]:
        """mid_chain_user_invocable — 체인 중간 배치인데 user-invocable이면 경고 (A3).

        원칙(사용자 확정): **user-invocable은 진입점으로 기능할 노드만 true여야
        한다.** `/skill`로 직접 부를 수 있다는 것은 "여기서 시작해도 된다"는
        선언인데, 앞 단계가 채워 놓은 블랙보드·진행 상태를 전제하는 중간 스킬을
        맥락 없이 시작하면 그 전제가 통째로 비어 있는 채로 돈다.

        false로 두어도 **모델 인보크는 그대로 되므로 체인은 끊기지 않는다** —
        앞 스킬의 "다음 단계" 지시가 여전히 이 스킬을 부른다. 잃는 것은 사람이
        직접 부르는 통로뿐이고, 그것이 정확히 막고 싶은 것이다.

        대상은 **프로젝트 그래프에 배치된 ProceduralSkill 중 incoming 전이가
        1개 이상**인 것뿐이다:
        - incoming 0개 = 진입점 후보이므로 정상.
        - 배치 안 된 스킬 = 독립 스킬이라 user_invocable true가 정상.
        - EntryPoint에서 오는 전이는 incoming으로 세지 않는다 — 그것이 곧
          "여기서 시작한다"는 뜻이다(WP-EP로 캔버스에 그리지 않을 뿐, 구버전
          파일의 시작 전이는 모델에 남아 있다).

        **tri-state(A8) 판정은 실효값 기준이다.** `None`(미지정)은 프론트매터
        키가 생략되어 CC 기본값 **true**로 동작하므로 경고 대상이다 — 설계에서
        선언하지 않았다는 이유로 넘어가면, 실제로는 `/스킬`로 시작할 수 있는
        중간 노드가 조용히 남는다. 다만 메시지에 미지정임을 병기해 무엇을
        고쳐야 하는지 알린다. **명시 `False`만 통과한다.**
        """
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill

        graph = getattr(project, "graph", None)
        if graph is None:
            return []

        incoming: dict[int, int] = {}
        for trans in graph.transitions:
            if isinstance(trans.source, EntryPoint):
                continue
            incoming[id(trans.target)] = incoming.get(id(trans.target), 0) + 1

        errors: list[ValidationError] = []
        for state in graph.states:
            if not isinstance(state, SimpleState):
                continue
            skill = state.skill_ref
            if not isinstance(skill, ProceduralSkill):
                continue
            if not incoming.get(id(state)):
                continue  # 진입점 후보
            declared = getattr(skill.config, "user_invocable", None)
            if declared is False:
                continue  # 명시적으로 끔 — 유일한 통과 조건
            note = (
                "user-invocable입니다"
                if declared
                else "user_invocable이 미지정(생략 시 CC 기본값 true)입니다"
            )
            errors.append(ValidationError(
                rule="mid_chain_user_invocable",
                message=(
                    f"스킬 '{skill.name}'은 체인 중간(선행 전이 있음)에 배치돼 "
                    f"있는데 {note} — 사용자가 앞 단계의 맥락 없이 "
                    f"직접 시작할 수 있습니다. 진입점으로 쓸 것이 아니면 "
                    f"user_invocable을 false로 지정하세요(모델 인보크는 그대로 "
                    f"되므로 체인은 끊기지 않습니다)."
                ),
                source=skill.name,
                subject=state,
                path=("project",),
            ))
        return errors
