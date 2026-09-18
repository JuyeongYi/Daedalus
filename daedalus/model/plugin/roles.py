# daedalus/model/plugin/roles.py
"""컴포넌트 **능력 표면**의 어휘 (REFACTOR_SPEC §2-a).

순수 enum만 있고 **아무것도 임포트하지 않는다** — plugin 패키지의 임포트 방향
`roles ← base ← config ← skill/agent`의 뿌리다. 여기 어휘가 다른 모듈을
참조하기 시작하면 그 방향이 곧바로 순환이 된다.

왜 enum인가. 오늘 종류별 분기는 "이 객체가 무슨 **클래스**인가"를 묻지만
실제로 알고 싶은 것은 **성질**이다(그래프에 놓이는가 / 산출 파일을 내는가 /
본문 정본이 어디인가). 성질을 클래스로 물으면 새 종류마다 모든 호출자를
고쳐야 하고, 빠뜨린 자리는 조용한 no-op가 된다(원칙 5). 성질을 값으로 선언하면
새 종류는 값을 고르기만 하면 된다.

`StrEnum`인 이유: 값이 그대로 진단 문구·직렬화 가능 형태로 나가야 할 때가
있어서다. 다만 **판정은 항상 멤버 동일성(`is`)으로 한다** — 문자열 비교로
하면 종류 리터럴이 다시 흩어진다.
"""
from __future__ import annotations

from enum import StrEnum


class Bucket(StrEnum):
    """컴포넌트가 담기는 프로젝트 목록 — 진짜 이분법이다(Q31의 뿌리).

    `project.skills` / `project.agents` 두 목록은 종류가 늘어도 늘지 않는다.
    """

    SKILLS = "skills"
    AGENTS = "agents"


class PlacementRole(StrEnum):
    """캔버스·그래프에서의 배치 역할 (Q5).

    - ``STATE``     그래프 `SimpleState` 노드 — **단일 배치**(중복 금지).
    - ``REFERENCE`` 참조 노드 — 복수 배치 가능, 산출 파일 없음.
    - ``EDGE``      전이 엣지에만 붙는다(노드가 아니다).
    - ``NONE``      캔버스에 놓이지 않는다.

    "포트를 갖는가"도 이 값 하나가 답한다 — **단일 배치 노드만** 출력/호출
    포트를 갖는다(REFACTOR_SPEC §2-b "포트를 갖는 종류").
    """

    STATE = "state"
    REFERENCE = "reference"
    EDGE = "edge"
    NONE = "none"


class BodySource(StrEnum):
    """본문(`body`)의 정본이 어디인가 (Q19).

    ``EXTERNAL``이면 본문 편집이 잠긴다 — 편집기는 본문 패널을 만들지 않고
    MCP `set_component_body`는 거절한다. 두 표면이 **같은 선언**을 봐야
    "GUI는 막는데 MCP는 조용히 성공"이 생기지 않는다(원칙 1·2).
    """

    OWNED = "owned"
    EXTERNAL = "external"


class OutputLocation(StrEnum):
    """플러그인 산출에서 이 종류가 차지하는 **위치의 종류** (Q6).

    경로 조립(`skills/<이름>/SKILL.md`)은 CC 플러그인 레이아웃 = 컴파일러
    어휘라 여기 없다. 모델은 "어느 자리에 나는가"까지만 말한다.
    ``NONE``은 산출 파일이 아예 없다는 뜻이고, `emits_output()`의 기본 판정이
    이 값을 본다.
    """

    SKILL_DIR = "skill_dir"
    AGENT_FILE = "agent_file"
    NONE = "none"
