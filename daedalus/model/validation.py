from __future__ import annotations

import re
from dataclasses import dataclass, field

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, State
from daedalus.model.fsm.strategy import (
    CompositeEvaluation,
    CompositeExecution,
    EvaluationStrategy,
    ExecutionStrategy,
    ToolEvaluation,
    ToolExecution,
)
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import VariableScope
from daedalus.model.plugin.enums import BuildTarget, PermissionMode


@dataclass
class ValidationError:
    """검증 결과 1건.

    subject: 문제의 모델 객체 (노드 점프용). compare=False이므로 UI에서는
      값 비교가 아니라 ``error.subject is node.model`` 같은 identity 비교로
      조회해야 한다.
    path: 중첩 위치. validate_project는 루트를 ``("skill:<이름>",)`` 또는
      ``("agent:<이름>",)``으로 주입하고, 재귀는 ``"agent:<이름>"``(CompositeState)
      / ``"region:<이름>"``(Region)을 누적한다.
    """
    rule: str
    message: str
    source: str = ""
    subject: object | None = field(default=None, compare=False, repr=False)
    path: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_warning(self) -> bool:
        """규칙이 경고 등급이면 True, 에러 등급이면 False.

        invalid_component_name은 빈 이름(에러)과 규약 불일치(경고)가 같은 rule 이름을
        공유한다 — 빈 이름 메시지는 "이름이 비어 있습니다"로 특정하여 에러로 분류.
        """
        if self.rule == "invalid_component_name":
            return "비어 있습니다" not in self.message
        return self.rule in WARNING_RULES


# 경고 등급 규칙 집합 (모델 단일 진실 — view에서 rule 이름 하드코딩 금지).
# invalid_component_name은 is_warning property에서 메시지 내용으로 세분화.
WARNING_RULES: frozenset[str] = frozenset({
    # 머신 수준 경고
    "missing_required_input",
    "pseudo_state_hooks",
    "completion_event_on_composite",
    "empty_delegation",
    "forget_completion_mismatch",
    "duplicate_state_name",
    "unreachable_state",
    "invalid_data_map_source",
    "trigger_unknown_event",
    "dangling_target_port",
    # WP-M FSM 의미론 경고
    "choice_completeness_missing_else",
    "parallel_join_count",
    # 프로젝트 수준 경고
    "dangling_teammate_ref",
    "dangling_string_reference",
    "unregistered_delegation",
    "invalid_component_name",  # 빈 이름 제외는 is_warning에서 처리
    # 도구(tool_shelf) 경고
    "dangling_tool_ref",
    "empty_tool_definition",
    # 훅(hook_library) 경고
    "dangling_hook_ref",
    "empty_hook_command",
    "hook_matcher_without_tool_event",
    # 블랙보드(blackboard) 경고 — WP-BB
    "dangling_blackboard_ref",
    "orphan_blackboard_field",
    "invalid_blackboard_field_type",
    # 파일 참조(files/) 경고 — WP-FR. 검사 로직은 Validator가 아니라
    # compiler/project_compiler.py 소관(검증기는 파일시스템 무접근 순수성
    # 유지)이지만, is_warning 판정 일관성을 위해 여기 등록한다.
    "dangling_file_ref",
    # 빌드 타깃(build_target) 경고 — WP-TG
    "mcp_agent_in_marketplace_build",
    "plugin_root_in_local_build",
    # WP-LA — 플러그인 서브에이전트가 무시하는 프론트매터 필드
    "unsupported_agent_field_in_marketplace_build",
})


# CC 내장 도구 이름 집합 — tool_shelf에 선언하지 않아도 ToolEvaluation/ToolExecution이
# 직접 참조할 수 있는 도구들. dangling_tool_ref 검사 시 shelf와 합쳐 유효 집합을 이룬다.
# (2026-06 기준 CC 1급 도구 + 본 환경 PowerShell. MCP 도구는 mcp__로 시작하므로 별도.)
CC_BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    "WebFetch", "WebSearch", "Agent", "Task",
    "TodoWrite", "NotebookEdit", "SlashCommand", "PowerShell",
})


# CC가 **플러그인 스킬에서만 치환하는** 변수 (공식 skills 문서의 치환 표).
# 프로젝트 설치(LOCAL) 빌드는 플러그인이 아니므로 이 변수들은 리터럴로 남는다.
# ${CLAUDE_PROJECT_DIR}/${CLAUDE_SKILL_DIR}은 플러그인 여부와 무관하게 치환되므로
# 여기 넣지 않는다 — LOCAL에서 files/를 가리키는 정상 경로다.
PLUGIN_ONLY_VARIABLES: tuple[str, ...] = (
    "${CLAUDE_PLUGIN_ROOT}",
    "${CLAUDE_PLUGIN_DATA}",
)


# skip_rules로 생략을 지원하는 규칙 집합 — 이름 오타/규칙 리네임이 조용한
# no-op이 되지 않도록 알려진 이름만 허용한다.
SKIPPABLE_RULES: frozenset[str] = frozenset({"unreachable_state"})


class Validator:
    @staticmethod
    def validate(
        sm: StateMachine,
        skip_rules: frozenset[str] = frozenset(),
    ) -> list[ValidationError]:
        return Validator._validate_machine(sm, skip_rules=skip_rules)

    @staticmethod
    def _validate_machine(
        sm: StateMachine,
        path: tuple[str, ...] = (),
        skip_rules: frozenset[str] = frozenset(),
    ) -> list[ValidationError]:
        """머신 수준 규칙을 검증한다.

        skip_rules: 이름이 속한 규칙 검사를 생략한다(기본값 빈 집합 — 하위 호환).
          재귀(sub_machine/Region)에는 **전파하지 않는다** — 호출부(validate_project)가
          프로젝트 그래프 자체에만 적용하도록 재귀 호출에는 넘기지 않는다.
        """
        unknown = skip_rules - SKIPPABLE_RULES
        if unknown:
            raise ValueError(f"skip_rules에 지원되지 않는 규칙: {sorted(unknown)}")
        errors: list[ValidationError] = []
        errors.extend(Validator._check_initial_in_states(sm, path))
        errors.extend(Validator._check_final_in_states(sm, path))
        errors.extend(Validator._check_nested_agents(sm.states, path))
        errors.extend(Validator._check_agent_to_agent(sm.transitions, path))
        errors.extend(Validator._check_required_inputs(sm.transitions, path))
        errors.extend(Validator._check_pseudo_state_hooks(sm.states, path))
        errors.extend(Validator._check_completion_events(sm, path))
        errors.extend(Validator._check_duplicate_skill_ref(sm.states, path))
        errors.extend(Validator._check_transfer_on_not_empty(sm.states, path))
        errors.extend(Validator._check_delegation_states(sm, path))
        # 신규 머신 수준 규칙
        errors.extend(Validator._check_transition_endpoints(sm, path))
        errors.extend(Validator._check_duplicate_state_name(sm, path))
        if "unreachable_state" not in skip_rules:
            errors.extend(Validator._check_unreachable_state(sm, path))
        errors.extend(Validator._check_invalid_data_map_source(sm.transitions, path))
        errors.extend(Validator._check_trigger_unknown_event(sm, path))
        errors.extend(Validator._check_dangling_target_port(sm, path))
        # WP-M FSM 의미론 규칙
        errors.extend(Validator._check_transition_type_consistency(sm.transitions, path))
        errors.extend(Validator._check_choice_completeness(sm, path))
        errors.extend(Validator._check_parallel_join_count(sm.states, path))
        # 재귀
        for state in sm.states:
            if isinstance(state, CompositeState):
                child_path = path + (f"agent:{state.name}",)
                errors.extend(Validator._validate_machine(state.sub_machine, child_path))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    child_path = path + (f"region:{region.name}",)
                    errors.extend(Validator._validate_machine(region.sub_machine, child_path))
        return errors

    # ------------------------------------------------------------------
    # 기존 규칙 (path 파라미터 추가)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_initial_in_states(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        if sm.states and sm.initial_state not in sm.states:
            return [ValidationError(
                rule="initial_state_in_states",
                message=(
                    f"'{sm.name}': 시작 상태 '{sm.initial_state.name}'이 "
                    f"삭제되었거나 이 FSM에 속하지 않습니다. "
                    f"FSM 편집기에서 시작 상태를 다시 지정하세요."
                ),
                source=sm.name,
                subject=sm,
                path=path,
            )]
        return []

    @staticmethod
    def _check_final_in_states(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for fs in sm.final_states:
            if fs not in sm.states:
                errors.append(ValidationError(
                    rule="final_states_in_states",
                    message=(
                        f"'{sm.name}': 종료 상태 '{fs.name}'이 "
                        f"삭제되었거나 이 FSM에 속하지 않습니다. "
                        f"해당 상태를 다시 추가하거나 종료 상태 목록에서 제거하세요."
                    ),
                    source=sm.name,
                    subject=fs,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_nested_agents(
        states: list[State],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for state in states:
            if isinstance(state, CompositeState):
                for child in state.sub_machine.states:
                    if isinstance(child, CompositeState):
                        errors.append(ValidationError(
                            rule="no_nested_agent",
                            message=(
                                f"CompositeState '{state.name}' 내부에 "
                                f"CompositeState '{child.name}'이 존재합니다."
                            ),
                            source=state.name,
                            subject=child,
                            path=path,
                        ))
        return errors

    @staticmethod
    def _check_agent_to_agent(
        transitions: list[Transition],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            if isinstance(t.source, CompositeState) and isinstance(t.target, CompositeState):
                errors.append(ValidationError(
                    rule="no_agent_to_agent",
                    message=(
                        f"Agent '{t.source.name}' → Agent '{t.target.name}' "
                        f"직접 전이 불가. Skill을 경유해야 합니다."
                    ),
                    source=f"{t.source.name}->{t.target.name}",
                    subject=t,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_required_inputs(
        transitions: list[Transition],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            target_required = [v for v in t.target.inputs if v.required]
            mapped_targets = set(t.data_map.values())
            for var in target_required:
                if var.name not in mapped_targets and var.scope != VariableScope.BLACKBOARD:
                    errors.append(ValidationError(
                        rule="missing_required_input",
                        message=(
                            f"전이 '{t.source.name}' → '{t.target.name}': "
                            f"필수 input '{var.name}'이 data_map에 없습니다."
                        ),
                        source=f"{t.source.name}->{t.target.name}",
                        subject=t,
                        path=path,
                    ))
        return errors

    @staticmethod
    def _check_pseudo_state_hooks(
        states: list[State],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        pseudo_types = (ChoiceState, TerminateState, EntryPoint, ExitPoint)
        # 라이프사이클 훅 필드 목록은 _STATE_ACTION_FIELDS 단일 진실을 재사용한다
        # (도구 참조 수집과 동일 집합 — 신규 훅 추가 시 한 곳만 갱신).
        for state in states:
            if isinstance(state, pseudo_types):
                # 라이프사이클 훅 필드 + custom_events(단순 반응) 모두 의사 상태에는 부적절.
                offending = None
                for field_name in Validator._STATE_ACTION_FIELDS:
                    if getattr(state, field_name, []):
                        offending = field_name
                        break
                if offending is None and getattr(state, "custom_events", None):
                    offending = "custom_events"
                if offending is not None:
                    errors.append(ValidationError(
                        rule="pseudo_state_hooks",
                        message=(
                            f"의사 상태 '{state.name}'({state.kind})에 "
                            f"'{offending}' 훅이 설정되어 있습니다."
                        ),
                        source=state.name,
                        subject=state,
                        path=path,
                    ))
        return errors

    @staticmethod
    def _check_completion_events(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []
        composite_states = [
            s for s in sm.states
            if isinstance(s, (CompositeState, ParallelState))
        ]
        for cs in composite_states:
            outgoing = [t for t in sm.transitions if t.source is cs]
            if outgoing and not any(isinstance(t.trigger, CompletionEvent) for t in outgoing):
                errors.append(ValidationError(
                    rule="completion_event_on_composite",
                    message=(
                        f"'{cs.name}'에서 나가는 전이에 CompletionEvent trigger가 없습니다."
                    ),
                    source=cs.name,
                    subject=cs,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_duplicate_skill_ref(
        states: list,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.delegation import DelegationDef
        seen: set[int] = set()
        errors: list[ValidationError] = []
        for state in states:
            if not isinstance(state, SimpleState):
                continue
            ref = state.skill_ref
            if ref is None:
                continue
            if isinstance(ref, DelegationDef):
                continue  # 위임 정의는 복수 배치 허용 (스펙 2절)
            ref_id = id(ref)
            if ref_id in seen:
                errors.append(ValidationError(
                    rule="no_duplicate_skill_ref",
                    message=(
                        f"'{ref.name}' 스킬/에이전트가 동일 StateMachine에 "
                        f"두 번 이상 배치되었습니다."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
            else:
                seen.add(ref_id)
        return errors

    @staticmethod
    def _check_transfer_on_not_empty(
        states: list,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.model.plugin.agent import AgentDefinition
        errors: list[ValidationError] = []
        for state in states:
            if not isinstance(state, SimpleState):
                continue
            ref = state.skill_ref
            if ref is None:
                continue
            if isinstance(ref, ProceduralSkill):
                if not ref.transfer_on:
                    errors.append(ValidationError(
                        rule="transfer_on_not_empty",
                        message=(
                            f"'{ref.name}' 스킬의 transfer_on이 비어 있습니다. "
                            f"최소 하나의 이벤트가 필요합니다."
                        ),
                        source=ref.name,
                        subject=ref,
                        path=path,
                    ))
            elif isinstance(ref, AgentDefinition):
                if not ref.output_events:
                    errors.append(ValidationError(
                        rule="transfer_on_not_empty",
                        message=(
                            f"'{ref.name}' 에이전트의 ExitPoint가 없습니다. "
                            f"최소 하나의 ExitPoint가 필요합니다."
                        ),
                        source=ref.name,
                        subject=ref,
                        path=path,
                    ))
        return errors

    @staticmethod
    def _check_delegation_states(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """위임 노드의 내용 누락(empty_delegation)과
        forget 모드 결과 분기(forget_completion_mismatch)를 검사."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.delegation import (
            AgoraDispatchDef,
            CompositionMode,
            DelegationDef,
            DynamicWorkflowDef,
            TeamSpawnDef,
            WaitMode,
        )
        errors: list[ValidationError] = []
        for state in sm.states:
            if not isinstance(state, SimpleState):
                continue
            ref = state.skill_ref
            if not isinstance(ref, DelegationDef):
                continue
            is_guided = ref.composition is CompositionMode.GUIDED
            empty_msg = None
            if isinstance(ref, TeamSpawnDef):
                if not is_guided:
                    # EXPLICIT 모드에서만 팀원 0명/count<1 경고
                    if not ref.teammates:
                        empty_msg = f"'{ref.name}' 팀에 팀원이 없습니다."
                    elif any(tm.count < 1 for tm in ref.teammates):
                        empty_msg = f"'{ref.name}' 팀원의 count가 1 미만입니다."
            elif isinstance(ref, DynamicWorkflowDef):
                if not is_guided and not ref.objective:
                    # EXPLICIT 모드에서만 objective 빈 값 경고
                    empty_msg = f"'{ref.name}' 워크플로의 objective가 비어 있습니다."
            elif isinstance(ref, AgoraDispatchDef) and not ref.msgtype:
                # AgoraDispatch msgtype 경고는 모드 무관 유지
                empty_msg = f"'{ref.name}' 송신의 msgtype이 비어 있습니다."
            if empty_msg:
                errors.append(ValidationError(
                    rule="empty_delegation",
                    message=empty_msg,
                    source=state.name,
                    subject=ref,
                    path=path,
                ))
            if ref.wait_mode is WaitMode.FIRE_AND_FORGET:
                completion_names = {
                    t.trigger.name
                    for t in sm.transitions
                    if t.source is state and isinstance(t.trigger, CompletionEvent)
                }
                if len(completion_names) > 1:
                    errors.append(ValidationError(
                        rule="forget_completion_mismatch",
                        message=(
                            f"'{state.name}'은 forget 모드인데 결과 분기"
                            f"({len(completion_names)}개 이벤트)를 시도합니다. "
                            f"결과가 없으므로 단일 진행만 유효합니다."
                        ),
                        source=state.name,
                        subject=state,
                        path=path,
                    ))
        return errors

    # ------------------------------------------------------------------
    # 신규 머신 수준 규칙 5종
    # ------------------------------------------------------------------

    @staticmethod
    def _check_transition_endpoints(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """transition_endpoint_not_in_states — source/target이 sm.states에 없으면 에러."""
        state_ids = {id(s) for s in sm.states}
        errors: list[ValidationError] = []
        for t in sm.transitions:
            if id(t.source) not in state_ids:
                errors.append(ValidationError(
                    rule="transition_endpoint_not_in_states",
                    message=(
                        f"'{sm.name}': 전이 source '{t.source.name}'이 states에 없습니다."
                    ),
                    source=sm.name,
                    subject=t,
                    path=path,
                ))
            if id(t.target) not in state_ids:
                errors.append(ValidationError(
                    rule="transition_endpoint_not_in_states",
                    message=(
                        f"'{sm.name}': 전이 target '{t.target.name}'이 states에 없습니다."
                    ),
                    source=sm.name,
                    subject=t,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_duplicate_state_name(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """duplicate_state_name — 동일 머신 내 동명 상태 경고."""
        seen: dict[str, State] = {}
        errors: list[ValidationError] = []
        for state in sm.states:
            if state.name in seen:
                errors.append(ValidationError(
                    rule="duplicate_state_name",
                    message=(
                        f"'{sm.name}': 상태 이름 '{state.name}'이 중복됩니다."
                    ),
                    source=sm.name,
                    subject=state,
                    path=path,
                ))
            else:
                seen[state.name] = state
        return errors

    @staticmethod
    def _check_unreachable_state(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """unreachable_state — initial_state + 모든 EntryPoint에서 도달 불가 상태 경고."""
        if not sm.states:
            return []

        state_ids = {id(s) for s in sm.states}

        # 시작점: initial_state + 모든 EntryPoint
        start_ids: set[int] = {id(sm.initial_state)}
        for s in sm.states:
            if isinstance(s, EntryPoint):
                start_ids.add(id(s))

        # 전이 그래프 BFS (source/target이 states에 속하는 것만)
        adj: dict[int, list[int]] = {id(s): [] for s in sm.states}
        for t in sm.transitions:
            src_id = id(t.source)
            tgt_id = id(t.target)
            if src_id in state_ids and tgt_id in state_ids:
                adj[src_id].append(tgt_id)

        visited: set[int] = set()
        queue = [sid for sid in start_ids if sid in state_ids]
        while queue:
            cur = queue.pop()
            if cur in visited:
                continue
            visited.add(cur)
            queue.extend(adj.get(cur, []))

        errors: list[ValidationError] = []
        for state in sm.states:
            sid = id(state)
            if sid not in visited and sid not in start_ids:
                errors.append(ValidationError(
                    rule="unreachable_state",
                    message=(
                        f"'{sm.name}': 상태 '{state.name}'({state.kind})은 "
                        f"도달 불가능합니다."
                    ),
                    source=sm.name,
                    subject=state,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_invalid_data_map_source(
        transitions: list[Transition],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """invalid_data_map_source — data_map key가 source의 outputs에 없으면 경고.
        pseudo 상태(ChoiceState, EntryPoint, ExitPoint, TerminateState)는 스킵.
        """
        errors: list[ValidationError] = []
        _pseudo = (ChoiceState, EntryPoint, ExitPoint, TerminateState)
        for t in transitions:
            if isinstance(t.source, _pseudo):
                continue
            source_outputs = getattr(t.source, "outputs", None)
            if source_outputs is None:
                continue
            output_names = {v.name for v in source_outputs}
            for key in t.data_map:
                if key not in output_names:
                    errors.append(ValidationError(
                        rule="invalid_data_map_source",
                        message=(
                            f"전이 '{t.source.name}' → '{t.target.name}': "
                            f"data_map 키 '{key}'가 source outputs에 없습니다."
                        ),
                        source=f"{t.source.name}->{t.target.name}",
                        subject=t,
                        path=path,
                    ))
        return errors

    @staticmethod
    def _check_trigger_unknown_event(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """trigger_unknown_event — CompletionEvent trigger의 이름이 source 출력 이벤트 집합에 없으면 경고."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.skill import ProceduralSkill
        from daedalus.model.plugin.agent import AgentDefinition

        errors: list[ValidationError] = []
        for t in sm.transitions:
            if not isinstance(t.trigger, CompletionEvent):
                continue
            source = t.source
            known_events: set[str] | None = None

            if isinstance(source, SimpleState) and source.skill_ref is not None:
                ref = source.skill_ref
                # ProceduralSkill/AgentDefinition만 출력 이벤트 집합을 정의한다.
                # DelegationDef·DeclarativeSkill 등은 known_events=None → 검사 스킵.
                # 주의: TransferSkill.output_events는 항상 []이므로 향후 분기에
                # 추가하면 모든 trigger가 오탐이 된다 — 추가 금지.
                if isinstance(ref, ProceduralSkill):
                    # transfer_on(output_events) + call_agents — 캔버스는 Agent Call
                    # 포트에서도 전이를 만들므로(trigger=CompletionEvent(이벤트명))
                    # call_agents 이벤트도 합법적 출력 이벤트 집합에 포함한다.
                    known_events = set(ref.output_events) | {
                        e.name for e in ref.call_agents
                    }
                elif isinstance(ref, AgentDefinition):
                    known_events = set(ref.output_events)
            elif isinstance(source, CompositeState):
                # sub_machine ExitPoint 이름 + "done"
                exit_names = {
                    s.name for s in source.sub_machine.states
                    if isinstance(s, ExitPoint)
                }
                exit_names.add("done")
                known_events = exit_names

            if known_events is not None and t.trigger.name not in known_events:
                errors.append(ValidationError(
                    rule="trigger_unknown_event",
                    message=(
                        f"전이 '{source.name}' → '{t.target.name}': "
                        f"trigger 이벤트 '{t.trigger.name}'이 source의 "
                        f"출력 이벤트 집합 {sorted(known_events)}에 없습니다."
                    ),
                    source=f"{source.name}->{t.target.name}",
                    subject=t,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_dangling_target_port(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """dangling_target_port — trigger_unknown_event의 입력판(WP-IC).

        Transition.target_port가 비어 있지 않은데 타깃 skill_ref의 entry_paths
        이름 집합에 없으면 경고 (EventDef rename 고아 전이 검출). 타깃이
        skill_ref 없는 상태(EntryPoint 등)면 스킵.
        """
        from daedalus.model.fsm.state import SimpleState

        errors: list[ValidationError] = []
        for t in sm.transitions:
            if not t.target_port:
                continue
            target = t.target
            if not isinstance(target, SimpleState) or target.skill_ref is None:
                continue
            entry_paths = getattr(target.skill_ref, "entry_paths", None)
            if entry_paths is None:
                continue
            known_names = {e.name for e in entry_paths}
            if t.target_port not in known_names:
                errors.append(ValidationError(
                    rule="dangling_target_port",
                    message=(
                        f"전이 '{t.source.name}' → '{target.name}': "
                        f"target_port '{t.target_port}'가 타깃의 입력 경로 "
                        f"집합 {sorted(known_names)}에 없습니다."
                    ),
                    source=f"{t.source.name}->{target.name}",
                    subject=t,
                    path=path,
                ))
        return errors

    # ------------------------------------------------------------------
    # WP-M FSM 의미론 규칙 3종
    # ------------------------------------------------------------------

    @staticmethod
    def _check_transition_type_consistency(
        transitions: list[Transition],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """transition_type_consistency — INTERNAL/SELF 타입인데 source≠target이면 에러.

        INTERNAL은 상태 비이탈 반응, SELF는 같은 상태로의 재진입이므로 두 경우 모두
        source와 target이 identity로 동일해야 한다.
        """
        from daedalus.model.fsm.transition import TransitionType
        errors: list[ValidationError] = []
        for t in transitions:
            if t.type in (TransitionType.INTERNAL, TransitionType.SELF):
                if t.source is not t.target:
                    errors.append(ValidationError(
                        rule="transition_type_consistency",
                        message=(
                            f"전이 '{t.source.name}' → '{t.target.name}': "
                            f"{t.type.value} 타입은 source와 target이 같아야 합니다."
                        ),
                        source=f"{t.source.name}->{t.target.name}",
                        subject=t,
                        path=path,
                    ))
        return errors

    @staticmethod
    def _check_choice_completeness(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """choice_completeness — ChoiceState 분기 완전성.

        관례: outgoing 중 **무가드 전이 = else 분기**.
          - outgoing 0개 → 에러 (막다른 분기)
          - 무가드 outgoing 2개 이상 → 에러 (비결정 else 중복)
          - 무가드 0개 → 경고 (else 부재 — LLM 해석 결정성 저하)
        """
        errors: list[ValidationError] = []
        for state in sm.states:
            if not isinstance(state, ChoiceState):
                continue
            outgoing = [t for t in sm.transitions if t.source is state]
            unguarded = [t for t in outgoing if t.guard is None]
            if not outgoing:
                errors.append(ValidationError(
                    rule="choice_completeness",
                    message=(
                        f"ChoiceState '{state.name}'에 나가는 전이가 없습니다 "
                        f"(막다른 분기)."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
                continue
            if len(unguarded) >= 2:
                errors.append(ValidationError(
                    rule="choice_completeness",
                    message=(
                        f"ChoiceState '{state.name}'에 무가드 전이가 "
                        f"{len(unguarded)}개입니다 — else 분기는 하나여야 "
                        f"합니다 (비결정)."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
            elif not unguarded:
                errors.append(ValidationError(
                    rule="choice_completeness_missing_else",
                    message=(
                        f"ChoiceState '{state.name}'에 무가드(else) 전이가 "
                        f"없습니다 — 어떤 가드도 통과하지 못하면 분기가 멈춥니다."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
        return errors

    @staticmethod
    def _check_parallel_join_count(
        states: list[State],
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
        """parallel_join_count — ParallelState.join이 count형(N_OF)인데
        join_count가 None이거나 region 수를 초과하면 경고."""
        from daedalus.model.fsm.join import JoinStrategy
        errors: list[ValidationError] = []
        for state in states:
            if not isinstance(state, ParallelState):
                continue
            if state.join is not JoinStrategy.N_OF:
                continue
            n_regions = len(state.regions)
            jc = state.join_count
            if jc is None:
                errors.append(ValidationError(
                    rule="parallel_join_count",
                    message=(
                        f"ParallelState '{state.name}'의 join이 N_OF인데 "
                        f"join_count가 지정되지 않았습니다."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
            elif jc > n_regions:
                errors.append(ValidationError(
                    rule="parallel_join_count",
                    message=(
                        f"ParallelState '{state.name}'의 join_count({jc})가 "
                        f"region 수({n_regions})를 초과합니다."
                    ),
                    source=state.name,
                    subject=state,
                    path=path,
                ))
        return errors

    # ------------------------------------------------------------------
    # 프로젝트 수준 규칙
    # ------------------------------------------------------------------

    @staticmethod
    def _graph_has_placements(graph: StateMachine) -> bool:
        """프로젝트 그래프에 EntryPoint 외 노드(placement)가 하나라도 있으면 True.

        빈 그래프(시작점만)는 검증을 스킵해 경고 폭주를 막는다.
        """
        return any(not isinstance(s, EntryPoint) for s in graph.states)

    @staticmethod
    def validate_project(project) -> list[ValidationError]:
        """프로젝트 전체 검증 — 모든 FSM의 머신 수준 규칙 + 프로젝트 수준 규칙."""
        errors: list[ValidationError] = []
        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                errors.extend(Validator._validate_machine(
                    fsm, path=(f"skill:{skill.name}",),
                ))
        for agent in project.agents:
            errors.extend(Validator._validate_machine(
                agent.fsm, path=(f"agent:{agent.name}",),
            ))
        # 프로젝트 워크플로 그래프 — placement가 하나라도 있을 때만 머신 규칙 적용.
        # 빈 캔버스(EntryPoint 하나뿐)는 검증 스킵 (경고 폭주 방지).
        # unreachable_state는 스킵한다(WP-EP): CC 플러그인 의미론상 프로젝트
        # 그래프의 모든 배치는 user_invocable 스킬 등으로 독립 시작 가능해
        # "도달 불가"가 성립하지 않는다. 재귀(에이전트 sub_machine)에는 전파되지
        # 않으므로 에이전트 FSM 내부의 unreachable_state는 기존대로 검사된다.
        graph = getattr(project, "graph", None)
        if graph is not None and Validator._graph_has_placements(graph):
            errors.extend(Validator._validate_machine(
                graph, path=("project",), skip_rules=frozenset({"unreachable_state"}),
            ))
        errors.extend(Validator._check_dangling_delegation_refs(project))
        errors.extend(Validator._check_unregistered_delegations(project))
        # 신규 프로젝트 수준 규칙
        errors.extend(Validator._check_duplicate_component_name(project))
        errors.extend(Validator._check_invalid_component_name(project))
        errors.extend(Validator._check_invalid_project_name(project))
        errors.extend(Validator._check_dangling_string_references(project))
        # 도구(tool_shelf) 규칙
        errors.extend(Validator._check_duplicate_tool_name(project))
        errors.extend(Validator._check_empty_tool_definition(project))
        errors.extend(Validator._check_dangling_tool_refs(project))
        # 훅(hook_library) 규칙
        errors.extend(Validator._check_duplicate_hook_name(project))
        errors.extend(Validator._check_empty_hook_command(project))
        errors.extend(Validator._check_hook_matcher_event(project))
        errors.extend(Validator._check_dangling_hook_refs(project))
        # 블랙보드(blackboard) 규칙 — WP-BB
        errors.extend(Validator._check_dangling_blackboard_refs(project))
        errors.extend(Validator._check_orphan_blackboard_fields(project))
        errors.extend(Validator._check_blackboard_field_types(project))
        # 빌드 타깃(build_target) 규칙 — WP-TG
        errors.extend(Validator._check_mcp_agent_in_marketplace_build(project))
        errors.extend(Validator._check_unsupported_agent_fields(project))
        errors.extend(Validator._check_plugin_root_in_local_build(project))
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
                names.extend(Validator._collect_eval_tools(child))
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
                names.extend(Validator._collect_exec_tools(child))
        return names

    # 상태/전이의 액션 체인 훅 필드 이름들 (custom_events는 dict로 별도 처리).
    _STATE_ACTION_FIELDS = (
        "on_entry_start", "on_entry", "on_entry_end",
        "on_exit_start", "on_exit", "on_exit_end", "on_active",
    )
    _TRANSITION_ACTION_FIELDS = (
        "on_guard_check", "on_traverse_start", "on_traverse", "on_traverse_end",
    )

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
                names.extend(Validator._collect_exec_tools(a.execution))

        for state in sm.states:
            for fname in Validator._STATE_ACTION_FIELDS:
                _actions(getattr(state, fname, None))
            for lst in getattr(state, "custom_events", {}).values():
                _actions(lst)
            # 재귀
            if isinstance(state, CompositeState):
                names.extend(Validator._collect_machine_tool_refs(state.sub_machine))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    names.extend(Validator._collect_machine_tool_refs(region.sub_machine))

        for t in sm.transitions:
            if t.guard is not None:
                names.extend(Validator._collect_eval_tools(t.guard.evaluation))
            for fname in Validator._TRANSITION_ACTION_FIELDS:
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
        for label, fsm in Validator._project_machines(project):
            for name in Validator._collect_machine_tool_refs(fsm):
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

        스킬/에이전트/에이전트 로컬 스킬의 config.hooks를 모두 훑는다.
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
            for local in getattr(agent, "skills", []):
                lcfg = getattr(local, "config", None)
                lhooks = getattr(lcfg, "hooks", None)
                if isinstance(lhooks, dict):
                    for name in lhooks:
                        yield (f"agent:{agent.name}/skill:{local.name}", name, local)

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
        """empty_hook_command — HookDef.command 빈 값 경고."""
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if not hook.command.strip():
                errors.append(ValidationError(
                    rule="empty_hook_command",
                    message=f"훅 '{hook.name}'의 command가 비어 있습니다.",
                    source=hook.name,
                    subject=hook,
                ))
        return errors

    @staticmethod
    def _check_hook_matcher_event(project) -> list[ValidationError]:
        """hook_matcher_without_tool_event — matcher가 있는데 event가
        Pre/PostToolUse가 아니면 경고 (도구 매칭은 도구 이벤트에만 유효)."""
        from daedalus.model.plugin.hook import TOOL_MATCH_EVENTS
        errors: list[ValidationError] = []
        for hook in getattr(project, "hook_library", []):
            if hook.matcher.strip() and hook.event not in TOOL_MATCH_EVENTS:
                errors.append(ValidationError(
                    rule="hook_matcher_without_tool_event",
                    message=(
                        f"훅 '{hook.name}'의 matcher '{hook.matcher}'는 "
                        f"event '{hook.event.value}'에서 무시됩니다. "
                        f"matcher는 PreToolUse/PostToolUse에서만 유효합니다."
                    ),
                    source=hook.name,
                    subject=hook,
                ))
        return errors

    @staticmethod
    def _check_dangling_hook_refs(project) -> list[ValidationError]:
        """dangling_hook_ref — config.hooks 키가 hook_library에 없으면 경고."""
        lib_names = {h.name for h in getattr(project, "hook_library", [])}
        errors: list[ValidationError] = []
        for label, name, subject in Validator._collect_hook_refs(project):
            if name not in lib_names:
                errors.append(ValidationError(
                    rule="dangling_hook_ref",
                    message=(
                        f"{label}: config.hooks가 참조하는 훅 '{name}'이 "
                        f"hook_library에 없습니다."
                    ),
                    source=name,
                    subject=subject,
                    path=(label,),
                ))
        return errors

    @staticmethod
    def _check_dangling_delegation_refs(project) -> list[ValidationError]:
        """위임 정의의 agent_ref가 프로젝트 agents에 실존하는지 검사."""
        from daedalus.model.plugin.delegation import DynamicWorkflowDef, TeamSpawnDef
        known = {id(a) for a in project.agents}
        errors: list[ValidationError] = []
        for d in project.delegations:
            refs: list = []
            if isinstance(d, TeamSpawnDef):
                # remove_component가 삭제된 에이전트의 agent_ref를 None으로 만들 수 있다.
                # None은 dangling이 아니라 '비워진 참조' — empty_delegation 규칙이 다룬다.
                refs = [tm.agent_ref for tm in d.teammates if tm.agent_ref is not None]
            elif isinstance(d, DynamicWorkflowDef):
                refs = [ph.agent_ref for ph in d.phases if ph.agent_ref is not None]
            for ref in refs:
                if id(ref) not in known:
                    errors.append(ValidationError(
                        rule="dangling_teammate_ref",
                        message=(
                            f"위임 '{d.name}'이 프로젝트에 없는 에이전트 "
                            f"'{ref.name}'을 참조합니다."
                        ),
                        source=d.name,
                        subject=ref,
                    ))
        return errors

    @staticmethod
    def _check_unregistered_delegations(project) -> list[ValidationError]:
        """unregistered_delegation — 배치된 SimpleState.skill_ref가 DelegationDef인데
        project.delegations에 미등록이면 경고."""
        from daedalus.model.fsm.state import SimpleState
        from daedalus.model.plugin.delegation import DelegationDef

        registered_ids = {id(d) for d in project.delegations}
        errors: list[ValidationError] = []

        def _scan_machine(sm: StateMachine) -> None:
            for state in sm.states:
                if isinstance(state, SimpleState):
                    ref = state.skill_ref
                    if isinstance(ref, DelegationDef) and id(ref) not in registered_ids:
                        errors.append(ValidationError(
                            rule="unregistered_delegation",
                            message=(
                                f"배치된 노드 '{state.name}'의 skill_ref "
                                f"'{ref.name}'({ref.kind})이 project.delegations에 "
                                f"등록되어 있지 않습니다."
                            ),
                            source=state.name,
                            subject=ref,
                        ))
                elif isinstance(state, CompositeState):
                    _scan_machine(state.sub_machine)
                elif isinstance(state, ParallelState):
                    for region in state.regions:
                        _scan_machine(region.sub_machine)

        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                _scan_machine(fsm)
        for agent in project.agents:
            _scan_machine(agent.fsm)
        graph = getattr(project, "graph", None)
        if graph is not None:
            _scan_machine(graph)

        return errors

    @staticmethod
    def _check_duplicate_component_name(project) -> list[ValidationError]:
        """duplicate_component_name — skills/agents/delegations 전체에서 동명 컴포넌트 에러."""
        seen: dict[str, object] = {}
        errors: list[ValidationError] = []
        all_components = [
            *project.skills,
            *project.agents,
            *project.delegations,
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
            *project.delegations,
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
            elif not Validator._COMPONENT_NAME_RE.match(name):
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
        if not Validator._COMPONENT_NAME_RE.match(name):
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

        # AgentConfig.skills 검사 (전역 + 에이전트 로컬 스킬 합산)
        for agent in project.agents:
            cfg = agent.config
            if not isinstance(cfg, AgentConfig):
                continue
            local_skill_names = {s.name for s in agent.skills}
            available_names = global_skill_names | local_skill_names
            for skill_name in cfg.skills:
                if skill_name not in available_names:
                    errors.append(ValidationError(
                        rule="dangling_string_reference",
                        message=(
                            f"에이전트 '{agent.name}'의 config.skills '{skill_name}'이 "
                            f"프로젝트 skills 또는 에이전트 로컬 skills에 없습니다."
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
        """
        for state in sm.states:
            visit(state)
            if isinstance(state, CompositeState):
                Validator._scan_state_access(state.sub_machine, visit)
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    Validator._scan_state_access(region.sub_machine, visit)

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
                Validator._scan_state_access(fsm, _make_checker((f"skill:{skill.name}",)))
        for agent in project.agents:
            Validator._scan_state_access(agent.fsm, _make_checker((f"agent:{agent.name}",)))
            # 에이전트 로컬 스킬 FSM도 검사 — dangling_hook_ref 전례 (리뷰 지적:
            # 제외하면 orphan이 오탐, dangling이 미검출된다)
            for local in getattr(agent, "skills", None) or []:
                local_fsm = getattr(local, "fsm", None)
                if local_fsm is not None:
                    Validator._scan_state_access(
                        local_fsm,
                        _make_checker((f"agent:{agent.name}", f"skill:{local.name}")),
                    )
        graph = getattr(project, "graph", None)
        if graph is not None:
            Validator._scan_state_access(graph, _make_checker(("project",)))

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
                Validator._scan_state_access(fsm, _collect)
        for agent in project.agents:
            Validator._scan_state_access(agent.fsm, _collect)
            for local in getattr(agent, "skills", None) or []:
                local_fsm = getattr(local, "fsm", None)
                if local_fsm is not None:
                    Validator._scan_state_access(local_fsm, _collect)
        graph = getattr(project, "graph", None)
        if graph is not None:
            Validator._scan_state_access(graph, _collect)

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
        """plugin_root_in_local_build — build_target=LOCAL인데 스킬/에이전트(로컬
        스킬 포함) 본문에 **플러그인 전용 변수**가 남아 있으면 경고.

        CC는 `${CLAUDE_PLUGIN_ROOT}`와 `${CLAUDE_PLUGIN_DATA}`를 **플러그인
        스킬에서만 치환한다**(공식 skills 문서의 치환 표). 프로젝트 설치 빌드는
        플러그인이 아니므로 이 변수들이 리터럴 문자열 그대로 남는다.

        files/ 참조(``${CLAUDE_PLUGIN_ROOT}/files/``)는 컴파일이
        ``${CLAUDE_PROJECT_DIR}/files/``로 자동 치환하므로 검사에서 제외한다 —
        `${CLAUDE_PROJECT_DIR}`는 플러그인 여부와 무관하게 치환된다(v2.1.196+).
        """
        build_target = getattr(project, "build_target", BuildTarget.MARKETPLACE)
        if build_target is not BuildTarget.LOCAL:
            return []
        errors: list[ValidationError] = []

        def _scan(label: str, subject: object, body: str, path: tuple[str, ...]) -> None:
            text = body or ""
            # files/ 참조는 컴파일이 자동 치환하므로 제거한 나머지에서만 검사.
            remaining = text.replace("${CLAUDE_PLUGIN_ROOT}/files/", "")
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
            # 잠금 계약 카드도 agent .md에 그대로 배출되므로 함께 검사한다
            # (리뷰 지적 C — body만 보면 계약 카드의 죽은 경로를 놓친다)
            for contract in getattr(agent, "caller_contracts", None) or []:
                _scan(
                    f"에이전트 '{agent.name}'의 호출 계약 '{contract.title}'",
                    agent, getattr(contract, "content", ""),
                    (f"agent:{agent.name}",),
                )
            for local in getattr(agent, "skills", None) or []:
                _scan(
                    f"에이전트 '{agent.name}'의 로컬 스킬 '{local.name}'",
                    local, getattr(local, "body", ""),
                    (f"agent:{agent.name}", f"skill:{local.name}"),
                )
        return errors
