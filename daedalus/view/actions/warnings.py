# daedalus/view/actions/warnings.py
"""컴포넌트별 검증 결과 필터 (A9-3).

F7은 프로젝트 전체 결과를 낸다. 노드 하나를 손보는 중에 "이 스킬에 관한 것만"
보고 싶을 때 목록에서 눈으로 골라내야 했다.

필터 함수만 여기 있고 dock 표시는 `ValidationActions`가 계속 맡는다 —
검증 패널을 띄우는 경로가 둘이면 어느 쪽이 마지막에 뭘 채웠는지 알 수 없다.
"""
from __future__ import annotations

from daedalus.model.validation import ValidationError


def findings_for(
    errors: list[ValidationError], component: object, project=None
) -> list[ValidationError]:
    """이 컴포넌트에 관한 결과만 골라낸다.

    세 가지를 모두 이 컴포넌트의 것으로 본다 — 하나만 보면 놓친다:

    1. `subject`가 컴포넌트 자신 (예: `skill_dir_token_in_agent`)
    2. `path`가 `"skill:<이름>"` / `"agent:<이름>"`으로 시작 (자체 FSM 규칙)
    3. `subject`가 **프로젝트 그래프에서 이 컴포넌트를 가리키는 placement 노드**
       (예: `mid_chain_user_invocable`) — 사용자가 우클릭한 그 노드다

    identity(`is`) 비교를 쓴다 — `ValidationError.subject`는 `compare=False`라
    값 비교가 성립하지 않고, 동명 컴포넌트가 있어도 헷갈리지 않는다.
    """
    name = getattr(component, "name", None)
    roots = {f"skill:{name}", f"agent:{name}"} if name else set()
    placements = _placement_ids(component, project)

    out: list[ValidationError] = []
    for error in errors:
        subject = error.subject
        if subject is component:
            out.append(error)
            continue
        if subject is not None and id(subject) in placements:
            out.append(error)
            continue
        path = getattr(error, "path", ()) or ()
        if path and path[0] in roots:
            out.append(error)
    return out


def _placement_ids(component: object, project) -> set[int]:
    """프로젝트 그래프에서 이 컴포넌트를 가리키는 placement 상태의 id 집합."""
    from daedalus.model.fsm.state import SimpleState

    graph = getattr(project, "graph", None)
    if graph is None:
        return set()
    return {
        id(state)
        for state in graph.states
        if isinstance(state, SimpleState) and state.skill_ref is component
    }
