from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class VariableScope(Enum):
    LOCAL = "local"
    BLACKBOARD = "blackboard"


class FieldType(Enum):
    """Variable / DynamicField 공용 필드 타입 (통합 열거형).

    JSON Schema 매핑은 blackboard.py의 ``FIELD_TYPE_TO_JSON_SCHEMA`` 참조.
    """
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    # deprecated: INT/FLOAT을 사용하라. 컴파일 시 JSON Schema "number"로 합류된다
    # (INT→integer, FLOAT/NUMBER→number). 신규 코드에서는 의미가 더 명확한
    # INT/FLOAT을 쓰고, NUMBER는 하위 호환을 위해서만 남겨둔다.
    NUMBER = "number"
    BOOL = "bool"
    LIST = "list"
    JSON = "json"
    ANY = "any"


class ConflictResolution(Enum):
    LAST_WRITE = "last_write"
    MERGE_LIST = "merge_list"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class Variable:
    name: str
    description: str
    scope: VariableScope = VariableScope.LOCAL
    field_type: FieldType = FieldType.ANY
    required: bool = False
    default: Any | None = None
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE
    # 안정 식별자 — 값 동등성 비교에서는 제외(compare=False).
    id: str = field(default_factory=lambda: uuid4().hex, compare=False, kw_only=True)
