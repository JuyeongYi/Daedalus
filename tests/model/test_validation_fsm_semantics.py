"""WP-M FSM 의미론 규칙 테스트 (감사 3-1).

규칙 3종:
  transition_type_consistency  (에러)
  choice_completeness          (에러: 0 outgoing / 무가드 2+)
  choice_completeness_missing_else (경고: 무가드 0)
  parallel_join_count          (경고)
"""
from __future__ import annotations

from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState
from daedalus.model.fsm.state import ParallelState, Region, SimpleState
from daedalus.model.fsm.strategy import ExpressionEvaluation
from daedalus.model.fsm.transition import Transition, TransitionType
from daedalus.model.validation import Validator


def _sm(states, transitions=None, *, initial=None) -> StateMachine:
    return StateMachine(
        name="t",
        states=states,
        transitions=transitions or [],
        initial_state=initial or states[0],
    )


def _guard(expr: str = "x == 1") -> Guard:
    return Guard(evaluation=ExpressionEvaluation(expression=expr))


# ─────────────── transition_type_consistency ───────────────


def test_internal_transition_with_different_endpoints_errors():
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    t = Transition(source=a, target=b, type=TransitionType.INTERNAL)
    errors = Validator.validate(_sm([a, b], [t]))
    matching = [e for e in errors if e.rule == "transition_type_consistency"]
    assert len(matching) == 1
    assert not matching[0].is_warning


def test_self_transition_with_different_endpoints_errors():
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    t = Transition(source=a, target=b, type=TransitionType.SELF)
    errors = Validator.validate(_sm([a, b], [t]))
    assert any(e.rule == "transition_type_consistency" for e in errors)


def test_internal_transition_same_endpoint_passes():
    a = SimpleState(name="A")
    t = Transition(source=a, target=a, type=TransitionType.INTERNAL)
    errors = Validator.validate(_sm([a], [t]))
    assert not any(e.rule == "transition_type_consistency" for e in errors)


def test_external_transition_different_endpoints_passes():
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    t = Transition(source=a, target=b, type=TransitionType.EXTERNAL)
    errors = Validator.validate(_sm([a, b], [t]))
    assert not any(e.rule == "transition_type_consistency" for e in errors)


# ─────────────── choice_completeness ───────────────


def test_choice_no_outgoing_errors():
    c = ChoiceState(name="decide")
    s = SimpleState(name="s")
    # initial이 s가 되도록 — choice는 도달만 가능하게
    t = Transition(source=s, target=c)
    errors = Validator.validate(_sm([s, c], [t], initial=s))
    matching = [e for e in errors if e.rule == "choice_completeness"]
    assert len(matching) == 1
    assert "막다른" in matching[0].message


def test_choice_two_unguarded_errors():
    c = ChoiceState(name="decide")
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    t1 = Transition(source=c, target=a)  # 무가드
    t2 = Transition(source=c, target=b)  # 무가드
    errors = Validator.validate(_sm([c, a, b], [t1, t2], initial=c))
    matching = [e for e in errors if e.rule == "choice_completeness"]
    assert len(matching) == 1
    assert not matching[0].is_warning


def test_choice_missing_else_warns():
    c = ChoiceState(name="decide")
    a = SimpleState(name="A")
    t = Transition(source=c, target=a, guard=_guard())  # 가드만, 무가드 없음
    errors = Validator.validate(_sm([c, a], [t], initial=c))
    matching = [e for e in errors if e.rule == "choice_completeness_missing_else"]
    assert len(matching) == 1
    assert matching[0].is_warning


def test_choice_one_guard_one_else_passes():
    c = ChoiceState(name="decide")
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    t1 = Transition(source=c, target=a, guard=_guard())  # 가드
    t2 = Transition(source=c, target=b)                  # 무가드 = else
    errors = Validator.validate(_sm([c, a, b], [t1, t2], initial=c))
    assert not any(
        e.rule in ("choice_completeness", "choice_completeness_missing_else")
        for e in errors
    )


# ─────────────── parallel_join_count ───────────────


def _region(name: str) -> Region:
    s = SimpleState(name=f"{name}_s")
    return Region(name=name, sub_machine=StateMachine(
        name=f"{name}_m", states=[s], initial_state=s))


def test_parallel_n_of_without_join_count_warns():
    p = ParallelState(name="par", regions=[_region("r1"), _region("r2")],
                      join=JoinStrategy.N_OF, join_count=None)
    errors = Validator.validate(_sm([p]))
    matching = [e for e in errors if e.rule == "parallel_join_count"]
    assert len(matching) == 1
    assert matching[0].is_warning
    assert "지정되지" in matching[0].message


def test_parallel_n_of_join_count_exceeds_regions_warns():
    p = ParallelState(name="par", regions=[_region("r1"), _region("r2")],
                      join=JoinStrategy.N_OF, join_count=5)
    errors = Validator.validate(_sm([p]))
    matching = [e for e in errors if e.rule == "parallel_join_count"]
    assert len(matching) == 1
    assert "초과" in matching[0].message


def test_parallel_n_of_valid_join_count_passes():
    p = ParallelState(name="par", regions=[_region("r1"), _region("r2")],
                      join=JoinStrategy.N_OF, join_count=1)
    errors = Validator.validate(_sm([p]))
    assert not any(e.rule == "parallel_join_count" for e in errors)


def test_parallel_all_strategy_skips_join_count_check():
    p = ParallelState(name="par", regions=[_region("r1")],
                      join=JoinStrategy.ALL, join_count=None)
    errors = Validator.validate(_sm([p]))
    assert not any(e.rule == "parallel_join_count" for e in errors)


# ─────────────── pseudo custom_events 검출 ───────────────


def test_pseudo_state_custom_events_warns():
    """의사 상태에 custom_events가 있으면 pseudo_state_hooks 경고."""
    from daedalus.model.fsm.action import Action
    from daedalus.model.fsm.strategy import LLMExecution
    c = ChoiceState(name="decide")
    c.custom_events = {"react": [Action(name="a", execution=LLMExecution())]}
    s = SimpleState(name="s")
    t = Transition(source=c, target=s)  # else 채워 choice 규칙 무관
    errors = Validator.validate(_sm([c, s], [t], initial=c))
    matching = [e for e in errors if e.rule == "pseudo_state_hooks"]
    assert any("custom_events" in e.message for e in matching)
