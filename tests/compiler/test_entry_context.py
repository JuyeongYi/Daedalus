# tests/compiler/test_entry_context.py
"""WP-IC Part C: "## 진입 맥락" 단락 + prev 규약 + "## 호출 계약" 그래프 유도.

단일 진실: docs/plans/2026-08-02-wp-ic-input-ports-entry-context.md Part C.
"""
from __future__ import annotations

from daedalus.compiler.emit import (
    _PROGRESS_UPDATE_NOTE,
    compile_agent,
    compile_skill,
)
from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.project import PluginProject

from tests.compiler.builders import (
    make_agent,
    make_declarative,
    make_procedural,
    make_transfer,
)


# ── 1) 기본 배치: 진입 맥락 단락 위치·기본 경로 그룹 ──


def test_entry_context_section_basic_default_port():
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(b, project=project)
    assert "## 진입 맥락" in text
    assert "`state/__progress__.json`의 `prev`" in text
    # WP-IP — 포트 그룹 헤딩은 퇴역, 출처 항목만 나열된다
    assert "### 기본 경로" not in text
    assert "- `a`에서 [완료 이벤트 'done']로 진입" in text


def test_entry_context_position_after_preamble_before_body():
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(b, project=project)
    preamble_idx = text.index("## 작업 재개")
    entry_idx = text.index("## 진입 맥락")
    body_idx = text.index("Do the work.")
    assert preamble_idx < entry_idx < body_idx


def test_entry_context_omitted_when_no_incoming():
    """기존(하위 호환): incoming 0개 배치는 진입 맥락 단락이 없다."""
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])
    sa = SimpleState(name="a", skill_ref=a)
    project.graph.states += [sa]
    text = compile_skill(a, project=project)
    assert "## 진입 맥락" not in text


def test_entry_context_omitted_when_unplaced():
    a = make_procedural(name="a")
    project = PluginProject(name="p", skills=[a])  # 미배치
    text = compile_skill(a, project=project)
    assert "## 진입 맥락" not in text


def test_entry_context_declarative_skill_also_gets_section():
    """배치된 DeclarativeSkill도 진입 맥락을 받는다(WP-RS 프리앰블과 동일한 포함 이유)."""
    a = make_procedural(name="a")
    d = make_declarative(name="know")
    project = PluginProject(name="p", skills=[a, d])
    sa = SimpleState(name="a", skill_ref=a)
    sd = SimpleState(name="know", skill_ref=d)
    project.graph.states += [sa, sd]
    project.graph.transitions.append(
        Transition(source=sa, target=sd, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(d, project=project)
    assert "## 진입 맥락" in text


# ── 2) 포트 그룹 없음 (WP-IP — 입력 포트 개념 자체가 없다) ──


def test_entry_context_has_no_port_group_headings():
    """WP-IP — 도착 노드는 입력 포트를 선언하지 않으므로 포트 그룹 헤딩 없이
    출처 항목만 나열된다."""
    a = make_procedural(name="a")
    t = make_procedural(name="t")
    project = PluginProject(name="p", skills=[a, t])
    sa = SimpleState(name="a", skill_ref=a)
    st = SimpleState(name="t", skill_ref=t)
    project.graph.states += [sa, st]
    project.graph.transitions.append(
        Transition(source=sa, target=st, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(t, project=project)
    assert "### 경로:" not in text
    assert "### 기본 경로" not in text
    assert "- `a`에서 [완료 이벤트 'done']로 진입" in text


def test_entry_context_carries_caller_output_description():
    """호출 시 정보가 담긴다(WP-IP) — 출처가 자기 출력 포트에 적은 description이
    도착 스킬의 진입 맥락 항목에 병기된다."""
    a = make_procedural(name="a")
    a.transfer_on = [EventDef("done", description="초안 완성 — 배선은 비어 있다")]
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(b, project=project)
    assert "- `a`에서 [완료 이벤트 'done']로 진입 — 초안 완성 — 배선은 비어 있다" in text


def test_next_steps_carry_caller_output_description():
    """호출자 쪽 "다음 단계"에도 갈래의 의미(출력 포트 description)가 실린다."""
    a = make_procedural(name="a")
    a.transfer_on = [EventDef("done", description="초안 완성")]
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(a, project=project)
    assert "→ `b` 스킬을 인보크하라 — 초안 완성" in text


def test_progress_note_records_branch():
    """진행 규약이 어느 갈래로 넘어갔는지 note에 남기도록 지시한다(WP-IP)."""
    assert "어느 갈래" in _PROGRESS_UPDATE_NOTE


# ── 3) 출처 항목: 정렬 + TransferSkill 합류 + 에이전트 출처 문구 ──


def test_entry_context_sources_sorted_by_name():
    z = make_procedural(name="zsrc")
    a = make_procedural(name="asrc")
    t = make_procedural(name="tgt")
    project = PluginProject(name="p", skills=[z, a, t])
    sz = SimpleState(name="zsrc", skill_ref=z)
    sa = SimpleState(name="asrc", skill_ref=a)
    st = SimpleState(name="tgt", skill_ref=t)
    project.graph.states += [sz, sa, st]
    project.graph.transitions += [
        Transition(source=sz, target=st, trigger=CompletionEvent(name="done")),
        Transition(source=sa, target=st, trigger=CompletionEvent(name="done")),
    ]
    text = compile_skill(t, project=project)
    idx_a = text.index("`asrc`에서")
    idx_z = text.index("`zsrc`에서")
    assert idx_a < idx_z


def test_entry_context_includes_transfer_skill_note():
    a = make_procedural(name="a")
    t = make_procedural(name="t")
    edge = make_transfer("edge-skill")
    edge.description = "인계 정리"
    project = PluginProject(name="p", skills=[a, t, edge])
    sa = SimpleState(name="a", skill_ref=a)
    st = SimpleState(name="t", skill_ref=t)
    project.graph.states += [sa, st]
    project.graph.transitions.append(
        Transition(
            source=sa, target=st, trigger=CompletionEvent(name="done"),
            skill_ref=edge,
        )
    )
    text = compile_skill(t, project=project)
    assert "전이 스킬 `edge-skill`(`인계 정리`)의 지침을 수행한 상태다" in text


def test_entry_context_agent_source_phrase():
    agent = make_agent("worker")
    t = make_procedural(name="t")
    project = PluginProject(name="p", skills=[t], agents=[agent])
    s_agent = SimpleState(name="worker", skill_ref=agent)
    st = SimpleState(name="t", skill_ref=t)
    project.graph.states += [s_agent, st]
    project.graph.transitions.append(
        Transition(source=s_agent, target=st, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(t, project=project)
    assert "에이전트 `worker`의 위임 완료 후" in text


# ── 4) prev 규약 ──


def test_progress_update_note_mentions_prev():
    assert "`prev`" in _PROGRESS_UPDATE_NOTE
    assert "이 스킬 이름" in _PROGRESS_UPDATE_NOTE


def test_resume_preamble_json_example_includes_prev():
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    project = PluginProject(name="p", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    project.graph.states += [sa, sb]
    project.graph.transitions.append(
        Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    )
    text = compile_skill(a, project=project)
    assert '"prev": ""' in text


# ── 5) 호출 계약 — 그래프에서만 유도 (WP-CT — 수동 카드 개념 없음) ──


def test_call_contract_absent_without_project_graph():
    """WP-CT — 호출 계약은 프로젝트 그래프의 incoming 호출 전이에서만 유도된다.
    그래프 없이(단독 컴파일) 에이전트에는 단락이 나오지 않는다(유도 산출은
    tests/mcp/test_mcp_tools.py가 검증)."""
    entry = EntryPoint(name="entry")
    fsm = StateMachine(name="f", states=[entry], initial_state=entry)
    agent = AgentDefinition(
        fsm=fsm, name="worker", description="워커", body="Do stuff.",
        transfer_on=[EventDef("done")],
    )
    text = compile_agent(agent)
    assert "## 호출 계약" not in text


def test_agent_origin_mentions_delegator_for_prev_matching():
    """에이전트 출처 항목에 위임 시작 스킬을 병기 + 도입부에 복귀 안내 (리뷰 지적 f —
    규약상 prev에는 에이전트가 아니라 위임 스킬 이름이 남으므로 병기 없이는
    prev로 항목을 특정할 수 없다)."""
    from daedalus.model.fsm.event import CompletionEvent
    from daedalus.model.fsm.machine import StateMachine
    from daedalus.model.fsm.state import SimpleState
    from daedalus.model.fsm.transition import Transition
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.project import PluginProject
    from daedalus.compiler.emit import compile_skill

    def _proc(name):
        s = SimpleState(name="s")
        fsm = StateMachine(name=f"{name}_f", initial_state=s, states=[s], final_states=[s])
        from daedalus.model.plugin.skill import ProceduralSkill
        return ProceduralSkill(fsm=fsm, name=name, description="d")

    beta = _proc("beta")
    a_s = SimpleState(name="a")
    worker = AgentDefinition(
        fsm=StateMachine(name="af", initial_state=a_s, states=[a_s], final_states=[a_s]),
        name="worker", description="d")
    project = PluginProject(name="p", skills=[beta], agents=[worker])
    pb = SimpleState(name="beta", skill_ref=beta)
    pw = SimpleState(name="worker", skill_ref=worker)
    project.graph.states.extend([pb, pw])
    project.graph.transitions.extend([
        Transition(source=pb, target=pw, trigger=CompletionEvent(name="needs-work")),
        Transition(source=pw, target=pb, trigger=CompletionEvent(name="done")),
    ])

    text = compile_skill(beta, project=project)
    assert "에이전트 위임에서 복귀한 경우" in text
    assert "위임을 시작한 스킬 — `beta`" in text
