# tests/compiler/test_body.py
"""본문(sections 트리 + FSM 절차 서술) 테스트."""
from __future__ import annotations

from daedalus.compiler.emit import compile_skill
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.strategy import ExpressionEvaluation
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.config import ProceduralSkillConfig

from tests.compiler.builders import make_procedural


# ─────────────────────── sections 트리 헤딩 깊이 ───────────────────────


def test_section_heading_depth():
    skill = make_procedural(
        sections=[
            Section("Top", "root content", [
                Section("Mid", "mid content", [
                    Section("Leaf", "leaf content"),
                ]),
            ]),
        ]
    )
    text = compile_skill(skill)
    assert "# Top" in text
    assert "## Mid" in text
    assert "### Leaf" in text
    # 내용 출력
    assert "root content" in text
    assert "leaf content" in text


def test_section_empty_content_emits_heading_only():
    skill = make_procedural(sections=[Section("Heading", "")])
    text = compile_skill(skill)
    assert "# Heading" in text


# ─────────────────────── FSM 절차 서술 ───────────────────────


def test_fsm_procedure_lists_states_in_order():
    skill = make_procedural()  # analyze → report
    text = compile_skill(skill)
    assert "## 워크플로 절차" in text
    # 시작/종료 표지
    assert "**analyze** (시작)" in text
    assert "**report** (종료)" in text
    # analyze가 report보다 먼저 등장
    assert text.index("**analyze**") < text.index("**report**")


def test_fsm_procedure_shows_transition_trigger():
    skill = make_procedural()
    text = compile_skill(skill)
    assert "→ **report**" in text
    assert "완료 이벤트 'done'" in text


def test_fsm_procedure_shows_guard():
    s1 = SimpleState(name="check")
    s2 = SimpleState(name="proceed")
    sm = StateMachine(name="g", initial_state=s1, states=[s1, s2], final_states=[s2])
    sm.transitions.append(
        Transition(
            source=s1,
            target=s2,
            trigger=CompletionEvent(name="done"),
            guard=Guard(evaluation=ExpressionEvaluation(expression="x > 0")),
        )
    )
    skill = make_procedural(fsm=sm)
    text = compile_skill(skill)
    assert "가드:" in text
    assert "x > 0" in text


def test_fsm_procedure_skill_ref_uses_skill_name():
    from tests.compiler.builders import make_declarative

    helper = make_declarative("helper-kb")
    s1 = SimpleState(name="use-helper", skill_ref=helper)
    s2 = SimpleState(name="end")
    sm = StateMachine(name="r", initial_state=s1, states=[s1, s2], final_states=[s2])
    sm.transitions.append(
        Transition(source=s1, target=s2, trigger=CompletionEvent(name="done"))
    )
    skill = make_procedural(fsm=sm)
    text = compile_skill(skill)
    assert "skill 'helper-kb'" in text


def test_transfer_on_output_events_documented():
    skill = make_procedural()
    skill.transfer_on = [
        EventDef("success", description="all good"),
        EventDef("failure", description="bad"),
    ]
    text = compile_skill(skill)
    assert "## 출력 이벤트" in text
    assert "`success` — all good" in text
    assert "`failure` — bad" in text


# ─────────────────────── transition skill_ref (transfer skill) ───────────────────────


def test_transition_transfer_skill_documented():
    from tests.compiler.builders import make_transfer

    edge = make_transfer("edge-helper")
    s1 = SimpleState(name="a")
    s2 = SimpleState(name="b")
    sm = StateMachine(name="t", initial_state=s1, states=[s1, s2], final_states=[s2])
    sm.transitions.append(
        Transition(
            source=s1, target=s2, trigger=CompletionEvent(name="done"), skill_ref=edge
        )
    )
    skill = make_procedural(fsm=sm)
    text = compile_skill(skill)
    assert "skill 'edge-helper'" in text


# ─────────────────────── 불완전 FSM 방어 가드 ───────────────────────


def test_incomplete_fsm_direct_compile_does_not_crash():
    """initial_state=None / states 비어 있는 FSM도 compile_skill/compile_agent
    직접 호출이 AttributeError 없이 동작한다 (게이트 비경유 경로 보호)."""
    from daedalus.compiler.emit import compile_agent
    from daedalus.model.plugin.agent import AgentDefinition

    empty = StateMachine(name="empty", initial_state=None, states=[])  # type: ignore[arg-type]
    skill = make_procedural(fsm=empty)
    text = compile_skill(skill)
    assert "## 워크플로 절차" not in text  # 절차 단락 생략
    assert "## 출력 이벤트" in text       # 출력 이벤트는 유지

    agent = AgentDefinition(fsm=empty, name="a1", description="d")
    atext = compile_agent(agent)
    assert "## 내부 워크플로" not in atext
