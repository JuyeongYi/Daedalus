from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from daedalus.model.fsm.variable import FieldType, Variable


class CollectionType(Enum):
    NONE = "none"
    LIST = "list"
    SET = "set"


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
