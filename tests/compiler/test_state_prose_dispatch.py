# tests/compiler/test_state_prose_dispatch.py
"""FSM 상태·전략·트리거 서술의 **디스패치 계약** (WP-11).

세 서술 함수는 `functools.singledispatch`다. 그 선택의 근거는 "기저 폴백이
옳다"였으므로, 폴백이 실제로 옳은지를 — 즉 **모르는 종류에서 터지지 않고
쓸 만한 문장을 낸다**는 것을 — 테스트가 고정한다. 폴백이 사라지면(예: 누군가
`raise`로 바꾸면) 구버전 프로젝트 하나가 컴파일 전체를 죽인다.

두 벌의 상태 서술이 **일부러 다르다**는 사실도 여기서 못 박는다 — 스킬 산출의
`_describe_step`과 에이전트 legacy 산출의 `_describe_legacy_step`은 같은
CompositeState에 다른 문구를 낸다(REFACTOR_SPEC §0-a: 합치면 산출 바이트가
바뀐다).
"""
from __future__ import annotations

from dataclasses import dataclass

from daedalus.compiler.emit.agent_sections import (
    _describe_legacy_step,
    _is_substantive_state,
    _legacy_extra_marks,
)
from daedalus.compiler.emit.sections import (
    _describe_evaluation,
    _describe_step,
    _describe_trigger,
    _unguarded_is_else,
)
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState, EntryPoint, ExitPoint, TerminateState
from daedalus.model.fsm.state import CompositeState, ParallelState, SimpleState, State
from daedalus.model.fsm.strategy import EvaluationStrategy, LLMEvaluation


@dataclass(eq=False)
class _UnknownState(State):
    """미래의(또는 구버전의) 상태 종류 — 폴백 대상."""

    @property
    def kind(self) -> str:
        return "unknown"


@dataclass
class _UnknownEvaluation(EvaluationStrategy):
    @property
    def kind(self) -> str:
        return "unknown"


def _machine() -> StateMachine:
    return StateMachine(name="m", initial_state=SimpleState(name="i"))


# ─────────────────────────── 폴백이 옳다 ───────────────────────────


def test_unknown_state_falls_back_to_a_bare_sentence():
    assert _describe_step(_UnknownState(name="x")) == "."
    assert _describe_legacy_step(_UnknownState(name="x")) == "."


def test_unknown_evaluation_falls_back_to_condition():
    assert _describe_evaluation(_UnknownEvaluation()) == "condition"


def test_trigger_fallback_covers_none_and_nameless():
    assert _describe_trigger(None) == ""
    assert _describe_trigger(object()) == ""


def test_unguarded_is_else_only_for_choice():
    assert _unguarded_is_else(ChoiceState(name="c")) is True
    assert _unguarded_is_else(SimpleState(name="s")) is False
    assert _unguarded_is_else(_UnknownState(name="x")) is False


# ─────────────────────────── 종류별 문구 ───────────────────────────


def test_each_state_kind_has_its_own_sentence():
    assert _describe_step(SimpleState(name="s")) == "."
    assert _describe_step(CompositeState(name="c", sub_machine=_machine())) == (
        ": delegate to agent `c` (runs in its own context)."
    )
    assert _describe_step(ParallelState(name="p")) == (
        ": run  in parallel (continue after every region finishes)."
    )
    assert "branch immediately" in _describe_step(ChoiceState(name="c"))
    assert _describe_step(TerminateState(name="t")) == ": stop the workflow here."
    assert _describe_step(EntryPoint(name="e")) == " — pseudo state (entry_point)."
    assert _describe_step(ExitPoint(name="x")) == " — pseudo state (exit_point)."


def test_evaluation_and_trigger_sentences():
    assert _describe_evaluation(LLMEvaluation(prompt="done?")) == "LLM judgment (done?)"
    assert _describe_evaluation(LLMEvaluation()) == "LLM judgment"
    assert _describe_trigger(CompletionEvent(name="done")) == "completion event `done`"


def test_legacy_agent_variant_is_deliberately_different():
    """합치면 구버전 에이전트 산출 바이트가 바뀐다 — 두 문구가 다른 것이 계약이다."""
    composite = CompositeState(name="c", sub_machine=_machine())
    assert _describe_legacy_step(composite) == ": delegate to agent `c`."
    assert _describe_step(composite) != _describe_legacy_step(composite)
    # legacy판에는 Parallel/Choice/Terminate 분기가 없다(전부 폴백).
    assert _describe_legacy_step(ParallelState(name="p")) == "."
    assert _describe_legacy_step(TerminateState(name="t")) == "."


def test_legacy_exit_mark_and_substance():
    assert _legacy_extra_marks(ExitPoint(name="x")) == ["exit"]
    assert _legacy_extra_marks(SimpleState(name="s")) == []
    assert _is_substantive_state(SimpleState(name="s")) is True
    assert _is_substantive_state(EntryPoint(name="e")) is False
    assert _is_substantive_state(ExitPoint(name="x")) is False
    assert _is_substantive_state(_UnknownState(name="u")) is True
