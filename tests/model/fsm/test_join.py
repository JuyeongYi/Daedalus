"""WP-M ③ JoinStrategy 위치 이동 + 하위 호환 re-export 검증."""
from __future__ import annotations


def test_join_strategy_new_location():
    from daedalus.model.fsm.join import JoinStrategy
    assert JoinStrategy.ALL.value == "all"
    assert JoinStrategy.ANY.value == "any"
    assert JoinStrategy.N_OF.value == "n_of"


def test_join_strategy_reexport_backward_compat():
    """기존 import 경로(plugin.policy)가 새 위치 심볼과 동일 객체다."""
    from daedalus.model.fsm.join import JoinStrategy as New
    from daedalus.model.plugin.policy import JoinStrategy as Old
    assert New is Old


def test_execution_policy_uses_reexported_join():
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
