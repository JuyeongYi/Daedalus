"""JoinStrategy 정본 위치(fsm/join.py) 검증 — plugin.policy re-export는 RF-1b에서 삭제."""
from __future__ import annotations


def test_join_strategy_new_location():
    from daedalus.model.fsm.join import JoinStrategy
    assert JoinStrategy.ALL.value == "all"
    assert JoinStrategy.ANY.value == "any"
    assert JoinStrategy.N_OF.value == "n_of"


def test_join_strategy_not_reexported_from_policy():
    """RF-1b — 별칭 경로는 없다. __all__에 ExecutionPolicy만 남는다."""
    from daedalus.model.plugin import policy
    assert policy.__all__ == ["ExecutionPolicy"]


def test_execution_policy_uses_fsm_join():
    from daedalus.model.fsm.join import JoinStrategy
    from daedalus.model.plugin.policy import ExecutionPolicy
    p = ExecutionPolicy(join=JoinStrategy.N_OF, join_count=2)
    assert p.join is JoinStrategy.N_OF
    assert p.join_count == 2


def test_parallel_state_join_defaults():
    from daedalus.model.fsm.join import JoinStrategy
    from daedalus.model.fsm.state import ParallelState
    p = ParallelState(name="par")
    assert p.join is JoinStrategy.ALL
    assert p.join_count is None
