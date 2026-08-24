"""mid_chain_user_invocable — 진입점 아닌 배치의 user-invocable 경고 (A3).

원칙(사용자 확정): user-invocable은 진입점으로 기능할 노드만 true여야 한다.
중간 노드로 사용자가 맥락 없이 진입하면 앞 단계가 채워 놓은 전제가 통째로
비어 있다. false여도 모델 인보크는 되므로 체인은 끊기지 않는다.
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.model.plugin.skill import DeclarativeSkill, ProceduralSkill
from daedalus.model.project import PluginProject
from daedalus.model.validation import Validator

_RULE = "mid_chain_user_invocable"


def _skill(name: str, user_invocable: bool = True) -> ProceduralSkill:
    s = SimpleState(name="start")
    fsm = StateMachine(name=f"{name}-fsm", initial_state=s, states=[s], final_states=[s])
    skill = ProceduralSkill(fsm=fsm, name=name, description="d")
    skill.config.user_invocable = user_invocable
    return skill


def _chain(*skills, connect: bool = True) -> PluginProject:
    """스킬들을 프로젝트 그래프에 일렬로 배치한다 (a → b → c)."""
    project = PluginProject(name="p", skills=list(skills))
    graph = project.graph
    nodes = []
    for skill in skills:
        node = SimpleState(name=skill.name, skill_ref=skill)
        graph.states.append(node)
        nodes.append(node)
    if connect:
        for src, tgt in zip(nodes, nodes[1:]):
            graph.transitions.append(Transition(source=src, target=tgt))
    return project


def _sources(project) -> list[str]:
    return [e.source for e in Validator.validate_project(project) if e.rule == _RULE]


def test_mid_chain_placement_warns():
    """선행 전이가 있는 배치는 경고 — 첫 노드는 진입점이라 대상이 아니다."""
    project = _chain(_skill("first"), _skill("second"), _skill("third"))
    assert _sources(project) == ["second", "third"]


def test_entry_placement_not_flagged():
    """incoming 0개 = 진입점 후보. user_invocable true가 정상이다."""
    project = _chain(_skill("first"), _skill("second", user_invocable=False))
    assert _sources(project) == []


def test_user_invocable_off_not_flagged():
    project = _chain(_skill("first"), _skill("second", user_invocable=False))
    assert _sources(project) == []


def test_unplaced_skill_not_flagged():
    """배치되지 않은 독립 스킬은 대상이 아니다 — 그쪽은 true가 정상이다."""
    project = PluginProject(name="p", skills=[_skill("solo")])
    assert _sources(project) == []


def test_entry_point_transition_is_not_incoming():
    """EntryPoint에서 오는 전이는 "여기서 시작한다"는 선언이라 세지 않는다.

    WP-EP로 캔버스에 그리지 않을 뿐 구버전 파일의 시작 전이는 모델에 남아 있다 —
    그것까지 incoming으로 세면 진입 스킬이 전부 경고를 받는다.
    """
    project = _chain(_skill("first"), connect=False)
    graph = project.graph
    entry = next(s for s in graph.states if isinstance(s, EntryPoint))
    node = next(s for s in graph.states if not isinstance(s, EntryPoint))
    graph.transitions.append(Transition(source=entry, target=node))
    assert _sources(project) == []


def test_declarative_skill_not_flagged():
    """대상은 ProceduralSkill뿐 — 배경 지식 스킬은 진입 개념이 없다."""
    decl = DeclarativeSkill(name="knowledge", description="d")
    project = _chain(_skill("first"))
    node = SimpleState(name="knowledge", skill_ref=decl)
    project.skills.append(decl)
    project.graph.states.append(node)
    first_node = next(
        s for s in project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is project.skills[0]
    )
    project.graph.transitions.append(Transition(source=first_node, target=node))
    assert _sources(project) == []


def test_warning_severity_and_subject():
    """경고 등급이고, subject는 노드 점프가 가능하도록 배치 상태를 가리킨다."""
    project = _chain(_skill("first"), _skill("second"))
    errors = [e for e in Validator.validate_project(project) if e.rule == _RULE]
    assert len(errors) == 1
    error = errors[0]
    assert error.is_warning is True
    assert error.path == ("project",)
    assert any(
        error.subject is s for s in project.graph.states
        if isinstance(s, SimpleState) and s.skill_ref is project.skills[1]
    )
