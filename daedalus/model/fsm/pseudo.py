from __future__ import annotations

from dataclasses import dataclass

from daedalus.model.fsm.state import State

#: 의사 상태의 `kind` 값 — **선언이 한 곳**이어야 종류를 묻는 쪽(캔버스 스타일·
#: 프로젝트 캔버스 제외 규칙)이 문자열을 손으로 베끼지 않는다. 종전에는 그 질문을
#: 전부 `isinstance(s, EntryPoint)`로 했는데, 그러면 뷰·직렬화가 모델 클래스를
#: 직접 수입하고 새 의사 상태마다 사다리가 한 칸씩 길어진다(WP-11).
ENTRY_POINT_KIND = "entry_point"
EXIT_POINT_KIND = "exit_point"


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
    """프로젝트 그래프의 시작 표지 / 에이전트 잔존 FSM의 루트 자리표(WP-EP/WP-AF)."""

    @property
    def kind(self) -> str:
        return ENTRY_POINT_KIND


@dataclass(eq=False)
class ExitPoint(State):
    """v1 에이전트 출력 포트의 잔존 표지 — 현행은 `AgentDefinition.transfer_on`."""
    color: str = "#cc6666"

    @property
    def kind(self) -> str:
        return EXIT_POINT_KIND
