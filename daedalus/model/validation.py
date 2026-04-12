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
            if isinstance(ref, (ProceduralSkill, AgentDefinition)):
                if not ref.transfer_on:
                    errors.append(ValidationError(
                        rule="transfer_on_not_empty",
                        message=(
                            f"'{ref.name}' 스킬/에이전트의 transfer_on이 비어 있습니다. "
                            f"최소 하나의 이벤트가 필요합니다."
                        ),
                        source=ref.name,
                    ))
        return errors
