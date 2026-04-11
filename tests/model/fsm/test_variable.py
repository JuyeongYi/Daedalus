from __future__ import annotations

from daedalus.model.fsm.variable import (
    Variable,
    VariableScope,
    VariableType,
    ConflictResolution,
)


def test_variable_scope_enum():
    assert VariableScope.LOCAL.value == "local"
    assert VariableScope.BLACKBOARD.value == "blackboard"


def test_variable_type_enum():
    assert VariableType.STRING.value == "string"
    assert VariableType.NUMBER.value == "number"
    assert VariableType.BOOL.value == "bool"
    assert VariableType.LIST.value == "list"
    assert VariableType.JSON.value == "json"
    assert VariableType.ANY.value == "any"


def test_conflict_resolution_enum():
    assert ConflictResolution.LAST_WRITE.value == "last_write"
    assert ConflictResolution.MERGE_LIST.value == "merge_list"
    assert ConflictResolution.ERROR.value == "error"
    assert ConflictResolution.CUSTOM.value == "custom"


def test_variable_instantiation():
    var = Variable(name="result", description="작업 결과")
    assert var.name == "result"
    assert var.description == "작업 결과"
    assert var.scope == VariableScope.LOCAL
    assert var.var_type == VariableType.ANY
    assert var.required is False
    assert var.default is None
    assert var.conflict_resolution == ConflictResolution.LAST_WRITE


def test_variable_blackboard_scope():
    var = Variable(
        name="user",
        description="사용자 정보",
        scope=VariableScope.BLACKBOARD,
        var_type=VariableType.JSON,
        required=True,
    )
    assert var.scope == VariableScope.BLACKBOARD
    assert var.var_type == VariableType.JSON
    assert var.required is True
