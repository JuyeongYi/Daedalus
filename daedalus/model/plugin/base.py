from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from daedalus.model.fsm.machine import StateMachine
from daedalus.model.plugin.roles import (
    BodySource,
    Bucket,
    OutputLocation,
    PlacementRole,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from daedalus.model.fsm.section import EventDef
    from daedalus.model.plugin.config import ComponentConfig


@dataclass
class PluginComponent(ABC):
    """플러그인 구성 요소 공통 + **능력 표면** (REFACTOR_SPEC §2-b).

    능력 표면이란 "이 컴포넌트가 무슨 종류인가"가 아니라 "무엇을 할 수 있는가"를
    각 컴포넌트가 스스로 말하게 하는 선언·메서드 묶음이다. 호출자가
    `isinstance(c, WrappedSkill)` 식으로 종류를 열거하면 새 종류가 생길 때마다
    모든 호출자를 고쳐야 하고 빠뜨린 자리는 조용한 no-op가 된다(원칙 5).

    **세 가지 기계적 규약** — 어기면 조용히 깨진다:

    1. **기존 컴포넌트 클래스에 dataclass 필드를 추가하지 않는다.** 능력은
       ① `ClassVar` ② **주석 없는** 클래스 속성 ③ 기본 구현이 있는 메서드로만
       선언한다. 기저에 필드를 올리면 다중 상속 dataclass의 필드 순서가 바뀐다
       (CLAUDE.md "dataclass 다중 상속 필드 순서").
    2. **기존 클래스에 `@dataclass`를 재선언하지 않는다.** ClassVar·메서드
       추가에는 필요 없고, 재선언하면 `eq=False` 정책 클래스가 `__eq__`를
       다시 만들며 unhashable로 되돌아간다.
    3. **`ClassVar`를 이름으로 임포트한다.** `from __future__ import annotations`
       아래에서 dataclass는 문자열 주석 ``"ClassVar[...]"``를 모듈에 그 이름이
       있을 때만 ClassVar로 인식한다 — 없으면 **조용히 필드가 된다**.

    종류 선언(`KIND`/`CONFIG_CLS`/`BUCKET`)에는 기본값이 없다. 추상 기저에서
    읽으면 `AttributeError`가 나고, 그것이 "추상을 종류처럼 썼다"는 시끄러운
    실패다(원칙 5).
    """

    name: str
    description: str

    # ── 종류 선언 (ClassVar — 구체 클래스만 값을 준다) ────────────────────
    #: 저장 파일의 ``kind`` 값 ("procedural_skill"). config의 KIND와 **다른**
    #: 어휘다(config는 "procedural") — 두 벌을 유지하는 것이 파일 포맷 불변의
    #: 값이고, 통일은 사용자 확정 대상이다(backlog).
    KIND: ClassVar[str]
    #: 이 종류의 설정 클래스. `kind` ↔ `config.kind` 짝의 선언 쪽 절반이다.
    CONFIG_CLS: ClassVar[type[ComponentConfig]]
    #: 담기는 프로젝트 목록 — 진짜 이분법(Q31의 뿌리).
    BUCKET: ClassVar[Bucket]
    #: 선언상의 배치 역할. **인스턴스 판정은 `effective_placement()`**를 쓴다
    #: (용도 스위치를 가진 종류가 있다).
    PLACEMENT: ClassVar[PlacementRole] = PlacementRole.NONE
    #: 산출 파일의 자리 종류. NONE이면 파일을 내지 않는다.
    OUTPUT_LOCATION: ClassVar[OutputLocation] = OutputLocation.NONE
    #: 본문의 정본이 어디인가 — EXTERNAL이면 본문 편집이 잠긴다.
    BODY_SOURCE: ClassVar[BodySource] = BodySource.OWNED
    #: 같은 값끼리 `__class__` 전환이 가능하다 (Q17 — 종류 전환 UI).
    CONVERT_FAMILY: ClassVar[str | None] = None
    #: 그래프에서 이 노드로 가는 전이는 "위임"이다 (Q9).
    DELEGATION_TARGET: ClassVar[bool] = False
    #: 본문이 서브에이전트 컨텍스트에서 돈다 (Q20).
    RUNS_IN_SUBAGENT: ClassVar[bool] = False
    #: 결과가 작업 알림으로 뒤늦게 온다 (Q20 — 비동기 fork).
    REPORTS_OUT_OF_BAND: ClassVar[bool] = False
    #: fork 스킬의 실행 기반이 될 수 있다 (Q27).
    IS_FORK_BASE: ClassVar[bool] = False
    #: 출력 포트가 비면 검증 에러다 (Q30 — transfer_on_not_empty).
    REQUIRES_OUTPUT_PORTS: ClassVar[bool] = False
    #: legacy 내부 FSM 절의 대상인가 (오늘은 AgentDefinition만).
    HAS_INTERNAL_FSM: ClassVar[bool] = False

    # ── 형상 기본값 ────────────────────────────────────────────────────
    # **주석을 달지 않는다** — 달면 dataclass 필드가 되어 MRO 필드 순서가 깨진다.
    # 구체 클래스가 같은 이름의 dataclass 필드를 가지면 인스턴스 속성이 이긴다.
    # 오늘 9종 구체 컴포넌트는 전부 `body`를 갖고, 스킬 7종만 `when_to_use`를
    # 갖는다 — 에이전트에서 `when_to_use`를 읽던 자리는 이미 기본값 ""로
    # 폴백하고 있어(`emit/frontmatter.py`·`mcp/tools/query.py`) 값이 같다.
    body = ""
    when_to_use = ""
    if TYPE_CHECKING:
        # 정적 타입만 — 런타임 클래스 속성이 **아니다**(9종 전부가 필드로 선언한다).
        config: ComponentConfig

    @property
    @abstractmethod
    def kind(self) -> str:
        """컴포넌트 종류 식별자 — 구체 클래스는 ``return self.KIND``."""

    # ── 인스턴스 훅 (종류 선언이 아니라 **인스턴스 상태**가 답하는 것) ──────

    def effective_placement(self) -> PlacementRole:
        """이 **인스턴스**의 실제 배치 역할.

        종류 선언(`PLACEMENT`)과 다를 수 있다 — 용도 스위치를 가진 종류는
        같은 클래스가 상태 노드로도 참조 노드로도 쓰인다.
        """
        return type(self).PLACEMENT

    def is_active(self) -> bool:
        """쓰이고 있는가 — 껐다 켤 수 있는 종류만 False가 될 수 있다.

        "지울 수 없고 끄기만 한다"는 종류(WP-WR)가 있어서 **끔**이 곧 "쓰지
        않음"이다. 산출·배선·검증이 전부 이 판정 하나를 봐야 "꺼 뒀는데 산출에는
        남는" 어긋남이 생기지 않는다.
        """
        return True

    def emits_output(self) -> bool:
        """자기 산출 파일을 내는가 — plan·guides·hooks·preview의 단일 판정.

        둘이 어긋나면 ① 아무도 가리키지 않는 가이드가 나가거나 ② 산출되지 않는
        파일에 포인터가 붙는다(`compiler/emit/common.emits_output_file` 주석).
        """
        return (
            type(self).OUTPUT_LOCATION is not OutputLocation.NONE
            and self.is_active()
        )

    def can_delete(self) -> tuple[bool, str | None]:
        """지울 수 있는가 — (가능 여부, 불가 사유).

        사유를 함께 돌려주는 이유는 거절이 조용하면 안 되기 때문이다(원칙 5):
        GUI는 이 문구를 비활성 툴팁으로, MCP는 거절 메시지로 쓴다.
        """
        return (True, None)

    # ── 형상 조회 (기본 = 없음) ───────────────────────────────────────────
    # 오버라이드는 **그 필드를 실제로 가진 클래스에서** 한다. `WorkflowComponent`
    # 믹스인에 두면 `StepSkill(Skill, WorkflowComponent)` MRO에서 여기 기본
    # 구현이 먼저 잡혀 **조용히 무시된다**(REFACTOR_SPEC §10 R2).

    def state_machines(self) -> list[StateMachine]:
        """이 컴포넌트가 소유한 FSM 목록 (없으면 빈 목록) — Q2."""
        return []

    def output_ports(self) -> list[EventDef]:
        """출력 포트(결과 분기) 정의 목록 — Q8. 복사본을 돌려준다."""
        return []

    def call_ports(self) -> list[EventDef]:
        """에이전트 호출 포트 정의 목록 — Q8. 복사본을 돌려준다."""
        return []

    def known_outgoing_events(self) -> frozenset[str] | None:
        """이 컴포넌트에서 나갈 수 있는 **합법 이벤트 이름** 집합 — Q30.

        ``None``은 "이 종류는 집합을 정의하지 않는다" = 검증 스킵이다. 빈
        집합(무엇도 나갈 수 없다)과 구분해야 하므로 `frozenset()`로 대신하지
        않는다.
        """
        return None

    # ── 참조 ──────────────────────────────────────────────────────────────

    def external_plugin_refs(self) -> list[str]:
        """이 컴포넌트가 배선을 요구하는 외부 플러그인 설치 id 목록 (정렬) — Q15."""
        return []

    @property
    def external_source(self) -> str | None:
        """외부 정본을 가리키는 원문(``플러그인:이름``) — 없으면 None (Q34)."""
        return None

    def delegated_agent_name(self) -> str | None:
        """본문을 실제로 실행하는 서브에이전트 이름 — 없으면 None (Q33)."""
        return None

    def hook_refs(self) -> list[str]:
        """참조하는 훅 이름 목록 — **삽입 순서 그대로** (Q24).

        정렬하지 않는다: `dangling_hook_ref` 경고가 "첫 등장 순서"로 나가는
        것이 오늘의 결정성 계약이다(`compiler/emit/hooks.py`). 정렬이 필요한
        호출자가 `sorted(...)`를 쓴다.

        **dict가 아닌 `hooks`는 "참조 없음"으로 답한다**(원칙 5). 역직렬화는
        `hooks`를 날것으로 싣기 때문에(`deser_plugin`은 강제 변환하지 않는다)
        손상된 `.daedalus.json`이 목록·문자열을 들고 들어올 수 있다. 여기서
        터지면 검증 패널과 MCP `compile_check`가 통째로 죽는다 — 깨진 사용자
        파일은 건드리지 않고 조용히 건너뛰는 것이 종전 동작이다.
        """
        hooks = self.config.hooks
        return list(hooks) if isinstance(hooks, dict) else []

    # ── 생성 ──────────────────────────────────────────────────────────────

    @classmethod
    def new(
        cls,
        name: str,
        description: str = "",
        *,
        fsm_factory: Callable[[str], StateMachine] | None = None,
        agent: str | None = None,
    ) -> PluginComponent:
        """레지스트리 팔레트·MCP `create_*`·캔버스 드롭이 공유할 **유일한 생성 경로**.

        오늘은 `view/actions/creation.make_component`의 kind별 람다 9개가 같은
        일을 하고 있다 — 종류마다 생성자 인수가 조금씩 다르다는 사실이 뷰에
        흩어져 있는 셈이고, 새 종류를 더하면 그 표를 고쳐야 한다.

        required 필드 `fsm`은 **dataclass 반영으로** 알아낸다. 믹스인
        (`WorkflowComponent`)에 훅을 두면 MRO에서 가려지므로(§10 R2) 반영을
        쓰되 **여기 한 곳**으로 제한한다.
        """
        kwargs: dict[str, Any] = {"name": name, "description": description}
        required = {
            f.name
            for f in dataclasses.fields(cls)
            if f.default is dataclasses.MISSING
            and f.default_factory is dataclasses.MISSING
        }
        if "fsm" in required:
            if fsm_factory is None:
                raise ValueError(
                    f"{cls.__name__}은(는) FSM이 필요합니다 — fsm_factory를 주세요."
                )
            kwargs["fsm"] = fsm_factory(name)
        kwargs.update(cls.creation_defaults(name=name, agent=agent))
        return cls(**kwargs)

    @classmethod
    def creation_defaults(cls, *, name: str, agent: str | None) -> dict[str, Any]:
        """**생성 시드** — dataclass 기본값과 다른 초기값 (기본 `{}`).

        dataclass 기본값은 "파일에서 읽을 때 키가 없으면 무엇인가"를 말하고,
        이 표는 "사용자가 새로 만들 때 무엇으로 시작하는가"를 말한다. 둘은
        같지 않다: 새 에이전트는 출력 포트 ``done`` 하나로 태어나야 하지만
        (없으면 배치 즉시 `transfer_on_not_empty` 에러), 저장 파일에 키가 없는
        에이전트에 포트를 **발명**하면 안 된다.
        """
        return {}


@dataclass
class WorkflowComponent(ABC):
    """FSM 보유 믹스인 — **필드 홀더다. 메서드를 두지 않는다.**

    여기 메서드를 두면 `StepSkill(Skill, WorkflowComponent)`의 MRO에서
    `PluginComponent`의 기본 구현이 **먼저** 잡혀 조용히 무시된다
    (REFACTOR_SPEC §10 R2). `state_machines()` 같은 형상 조회는 이 믹스인을
    섞는 **구체/중간 클래스**에서 오버라이드한다.
    `tests/model/plugin/test_capability_surface.py`가 이 규약을 고정한다.
    """

    fsm: StateMachine
