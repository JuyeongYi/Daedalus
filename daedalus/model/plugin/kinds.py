# daedalus/model/plugin/kinds.py
"""컴포넌트 **종류 레지스트리** — 등록 지점 단일화 (REFACTOR_SPEC §3).

오늘 "종류가 몇 가지인가"라는 사실은 최소 여섯 벌로 흩어져 있었다: 역직렬화의
`step_kinds`·`_CONFIG_KINDS`·"사용 가능" 문구 2개, 뷰의 생성 람다 9개와 전환
표 2개, MCP의 `_SKILL_KINDS`/`_AGENT_KINDS`. 표가 여러 벌이면 새 종류를 더할 때
**어디를 고쳐야 하는지 아무도 말해 주지 않고**, 빠뜨린 자리는 예외가 아니라
조용한 부재가 된다 — 레지스트리에 없는 종류는 MCP가 "알 수 없는 종류"로
거절하고, 팔레트에서 사라지고, 파일에서 읽히지 않는다(👻).

그래서 등록 지점은 **`COMPONENT_CLASSES` 튜플 하나**다. 나머지는 전부 파생이고,
`tests/test_kind_registry_parity.py`가 파생된 집합들이 서로 같은지를 양방향으로
고정한다. `tests/model/plugin/test_registry_discovery.py`는 pkgutil로 패키지를
훑어 **구체 서브클래스 집합 == COMPONENT_CLASSES**를 강제한다 — 새 종류를 만들고
튜플에 올리는 것을 잊으면 그 자리에서 실패한다.

**`__init_subclass__` 자동 등록을 쓰지 않는 이유**(§0-c): ① 모듈이 임포트되지
않으면 등록도 안 돼 조용한 부재가 그대로 남고 ② `@dataclass` 적용 **전**에 돌아
`fields()`를 볼 수 없다. 명시 튜플 한 줄이 더 싸고 시끄럽다.

**임포트 방향.** `roles ← base ← config ← skill/agent ← kinds`(+`field_matrix`).
`kinds`는 plugin 패키지의 **리프 소비자**다 — 어느 plugin 모듈도 이것을 임포트하지
않는다. 그 규칙이 깨지면 곧바로 순환이다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any

from daedalus.model.plugin.agent import AgentDefinition, ExternalAgent, ForkAgent
from daedalus.model.plugin.base import PluginComponent
from daedalus.model.plugin.config import ComponentConfig
from daedalus.model.plugin.field_matrix import (
    AGENT_FIELD_MATRIX,
    SKILL_FIELD_MATRIX,
    FieldRule,
)
from daedalus.model.plugin.roles import (
    BodySource,
    Bucket,
    OutputLocation,
    PlacementRole,
)
from daedalus.model.plugin.skill import (
    AsyncForkSkill,
    DeclarativeSkill,
    ProceduralSkill,
    ReferenceSkill,
    SyncForkSkill,
    TransferSkill,
    WrappedSkill,
)


@dataclass(frozen=True)
class KindSpec:
    """한 종류에 대해 **모든 계층이 묻는 것**을 한 행에 모은 값 객체.

    필드는 전부 클래스 선언(`§2-b`의 ClassVar)과 `field_matrix`에서 **파생**된다 —
    여기에 손으로 값을 적는 칸은 하나도 없다. 레지스트리가 사실을 새로 발명하면
    클래스와 레지스트리가 어긋나고, 그 어긋남은 아무도 알려 주지 않는다.

    `field_matrix`는 `MappingProxyType` **읽기 전용 뷰**다 — 살아 있는 dict를
    그대로 들려주면 한 호출자의 제자리 수정이 모듈 표를 오염시킨다(그리고 그
    오염은 다음 컴파일에서야 드러난다).
    """

    kind: str
    """저장 파일의 `kind` 값 — 1차 키 ("procedural_skill")."""
    config_kind: str
    """config 종류 어휘 — 매트릭스 키 / MCP·팔레트 어휘 ("procedural")."""
    bucket: Bucket
    component_cls: type[PluginComponent]
    config_cls: type[ComponentConfig]
    field_matrix: Mapping[Enum, FieldRule]
    placement: PlacementRole
    """**선언** 기본값. 인스턴스 판정은 `component.effective_placement()`."""
    output_location: OutputLocation
    body_source: BodySource
    convert_family: str | None
    delegation_target: bool
    runs_in_subagent: bool
    reports_out_of_band: bool
    is_fork_base: bool

    @classmethod
    def from_class(cls, component_cls: type[PluginComponent]) -> KindSpec:
        """구체 컴포넌트 클래스 한 개에서 행을 만든다 — 손으로 적는 값은 없다.

        Raises:
            ValueError: 그 config 종류에 프론트매터 표가 없을 때. 표 없이
                등록되면 편집기·컴파일러가 **조용히 빈 폼/빈 프론트매터**를
                만든다(원칙 5 — 거절은 이유와 고칠 자리를 말한다).
        """
        config_cls = component_cls.CONFIG_CLS
        bucket = component_cls.BUCKET
        table = SKILL_FIELD_MATRIX if bucket is Bucket.SKILLS else AGENT_FIELD_MATRIX
        if config_cls.KIND not in table:
            table_name = "SKILL" if bucket is Bucket.SKILLS else "AGENT"
            raise ValueError(
                f"'{component_cls.__name__}'의 config 종류 "
                f"'{config_cls.KIND}'에 프론트매터 표가 없습니다 — "
                f"field_matrix.py의 {table_name}_FIELD_MATRIX에 행을 추가하세요."
            )
        return cls(
            kind=component_cls.KIND,
            config_kind=config_cls.KIND,
            bucket=bucket,
            component_cls=component_cls,
            config_cls=config_cls,
            field_matrix=MappingProxyType(table[config_cls.KIND]),
            placement=component_cls.PLACEMENT,
            output_location=component_cls.OUTPUT_LOCATION,
            body_source=component_cls.BODY_SOURCE,
            convert_family=component_cls.CONVERT_FAMILY,
            delegation_target=component_cls.DELEGATION_TARGET,
            runs_in_subagent=component_cls.RUNS_IN_SUBAGENT,
            reports_out_of_band=component_cls.REPORTS_OUT_OF_BAND,
            is_fork_base=component_cls.IS_FORK_BASE,
        )


#: **유일한 등록 지점.** 선언 순서 = 팔레트 탭 순서 = MCP 안내 문구 순서다
#: (결정성 — 같은 질문에 같은 순서로 답한다). 새 종류는 여기 한 줄이 전부이고,
#: 빠뜨리면 `test_registry_discovery`가 이름을 찍고 실패한다.
COMPONENT_CLASSES: tuple[type[PluginComponent], ...] = (
    ProceduralSkill,
    SyncForkSkill,
    AsyncForkSkill,
    DeclarativeSkill,
    TransferSkill,
    ReferenceSkill,
    WrappedSkill,
    AgentDefinition,
    ForkAgent,
    ExternalAgent,
)


def _build_registry() -> dict[str, KindSpec]:
    """`COMPONENT_CLASSES` → kind별 행. 중복 KIND는 **즉시** ValueError다.

    중복을 허용하면 뒤에 선언된 종류가 앞의 것을 조용히 덮어써 파일에서 읽히는
    클래스가 바뀐다 — 저장·산출이 통째로 다른 물건이 된다.
    """
    registry: dict[str, KindSpec] = {}
    for component_cls in COMPONENT_CLASSES:
        spec = KindSpec.from_class(component_cls)
        if spec.kind in registry:
            raise ValueError(
                f"종류 '{spec.kind}'가 두 번 등록됐습니다 — "
                f"{registry[spec.kind].component_cls.__name__}와 "
                f"{component_cls.__name__}."
            )
        registry[spec.kind] = spec
    return registry


#: 컴포넌트 `KIND` → 행. 삽입 순서 = 선언 순서.
KIND_REGISTRY: dict[str, KindSpec] = _build_registry()

#: config `KIND` → 행. 두 어휘가 짝이라는 사실의 반대 방향 색인이다.
CONFIG_KIND_INDEX: dict[str, KindSpec] = {
    spec.config_kind: spec for spec in KIND_REGISTRY.values()
}

#: 진단 문구에서 버킷을 부르는 말 — 거절은 **무엇의** 종류인지까지 말한다.
_BUCKET_LABEL: dict[Bucket, str] = {
    Bucket.SKILLS: "스킬",
    Bucket.AGENTS: "에이전트",
}

#: 버킷 → `PluginProject`의 목록 속성 이름.
_BUCKET_ATTR: dict[Bucket, str] = {
    Bucket.SKILLS: "skills",
    Bucket.AGENTS: "agents",
}


def spec_for(component: object) -> KindSpec:
    """이 **인스턴스**의 종류 행.

    종류 행이 없는 값은 `TypeError`다(이유 포함) — 여기서 관용하면 호출자가
    "왜 스킬 목록에 들어갔지"를 한참 뒤에야 알게 된다. 비-컴포넌트를 관용해야
    하는 자리는 `placement.placement_role_of` 하나이고 그쪽은 배치 질문 전용이다.

    `PluginComponent`는 스킬·에이전트보다 **넓다** — `Tool`·`HookDef`도 같은
    기저에서 name/description/kind를 물려받는다. 그래서 상속만으로는 부족하고
    `KIND` 선언까지 봐야 한다(`Tool`·`HookDef`는 선언하지 않는다).
    """
    kind = (
        getattr(type(component), "KIND", None)
        if isinstance(component, PluginComponent)
        else None
    )
    if kind is None:
        raise TypeError(
            f"{type(component).__name__}은(는) 종류 행을 가진 플러그인 "
            f"컴포넌트(스킬·에이전트)가 아닙니다."
        )
    return spec_by_kind(kind)


def spec_by_kind(
    kind: object, *, bucket: Bucket | None = None, subject: str = ""
) -> KindSpec:
    """컴포넌트 `kind` 문자열 → 행. 미지 종류는 **이유와 선택지**를 말한다.

    `bucket`을 주면 그 버킷의 종류로 좁힌다 — 스킬 목록에 `"agent"`가 적힌
    파일이 조용히 에이전트를 만들어 내지 않게 하는 게이트다. `subject`는
    "스킬 'foo'" 꼴의 맥락으로, 어느 항목이 문제인지 문구에 실린다.
    """
    available = kinds_in(bucket) if bucket is not None else tuple(KIND_REGISTRY)
    spec = KIND_REGISTRY.get(kind) if isinstance(kind, str) else None
    if spec is None or (bucket is not None and spec.bucket is not bucket):
        label = _BUCKET_LABEL.get(bucket) if bucket is not None else None
        head = f"알 수 없는 {label} 종류" if label else "알 수 없는 종류"
        where = f" ({subject})" if subject else ""
        raise ValueError(
            f"{head}: {kind!r}{where}. 사용 가능: {', '.join(available)}"
        )
    return spec


def spec_by_config_kind(kind: object) -> KindSpec:
    """config `kind` 문자열 → 행 (`matrix_for`와 같은 거절 정책)."""
    spec = CONFIG_KIND_INDEX.get(kind) if isinstance(kind, str) else None
    if spec is None:
        raise ValueError(
            f"알 수 없는 config 종류: {kind!r}. "
            f"사용 가능: {', '.join(CONFIG_KIND_INDEX)}"
        )
    return spec


def kinds_in(bucket: Bucket) -> tuple[str, ...]:
    """이 버킷의 컴포넌트 `kind` 튜플 — **선언 순서**."""
    return tuple(k for k, spec in KIND_REGISTRY.items() if spec.bucket is bucket)


def config_kinds_in(bucket: Bucket) -> tuple[str, ...]:
    """이 버킷의 config `kind` 튜플 — MCP `create_*`·팔레트가 쓰는 어휘."""
    return tuple(
        spec.config_kind for spec in KIND_REGISTRY.values() if spec.bucket is bucket
    )


def convert_family_kinds(family: str | None) -> tuple[str, ...]:
    """`__class__` 전환이 가능한 같은 가족의 config `kind` 튜플.

    `family`가 `None`이면 빈 튜플이다 — "전환 가족에 속하지 않는다"는 답이지
    "모든 종류"가 아니다.
    """
    if family is None:
        return ()
    return tuple(
        spec.config_kind
        for spec in KIND_REGISTRY.values()
        if spec.convert_family == family
    )


def bucket_of(project: Any, component: object) -> list:
    """이 컴포넌트가 들어갈 프로젝트 목록 (`project.skills` / `project.agents`).

    **에이전트 두 종류를 `project.agents`로 보내는 단 하나의 판정**이다 —
    워크플로 에이전트로 좁히면 fork 에이전트가 `skills`에 들어가 저장·레지스트리·
    검증·산출 계획이 전부 어긋난다. 종류가 아니라 `BUCKET` 선언이 답한다.
    """
    return getattr(project, _BUCKET_ATTR[spec_for(component).bucket])
