# daedalus/mcp/tools/placement_prose.py
"""배치 거절 문구 — **배치 역할 선언**에서 파생한다 (WP-8 P5).

거절 문구가 종류 이름을 손으로 열거하면(`"declarative는 배경 지식, transfer는
전이 위의 단계, fork_agent는 …"`) 새 종류가 생기는 날 **문구가 거짓말을 한다** —
거절은 되는데 이유가 다른 종류의 설명이고, 그 어긋남은 테스트도 컴파일도
실패시키지 않는다(카탈로그 P5 👻).

그래서 여기 있는 표는 **`PlacementRole` 4행**이다: 역할 하나당 한 문장이고
종류 이름은 한 글자도 없다. 어느 종류가 그 역할인지는 레지스트리가 답한다
(`kinds_with_placement`). 새 종류는 역할을 선언하는 것만으로 올바른 문구를
얻는다 — 이 파일을 고칠 일이 없다.

소비자는 MCP 두 곳이다: `props._create_component`(생성 시 좌표를 준 경우)와
`canvas.place_component`(배치 도구). 같은 사실을 두 문구로 말하지 않는다(원칙 1).
"""
from __future__ import annotations

from daedalus.model.plugin.roles import PlacementRole

#: 배치 역할 → 사람에게 하는 한 문장. `PlacementRole` 전수(4행)다 —
#: 멤버가 늘면 `placement_role_prose`가 KeyError로 시끄럽게 실패한다(원칙 5).
_ROLE_PROSE: dict[PlacementRole, str] = {
    PlacementRole.STATE: "그래프의 단계 노드로 놓입니다",
    PlacementRole.REFERENCE: (
        "상태 노드가 아니라 참조 노드로 놓입니다 — place_reference를 쓰세요"
    ),
    PlacementRole.EDGE: "전이 위에서 도는 단계라 그래프 노드가 아닙니다",
    PlacementRole.NONE: "그래프에 놓이지 않습니다",
}


def placement_role_prose(role: PlacementRole) -> str:
    """이 배치 역할을 사람에게 설명하는 한 문장."""
    return _ROLE_PROSE[role]


def kinds_with_placement(role: PlacementRole) -> tuple[str, ...]:
    """같은 배치 역할을 **선언한** config 종류들 — 선언 순서(결정적)."""
    from daedalus.model.plugin.kinds import KIND_REGISTRY

    return tuple(
        spec.config_kind
        for spec in KIND_REGISTRY.values()
        if spec.placement is role
    )
