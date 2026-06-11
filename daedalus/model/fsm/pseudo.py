from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.state import State


@dataclass(eq=False)
class ChoiceState(State):
    """즉시 평가 후 분기. 머무르지 않음.

    else 관례 (의미론 정본):
      ChoiceState의 outgoing 전이 중 **무가드 전이(guard is None)가 else 분기**다.
      가드가 있는 전이들을 선언 순서로 평가하고, 어느 가드도 통과하지 못하면
      유일한 무가드 전이로 진행한다.

    완전성은 ``choice_completeness`` 규칙이 강제한다:
      - outgoing 0개 → 에러
      - 무가드 outgoing 2개 이상 → 에러 (else 중복, 비결정)
      - 무가드 0개 → 경고 (else 부재, LLM 해석 결정성 저하)
    """

    @property
    def kind(self) -> str:
        return "choice"


@dataclass(eq=False)
class TerminateState(State):
    """FSM 강제 종료."""

    @property
    def kind(self) -> str:
        return "terminate"


@dataclass(eq=False)
class EntryPoint(State):
    """CompositeState의 특정 하위 상태로 직접 진입."""

    @property
    def kind(self) -> str:
        return "entry_point"


@dataclass(eq=False)
class ExitPoint(State):
    """CompositeState에서 특정 경로로 탈출."""
    color: str = "#cc6666"

    @property
    def kind(self) -> str:
        return "exit_point"
