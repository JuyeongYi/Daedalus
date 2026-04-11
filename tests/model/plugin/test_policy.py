from __future__ import annotations

from daedalus.model.plugin.policy import ExecutionPolicy, JoinStrategy


def test_join_strategy():
    assert JoinStrategy.ALL.value == "all"
    assert JoinStrategy.ANY.value == "any"
    assert JoinStrategy.N_OF.value == "n_of"


def test_execution_policy_defaults():
    p = ExecutionPolicy()
    assert p.mode == "fixed"
    assert p.count == 1
    assert p.join == JoinStrategy.ALL
    assert p.join_count is None


def test_execution_policy_parallel():
    p = ExecutionPolicy(mode="fixed", count=3, join=JoinStrategy.N_OF, join_count=2)
    assert p.count == 3
    assert p.join == JoinStrategy.N_OF
    assert p.join_count == 2


def test_execution_policy_dynamic():
    p = ExecutionPolicy(mode="dynamic")
    assert p.mode == "dynamic"
