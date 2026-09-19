from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from daedalus.model.plugin.roles import Bucket
from daedalus.model.plugin.serial_fields import (
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


def is_external_skill_ref(name: str) -> bool:
    """``config.skills`` 항목이 **외부 플러그인 스킬** 참조인가 — ``플러그인:스킬``.

    콜론이 있으면 외부 참조다(WP-B, 사용자 확정 2026-09-19 — 외부 플러그인
    스킬의 사용 경로는 fork 에이전트 ``skills:`` 프론트매터 하나뿐이다).
    프로젝트 컴포넌트 이름은 ``^[a-z0-9][a-z0-9-]*$``라 콜론을 가질 수 없으므로
    오검출이 없다. ``@마켓``은 붙이지 않는다 — CC가 fork 에이전트 ``skills:``로
    프리로드하는 이름이 그 형식이다(실측, CC 2.1.278 — `plugin-model.md`).
    """
    return ":" in name


def bare_plugin_id(plugin_id: str) -> str:
    """설치 식별자(``플러그인[@마켓]``)에서 ``@마켓``을 뗀 플러그인 이름."""
    return plugin_id.partition("@")[0]


def plugin_ids_match(a: str, b: str) -> bool:
    """설치 식별자 둘이 같은 플러그인을 가리키는가 — **매칭 정책의 단일 진실**.

    정확 일치, 또는 **한쪽만 bare**일 때 bare 이름 일치다. 양쪽 다 마켓을
    달고 있으면 정확 일치만 인정한다(``alpha@mkt1`` ≠ ``alpha@mkt2`` — 다른
    설치 대상). 완화가 필요한 이유는 카탈로그 자신이 마켓 표기를 **비대칭**으로
    내기 때문이다: 선언(`external_plugins`)은 ``플러그인@마켓``이고, 에이전트
    `agent_type`·스킬 `skill_ref`는 CC가 찾는 이름 그대로 ``플러그인:이름``
    (bare)이다(WP-9·WP-B 실측). 그 표준 경로를 따르기만 해도 경고가 뜨면
    안 된다(원칙 5 — 경고는 진짜 불일치에만). 참조의 출처(``source``냐
    ``skills`` 항목이냐)로 정책을 가르지 않는다(원칙 1, 2026-09-19 리뷰).
    """
    if a == b:
        return True
    if "@" in a and "@" in b:
        return False
    return bare_plugin_id(a) == bare_plugin_id(b)


def external_source_refs_match(a: str, b: str) -> bool:
    """외부 정본 참조 둘(``플러그인[@마켓]:이름``)이 **같은 대상**을 가리키는가.

    플러그인 부분은 `plugin_ids_match`(마켓 표기 비대칭 완화)로, 이름 부분은
    정확 일치로 본다 — 카탈로그가 내는 `agent_type`은 bare(``hookify:doctor``)
    인데 사용자가 선언한 `source`는 마켓을 달고 있을 수 있고(``hookify@mkt:doctor``),
    그 둘을 다르게 세면 **이미 등록한 에이전트가 미등록 목록에 또 나온다**.

    이름에 콜론이 더 있을 수 있다(에이전트 하위 폴더 — ``plugin:review:security``)
    므로 **첫 콜론**에서만 가른다. 콜론이 없는 참조는 형식이 깨진 것이라
    원문 정확 일치로만 같다고 본다.
    """
    plugin_a, sep_a, name_a = a.partition(":")
    plugin_b, sep_b, name_b = b.partition(":")
    if not sep_a or not sep_b:
        return a.strip() == b.strip()
    return name_a.strip() == name_b.strip() and plugin_ids_match(
        plugin_a.strip(), plugin_b.strip()
    )


def external_plugin_id_declared(plugin_id: str, declared: set[str]) -> bool:
    """``plugin_id``가 선언 집합의 어느 항목과 `plugin_ids_match`하는가."""
    return any(plugin_ids_match(plugin_id, d) for d in declared)


def declared_external_plugin_ids(project) -> set[str]:
    """`project.external_plugins` 선언을 공백 정리한 집합 (빈 항목 제외)."""
    return {
        str(p).strip()
        for p in getattr(project, "external_plugins", None) or []
        if str(p).strip()
    }


def external_skill_ref_has_marketplace(ref: str) -> bool:
    """외부 스킬 참조의 플러그인 부분에 ``@마켓``이 붙어 있는가.

    CC는 fork 에이전트 ``skills:``의 외부 스킬을 마켓 표기 **없는** 이름으로
    찾는다(실측, CC 2.1.278). 붙이면 산출은 원문 그대로 나가고 런타임에
    조용히 해소되지 않으므로 검증이 짚는다(`external_skill_ref_marketplace`).
    """
    return is_external_skill_ref(ref) and "@" in ref.partition(":")[0]


def normalize_external_skill_ref(ref: str) -> str:
    """외부 스킬 참조를 CC가 찾는 형식 ``플러그인:스킬``(bare)로 정규화한다."""
    plugin_id, sep, skill_name = ref.partition(":")
    if not sep:
        return ref
    return f"{bare_plugin_id(plugin_id.strip())}:{skill_name.strip()}"


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

    def external_skill_refs(self) -> list[str]:
        """이 설정의 **외부 플러그인 스킬 참조**(``플러그인:스킬`` 원문) 목록 (기본 없음).

        `AgentConfigBase`만 오버라이드한다(``skills`` 항목, WP-B).
        """
        return []

    def external_plugin_refs(self) -> list[str]:
        """이 설정이 배선을 요구하는 외부 플러그인 설치 id 목록 (기본 없음).

        `PluginComponent.external_plugin_refs()`의 기본 구현이 이것을 그대로
        돌려준다 — 컴포넌트가 다른 외부 정본(`ExternalAgent.source`)을 가지면
        그 클래스가 오버라이드한다. 매칭 정책은 출처와 무관하게 하나다
        (`plugin_ids_match`).
        """
        return []


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
        """``skills``는 **프로젝트 스킬** 이름 참조 목록이다 — 외부 플러그인
        참조(``플러그인:스킬``, WP-B)는 **제외**한다.

        포함시키면 프로젝트에 그 이름의 스킬이 없다는 이유로
        `dangling_string_reference`가 오탐하고, `rename_ref`가 무관한
        문자열을 건드릴 뻔한다(콜론 때문에 실제로는 안 맞지만 판단 자체가
        틀린 자리에 있으면 안 된다 — 원칙 1). 배선 필요 여부는
        `external_plugin_refs()`가 대신 답한다.
        """
        if namespace is Bucket.SKILLS and isinstance(self.skills, list):
            return [s for s in self.skills if not is_external_skill_ref(s)]
        return []

    def rename_ref(self, namespace: Bucket, old: str, new: str) -> None:
        if namespace is Bucket.SKILLS and isinstance(self.skills, list):
            self.skills = [new if s == old else s for s in self.skills]

    def external_skill_refs(self) -> list[str]:
        """``skills`` 항목 중 외부 플러그인 스킬 참조(``플러그인:스킬``) 원문.

        형식이 깨진 참조(플러그인 부분이 비었거나 스킬 이름이 없음)는
        건너뛴다 — CC가 못 찾으면 조용히 무시하는 실패이고, 이 종류의 참조에는
        `external_source_missing`류의 전용 경고가 없다(참조는 콜론 유무로만
        외부/내부를 가른다).
        """
        refs: list[str] = []
        for s in self.skills if isinstance(self.skills, list) else []:
            if not is_external_skill_ref(s):
                continue
            plugin_id, _, skill_name = s.partition(":")
            if plugin_id.strip() and skill_name.strip():
                refs.append(s)
        return refs

    def external_plugin_refs(self) -> list[str]:
        """외부 스킬 참조가 가리키는 플러그인 설치 id — 참조에 적힌 **원문 그대로**
        (``@마켓``을 떼지 않는다 — 떼면 `external_skill_ref_marketplace` 경고와
        어긋난 사실을 검증이 못 본다). 선언과의 대조는 `plugin_ids_match`."""
        return [ref.partition(":")[0].strip() for ref in self.external_skill_refs()]


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
class ExternalSourceConfig(ComponentConfig, ABC):
    """정본이 **외부 플러그인**에 있는 컴포넌트의 공통 설정 — 우리가 소유하는
    값은 `source` 하나다 (WP-EX).

    **`AgentConfigBase`를 상속하지 않는다.** tools·skills·permission_mode·color·
    max_turns 따위는 전부 **그 플러그인이 소유한 파일**의 값이다. 우리 쪽에
    칸을 만들어 두면 사용자가 채워 넣고도 아무 일이 일어나지 않는다 — 산출
    파일이 없으니 배출될 자리 자체가 없다(원칙 5: 조용한 no-op 금지).

    기저의 `model`/`effort`/`hooks`는 상속되지만 `AGENT_FIELD_MATRIX`의
    외부 행들에 없어 편집기·MCP가 노출하지 않는다 — 같은 이유다.

    `source`는 ``플러그인[@마켓]:에이전트`` 원문이고, 이것이 곧 **CC가 그
    서브에이전트를 찾는 이름**이다(정확 일치). 형식 검사는
    `validation.project_rules.naming._check_external_sources`가,
    사용 선언 검사는 `_check_external_plugins`가, 같은 source를 두 역할로
    등록했는지는 `_check_external_source_roles`가 맡는다 — 전부 종류를 묻지
    않고 `external_source`/`external_plugin_refs()`만 본다.

    **추상이다** — 두 구체 설정(그래프 노드 / fork 실행 기반)은 필드가 같고
    `KIND`만 다르다. 한쪽이 다른 쪽을 상속하면 "구체가 구체를 상속한다"가 되어
    `isinstance(cfg, ExternalAgentConfig)`가 두 역할을 함께 잡는다 — 역할을
    고정하려고 종류를 나눈 의미가 사라진다(사용자 확정 2026-09-19).
    """

    SERIALIZED_FIELDS: ClassVar[tuple[FieldSpec, ...]] = (
        ComponentConfig.SERIALIZED_FIELDS + (FieldSpec("source", STR),)
    )

    source: str = ""


@dataclass
class ExternalAgentConfig(ExternalSourceConfig):
    """외부 플러그인 서브에이전트를 **그래프 노드**로 쓸 때의 설정 (WP-9)."""

    KIND: ClassVar[str] = "external_agent"

    @property
    def kind(self) -> str:
        return self.KIND


@dataclass
class ExternalForkAgentConfig(ExternalSourceConfig):
    """외부 플러그인 서브에이전트를 **fork 실행 기반**으로 쓸 때의 설정 (WP-EX).

    `ExternalAgentConfig`와 필드는 같고 `KIND`만 다르다 — 그 차이가 곧
    **역할 고정**이다(같은 source를 두 역할로 등록할 수 없다).
    """

    KIND: ClassVar[str] = "external_fork_agent"

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


