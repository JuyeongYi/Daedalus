# daedalus/model/validation/machine_rules.py
"""머신 수준 규칙 — StateMachine 하나를 놓고 판정할 수 있는 검사들.

``_MachineRules``는 ``Validator``가 상속하는 믹스인이다(WP-RF-3d 분해 — 이동만,
동작 불변). 규칙 이름·메시지·발급 순서는 분해 전과 동일하며, 외부는 계속
``Validator._check_*`` 이름으로 부를 수 있다.
"""
from __future__ import annotations

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, State
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import VariableScope
from daedalus.model.validation.severity import ValidationError


# skip_rules로 생략을 지원하는 규칙 집합 — 이름 오타/규칙 리네임이 조용한
# no-op이 되지 않도록 알려진 이름만 허용한다.
SKIPPABLE_RULES: frozenset[str] = frozenset({"unreachable_state"})


class _MachineRules:
    """머신 수준 규칙 모음 (Validator 믹스인)."""

    # 상태/전이의 액션 체인 훅 필드 이름들 (custom_events는 dict로 별도 처리).
    # 의사 상태 훅 검사(_check_pseudo_state_hooks)와 도구 참조 수집
    # (_ProjectRules._collect_machine_tool_refs)이 공유하는 단일 진실 —
    # 신규 훅 필드가 늘면 여기 한 곳만 갱신한다.
    _STATE_ACTION_FIELDS = (
        "on_entry_start", "on_entry", "on_entry_end",
        "on_exit_start", "on_exit", "on_exit_end", "on_active",
    )
    _TRANSITION_ACTION_FIELDS = (
        "on_guard_check", "on_traverse_start", "on_traverse", "on_traverse_end",
    )

    @staticmethod
    def validate(
        sm: StateMachine,
        skip_rules: frozenset[str] = frozenset(),
    ) -> list[ValidationError]:
        return _MachineRules._validate_machine(sm, skip_rules=skip_rules)

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
        errors.extend(_MachineRules._check_initial_in_states(sm, path))
        errors.extend(_MachineRules._check_final_in_states(sm, path))
        errors.extend(_MachineRules._check_nested_agents(sm.states, path))
        errors.extend(_MachineRules._check_agent_to_agent(sm.transitions, path))
        errors.extend(_MachineRules._check_required_inputs(sm.transitions, path))
        errors.extend(_MachineRules._check_pseudo_state_hooks(sm.states, path))
        errors.extend(_MachineRules._check_completion_events(sm, path))
        errors.extend(_MachineRules._check_duplicate_skill_ref(sm.states, path))
        errors.extend(_MachineRules._check_transfer_on_not_empty(sm.states, path))
        # 신규 머신 수준 규칙
        errors.extend(_MachineRules._check_transition_endpoints(sm, path))
        errors.extend(_MachineRules._check_duplicate_state_name(sm, path))
        if "unreachable_state" not in skip_rules:
            errors.extend(_MachineRules._check_unreachable_state(sm, path))
        errors.extend(_MachineRules._check_invalid_data_map_source(sm.transitions, path))
        errors.extend(_MachineRules._check_trigger_unknown_event(sm, path))
        # WP-M FSM 의미론 규칙
        errors.extend(_MachineRules._check_transition_type_consistency(sm.transitions, path))
        errors.extend(_MachineRules._check_choice_completeness(sm, path))
        errors.extend(_MachineRules._check_parallel_join_count(sm.states, path))
        # 재귀 — 여기만 ``model/fsm/walk.iter_machines``로 환원하지 않는다.
        # path 누적(agent:/region: 접두)과 머신별 규칙 적용이 재귀 골격과 얽혀
        # 있어 순회만 떼어내면 동작(경로 라벨) 불변을 보장할 수 없다.
        for state in sm.states:
            if isinstance(state, CompositeState):
                child_path = path + (f"agent:{state.name}",)
                errors.extend(_MachineRules._validate_machine(state.sub_machine, child_path))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    child_path = path + (f"region:{region.name}",)
                    errors.extend(_MachineRules._validate_machine(region.sub_machine, child_path))
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
                for field_name in _MachineRules._STATE_ACTION_FIELDS:
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
        seen: set[int] = set()
        errors: list[ValidationError] = []
        for state in states:
            if not isinstance(state, SimpleState):
                continue
            ref = state.skill_ref
            if ref is None:
                continue
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
                # WP-AF — 출력 포트는 transfer_on이 단일 진실.
                if not ref.output_events:
                    errors.append(ValidationError(
                        rule="transfer_on_not_empty",
                        message=(
                            f"'{ref.name}' 에이전트의 출력 포트(transfer_on)가 "
                            f"비어 있습니다. 최소 하나의 출력 이벤트가 필요합니다."
                        ),
                        source=ref.name,
                        subject=ref,
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
                # DeclarativeSkill 등은 known_events=None → 검사 스킵.
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
