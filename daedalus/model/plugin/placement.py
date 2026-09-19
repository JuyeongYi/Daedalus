# daedalus/model/plugin/placement.py
"""배치 가능 판정 + fork 스킬 역참조 (순수 도메인 모델 — Qt 무관).

**두 판정이다.** 하나로 합치면 참조 스킬 경로가 죽는다:

- `is_state_placeable` — 그래프에 **SimpleState 노드**로 놓을 수 있는가.
- `is_canvas_placeable` — 캔버스에 끌어놓거나 "여기에 만들기"로 놓을 수 있는가
  (상태 노드 **또는** 참조 노드로).
- `is_edge_placeable` — 전이 엣지에 붙는가(전이 스킬).

캔버스 드롭·레지스트리 드래그·"여기에 만들기"·MCP `place_component`가 전부
여기를 부른다 — 음성 목록(NO_PLACE_KINDS 등)을 표면마다 따로 들고 있으면
어긋난다(원칙 1).

**판정의 실체는 컴포넌트 자신이다**(WP-2b). 여기 있는 것은 "어떤 배치 역할이
무슨 이름으로 불리는가"라는 어휘 번역뿐이고, 종류 목록은 없다 — 새 종류는
`PLACEMENT` ClassVar 한 줄을 고르는 것으로 이 두 함수의 답을 얻는다.
"""
from __future__ import annotations

from daedalus.model.plugin.roles import Bucket, PlacementRole


def placement_role_of(component: object) -> PlacementRole:
    """컴포넌트의 실제 배치 역할 — 컴포넌트가 **아니면** ``NONE``.

    호출자가 넘기는 값에는 `None`(빈 노드의 skill_ref)이나 kind 문자열 같은
    비-컴포넌트가 섞인다. 예외로 터뜨리는 대신 "놓을 수 없다"로 답하는 것이
    종전 `isinstance` 사다리의 동작이었고, 그 계약을 그대로 유지한다.

    `skill.is_reference_usage`도 이것을 쓴다 — 관용 규칙이 두 벌이면 한쪽만
    None을 견디는 어긋남이 생긴다(원칙 1). `placement`는 `skill`을 임포트하지
    않으므로(반대 방향) 실체를 여기 둔다.
    """
    role = getattr(component, "effective_placement", None)
    return role() if callable(role) else PlacementRole.NONE


def is_state_placeable(component: object) -> bool:
    """그래프에 상태 노드로 놓을 수 있는 컴포넌트인가.

    실체는 `component.effective_placement() is PlacementRole.STATE` 하나다 —
    **단일 배치** 노드만 상태가 된다. 오늘 True인 것: `StepSkill`(절차형·fork
    2종), 용도가 `reference`가 **아닌** `WrappedSkill`(state 또는 미정 — 미정은
    배치 경로가 state로 고정한다), `AgentDefinition`.
    False: `DeclarativeSkill`(PLACEMENT=NONE)·`TransferSkill`(EDGE)·
    `ReferenceSkill`(REFERENCE — 참조 노드는 별도 경로)·`ForkAgent`(NONE —
    fork 스킬이 부르는 실행 기반이라 그래프 노드가 아니다).

    **"포트를 갖는가"도 같은 질문이다**(WP-2d): 워크플로 단계로 한 번 놓이는
    노드만 출력 포트·에이전트 호출 포트를 선언할 의미가 있다. 편집기 포트
    패널·MCP 포트 도구·캔버스 호출 판정이 전부 이 함수를 부른다 — 손으로
    같은 enum 비교를 적으면 표면마다 답이 갈린다(원칙 1).
    """
    return placement_role_of(component) is PlacementRole.STATE


def is_canvas_placeable_role(role: PlacementRole) -> bool:
    """이 **배치 역할**이 캔버스에 놓이는가 — 인스턴스가 아직 없는 자리 전용.

    MCP `create_skill(x=, y=)`처럼 **만들기 전에** 거절해야 하는 자리는 kind
    문자열밖에 갖고 있지 않다(종전 `creation.NO_PLACE_KINDS` 음성 목록이 그
    자리였고, 목록과 판정이 어긋나도 아무도 알려 주지 않았다). 종류의
    `PLACEMENT` 선언을 그대로 물어 두 답이 갈리지 않게 한다 —
    `is_canvas_placeable`은 이 함수의 인스턴스 판본이다.
    """
    return role in (PlacementRole.STATE, PlacementRole.REFERENCE)


def is_edge_placeable(component: object) -> bool:
    """전이 **엣지**에 붙는 컴포넌트인가 — 오늘 `TransferSkill` 하나.

    캔버스 엣지 메뉴·MCP `_find_transfer_skill`·컴파일러의 전이 스킬 단락이
    같은 목록을 말해야 하므로 실체는 여기다. "종류가 TransferSkill인가"가
    아니라 **배치 역할이 EDGE인가**를 묻는다.
    """
    return placement_role_of(component) is PlacementRole.EDGE


def is_reference_placed(component: object) -> bool:
    """참조처럼 배치되는 컴포넌트인가 — 배치 역할이 ``REFERENCE``인가.

    `is_state_placeable`/`is_edge_placeable`과 **같은 층의 이름**이다. 이
    질문도 손으로 `placement_role_of(c) is PlacementRole.REFERENCE`를 적으면
    표면마다 답이 갈린다(원칙 1) — `skill.is_reference_usage`는 이 함수의
    한 줄 파사드이고, 실체는 여기 하나다.
    """
    return placement_role_of(component) is PlacementRole.REFERENCE


def is_canvas_placeable(component: object) -> bool:
    """캔버스에 놓이는 컴포넌트인가 — 상태 노드 또는 참조 노드.

    `is_state_placeable`과 **다른 질문**이다: 참조 스킬은 상태 노드가 될 수
    없지만 캔버스에는 참조 노드로 놓인다(레지스트리에서 드래그 가능).
    """
    return is_canvas_placeable_role(placement_role_of(component))


def fork_skills_using(agent, project) -> list[str]:
    """이 프로젝트 에이전트를 fork 에이전트로 쓰는 fork 스킬 이름 (정렬 — 결정적).

    화면("사용하는 fork 스킬" 패널·삭제 확인)·산출(에이전트 "## Invocation
    Contract")·MCP(`delete_component`의 `still_referenced_by`)가 같은 목록을
    말해야 하므로 실체는 여기 하나다. 컴파일러는 뷰를 임포트할 수 없으므로
    (import 계약) 실체가 모델에 있어야 한다.

    술어는 **"설정이 AGENTS 네임스페이스의 이 이름을 참조하는가"**다(Q14 —
    `config.name_refs`). `ForkSkillConfig.name_refs(AGENTS)`만 `[agent]`를
    내놓고 나머지 스킬 설정은 기저의 빈 목록을 물려받으므로 종전
    `isinstance(s, ForkSkill) and s.config.agent == name`과 **정확히 같은
    집합**이다.

    `delegated_agent_name()`(Q33)을 쓰지 않는 이유: 랩핑 스킬은 **자기 이름의
    러너**를 답하므로 에이전트와 동명인 랩퍼가 fork 스킬 참조자로 섞여 든다.
    이름 중복은 `duplicate_component_name`이 짚지만 그것은 검증 에러일 뿐
    게이트가 아니고, 삭제 확인·MCP `delete_component`/`get_component`는
    검증 상태와 무관하게 이 목록을 읽는다 — 편집 도중의 이름 충돌이 틀린
    참조자 목록으로 새 나가면 안 된다.
    """
    name = getattr(agent, "name", None)
    if not name:
        return []
    return sorted(
        s.name
        for s in getattr(project, "skills", None) or []
        if name in s.config.name_refs(Bucket.AGENTS)
    )
