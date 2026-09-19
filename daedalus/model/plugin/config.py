from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.serial_fields import (
    BOOL,
    ENUM,
    ENUM_OPT,
    ENUM_OR_STR,
    LIST,
    RAW,
    STR,
    STR_OR_DEFAULT,
    FieldSpec,
)
from daedalus.model.plugin.enums import (
    AgentColor,
    AgentIsolation,
    EffortLevel,
    MemoryScope,
    ModelType,
    PermissionMode,
    SkillShell,
)


@dataclass
class ComponentConfig(ABC):
    """플러그인 컴포넌트 공통 설정 + **이름 참조 계약** (REFACTOR_SPEC §2-c).

    `KIND`는 config 종류 어휘("procedural")이고 컴포넌트의 `KIND`
    ("procedural_skill")와 **다른 벌**이다 — 저장 파일 포맷이 두 벌을 쓰기
    때문이고, 통일은 사용자 확정 대상이다(backlog). 여기서도 기본값을 주지
    않아 추상 config에서 읽으면 `AttributeError`가 난다(원칙 5).

    `name_refs`/`rename_ref`는 "이 설정이 **어느 네임스페이스의** 이름을
    가리키는가"를 설정 자신이 답하게 한다 (Q14). 오늘 `project.rename_component`
    는 `isinstance(cfg, ForkSkillConfig)` / `isinstance(cfg, AgentConfigBase)`
    두 분기로 같은 일을 하고, 새 설정 종류가 이름 참조를 가지면 그 함수를
    고쳐야 한다는 사실을 아무도 알려 주지 않는다. 네임스페이스를 인수로 받는
    이유는 **동명-다른타입**(스킬 "x"와 에이전트 "x")이 공존할 수 있어서다 —
    네임스페이스를 안 보면 무관한 참조를 오갱신한다.

    `SERIALIZED_FIELDS`는 "이 설정이 저장 파일에 무엇을 어떤 순서로 쓰는가"의
    단일 진실이다 (WP-4). **MRO 역순 누적이 아니라 각 클래스가 명시 튜플로
    선언한다** — 누적이면 선언 순서와 JSON 키 순서가 상속 그래프에 숨어 버리고,
    오늘 `AgentConfig`처럼 `color`가 `background`보다 **앞**에 나가는(필드 순서와
    다른) 사실을 표현할 수 없다. 선언 순서 = JSON 키 순서다.
    """

    KIND: ClassVar[str]
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        # `model`의 키 부재값은 **None**이다 — dataclass 기본값(INHERIT)과 다르다.
        # 오늘의 결함이지만(backlog D10) 고치면 저장 파일 해석이 바뀌므로 보존한다.
        FieldSpec("model", ENUM_OR_STR(ModelType), missing=None),
        FieldSpec("effort", ENUM_OPT(EffortLevel)),
        FieldSpec("hooks", RAW),
    )

    model: ModelType | str = ModelType.INHERIT
    effort: EffortLevel | None = None
    # hooks: 키 = PluginProject.hook_library의 HookDef.name 참조,
    #        값 = 오버라이드 dict (빈 dict면 HookDef 정의 그대로 사용).
    # 이름 참조 규약은 tool_shelf 선례와 동일하며, 빈 dict 본문 보존 write-back
    # (skill_editor의 {name: existing.get(name, {})})과 자연 호환된다.
    hooks: dict[str, Any] | None = None

    @property
    @abstractmethod
    def kind(self) -> str:
        """설정 종류 식별자 — 구체 클래스는 ``return self.KIND``."""

    # ── 직렬화 (WP-4 — `_ser_config`/`_deser_config` 사다리를 흡수했다) ──

    def to_dict(self) -> dict[str, Any]:
        """설정 → JSON 호환 dict. 첫 키는 다형성 태그 `kind`."""
        out: dict[str, Any] = {"kind": self.kind}
        for spec in type(self).SERIALIZED_FIELDS:
            out[spec.name] = spec.codec.encode(getattr(self, spec.name))
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Any:
        """저장 dict → 설정. 키 부재는 `FieldSpec.missing`(기본: dataclass 기본값).

        `kind`는 여기서 보지 않는다 — 어느 클래스로 읽을지는 호출자가 레지스트리
        (`kinds.spec_by_config_kind`)로 이미 정했다. 여기서 또 물으면 같은 판정이
        두 곳에 생긴다(원칙 1).
        """
        kwargs: dict[str, Any] = {}
        for spec in cls.SERIALIZED_FIELDS:
            use, value = spec.read(d)
            if use:
                kwargs[spec.name] = value
        return cls(**kwargs)

    def name_refs(self, namespace: Bucket) -> list[str]:
        """이 설정이 가리키는 ``namespace`` 컴포넌트 이름 목록 (기본 없음)."""
        return []

    def rename_ref(self, namespace: Bucket, old: str, new: str) -> None:
        """``namespace``의 이름 ``old``를 ``new``로 **제자리** 치환 (기본 무동작)."""
        return None


@dataclass
class SkillConfig(ComponentConfig, ABC):
    """스킬 공통 프론트매터."""

    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        ComponentConfig.SERIALIZED_FIELDS
        + (
            FieldSpec("argument_hint", RAW),
            FieldSpec("allowed_tools", LIST),
            FieldSpec("paths", RAW),
        )
    )

    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    paths: list[str] | None = None


@dataclass
class StepSkillConfig(SkillConfig, ABC):
    """워크플로 **단계** 스킬의 공통 설정 — 절차형·fork 2종의 부모.

    `kind`를 정의하지 않으므로 추상이다(인스턴스화 금지) — 종류를 말하지 않는
    단계 설정은 존재하지 않는다.
    """

    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        SkillConfig.SERIALIZED_FIELDS
        + (
            FieldSpec("disable_model_invocation", RAW),
            FieldSpec("user_invocable", RAW),
            FieldSpec("shell", ENUM(SkillShell, SkillShell.BASH)),
        )
    )

    # 진입 의미론 두 필드는 **tri-state**다 (A8): None = 미지정(프론트매터 키 생략 →
    # CC 기본값에 위임) / True·False = 명시 지정. 순수 bool이면 "기본값을 쓴다"와
    # "기본값과 같은 값을 못 박았다"가 구분되지 않아, 캔버스 프리셋의 "일반 상태로"
    # (두 필드 미지정)를 표현할 수 없다. 컴파일은 기존 규칙 그대로 동작한다 —
    # "OPTIONAL 값이 선언 기본값과 같으면 생략"에서 선언 기본값이 None이 되므로
    # None은 생략되고 명시 True/False는 발행된다(`user-invocable: true`가 나가는 것은
    # 사용자가 진입점으로 못 박았다는 뜻이라 정상이다).
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None
    shell: SkillShell = SkillShell.BASH


@dataclass
class ProceduralSkillConfig(StepSkillConfig):
    KIND: ClassVar[str] = "procedural"

    @property
    def kind(self) -> str:
        return self.KIND


#: CC 내장 서브에이전트 이름 — fork 스킬의 `agent`로 그대로 적는다. 정확 일치라
#: 대소문자까지 맞아야 한다(2026-09-13 실측, CC 2.1.268 — 없는 이름은 조용히
#: general-purpose로 떨어진다).
BUILTIN_FORK_AGENTS: tuple[str, ...] = ("general-purpose", "Explore", "Plan")


@dataclass
class ForkSkillConfig(StepSkillConfig, ABC):
    """fork 스킬 공통 — 본문을 작업 지시로 삼아 `agent` 서브에이전트에서 실행된다.

    ``agent``는 세 종류 중 하나의 이름이다(사용자 확정 2026-09-13): 내장
    (`BUILTIN_FORK_AGENTS`), 사용 선언한 외부 플러그인의 에이전트
    (``플러그인:이름``), 프로젝트의 **fork 에이전트**. 산출 이름
    (마켓 ``플러그인:이름`` / LOCAL ``이름``)은 컴파일러가 정한다.
    ``allowed_tools``는 필드 매트릭스에 없다 — fork에서는 에이전트 도구가
    이겨 효과가 없다(실측).

    **추상이다** — `background` 값이 동기/비동기를 가르고(사용자 확정
    2026-09-17) 그 값은 매트릭스 전용 FIXED 필드라 config에 두지 않는다.
    즉 "어느 fork인가"는 구체 클래스(= `kind`)만이 답한다.
    """

    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        StepSkillConfig.SERIALIZED_FIELDS
        + (FieldSpec("agent", STR_OR_DEFAULT("general-purpose")),)
    )

    agent: str = "general-purpose"

    def name_refs(self, namespace: Bucket) -> list[str]:
        """``agent``는 **에이전트** 이름 참조다 — 내장 이름·외부 플러그인 이름 포함."""
        if namespace is Bucket.AGENTS:
            return [self.agent]
        return []

    def rename_ref(self, namespace: Bucket, old: str, new: str) -> None:
        if namespace is Bucket.AGENTS and self.agent == old:
            self.agent = new


@dataclass
class SyncForkSkillConfig(ForkSkillConfig):
    """동기 fork — `background: false`. 부른 쪽이 보고를 기다린다."""

    KIND: ClassVar[str] = "sync_fork"

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class AsyncForkSkillConfig(ForkSkillConfig):
    """비동기 fork — `background: true`. 보고는 작업 알림으로 뒤늦게 온다."""

    KIND: ClassVar[str] = "async_fork"

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class WrappedSkillConfig(SkillConfig):
    """스킬 랩핑 (WP-WR) — 다른 플러그인 스킬의 절차 재사용.

    ``source``가 핵심이다: ``<플러그인>:<스킬>`` 문자열 참조로, 본문의 정본은
    그 스킬이고 랩퍼는 워크플로 위치·배선·프론트매터만 소유한다(사용자 확정 —
    본문 수정 불가). 진입 의미론 tri-state는 ProceduralSkillConfig와 동일.

    ``usage``(사용자 확정 2026-09-07): ""(미정) / "state" / "reference".
    최초 배치 시 사용자가 고르면 **고정**된다 — 한 랩핑 스킬이 워크플로
    단계와 참조 두 용도로 동시에 쓰이는 것을 막는다. state는 단일 배치 +
    SKILL.md 산출(현행), reference는 참조 노드 복수 배치 + **산출 파일 없음**
    (링크된 노드의 산출에 consult 지시만 합류). 배치 경로가 고정하는 파생
    상태라 프론트매터로 나가지 않고 매트릭스에도 없다(set_component_field
    거부). 구버전 파일(키 부재)은 "state"로 로드된다 — 그때는 state만 있었다.

    ``enabled``(사용자 확정 2026-09-07 — "삭제가 불가능하게 해라. 삭제 대신
    비활성화"): 랩핑 스킬은 **지울 수 없고** 이 스위치로 끈다. 소스·프론트매터·
    배선을 다시 입력하는 비용이 큰 데다, 지우면 이 프로젝트가 그 외부 스킬을
    한때 썼다는 사실 자체가 사라진다. `False`면 산출에서 빠지고(state 용도는
    SKILL.md 미산출, reference 용도는 consult 지시 미합류) 외부 플러그인 배선
    판정에서도 참조로 치지 않는다 — 꺼둔 것은 쓰지 않는 것이다. 구버전
    파일(키 부재)은 True.
    """
    KIND: ClassVar[str] = "wrapped"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        SkillConfig.SERIALIZED_FIELDS
        + (
            # `source`는 **RAW**다 — 저장 파일의 명시적 `null`이 그대로 들어오는
            # 것이 오늘의 계약이고, 그 날것을 견디는 쪽은
            # `WrappedSkill.external_source` 하나다(원칙 1).
            FieldSpec("source", RAW),
            # 키 부재는 구버전 파일 — 그때는 state 용도만 있었다.
            FieldSpec("usage", STR, missing="state"),
            FieldSpec("enabled", BOOL),
            FieldSpec("disable_model_invocation", RAW),
            FieldSpec("user_invocable", RAW),
        )
    )
    #: ``usage``의 "참조 용도" 값. 판정하는 쪽이 리터럴을 복제하면 값이 바뀔 때
    #: 한쪽만 고쳐져 조용히 어긋난다 — 선언은 값을 가진 클래스에 둔다.
    USAGE_REFERENCE: ClassVar[str] = "reference"

    source: str = ""
    usage: str = ""
    enabled: bool = True
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class DeclarativeSkillConfig(SkillConfig):
    KIND: ClassVar[str] = "declarative"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        SkillConfig.SERIALIZED_FIELDS
        + (
            FieldSpec("disable_model_invocation", RAW),
            FieldSpec("user_invocable", RAW),
        )
    )

    # tri-state — ProceduralSkillConfig의 같은 필드 주석 참조 (A8).
    disable_model_invocation: bool | None = None
    user_invocable: bool | None = None

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class AgentConfigBase(ComponentConfig, ABC):
    """에이전트 두 종류(워크플로/fork)의 공통 설정.

    `color`는 **여기 두지 않는다** — 두 구체 클래스가 각자 마지막에 선언해야
    `AgentConfig`의 필드 순서가 종전(`… memory, background, isolation, color`)과
    같아진다(2026-09-17 실측).
    """

    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        ComponentConfig.SERIALIZED_FIELDS
        + (
            FieldSpec("tools", RAW),
            FieldSpec("disallowed_tools", RAW),
            FieldSpec(
                "permission_mode", ENUM(PermissionMode, PermissionMode.DEFAULT)
            ),
            FieldSpec("max_turns", RAW),
            FieldSpec("skills", LIST),
            FieldSpec("mcp_servers", RAW),
            FieldSpec("memory", ENUM_OPT(MemoryScope)),
        )
    )

    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    max_turns: int | None = None
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] | None = None  # MCP 서버 이름 참조 목록 — 서버 정의 자체는 .mcp.json 등 외부 소유, 모델은 이름만 참조
    memory: MemoryScope | None = None

    def name_refs(self, namespace: Bucket) -> list[str]:
        """``skills``는 **스킬** 이름 참조 목록이다."""
        if namespace is Bucket.SKILLS and isinstance(self.skills, list):
            return list(self.skills)
        return []

    def rename_ref(self, namespace: Bucket, old: str, new: str) -> None:
        if namespace is Bucket.SKILLS and isinstance(self.skills, list):
            self.skills = [new if s == old else s for s in self.skills]


@dataclass
class AgentConfig(AgentConfigBase):
    """워크플로 에이전트(캔버스 노드) 설정."""

    KIND: ClassVar[str] = "agent"
    #: `color`가 `background`·`isolation`보다 **앞**이다 — dataclass 필드 순서와
    #: 다르지만 저장 파일의 키 순서가 그렇다(바꾸면 JSON 바이트가 바뀐다).
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        AgentConfigBase.SERIALIZED_FIELDS
        + (
            FieldSpec("color", ENUM_OPT(AgentColor)),
            FieldSpec("background", RAW),
            FieldSpec("isolation", ENUM(AgentIsolation, AgentIsolation.NONE)),
        )
    )

    background: bool = False
    isolation: AgentIsolation = AgentIsolation.NONE
    color: AgentColor | None = None

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class ForkAgentConfig(AgentConfigBase):
    """fork 에이전트 설정 — fork 스킬의 실행 기반.

    `background`·`isolation`이 없다: 백그라운드 여부는 **스킬 종류**가 정하고
    (sync/async fork), isolation은 fork 실행에 적용되지 않는다(실측 2026-09-13,
    CC 2.1.268). 없는 필드를 두면 걸어 둔 제약이 조용히 사라진다(원칙 5).
    """

    KIND: ClassVar[str] = "fork_agent"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        AgentConfigBase.SERIALIZED_FIELDS + (FieldSpec("color", ENUM_OPT(AgentColor)),)
    )

    color: AgentColor | None = None

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class ExternalAgentConfig(ComponentConfig):
    """외부 플러그인 서브에이전트 설정 (WP-9) — 우리가 소유하는 값은 `source` 하나다.

    **`AgentConfigBase`를 상속하지 않는다.** tools·skills·permission_mode·color·
    max_turns 따위는 전부 **그 플러그인이 소유한 파일**의 값이다. 우리 쪽에
    칸을 만들어 두면 사용자가 채워 넣고도 아무 일이 일어나지 않는다 — 산출
    파일이 없으니 배출될 자리 자체가 없다(원칙 5: 조용한 no-op 금지).

    기저의 `model`/`effort`/`hooks`는 상속되지만 `AGENT_FIELD_MATRIX`의
    `external_agent` 행에 없어 편집기·MCP가 노출하지 않는다 — 같은 이유다.

    `source`는 ``플러그인[@마켓]:에이전트`` 원문이고, 이것이 곧 **CC가 그
    서브에이전트를 찾는 이름**이다(정확 일치). 형식 검사는
    `validation.project_rules.naming._check_external_sources`가,
    사용 선언 검사는 `_check_external_plugins`가 맡는다 — 둘 다 종류를 묻지
    않고 `external_source`/`external_plugin_refs()`만 본다.
    """

    KIND: ClassVar[str] = "external_agent"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        ComponentConfig.SERIALIZED_FIELDS + (FieldSpec("source", STR),)
    )

    source: str = ""

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class TransferSkillConfig(SkillConfig):
    """전이 엣지 전용 스킬 설정. user_invocable은 항상 False (UI 노출 불필요)."""

    KIND: ClassVar[str] = "transfer"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        SkillConfig.SERIALIZED_FIELDS
        + (
            FieldSpec("disable_model_invocation", RAW),
            FieldSpec("user_invocable", RAW),
            FieldSpec("shell", ENUM(SkillShell, SkillShell.BASH)),
        )
    )

    disable_model_invocation: bool = False
    user_invocable: bool = False   # fixed — transfer skills are never user-invocable
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class ReferenceSkillConfig(SkillConfig):
    """참조 스킬 설정. 워크플로우에 참여하지 않는 참고용 노드."""

    KIND: ClassVar[str] = "reference"
    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        SkillConfig.SERIALIZED_FIELDS + (FieldSpec("user_invocable", RAW),)
    )

    user_invocable: bool = False

    @property
    def kind(self) -> str:
        return self.KIND


