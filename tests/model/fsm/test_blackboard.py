from __future__ import annotations

from daedalus.model.fsm.blackboard import (
    Blackboard,
    DynamicClass,
    DynamicField,
    DynamicFieldType,
    CollectionType,
)
from daedalus.model.fsm.variable import Variable, VariableScope


def test_dynamic_field_type_enum():
    assert DynamicFieldType.STRING.value == "string"
    assert DynamicFieldType.INT.value == "int"
    assert DynamicFieldType.FLOAT.value == "float"
    assert DynamicFieldType.BOOL.value == "bool"


def test_collection_type_enum():
    assert CollectionType.NONE.value == "none"
    assert CollectionType.LIST.value == "list"
    assert CollectionType.SET.value == "set"


def test_dynamic_field():
    f = DynamicField(name="status", field_type=DynamicFieldType.STRING)
    assert f.name == "status"
    assert f.collection == CollectionType.NONE
    assert f.required is False
    assert f.default is None


def test_dynamic_class():
    fields = [
        DynamicField(name="status", field_type=DynamicFieldType.STRING, required=True),
        DynamicField(name="errors", field_type=DynamicFieldType.STRING, collection=CollectionType.LIST),
        DynamicField(name="count", field_type=DynamicFieldType.INT, default=0),
    ]
    dc = DynamicClass(name="BuildResult", description="빌드 결과", fields=fields)
    assert dc.name == "BuildResult"
    assert len(dc.fields) == 3
    assert dc.fields[0].required is True
    assert dc.fields[1].collection == CollectionType.LIST
    assert dc.fields[2].default == 0


def test_blackboard_empty():
    bb = Blackboard()
    assert bb.class_definitions == []
    assert bb.variables == {}
    assert bb.parent is None


def test_blackboard_with_variables():
    var = Variable(name="status", description="상태", scope=VariableScope.BLACKBOARD)
    bb = Blackboard(variables={"status": var})
    assert "status" in bb.variables
    assert bb.variables["status"] is var


def test_blackboard_scoping():
    parent_bb = Blackboard()
    child_bb = Blackboard(parent=parent_bb)
    assert child_bb.parent is parent_bb


def test_blackboard_with_dynamic_class():
    dc = DynamicClass(
        name="DeployLog",
        description="배포 로그",
        fields=[DynamicField(name="timestamp", field_type=DynamicFieldType.STRING)],
    )
    bb = Blackboard(class_definitions=[dc])
    assert len(bb.class_definitions) == 1
    assert bb.class_definitions[0].name == "DeployLog"
