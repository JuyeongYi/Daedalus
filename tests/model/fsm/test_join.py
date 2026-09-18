"""JoinStrategy 정본 위치(fsm/join.py) 검증.

`plugin.policy` re-export는 RF-1b에서, `ExecutionPolicy`와 그 모듈 자체는
2026-09-19(WP-1 D8)에 퇴역했다 — 에이전트의 병렬 실행 정책은 편집 표면 0에
직렬화 왕복만 하던 잔재였다. `JoinStrategy`는 `ParallelState`가 계속 쓴다.
"""
from __future__ import annotations


def test_join_strategy_new_location():
    from daedalus.model.fsm.join import JoinStrategy
    assert JoinStrategy.ALL.value == "all"
    assert JoinStrategy.ANY.value == "any"
    assert JoinStrategy.N_OF.value == "n_of"


def test_policy_module_is_retired():
    """`model/plugin/policy.py`는 통째로 퇴역했다 (D8) — 잔재 경로가 없다."""
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("daedalus.model.plugin.policy")


def test_parallel_state_join_defaults():
    from daedalus.model.fsm.join import JoinStrategy
    from daedalus.model.fsm.state import ParallelState
    p = ParallelState(name="par")
    assert p.join is JoinStrategy.ALL
    assert p.join_count is None
