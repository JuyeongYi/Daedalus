# daedalus/view/actions/agent_links.py
"""에이전트 호출자 유도 + 출력 포트 편집 진입 (A9-4, A9-5).

에이전트가 **누구에게 불리는지**는 모델 어디에도 적혀 있지 않다 — 프로젝트
그래프의 incoming 호출 전이에서 유도할 뿐이다(WP-CT: 같은 사실의 소스가 둘이면
반드시 어긋난다). 컴파일의 "## 호출 계약"이 쓰는 것과 **같은 유도**를 UI도
쓰도록 이 모듈에 모은다 — 화면과 산출이 다른 호출자 목록을 말하면 안 된다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallerRef:
    """이 에이전트를 부르는 경로 하나."""

    caller: object            # 호출자 컴포넌트(스킬)
    caller_name: str
    port: str                 # 호출 포트(전이 trigger) 이름
    description: str          # 호출자가 자기 call_agents 포트에 적은 설명
    source_state: object      # 캔버스 포커스 대상 — 호출자 placement 노드

    @property
    def label(self) -> str:
        """메뉴/목록 표시 문구 — "<호출자> · <포트>"."""
        return f"{self.caller_name} · {self.port}" if self.port else self.caller_name


def callers_of(agent: object, project) -> list[CallerRef]:
    """이 에이전트를 부르는 경로 목록. 호출자 이름·포트 순 (결정적).

    정렬 기준이 컴파일의 `_call_contract_section`과 같다 — 목록의 순서가 산출
    문서의 순서와 어긋나면 둘을 나란히 놓고 볼 수 없다.
    """
    graph = getattr(project, "graph", None)
    if graph is None:
        return []

    out: list[CallerRef] = []
    for trans in getattr(graph, "transitions", None) or []:
        if getattr(trans.target, "skill_ref", None) is not agent:
            continue
        caller = getattr(trans.source, "skill_ref", None)
        name = getattr(caller, "name", None)
        if not name:
            continue  # 빈 노드에서 온 전이 — 가리킬 호출자가 없다
        port = getattr(getattr(trans, "trigger", None), "name", "") or ""
        description = ""
        for event in getattr(caller, "call_agents", None) or []:
            if event.name == port:
                description = (event.description or "").strip()
                break
        out.append(CallerRef(
            caller=caller, caller_name=name, port=port,
            description=description, source_state=trans.source,
        ))
    out.sort(key=lambda ref: (ref.caller_name, ref.port))
    return out
