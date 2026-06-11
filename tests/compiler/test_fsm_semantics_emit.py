"""WP-M 컴파일러 절차 서술 — ChoiceState else / ParallelState join 골든."""
from __future__ import annotations

from daedalus.compiler.emit import compile_skill
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.join import JoinStrategy
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import ChoiceState
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import ParallelState, Region, SimpleState
from daedalus.model.fsm.strategy import ExpressionEvaluation
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import ProceduralSkillConfig
from daedalus.model.plugin.skill import ProceduralSkill


def _proc(fsm: StateMachine) -> ProceduralSkill:
    return ProceduralSkill(
        fsm=fsm, name="my-skill", description="d", when_to_use="x",
        config=ProceduralSkillConfig(),
        sections=[Section("Instructions", "Do it.")],
        transfer_on=[EventDef("done")],
    )


def test_choice_else_branch_in_procedure():
    """ChoiceState 무가드 전이가 [else]로 서술된다."""
    decide = ChoiceState(name="decide")
    a = SimpleState(name="A")
    b = SimpleState(name="B")
    end = SimpleState(name="end")
    g = Guard(evaluation=ExpressionEvaluation(expression="x == 1"))
    fsm = StateMachine(
        name="m", initial_state=decide, states=[decide, a, b, end],
        final_states=[end],
        transitions=[
            Transition(source=decide, target=a, guard=g),     # 가드
            Transition(source=decide, target=b),              # 무가드 = else
            Transition(source=a, target=end, trigger=CompletionEvent(name="done")),
            Transition(source=b, target=end, trigger=CompletionEvent(name="done")),
        ],
    )
    text = compile_skill(_proc(fsm))
    # 가드 전이는 조건 표시, 무가드 전이는 [else]
    assert "→ **B** [else]" in text
    assert "→ **A** [가드: 표현식 `x == 1`]" in text


def test_parallel_join_all_description():
    inner = SimpleState(name="I")
    inner_m = StateMachine(name="im", initial_state=inner, states=[inner])
    par = ParallelState(name="par", regions=[Region(name="r1", sub_machine=inner_m)])
    end = SimpleState(name="end")
    fsm = StateMachine(
        name="m", initial_state=par, states=[par, end], final_states=[end],
        transitions=[Transition(source=par, target=end,
                                trigger=CompletionEvent(name="done"))],
    )
    text = compile_skill(_proc(fsm))
    assert "모든 리전 완료 후 종합" in text


def test_parallel_join_n_of_description():
    inner = SimpleState(name="I")
    inner_m = StateMachine(name="im", initial_state=inner, states=[inner])
    par = ParallelState(
        name="par",
        regions=[Region(name="r1", sub_machine=inner_m),
                 Region(name="r2", sub_machine=StateMachine(
                     name="im2", initial_state=SimpleState(name="J"),
                     states=[SimpleState(name="J")]))],
        join=JoinStrategy.N_OF, join_count=1,
    )
    end = SimpleState(name="end")
    fsm = StateMachine(
        name="m", initial_state=par, states=[par, end], final_states=[end],
        transitions=[Transition(source=par, target=end,
                                trigger=CompletionEvent(name="done"))],
    )
    text = compile_skill(_proc(fsm))
    assert "리전 1개가 완료하면 다음으로 진행" in text
