from __future__ import annotations

import re
from dataclasses import dataclass, field

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, State
from daedalus.model.fsm.transition import Transition
from daedalus.model.fsm.variable import VariableScope


@dataclass
class ValidationError:
    rule: str
    message: str
    source: str = ""
    subject: object | None = field(default=None, compare=False, repr=False)
    path: tuple[str, ...] = field(default_factory=tuple)


class Validator:
    @staticmethod
    def validate(sm: StateMachine) -> list[ValidationError]:
        return Validator._validate_machine(sm)

    @staticmethod
    def _validate_machine(
        sm: StateMachine,
        path: tuple[str, ...] = (),
    ) -> list[ValidationError]:
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
        errors.extend(Validator._check_unreachable_state(sm, path))
        errors.extend(Validator._check_invalid_data_map_source(sm.transitions, path))
        errors.extend(Validator._check_trigger_unknown_event(sm, path))
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
                message=f"'{sm.name}': initial_state '{sm.initial_state.name}'이 states에 포함되지 않습니다.",
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
                    message=f"'{sm.name}': final_state '{fs.name}'이 states에 포함되지 않습니다.",
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
        hook_fields = [
            "on_entry_start", "on_entry", "on_entry_end",
            "on_exit_start", "on_exit", "on_exit_end",
            "on_active",
        ]
        for state in states:
            if isinstance(state, pseudo_types):
                for field_name in hook_fields:
                    if getattr(state, field_name, []):
                        errors.append(ValidationError(
                            rule="pseudo_state_hooks",
                            message=(
                                f"의사 상태 '{state.name}'({state.kind})에 "
                                f"'{field_name}' 훅이 설정되어 있습니다."
                            ),
                            source=state.name,
                            subject=state,
                            path=path,
                        ))
                        break  # 상태당 1개 경고
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
            empty_msg = None
            if isinstance(ref, TeamSpawnDef):
                if not ref.teammates:
                    empty_msg = f"'{ref.name}' 팀에 팀원이 없습니다."
                elif any(tm.count < 1 for tm in ref.teammates):
                    empty_msg = f"'{ref.name}' 팀원의 count가 1 미만입니다."
            elif isinstance(ref, DynamicWorkflowDef) and not ref.objective:
                empty_msg = f"'{ref.name}' 워크플로의 objective가 비어 있습니다."
            elif isinstance(ref, AgoraDispatchDef) and not ref.msgtype:
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
                if isinstance(ref, ProceduralSkill):
                    known_events = set(ref.output_events)
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
    # 프로젝트 수준 규칙
    # ------------------------------------------------------------------

    @staticmethod
    def validate_project(project) -> list[ValidationError]:
        """프로젝트 전체 검증 — 모든 FSM의 머신 수준 규칙 + 프로젝트 수준 규칙."""
        errors: list[ValidationError] = []
        for skill in project.skills:
            fsm = getattr(skill, "fsm", None)
            if fsm is not None:
                errors.extend(Validator._validate_machine(fsm))
        for agent in project.agents:
            errors.extend(Validator._validate_machine(agent.fsm))
        errors.extend(Validator._check_dangling_delegation_refs(project))
        # 신규 프로젝트 수준 규칙
        errors.extend(Validator._check_duplicate_component_name(project))
        errors.extend(Validator._check_invalid_component_name(project))
        errors.extend(Validator._check_dangling_string_references(project))
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
                refs = [tm.agent_ref for tm in d.teammates]
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
    def _check_duplicate_component_name(project) -> list[ValidationError]:
        """duplicate_component_name — skills/agents/delegations 전체에서 동명 컴포넌트 에러."""
        from daedalus.model.plugin.skill import Skill
        from daedalus.model.plugin.agent import AgentDefinition
        from daedalus.model.plugin.delegation import DelegationDef

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
