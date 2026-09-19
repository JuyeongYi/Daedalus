# daedalus/compiler/emit/pointer_rules.py
"""공통 안내 파일 포인터의 **대상 판정** (WP-6 — `guides.py`에서 분리).

"이 컴포넌트가 어느 가이드를 가리키는가"는 두 사실의 곱이다:

1. **가이드가 말할 것이 있는가** — 그래프에 배치 노드가 있는가 / 블랙보드
   클래스가 있는가(`_workflow_guide_available` / `_blackboard_guide_available`).
2. **이 종류가 포인터를 받는가** — 절 적용 표의 선언(`GuidePointerRule`,
   `SectionId.BLACKBOARD ∈ sections`)과 **이 인스턴스**의 배치 상태.

둘째가 종류 선언을 읽기 때문에 판정이 `section_plan`보다 **위**에 있어야 하고,
포인터 줄의 문구(`guides.guide_pointer_line`)는 다시 이 판정을 읽어야 한다.
한 파일에 두면 `guides → section_plan → … → guides` 순환이므로 판정만 떼어
아래층에 두고 `guides.py`가 이름을 재-export한다(호출자 무수정,
`tests/compiler/test_emit_import_acyclic.py`가 방향을 강제한다).
"""
from __future__ import annotations

from daedalus.compiler.emit.common import _graph_placements, _graph_placements_any
from daedalus.compiler.emit.section_plan import (
    GuidePointerRule,
    SectionId,
    plan_for_kind,
)
from daedalus.model.plugin.placement import is_reference_placed


def _blackboard_classes(project) -> list:
    bb = getattr(project, "blackboard", None)
    return list(getattr(bb, "class_definitions", None) or [])


def _workflow_guide_available(project) -> bool:
    """워크플로 가이드가 말할 것이 있는가 — 그래프에 배치 노드가 하나라도 있는가."""
    return project is not None and _graph_placements_any(project)


def _blackboard_guide_available(project) -> bool:
    return project is not None and bool(_blackboard_classes(project))


def workflow_pointer_kind(component, project) -> str:
    """이 컴포넌트가 받는 워크플로 가이드 포인터 종류 — "" | "main" | "fork".

    "main"은 **메인 대화에서 도는 배치 컴포넌트**다(배치된 절차형·선언형·state
    용도 랩핑 스킬·워크플로 에이전트, placement가 있는 프로젝트의 전이 스킬).

    fork 스킬은 "fork"다 — 가이드 2·3절("진행 기록을 이렇게 갱신하라", "current가
    다르면 사용자에게 확인하라")은 fork 자신의 "## Report"("진행 파일을 네가
    갱신하지 말라")와 정면으로 충돌하고, fork 서브에이전트는 사용자에게 되물을
    수도 없다. 그래서 보고 양식만 가리키는 전용 줄을 낸다.

    fork 에이전트·참조 스킬·랩핑 실행 에이전트·미배치 스킬은 대상이 아니다("").

    **종류 쪽 판정은 절 적용 표의 `GuidePointerRule` 한 줄이다**(WP-6 — 종전에는
    `PLACEMENT`/`RUNS_IN_SUBAGENT`/`IS_FORK_BASE`를 여기서 다시 조합했다).
    거기에 **인스턴스** 상태(배치돼 있는가·참조 노드로 쓰이는가)를 곱한다.
    """
    if not _workflow_guide_available(project):
        return ""
    rule = plan_for_kind(getattr(type(component), "KIND", None)).guide_pointer
    if rule is GuidePointerRule.NONE:
        return ""
    if rule is GuidePointerRule.MAIN_IF_ANY_PLACEMENT:
        # 엣지 스킬은 그래프 노드가 아니다 — 진행 파일을 만드는 배치 스킬이
        # 하나라도 있으면(위 게이트) 지침이 고아가 아니다.
        return "main"
    if not _graph_placements(component, project):
        return ""
    if is_reference_placed(component):
        # 참조 노드는 스스로 워크플로를 진행시키지 않는다. 참조 용도 랩핑
        # 스킬은 산출 파일도 없지만, D1 이전에 만든 `.ddpj`에는 state 노드로
        # 박혀 있을 수 있어 여기까지 도달한다.
        return ""
    return "fork" if rule is GuidePointerRule.FORK_IF_PLACED else "main"


def blackboard_pointer_wanted(component, project) -> bool:
    """이 컴포넌트가 블랙보드 가이드 포인터를 받는가.

    **"## Shared State (Blackboard)"가 배출되는 컴포넌트와 같은 집합**이고, 이제
    그 사실을 절 적용 표에서 직접 읽는다(WP-6 — 종전에는 `BUCKET`/`PLACEMENT`로
    같은 집합을 다시 유도했다. 두 표가 어긋나면 "단락은 없는데 포인터만 나가는"
    조용한 거짓말이 된다). 클래스 정의가 하나도 없으면 가이드 자체가 없다.

    거기서 **인스턴스**가 참조 노드로 쓰이는 것만 뺀다 — 선언(종류가 블랙보드
    단락을 갖는가)과 상태(이 인스턴스가 참조로 놓였는가)를 나눠 묻는다.
    """
    if not _blackboard_guide_available(project):
        return False
    if is_reference_placed(component):
        return False
    plan = plan_for_kind(getattr(type(component), "KIND", None))
    return SectionId.BLACKBOARD in plan.sections
