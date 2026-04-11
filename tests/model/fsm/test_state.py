from __future__ import annotations

import pytest
from daedalus.model.fsm.state import (
    State,
    SimpleState,
    CompositeState,
    ParallelState,
    Region,
)
from daedalus.model.fsm.action import Action
from daedalus.model.fsm.strategy import LLMExecution
from daedalus.model.fsm.variable import Variable, VariableScope


def test_state_is_abstract():
    with pytest.raises(TypeError):
        State(name="s")


def test_simple_state():
    s = SimpleState(name="idle")
    assert s.name == "idle"
    assert s.on_entry == []
    assert s.on_exit == []
    assert s.inputs == []
    assert s.outputs == []
    assert s.custom_events == {}


def test_simple_state_with_actions():
    action = Action(name="greet", execution=LLMExecution(prompt="인사"))
    s = SimpleState(
        name="greeting",
        on_entry=[action],
    )
    assert len(s.on_entry) == 1
    assert s.on_entry[0].name == "greet"


def test_simple_state_with_io():
    inp = Variable(name="data", description="입력")
    out = Variable(name="result", description="출력", scope=VariableScope.BLACKBOARD)
    s = SimpleState(name="process", inputs=[inp], outputs=[out])
    assert len(s.inputs) == 1
    assert len(s.outputs) == 1
    assert s.outputs[0].scope == VariableScope.BLACKBOARD


def test_composite_state():
    child1 = SimpleState(name="s1")
    child2 = SimpleState(name="s2")
    cs = CompositeState(
        name="agent_x",
        children=[child1, child2],
        initial_state=child1,
        final_states=[child2],
    )
    assert cs.name == "agent_x"
    assert len(cs.children) == 2
    assert cs.initial_state is child1
    assert cs.final_states == [child2]
    assert cs.on_child_enter == []
    assert cs.on_child_exit == []


def test_region():
    s1 = SimpleState(name="r1_s1")
    r = Region(name="region_1", states=[s1], initial_state=s1)
    assert r.name == "region_1"
    assert r.initial_state is s1


def test_parallel_state():
    s1 = SimpleState(name="a")
    s2 = SimpleState(name="b")
    r1 = Region(name="r1", states=[s1], initial_state=s1)
    r2 = Region(name="r2", states=[s2], initial_state=s2)
    ps = ParallelState(name="parallel", regions=[r1, r2])
    assert len(ps.regions) == 2
