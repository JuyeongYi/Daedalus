"""WP-Q: 프로젝트 그래프 백킹(PluginProject.graph) — 직렬화/검증/컴파일."""
import json

from daedalus.model.fsm.event import CompletionEvent
from daedalus.model.fsm.guard import Guard
from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint, ExitPoint
from daedalus.model.fsm.section import EventDef
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.strategy import LLMEvaluation
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.agent import AgentDefinition
from daedalus.model.plugin.skill import ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.serialize import deserialize_project, serialize_project
from daedalus.model.validation import Validator
from daedalus.compiler.emit import compile_agent, compile_skill


# ─────────────────────── 빌더 ───────────────────────


def _mk_skill_fsm(name: str) -> StateMachine:
    s = SimpleState(name="start")
    return StateMachine(name=f"{name}_fsm", states=[s], initial_state=s)


def _mk_agent_fsm(name: str) -> StateMachine:
    e = EntryPoint(name="entry")
    x = ExitPoint(name="done")
    return StateMachine(
        name=f"{name}_fsm", states=[e, x], initial_state=e, final_states=[x]
    )


def _mk_proc(name: str) -> ProceduralSkill:
    return ProceduralSkill(
        fsm=_mk_skill_fsm(name), name=name, description=f"{name}.",
        transfer_on=[EventDef(name="done")],
    )


# ─────────────────────── 기본 ───────────────────────


def test_default_graph_has_entry_point():
    p = PluginProject(name="p")
    assert isinstance(p.graph, StateMachine)
    assert p.graph.initial_state.name == "start"
    assert isinstance(p.graph.initial_state, EntryPoint)
    assert p.graph.initial_state in p.graph.states


def test_graph_blackboard_parent_wired_on_construction():
    p = PluginProject(name="p")
    assert p.graph.blackboard.parent is p.blackboard


# ─────────────────────── 직렬화 왕복 (버그 1) ───────────────────────


def test_graph_roundtrip_states_transitions_layout():
    a = _mk_proc("a")
    b = _mk_proc("b")
    p = PluginProject(name="proj", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    p.graph.states += [sa, sb]
    t = Transition(source=sa, target=sb, trigger=CompletionEvent(name="done"))
    p.graph.transitions.append(t)
    p.graph_layout[sa.id] = [10.0, 20.0]
    p.graph_layout[sb.id] = [30.0, 40.0]

    p2 = deserialize_project(json.loads(json.dumps(serialize_project(p))))

    # 상태 수(EntryPoint + 2 placement)
    assert len(p2.graph.states) == 3
    names = {s.name for s in p2.graph.states}
    assert names == {"start", "a", "b"}
    # 전이 endpoint 복원
    assert len(p2.graph.transitions) == 1
    tr = p2.graph.transitions[0]
    assert tr.source.name == "a" and tr.target.name == "b"
    # skill_ref 2-pass 해소 — 역직렬화된 컴포넌트를 가리킨다
    sa2 = next(s for s in p2.graph.states if s.name == "a")
    a2 = next(s for s in p2.skills if s.name == "a")
    assert sa2.skill_ref is a2
    # graph_layout 좌표 보존
    assert p2.graph_layout[sa2.id] == [10.0, 20.0]


def test_graph_blackboard_parent_reconnected_on_deserialize():
    p = PluginProject(name="proj")
    p2 = deserialize_project(json.loads(json.dumps(serialize_project(p))))
    assert p2.graph.blackboard.parent is p2.blackboard


def test_old_version_without_graph_key_no_warnings():
    """구버전 dict(graph 키 없음) → 빈 그래프 + 경고 없음 (하위 호환)."""
    data = {"format": 1, "name": "old", "skills": [], "agents": []}
    warns: list[str] = []
    p = deserialize_project(data, collect_warnings=warns)
    assert warns == []
    assert p.graph.initial_state.name == "start"
    assert len(p.graph.states) == 1
    assert p.graph_layout == {}
    assert p.graph.blackboard.parent is p.blackboard


# ─────────────────────── 검증 ───────────────────────


def test_empty_graph_validation_skipped():
    """placement 0개(EntryPoint 하나뿐)면 그래프 머신 검증 스킵."""
    p = PluginProject(name="proj")
    errors = Validator.validate_project(p)
    # project path로 발급된 그래프 오류가 없어야 한다
    assert not [e for e in errors if e.path and e.path[0] == "project"]


def test_graph_with_placement_validated_with_project_path():
    """placement가 있으면 머신 규칙이 path=('project',)로 적용된다."""
    a = _mk_proc("a")
    p = PluginProject(name="proj", skills=[a])
    sa = SimpleState(name="a", skill_ref=a)
    p.graph.states.append(sa)
    # 도달 불가 상태를 만들어 unreachable_state 경고 유도 (EntryPoint→a 전이 없음)
    errors = Validator.validate_project(p)
    project_errors = [e for e in errors if e.path and e.path[0] == "project"]
    assert project_errors, "placement 있는 그래프는 머신 규칙이 적용되어야 한다"
    assert any(e.rule == "unreachable_state" for e in project_errors)


# ─────────────────────── 컴파일: 다음 단계 (버그 2) ───────────────────────


def test_compile_next_steps_skill_invoke():
    a = _mk_proc("a")
    b = _mk_proc("b")
    p = PluginProject(name="proj", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    p.graph.states += [sa, sb]
    p.graph.transitions.append(Transition(
        source=sa, target=sb, trigger=CompletionEvent(name="done"),
        guard=Guard(evaluation=LLMEvaluation(prompt="B 필요시")),
    ))
    txt = compile_skill(a, project=p)
    assert "## 다음 단계" in txt
    assert "`b` 스킬을 인보크하라" in txt
    # 가드 조건이 표기된다
    assert "B 필요시" in txt


def test_compile_next_steps_agent_inline_chain():
    """A → 에이전트 W → C 체인 — A의 SKILL.md에 위임 + 후속 인라인."""
    a = _mk_proc("a")
    c = _mk_proc("c")
    w = AgentDefinition(fsm=_mk_agent_fsm("w"), name="w", description="W.")
    p = PluginProject(name="proj", skills=[a, c], agents=[w])
    sa = SimpleState(name="a", skill_ref=a)
    sw = SimpleState(name="w", skill_ref=w)
    sc = SimpleState(name="c", skill_ref=c)
    p.graph.states += [sa, sw, sc]
    p.graph.transitions.append(Transition(
        source=sa, target=sw, trigger=CompletionEvent(name="done")))
    p.graph.transitions.append(Transition(
        source=sw, target=sc, trigger=CompletionEvent(name="done")))

    txt = compile_skill(a, project=p)
    assert "## 다음 단계" in txt
    assert "에이전트 `w`에게 위임하라" in txt
    assert "위임 완료 후" in txt
    assert "`c` 스킬을 인보크하라" in txt


def test_compile_no_next_steps_when_no_outgoing():
    a = _mk_proc("a")
    p = PluginProject(name="proj", skills=[a])
    sa = SimpleState(name="a", skill_ref=a)
    p.graph.states.append(sa)
    txt = compile_skill(a, project=p)
    assert "## 다음 단계" not in txt


def test_agent_md_has_no_next_steps():
    """에이전트 .md에는 다음 단계 단락을 넣지 않는다."""
    c = _mk_proc("c")
    w = AgentDefinition(fsm=_mk_agent_fsm("w"), name="w", description="W.")
    p = PluginProject(name="proj", skills=[c], agents=[w])
    sw = SimpleState(name="w", skill_ref=w)
    sc = SimpleState(name="c", skill_ref=c)
    p.graph.states += [sw, sc]
    p.graph.transitions.append(Transition(
        source=sw, target=sc, trigger=CompletionEvent(name="done")))
    txt = compile_agent(w, project=p)
    assert "## 다음 단계" not in txt


def test_compile_next_steps_unguarded_with_trigger_shows_trigger():
    """무가드(완료 트리거만) 전이는 트리거 조건을 표기한다."""
    a = _mk_proc("a")
    b = _mk_proc("b")
    p = PluginProject(name="proj", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    p.graph.states += [sa, sb]
    p.graph.transitions.append(Transition(
        source=sa, target=sb, trigger=CompletionEvent(name="done")))
    txt = compile_skill(a, project=p)
    section = txt[txt.index("## 다음 단계"):]
    assert "완료 이벤트 'done'" in section
    assert "`b` 스킬을 인보크하라" in section


def test_compile_next_steps_no_trigger_no_guard_unconditional():
    """트리거·가드 모두 없는 전이는 '무조건' 표기."""
    a = _mk_proc("a")
    b = _mk_proc("b")
    p = PluginProject(name="proj", skills=[a, b])
    sa = SimpleState(name="a", skill_ref=a)
    sb = SimpleState(name="b", skill_ref=b)
    p.graph.states += [sa, sb]
    p.graph.transitions.append(Transition(source=sa, target=sb, trigger=None))
    txt = compile_skill(a, project=p)
    assert "무조건" in txt[txt.index("## 다음 단계"):]
