from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VariableScope(Enum):
    LOCAL = "local"
    BLACKBOARD = "blackboard"


class VariableType(Enum):
    STRING = "string"
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
    var_type: VariableType = VariableType.ANY
    required: bool = False
    default: Any | None = None
    conflict_resolution: ConflictResolution = ConflictResolution.LAST_WRITE
