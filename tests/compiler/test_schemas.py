"""WP-N ⑤ compile_schemas_json — DynamicClass → JSON Schema 매핑 골든."""
from __future__ import annotations

import json

from daedalus.compiler.emit import compile_schemas_json
from daedalus.model.fsm.blackboard import (
    Blackboard,
    CollectionType,
    DynamicClass,
    DynamicField,
)
from daedalus.model.fsm.variable import FieldType
from daedalus.model.project import PluginProject


def test_empty_class_definitions_returns_none():
    """class_definitions가 없으면 None (파일 생성 안 함)."""
    assert compile_schemas_json(PluginProject(name="p")) is None


def test_field_type_mapping_golden():
    """FieldType → JSON Schema 타입 매핑 표 (json.loads 왕복)."""
    dc = DynamicClass(
        name="Sample", description="설명",
        fields=[
            DynamicField(name="s", field_type=FieldType.STRING),
            DynamicField(name="i", field_type=FieldType.INT),
            DynamicField(name="f", field_type=FieldType.FLOAT),
            DynamicField(name="b", field_type=FieldType.BOOL),
            DynamicField(name="l", field_type=FieldType.LIST),
            DynamicField(name="j", field_type=FieldType.JSON),
            DynamicField(name="a", field_type=FieldType.ANY),
        ],
    )
    p = PluginProject(name="p", blackboard=Blackboard(class_definitions=[dc]))
    text = compile_schemas_json(p)
    assert text is not None
    obj = json.loads(text)
    props = obj["Sample"]["properties"]
    assert props["s"] == {"type": "string"}
    assert props["i"] == {"type": "integer"}
    assert props["f"] == {"type": "number"}
    assert props["b"] == {"type": "boolean"}
    assert props["l"] == {"type": "array"}
    assert props["j"] == {"type": "object"}
    assert props["a"] == {}  # ANY → 빈 스키마
    assert obj["Sample"]["type"] == "object"
    assert obj["Sample"]["description"] == "설명"


def test_collection_wraps_array():
    """CollectionType LIST/SET이 array로 래핑."""
    dc = DynamicClass(
        name="C", description="",
        fields=[
            DynamicField(name="tags", field_type=FieldType.STRING,
                         collection=CollectionType.LIST),
            DynamicField(name="uniq", field_type=FieldType.INT,
                         collection=CollectionType.SET),
        ],
    )
    p = PluginProject(name="p", blackboard=Blackboard(class_definitions=[dc]))
    obj = json.loads(compile_schemas_json(p))
    props = obj["C"]["properties"]
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert props["uniq"] == {
        "type": "array", "items": {"type": "integer"}, "uniqueItems": True,
    }


def test_required_fields_listed():
    dc = DynamicClass(
        name="C", description="",
        fields=[
            DynamicField(name="must", field_type=FieldType.STRING, required=True),
            DynamicField(name="opt", field_type=FieldType.STRING, required=False),
        ],
    )
    p = PluginProject(name="p", blackboard=Blackboard(class_definitions=[dc]))
    obj = json.loads(compile_schemas_json(p))
    assert obj["C"]["required"] == ["must"]


def test_default_value_embedded():
    dc = DynamicClass(
        name="C", description="",
        fields=[DynamicField(name="step", field_type=FieldType.INT, default=0)],
    )
    p = PluginProject(name="p", blackboard=Blackboard(class_definitions=[dc]))
    obj = json.loads(compile_schemas_json(p))
    assert obj["C"]["properties"]["step"]["default"] == 0


def test_schemas_text_is_lf_and_ends_newline():
    dc = DynamicClass(name="C", description="",
                      fields=[DynamicField(name="x", field_type=FieldType.STRING)])
    p = PluginProject(name="p", blackboard=Blackboard(class_definitions=[dc]))
    text = compile_schemas_json(p)
    assert "\r" not in text
    assert text.endswith("\n")
