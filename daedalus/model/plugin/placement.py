# daedalus/model/plugin/placement.py
"""배치 가능 판정 + fork 스킬 역참조 (순수 도메인 모델 — Qt 무관).

**두 판정이다.** 하나로 합치면 참조 스킬 경로가 죽는다:

- `is_state_placeable` — 그래프에 **SimpleState 노드**로 놓을 수 있는가.
- `is_canvas_placeable` — 캔버스에 끌어놓거나 "여기에 만들기"로 놓을 수 있는가
  (상태 노드 **또는** 참조 노드로).

캔버스 드롭·레지스트리 드래그·"여기에 만들기"·MCP `place_component`가 전부
여기를 부른다 — 음성 목록(NO_PLACE_KINDS 등)을 표면마다 따로 들고 있으면
어긋난다(원칙 1).
"""
from __future__ import annotations


def is_state_placeable(component: object) -> bool:
    """그래프에 상태 노드로 놓을 수 있는 컴포넌트인가.

    True: `StepSkill`(절차형·fork 2종), 용도가 `reference`가 **아닌**
    `WrappedSkill`(state 또는 미정 — 미정은 배치 경로가 state로 고정한다),
    `AgentDefinition`.
    False: `DeclarativeSkill`·`TransferSkill`·`ReferenceSkill`(참조 노드는 별도
    경로)·`ForkAgent`(fork 스킬이 부르는 실행 기반이라 그래프 노드가 아니다).
    """
    from daedalus.model.plugin.agent import AgentDefinition
    from daedalus.model.plugin.skill import (
        StepSkill,
        WrappedSkill,
        is_reference_usage,
    )

    if isinstance(component, AgentDefinition):
        return True
    if isinstance(component, StepSkill):
        return True
    if isinstance(component, WrappedSkill):
        return not is_reference_usage(component)
    return False


def is_canvas_placeable(component: object) -> bool:
    """캔버스에 놓이는 컴포넌트인가 — 상태 노드 또는 참조 노드.

    `is_state_placeable`과 **다른 질문**이다: 참조 스킬은 상태 노드가 될 수
    없지만 캔버스에는 참조 노드로 놓인다(레지스트리에서 드래그 가능).
    """
    from daedalus.model.plugin.skill import is_reference_usage

    return is_state_placeable(component) or is_reference_usage(component)


def fork_skills_using(agent, project) -> list[str]:
    """이 프로젝트 에이전트를 fork 에이전트로 쓰는 fork 스킬 이름 (정렬 — 결정적).

    화면("사용하는 fork 스킬" 패널·삭제 확인)·산출(에이전트 "## Invocation
    Contract")·MCP(`delete_component`의 `still_referenced_by`)가 같은 목록을
    말해야 하므로 실체는 여기 하나다. 컴파일러는 뷰를 임포트할 수 없으므로
    (import 계약) 실체가 모델에 있어야 한다.
    """
    from daedalus.model.plugin.skill import ForkSkill

    name = getattr(agent, "name", None)
    if not name:
        return []
    return sorted(
        s.name for s in getattr(project, "skills", None) or []
        if isinstance(s, ForkSkill) and getattr(s.config, "agent", "") == name
    )
