from __future__ import annotations

from dataclasses import dataclass

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


class Validator:
    @staticmethod
    def validate(sm: StateMachine) -> list[ValidationError]:
        return Validator._validate_machine(sm)

    @staticmethod
    def _validate_machine(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        errors.extend(Validator._check_initial_in_states(sm))
        errors.extend(Validator._check_final_in_states(sm))
        errors.extend(Validator._check_nested_agents(sm.states))
        errors.extend(Validator._check_agent_to_agent(sm.transitions))
        errors.extend(Validator._check_required_inputs(sm.transitions))
        errors.extend(Validator._check_pseudo_state_hooks(sm.states))
        errors.extend(Validator._check_completion_events(sm))
        errors.extend(Validator._check_duplicate_skill_ref(sm.states))
        errors.extend(Validator._check_transfer_on_not_empty(sm.states))
        errors.extend(Validator._check_delegation_states(sm))
        # 재귀
        for state in sm.states:
            if isinstance(state, CompositeState):
                errors.extend(Validator._validate_machine(state.sub_machine))
            elif isinstance(state, ParallelState):
                for region in state.regions:
                    errors.extend(Validator._validate_machine(region.sub_machine))
        return errors

    @staticmethod
    def _check_initial_in_states(sm: StateMachine) -> list[ValidationError]:
        if sm.states and sm.initial_state not in sm.states:
            return [ValidationError(
                rule="initial_state_in_states",
                message=f"'{sm.name}': initial_state '{sm.initial_state.name}'이 states에 포함되지 않습니다.",
                source=sm.name,
            )]
        return []

    @staticmethod
    def _check_final_in_states(sm: StateMachine) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for fs in sm.final_states:
            if fs not in sm.states:
                errors.append(ValidationError(
                    rule="final_states_in_states",
                    message=f"'{sm.name}': final_state '{fs.name}'이 states에 포함되지 않습니다.",
                    source=sm.name,
                ))
        return errors

    @staticmethod
    def _check_nested_agents(states: list[State]) -> list[ValidationError]:
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
                        ))
        return errors

    @staticmethod
    def _check_agent_to_agent(transitions: list[Transition]) -> list[ValidationError]:
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
                ))
        return errors

    @staticmethod
    def _check_required_inputs(transitions: list[Transition]) -> list[ValidationError]:
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
                    ))
        return errors

    @staticmethod
    def _check_pseudo_state_hooks(states: list[State]) -> list[ValidationError]:
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
                        ))
                        break  # 상태당 1개 경고
        return errors

    @staticmethod
    def _check_completion_events(sm: StateMachine) -> list[ValidationError]:
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
                ))
        return errors

    @staticmethod
    def _check_duplicate_skill_ref(states: list) -> list[ValidationError]:
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
                ))
            else:
                seen.add(ref_id)
        return errors

    @staticmethod
    def _check_transfer_on_not_empty(states: list) -> list[ValidationError]:
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
                    ))
        return errors

    @staticmethod
    def _check_delegation_states(sm: StateMachine) -> list[ValidationError]:
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
                    ))
        return errors

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
                    ))
        return errors
