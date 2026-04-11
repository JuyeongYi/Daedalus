from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.state import CompositeState, State
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
        errors: list[ValidationError] = []
        errors.extend(Validator._check_nested_agents(sm.states))
        errors.extend(Validator._check_agent_to_agent(sm.transitions))
        errors.extend(Validator._check_required_inputs(sm.transitions))
        return errors

    @staticmethod
    def _check_nested_agents(states: list[State]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for state in states:
            if isinstance(state, CompositeState):
                for child in state.children:
                    if isinstance(child, CompositeState):
                        errors.append(
                            ValidationError(
                                rule="no_nested_agent",
                                message=(
                                    f"CompositeState '{state.name}' 내부에 "
                                    f"CompositeState '{child.name}'이 존재합니다."
                                ),
                                source=state.name,
                            )
                        )
        return errors

    @staticmethod
    def _check_agent_to_agent(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            if isinstance(t.source, CompositeState) and isinstance(t.target, CompositeState):
                errors.append(
                    ValidationError(
                        rule="no_agent_to_agent",
                        message=(
                            f"Agent '{t.source.name}' → Agent '{t.target.name}' "
                            f"직접 전이 불가. Skill을 경유해야 합니다."
                        ),
                        source=f"{t.source.name}->{t.target.name}",
                    )
                )
        return errors

    @staticmethod
    def _check_required_inputs(transitions: list[Transition]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        for t in transitions:
            target_required = [v for v in t.target.inputs if v.required]
            mapped_targets = set(t.data_map.values())
            for var in target_required:
                if var.name not in mapped_targets and var.scope != VariableScope.BLACKBOARD:
                    errors.append(
                        ValidationError(
                            rule="missing_required_input",
                            message=(
                                f"전이 '{t.source.name}' → '{t.target.name}': "
                                f"필수 input '{var.name}'이 data_map에 없습니다."
                            ),
                            source=f"{t.source.name}->{t.target.name}",
                        )
                    )
        return errors
