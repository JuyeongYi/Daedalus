from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import uuid4

from daedalus.model.plugin.base import PluginComponent
from daedalus.model.plugin.enums import SkillShell
from daedalus.model.plugin.serial_fields import ENUM, RAW, FieldSpec


@dataclass
class Tool(PluginComponent, ABC):
    """프로젝트 tool_shelf에 놓이는 도구의 공통 베이스 (단일 진실).

    Daedalus는 내장 도구·MCP 도구·사용자 정의 도구를 모두 하나의 Tool 계층으로
    다룬다 (세션 문서 결정 D — ABC + 3 서브클래스 + 프로젝트 Registry).

    물리 분리(결정 Z): shelf = 프로젝트가 소유, assigned = 컴포넌트가 **이름 문자열**로
    참조. ``ToolEvaluation.tool`` / ``ToolExecution.tool`` 등 fsm/ 레이어의 도구 참조는
    이 ``Tool.name``을 가리킨다. fsm/는 Claude 무관 원칙이라 plugin 레이어의 Tool 객체를
    알지 못하므로, 결합은 이름으로만 하고 실존 여부는 Validator가 검증한다 (결정 B1).

    ``name``은 PluginComponent에서 상속 — CC ``allowedTools`` granularity에 맞춰
    한 Tool = 한 참조 단위(결정 α: ``GitCommit``/``GitPush``를 별개로 선언)다.
    """

    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False, WP-F 패턴).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)

    @property
    @abstractmethod
    def kind(self) -> str:
        """도구 종류 식별자."""


@dataclass
class BuiltinTool(Tool):
    """CC 내장 도구 참조 (Read/Write/Edit/Bash/Grep/...).

    ``name``이 곧 CC 내장 도구 이름이다. ``allowed_arguments_note``는 서브커맨드·
    인자 허용 범위에 대한 설계 메모(컴파일러가 권한 문자열을 좁힐 때 참고용,
    자유 텍스트 — 강한 스키마는 Tier 2).
    """

    allowed_arguments_note: str = ""

    @property
    def kind(self) -> str:
        return "builtin"


@dataclass
class MCPTool(Tool):
    """MCP 서버가 노출하는 도구 참조.

    ``server``는 MCP 서버명, ``tool_name``은 서버 내 도구명이다. CC에서 도구의
    유효 식별자는 ``mcp__<server>__<tool>`` 형식이지만, shelf 멤버십·참조 결합에
    쓰이는 키는 어디까지나 ``Tool.name``(자유 표기)이다.
    """

    server: str = ""
    tool_name: str = ""

    @property
    def kind(self) -> str:
        return "mcp"


@dataclass
class UserDefinedTool(Tool):
    """사용자가 구현 본문(스크립트/지침)을 직접 정의하는 도구.

    ``body``는 실행 스크립트 또는 지침 본문, ``shell``은 실행 셸이다.
    로드맵 4-8 '외부 스크립트 실행 노드'는 별도 모델 타입이 아니라
    ``ToolExecution(tool=<이 도구 이름>)``을 on_entry로 갖는 SimpleState 프리셋
    (view 레이어, 향후)으로 재정의된다 — UserDefinedTool이 그 단일 진실이다.

    인자 이스케이프·shell 분기·env/cwd/timeout 같은 정교한 실행 모델은 Tier 2
    (``Command`` 객체)로 미룬다 — 여기서는 YAGNI를 유지한다.
    """

    body: str = ""
    shell: SkillShell = SkillShell.BASH

    @property
    def kind(self) -> str:
        return "user"


# ─────────────────────────── 종류 레지스트리 (WP-11) ───────────────────────────


@dataclass(frozen=True)
class ToolKindSpec:
    """Tool 한 종류의 **저장 계약** — kind 태그 · 클래스 · 종류 고유 필드.

    종전에는 이 한 사실이 세 벌로 흩어져 있었다: `ser._KNOWN_TOOL_KINDS`(집합),
    `_ser_tool`의 isinstance 사다리, `_deser_tool`의 kind 문자열 사다리. 셋 중
    하나만 고치면 그 필드는 저장은 되고 로드는 안 되거나(또는 그 반대) **조용히**
    사라진다. 이제 등록 지점은 `TOOL_KINDS` 한 튜플이고 직렬화 양쪽이 이것을
    읽는다 — 컴포넌트 config의 `SERIALIZED_FIELDS`와 같은 규약이다.

    **`KIND` ClassVar를 클래스에 두지 않는 이유**: `PluginComponent`의 `KIND`는
    종류 레지스트리(`kinds.py`)의 등록 표식이고, `Tool`은 그 레지스트리의 대상이
    아니다(`tests/model/plugin/test_registry_discovery.py`가 `Tool` 계열에
    `KIND`가 **없음**을 못 박는다 — 있으면 도구가 스킬 팔레트에 새어 나온다).
    그래서 kind 태그는 클래스 밖, 이 표 안에 있다.
    """

    kind: str
    cls: type[Tool]
    fields: tuple[FieldSpec, ...]


#: 등록 지점. 새 Tool 서브클래스는 **여기 한 줄**이면 저장·로드가 함께 따라온다.
#: `tests/model/test_serialize_tool.py`가 구체 서브클래스 집합과 양방향으로 맞춘다.
TOOL_KINDS: tuple[ToolKindSpec, ...] = (
    ToolKindSpec("builtin", BuiltinTool, (
        FieldSpec("allowed_arguments_note", RAW),
    )),
    ToolKindSpec("mcp", MCPTool, (
        FieldSpec("server", RAW),
        FieldSpec("tool_name", RAW),
    )),
    ToolKindSpec("user", UserDefinedTool, (
        FieldSpec("body", RAW),
        FieldSpec("shell", ENUM(SkillShell, SkillShell.BASH)),
    )),
)

#: kind 태그 → 행. 조회 실패는 조용한 강등이 아니라 호출자의 명시 에러다(원칙 5).
TOOL_KIND_BY_NAME: Mapping[str, ToolKindSpec] = MappingProxyType(
    {spec.kind: spec for spec in TOOL_KINDS}
)
