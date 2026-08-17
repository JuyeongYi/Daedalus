"""컴파일러 산출 스키마 ↔ CLI 검증기 결합 고정 (WP-BB1).

``daedalus/cli/**``는 ``daedalus.model``을 임포트할 수 없다 — 검증의 정본이
컴파일 산출 ``schemas/schemas.json`` **파일**이기 때문이다. 그 대신 결합이
어디에도 고정되지 않으면, 컴파일러가 스키마 형상을 바꿔도(예: ``items`` 중첩
변경) 손으로 쓴 픽스처를 쓰는 CLI 테스트는 전부 초록인 채 런타임만 깨진다.

테스트는 양쪽을 임포트할 수 있으므로 여기서 묶는다: ``compile_schemas_json``이
**실제로 만든 텍스트**를 그대로 ``schemas.json``으로 놓고 CLI를 돌린다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli.blackboard import main
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
def run(tmp_path: Path, capsys):
    """컴파일러가 만든 schemas.json을 그대로 깔고 CLI를 도는 러너."""
    text = compile_schemas_json(_project())
    assert text is not None
    schemas_path = tmp_path / "schemas" / "schemas.json"
    schemas_path.parent.mkdir(parents=True)
    schemas_path.write_text(text, encoding="utf-8")

    def _run(*argv: str):
        code = main(
            [
                "--state-dir",
                str(tmp_path / "state"),
                "--schemas",
                str(schemas_path),
                *argv,
            ]
        )
        captured = capsys.readouterr()
        out = json.loads(captured.out) if captured.out.strip() else None
        return code, out, captured.err

    return _run


def test_cli_reads_compiler_output_shape(run):
    """list가 컴파일 산출 스키마의 타입·컬렉션·required를 그대로 읽어낸다."""
    code, out, _ = run("list")
    assert code == 0
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


def test_init_and_write_round_trip_on_compiler_output(run):
    code, out, _ = run("init", "Task")
    assert code == 0
    # default=True인 required boolean은 default를 따른다(제로값 false가 아니다).
    assert out == {"title": "", "count": 0, "done": True, "tags": []}

    code, out, _ = run(
        "write", "Task", "--set", "title=t", "--set", "count=2", "--append", "tags=a"
    )
    assert code == 0
    assert out == {"title": "t", "count": 2, "done": True, "tags": ["a"]}

    assert run("validate", "Task")[0] == 0


def test_validate_catches_violation_against_compiler_output(run, tmp_path):
    """손으로 망가뜨린 상태 파일을 컴파일 산출 스키마 기준으로 잡아낸다."""
    run("init", "Task")
    (tmp_path / "state" / "Task.json").write_text(
        json.dumps({"title": 1, "count": 0, "done": True, "tags": ["a", 2]}),
        encoding="utf-8",
    )
    code, out, _ = run("validate", "Task")
    assert code == 1
    assert any("Task.title" in v for v in out["violations"])
    assert any("Task.tags[1]" in v for v in out["violations"])


def test_legacy_field_shapes_are_handled(run):
    """BLACKBOARD_FIELD_TYPES 밖 타입(JSON/LIST/ANY)도 컴파일을 통과한다 — 경고 등급."""
    code, out, _ = run("list")
    fields = {f["name"]: f for f in out["classes"][1]["fields"]}
    assert fields["blob"]["type"] == "object" and fields["blob"]["collection"] == "none"
    # bare LIST는 items 없는 array — 원소 타입이 없으니 any로 보고한다.
    assert fields["bag"]["collection"] == "list" and fields["bag"]["type"] == "any"
    assert fields["free"]["type"] == "any"

    code, out, _ = run("write", "Legacy", "--set", 'blob={"k": 1}', "--set", "free=3")
    assert code == 0
    assert out == {"blob": {"k": 1}, "free": 3}
    assert run("validate", "Legacy")[0] == 0
