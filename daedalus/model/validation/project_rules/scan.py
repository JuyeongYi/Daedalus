# daedalus/model/validation/project_rules/scan.py
"""규칙 그룹들이 공유하는 순회 헬퍼 (이동만 — 동작 불변).

분해 전에는 ``_ProjectRules`` 클래스의 staticmethod였다. 그룹 모듈이 여럿이
되면서 서로를 ``_ProjectRules.<헬퍼>``로 부르면 파사드(``__init__``)와 순환
임포트가 되므로, 실체를 **모듈 수준 함수**로 내리고 각 믹스인이 같은 객체를
``staticmethod``로 재노출한다(``Validator._graph_has_placements`` 등 기존 이름
보존 — ``compiler/emit/common.py``가 그 경로로 부른다).
"""
from __future__ import annotations

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.fsm.pseudo import EntryPoint
from daedalus.model.fsm.walk import iter_states, iter_transitions


def graph_has_placements(graph: StateMachine) -> bool:
    """프로젝트 그래프에 EntryPoint 외 노드(placement)가 하나라도 있으면 True.

    빈 그래프(시작점만)는 검증을 스킵해 경고 폭주를 막는다.
    """
    return any(not isinstance(s, EntryPoint) for s in graph.states)


def project_machines(project):
    """프로젝트의 모든 최상위 FSM을 (label, sm)로 yield.

    "FSM을 갖는가"는 컴포넌트가 답한다(`state_machines()` — Q2). FSM이 없는
    종류(선언형·참조 스킬·fork 에이전트)는 빈 목록을 답해 자연 제외된다 —
    `getattr(x, "fsm", None)`로 형상을 더듬던 자리다.
    """
    for skill in project.skills:
        for sm in skill.state_machines():
            yield (f"skill:{skill.name}", sm)
    for agent in project.agents:
        for sm in agent.state_machines():
            yield (f"agent:{agent.name}", sm)


def scan_state_access(sm: StateMachine, visit) -> None:
    """머신(재귀 — sub_machine/Region 포함)의 모든 상태에 visit(state)를 적용한다.

    dangling_blackboard_ref/orphan_blackboard_field가 공유하는 순회 로직.
    재귀 골격 자체는 ``model/fsm/walk.iter_states``가 단일 진실이다.
    """
    for state in iter_states(sm):
        visit(state)


def scan_transitions(sm: StateMachine, visit) -> None:
    """머신(재귀 — sub_machine/Region 포함)의 모든 전이에 visit(transition)를 적용.

    ``scan_state_access``의 전이판이다 — 같은 재귀 범위를 두 번 적으면 한쪽만
    고쳐졌을 때 규칙마다 보는 그래프가 달라진다. 그래서 재귀 골격은
    ``model/fsm/walk.iter_transitions``가 단일 진실이다.
    """
    for trans in iter_transitions(sm):
        visit(trans)
