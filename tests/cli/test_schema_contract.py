"""컴파일러 산출 스키마 ↔ 블랙보드 코어 결합 고정 (WP-BB1 → WP-BM).

``daedalus/cli/**``는 ``daedalus.model``을 임포트할 수 없다 — 검증의 정본이
컴파일 산출 ``schemas/<플러그인>.json`` **파일**이기 때문이다. 그 대신 결합이
어디에도 고정되지 않으면, 컴파일러가 스키마 형상을 바꿔도(예: ``items`` 중첩
변경) 손으로 쓴 픽스처를 쓰는 코어 테스트는 전부 초록인 채 런타임만 깨진다.

테스트는 양쪽을 임포트할 수 있으므로 여기서 묶는다: ``compile_schemas_json``이
**실제로 만든 텍스트**를 그대로 스키마 파일로 놓고 **서버 핸들러**를 돌린다
(모델이 실제로 닿는 표면 — WP-BM).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli.mcp_server import BlackboardTools
from daedalus.compiler.emit import compile_schemas_json
from daedalus.model.fsm.blackboard import (
    Blackboard,
    CollectionType,
    DynamicClass,
    DynamicField,
    FieldType,
)
from daedalus.model.project import PluginProject


def _project() -> PluginProject:
    """블랙보드 허용 타입 4종 × 컬렉션 3종 + legacy 타입(경고 등급이라 실제로 나온다)."""
    task = DynamicClass(
        name="Task",
        description="작업 항목",
        fields=[
            DynamicField("title", FieldType.STRING, required=True),
            DynamicField("count", FieldType.INT, required=True),
            DynamicField("ratio", FieldType.FLOAT),
            DynamicField("done", FieldType.BOOL, default=True, required=True),
            DynamicField("tags", FieldType.STRING, collection=CollectionType.LIST,
                         required=True),
            DynamicField("owners", FieldType.STRING, collection=CollectionType.SET),
        ],
    )
    legacy = DynamicClass(
        name="Legacy",
        description="",
        fields=[
            DynamicField("blob", FieldType.JSON),
            DynamicField("bag", FieldType.LIST),
            DynamicField("free", FieldType.ANY),
        ],
    )
    project = PluginProject(name="p", description="", version="0.1.0")
    project.blackboard = Blackboard(class_definitions=[task, legacy])
    return project


@pytest.fixture
def tools(tmp_path: Path) -> BlackboardTools:
    """컴파일러가 만든 스키마를 그대로 깔고 서버 핸들러를 쥔다."""
    text = compile_schemas_json(_project())
    assert text is not None
    schemas_path = tmp_path / "schemas" / "p.json"
    schemas_path.parent.mkdir(parents=True)
    schemas_path.write_text(text, encoding="utf-8")
    return BlackboardTools(schemas_path, tmp_path / "state")


def _ok(result):
    """도구 실패는 결과로 온다 — 시나리오가 성공을 기대하면 여기서 시끄럽게 걸린다.

    판정은 `error` 키다. `validate`의 `ok: false`는 **성공한 호출의 결과**이지
    실패가 아니다(검증에 걸린 것을 결과로 말하는 것이 그 도구의 계약이다).
    """
    assert not (isinstance(result, dict) and "error" in result), result
    return result


def test_core_reads_compiler_output_shape(tools):
    """list가 컴파일 산출 스키마의 타입·컬렉션·required를 그대로 읽어낸다."""
    out = _ok(tools.tool_list())
    classes = {cls["name"]: cls for cls in out["classes"]}
    assert list(classes) == ["Task", "Legacy"]
    fields = {f["name"]: f for f in classes["Task"]["fields"]}
    assert fields["title"]["type"] == "string" and fields["title"]["required"] is True
    assert fields["count"]["type"] == "integer"
    assert fields["ratio"]["type"] == "number" and fields["ratio"]["required"] is False
    assert fields["done"]["type"] == "boolean" and fields["done"]["default"] is True
    assert fields["tags"] == {
        "name": "tags",
        "type": "string",
        "collection": "list",
        "required": True,
    }
    assert fields["owners"]["collection"] == "set"


def test_init_and_write_round_trip_on_compiler_output(tools):
    out = _ok(tools.tool_init("Task"))
    # default=True인 required boolean은 default를 따른다(제로값 false가 아니다).
    assert out == {"title": "", "count": 0, "done": True, "tags": []}

    out = _ok(tools.tool_write(
        "Task", set={"title": "t", "count": "2"}, append={"tags": "a"},
    ))
    assert out == {"title": "t", "count": 2, "done": True, "tags": ["a"]}

    assert _ok(tools.tool_validate(["Task"]))["ok"] is True


def test_validate_catches_violation_against_compiler_output(tools, tmp_path):
    """손으로 망가뜨린 상태 파일을 컴파일 산출 스키마 기준으로 잡아낸다."""
    tools.tool_init("Task")
    (tmp_path / "state" / "Task.json").write_text(
        json.dumps({"title": 1, "count": 0, "done": True, "tags": ["a", 2]}),
        encoding="utf-8",
    )
    out = _ok(tools.tool_validate(["Task"]))
    assert out["ok"] is False
    assert any("Task.title" in v for v in out["violations"])
    assert any("Task.tags[1]" in v for v in out["violations"])


def test_legacy_field_shapes_are_handled(tools):
    """BLACKBOARD_FIELD_TYPES 밖 타입(JSON/LIST/ANY)도 컴파일을 통과한다 — 경고 등급."""
    out = _ok(tools.tool_list())
    fields = {f["name"]: f for f in out["classes"][1]["fields"]}
    assert fields["blob"]["type"] == "object" and fields["blob"]["collection"] == "none"
    # bare LIST는 items 없는 array — 원소 타입이 없으니 any로 보고한다.
    assert fields["bag"]["collection"] == "list" and fields["bag"]["type"] == "any"
    assert fields["free"]["type"] == "any"

    out = _ok(tools.tool_write("Legacy", set={"blob": '{"k": 1}', "free": "3"}))
    assert out == {"blob": {"k": 1}, "free": 3}
    assert _ok(tools.tool_validate(["Legacy"]))["ok"] is True
