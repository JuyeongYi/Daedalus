from __future__ import annotations

from enum import Enum

__all__ = ["JoinStrategy"]


class JoinStrategy(Enum):
    """ParallelState의 조인(완료 종합) 전략.

    순수 FSM 개념이므로 ``model/fsm/``에 둔다.

      - ALL: 모든 Region(또는 모든 인스턴스) 완료 시 join.
      - ANY: 하나라도 완료하면 join (나머지는 취소/방치).
      - N_OF: ``join_count``개가 완료하면 join (count형 — join_count 필수).
    """
    ALL = "all"
    ANY = "any"
    N_OF = "n_of"
