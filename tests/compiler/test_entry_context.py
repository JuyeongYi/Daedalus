# tests/compiler/test_entry_context.py
"""WP-IC Part C: "## 진입 맥락" 단락 + prev 규약 + caller_contracts 배출.

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
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef, Section
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
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
    assert "`state/__progress__.json`의 `prev`를 확인하고" in text
    assert "### 기본 경로" in text
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


# ── 2) 포트 그룹 (entry_paths) ──


def _dual_port_target(name: str = "target") -> ProceduralSkill:
    from tests.compiler.builders import make_linear_fsm
    return ProceduralSkill(
        fsm=make_linear_fsm(name),
        name=name,
        description="Target skill",
        entry_paths=[
            EventDef("main", description="일반 진입"),
            EventDef("retry", description="재시도 진입"),
        ],
    )


def test_entry_context_named_port_group_with_description():
    a = make_procedural(name="a")
    t = _dual_port_target("t")
    project = PluginProject(name="p", skills=[a, t])
    sa = SimpleState(name="a", skill_ref=a)
    st = SimpleState(name="t", skill_ref=t)
    project.graph.states += [sa, st]
    project.graph.transitions.append(
        Transition(
            source=sa, target=st, trigger=CompletionEvent(name="done"),
            target_port="retry",
        )
    )
    text = compile_skill(t, project=project)
    assert "### 경로: retry" in text
    assert "재시도 진입" in text
    assert "### 기본 경로" not in text  # main 포트로 들어오는 전이가 없으므로 생략 X, 기본경로만 없음


def test_entry_context_only_incoming_ports_emitted():
    """incoming이 있는 포트만 배출 — main 포트에 incoming 없으면 생략."""
    a = make_procedural(name="a")
    t = _dual_port_target("t2")
    project = PluginProject(name="p", skills=[a, t])
    sa = SimpleState(name="a", skill_ref=a)
    st = SimpleState(name="t2", skill_ref=t)
    project.graph.states += [sa, st]
    project.graph.transitions.append(
        Transition(
            source=sa, target=st, trigger=CompletionEvent(name="done"),
            target_port="retry",
        )
    )
    text = compile_skill(t, project=project)
    assert "### 경로: main" not in text
    assert "### 경로: retry" in text


def test_entry_context_dangling_target_port_falls_back_to_default_group():
    """entry_paths에 없는 target_port 이름은 기본 경로 그룹으로 수렴한다."""
    a = make_procedural(name="a")
    t = _dual_port_target("t3")
    project = PluginProject(name="p", skills=[a, t])
    sa = SimpleState(name="a", skill_ref=a)
    st = SimpleState(name="t3", skill_ref=t)
    project.graph.states += [sa, st]
    project.graph.transitions.append(
        Transition(
            source=sa, target=st, trigger=CompletionEvent(name="done"),
            target_port="renamed-away",  # entry_paths에 없는 이름(rename 고아)
        )
    )
    text = compile_skill(t, project=project)
    assert "### 기본 경로" in text
    assert "### 경로: renamed-away" not in text


def test_entry_context_port_order_matches_entry_paths_declaration_with_default_last():
    """포트 순서는 entry_paths 선언 순서, 기본 경로는 항상 마지막."""
    a = make_procedural(name="a")
    b = make_procedural(name="b")
    t = _dual_port_target("t4")
    project = PluginProject(name="p", skills=[a, b, t])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    st = SimpleState(name="t4", skill_ref=t)
    project.graph.states += [sa, sb, st]
    # 기본 경로 전이를 먼저 추가하고, main/retry는 나중에 추가해도 순서는
    # entry_paths 선언(main, retry) 뒤 기본 경로가 마지막이어야 한다.
    project.graph.transitions += [
        Transition(source=sa, target=st, trigger=CompletionEvent(name="done"), target_port=""),
        Transition(source=sb, target=st, trigger=CompletionEvent(name="done"), target_port="main"),
    ]
    text = compile_skill(t, project=project)
    idx_main = text.index("### 경로: main")
    idx_default = text.index("### 기본 경로")
    assert idx_main < idx_default


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


# ── 5) caller_contracts 배출 ──


def _make_agent_with_contracts(contracts: list[Section]) -> AgentDefinition:
    entry = EntryPoint(name="entry")
    done = ExitPoint(name="done")
    fsm = StateMachine(
        name="f", states=[entry, done], initial_state=entry, final_states=[done],
    )
    agent = AgentDefinition(fsm=fsm, name="worker", description="워커", body="Do stuff.")
    agent.caller_contracts = contracts
    return agent


def test_legacy_manual_contract_cards_no_longer_emitted():
    """WP-CT — 수동 계약 카드는 산출에 반영되지 않는다. 같은 사실의 소스가
    둘(호출자 포트 + 수동 카드)이면 반드시 어긋난다 — 호출 계약은 그래프에서
    유도한다(유도 산출은 tests/mcp/test_mcp_tools.py가 검증)."""
    agent = _make_agent_with_contracts([
        Section(title="caller: a (done)", content="A가 기대하는 입력"),
    ])
    text = compile_agent(agent)
    assert "## 호출 계약" not in text
    assert "A가 기대하는 입력" not in text


def test_caller_contracts_section_omitted_when_empty():
    agent = _make_agent_with_contracts([])
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
