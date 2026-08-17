from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from daedalus.model.fsm.variable import FieldType, Variable


class CollectionType(Enum):
    NONE = "none"
    LIST = "list"
    SET = "set"


# 블랙보드 필드에 허용되는 타입 — 스칼라 원소 타입만 (사용자 확정, WP-BT).
# 컨테이너 형상은 CollectionType이 전담한다: "문자열 목록" = STRING × LIST.
# FieldType enum 자체는 Variable과 공용이라 멤버를 제거하지 않는다(구버전 호환).
BLACKBOARD_FIELD_TYPES: tuple[FieldType, ...] = (
    FieldType.STRING,
    FieldType.INT,
    FieldType.FLOAT,
    FieldType.BOOL,
)


@dataclass
class DynamicField:
    name: str
    field_type: FieldType
    collection: CollectionType = CollectionType.NONE
    default: Any | None = None
    required: bool = False


@dataclass
class DynamicClass:
    name: str
    description: str
    fields: list[DynamicField] = field(default_factory=list)


@dataclass
class Blackboard:
    class_definitions: list[DynamicClass] = field(default_factory=list)
    variables: dict[str, Variable] = field(default_factory=dict)
    parent: Blackboard | None = None


# DynamicClass/DynamicField → JSON Schema 타입 매핑 정본 (schemas.json 컴파일 기준).
#
#   FieldType.STRING  → "string"
#   FieldType.INT     → "integer"
#   FieldType.FLOAT   → "number"
#   FieldType.BOOL    → "boolean"
#   FieldType.LIST    → "array"
#   FieldType.JSON    → "object"
#   FieldType.ANY     → {}         (제약 없음 — 빈 스키마)
#
# CollectionType은 필드를 감싼다:
#   NONE → 위 스칼라 스키마 그대로
#   LIST → {"type": "array", "items": <스칼라 스키마>}
#   SET  → {"type": "array", "items": <스칼라 스키마>, "uniqueItems": True}
FIELD_TYPE_TO_JSON_SCHEMA: dict[FieldType, dict] = {
    FieldType.STRING: {"type": "string"},
    FieldType.INT: {"type": "integer"},
    FieldType.FLOAT: {"type": "number"},
    FieldType.BOOL: {"type": "boolean"},
    FieldType.LIST: {"type": "array"},
    FieldType.JSON: {"type": "object"},
    FieldType.ANY: {},
}
