"""블랙보드 CLI(``daedalus-bb``) E2E — 임시 폴더 + main() 함수 호출 (WP-BB1).

CLI는 설치 대상 프로젝트에서 도는 물건이라, 여기서도 실제와 같은 모양으로
검증한다: 임시 폴더에 컴파일 산출과 같은 ``schemas/schemas.json``과 ``state/``를
만들고 ``main([...])``을 호출해 exit code·stdout(JSON)·파일 내용을 본다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli.blackboard import main

# 컴파일러(compile_schemas_json)가 실제로 만드는 형상 — scalar 4종 + list/set 컬렉션.
SCHEMAS = {
    "Task": {
        "type": "object",
        "description": "작업 항목",
        "properties": {
            "title": {"type": "string"},
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "done": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "owners": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "note": {"type": "string", "default": "n/a"},
        },
        "required": ["title", "count", "done", "tags"],
    },
    "Config": {
        "type": "object",
        "properties": {"level": {"type": "integer"}},
        "required": ["level"],
    },
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    schemas_path = tmp_path / "schemas" / "schemas.json"
    schemas_path.parent.mkdir(parents=True)
    schemas_path.write_text(
        json.dumps(SCHEMAS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (tmp_path / "state").mkdir()
    return tmp_path


@pytest.fixture
def run(workspace: Path, capsys):
    """CLI 한 번 실행 → (exit code, stdout 파싱 결과 또는 None, stderr)."""

    def _run(*argv: str):
        code = main(
            [
                "--state-dir",
                str(workspace / "state"),
                "--schemas",
                str(workspace / "schemas" / "schemas.json"),
                *argv,
            ]
        )
        captured = capsys.readouterr()
        out = json.loads(captured.out) if captured.out.strip() else None
        return code, out, captured.err

    return _run


@pytest.fixture
def run_with_schemas(tmp_path: Path, capsys):
    """SCHEMAS 픽스처가 아닌 임의 스키마로 CLI를 도는 러너 팩토리."""

    def _factory(schemas: dict):
        root = tmp_path / f"ws{len(list(tmp_path.iterdir()))}"
        schemas_path = root / "schemas" / "schemas.json"
        schemas_path.parent.mkdir(parents=True)
        schemas_path.write_text(
            json.dumps(schemas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        def _run(*argv: str):
            code = main(
                ["--state-dir", str(root / "state"), "--schemas", str(schemas_path), *argv]
            )
            captured = capsys.readouterr()
            out = json.loads(captured.out) if captured.out.strip() else None
            return code, out, captured.err

        return root, _run

    return _factory


def _state(workspace: Path, cls: str) -> Path:
    return workspace / "state" / f"{cls}.json"


def _load(workspace: Path, cls: str):
    return json.loads(_state(workspace, cls).read_text(encoding="utf-8"))


# ─────────────────────────── list ───────────────────────────


def test_list_reports_classes_and_fields(run):
    code, out, _ = run("list")
    assert code == 0
    names = [cls["name"] for cls in out["classes"]]
    assert names == ["Task", "Config"]
    task = out["classes"][0]
    assert task["description"] == "작업 항목"
    fields = {f["name"]: f for f in task["fields"]}
    assert fields["title"] == {
        "name": "title",
        "type": "string",
        "collection": "none",
        "required": True,
    }
    assert fields["tags"]["collection"] == "list"
    assert fields["owners"]["collection"] == "set"
    assert fields["owners"]["type"] == "string"
    assert fields["note"]["required"] is False
    assert fields["note"]["default"] == "n/a"


def test_list_stdout_is_json_only(workspace, capsys):
    code = main(
        [
            "--state-dir",
            str(workspace / "state"),
            "--schemas",
            str(workspace / "schemas" / "schemas.json"),
            "list",
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    json.loads(captured.out)  # stdout은 통째로 JSON 하나여야 한다


# ─────────────────────────── init ───────────────────────────


def test_init_creates_zero_valued_required_fields_only(run, workspace):
    code, out, _ = run("init", "Task")
    assert code == 0
    assert out == {"title": "", "count": 0, "done": False, "tags": []}
    assert _load(workspace, "Task") == out
    assert "note" not in out and "ratio" not in out


def test_init_uses_schema_default_when_type_matches(run_with_schemas):
    """컴파일러가 배출한 default는 제로값보다 우선한다 (default true → false 금지)."""
    _, run = run_with_schemas(
        {
            "Flag": {
                "type": "object",
                "properties": {
                    "done": {"type": "boolean", "default": True},
                    "label": {"type": "string", "default": "n/a"},
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["a"],
                    },
                },
                "required": ["done", "label", "items"],
            }
        }
    )
    code, out, _ = run("init", "Flag")
    assert code == 0
    assert out == {"done": True, "label": "n/a", "items": ["a"]}


def test_init_default_is_copied_not_shared(run_with_schemas):
    """배열 default를 --append로 늘려도 스키마 쪽 객체가 오염되지 않는다."""
    root, run = run_with_schemas(
        {
            "Flag": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "string"}, "default": ["a"]}
                },
                "required": ["items"],
            }
        }
    )
    assert run("write", "Flag", "--append", "items=b")[0] == 0
    schemas = json.loads((root / "schemas" / "schemas.json").read_text(encoding="utf-8"))
    assert schemas["Flag"]["properties"]["items"]["default"] == ["a"]


def test_init_falls_back_to_zero_when_default_type_mismatches(run_with_schemas):
    """편집기는 default를 자유 텍스트로 받는다 — 타입이 어긋나면 제로값으로 물러난다."""
    _, run = run_with_schemas(
        {
            "Flag": {
                "type": "object",
                "properties": {"done": {"type": "boolean", "default": "true"}},
                "required": ["done"],
            }
        }
    )
    code, out, _ = run("init", "Flag")
    assert code == 0, "타입이 어긋난 default 때문에 init 자체가 실패하면 안 된다"
    assert out == {"done": False}


def test_init_refuses_existing_file(run, workspace):
    assert run("init", "Task")[0] == 0
    _state(workspace, "Task").write_text('{"title": "keep"}', encoding="utf-8")
    code, _, err = run("init", "Task")
    assert code == 2
    assert "--force" in err
    assert _load(workspace, "Task") == {"title": "keep"}  # 불변


def test_init_force_recreates(run, workspace):
    assert run("init", "Task")[0] == 0
    _state(workspace, "Task").write_text('{"title": "old"}', encoding="utf-8")
    code, out, _ = run("init", "Task", "--force")
    assert code == 0
    assert out["title"] == ""
    assert _load(workspace, "Task")["title"] == ""


def test_init_unknown_class_lists_available(run):
    code, out, err = run("init", "Nope")
    assert code == 2
    assert out is None
    assert "Task" in err and "Config" in err


# ─────────────────────────── read ───────────────────────────


def test_read_missing_file_is_exit_3(run):
    code, out, err = run("read", "Task")
    assert code == 3
    assert out is None
    assert "상태 파일이 없다" in err


def test_read_whole_object(run):
    run("init", "Task")
    code, out, _ = run("read", "Task")
    assert code == 0
    assert out == {"title": "", "count": 0, "done": False, "tags": []}


def test_read_field(run):
    run("init", "Task")
    run("write", "Task", "--set", "count=7")
    code, out, _ = run("read", "Task", "--field", "count")
    assert code == 0
    assert out == 7


def test_read_declared_but_absent_field_is_null(run):
    run("init", "Task")
    code, out, _ = run("read", "Task", "--field", "note")
    assert code == 0
    assert out is None


def test_read_unknown_field_lists_available(run):
    run("init", "Task")
    code, out, err = run("read", "Task", "--field", "nope")
    assert code == 2
    assert out is None
    assert "title" in err and "owners" in err


def test_read_unknown_field_checked_before_missing_file(run):
    """필드 오타는 파일 유무와 무관하게 사용법 오류(2)로 잡힌다."""
    code, _, err = run("read", "Task", "--field", "nope")
    assert code == 2
    assert "가용 필드" in err


# ─────────────────────────── write: 코어션 ───────────────────────────


def test_write_coerces_scalars_by_schema_type(run, workspace):
    code, out, _ = run(
        "write",
        "Task",
        "--set",
        "title=hello",
        "--set",
        "count=42",
        "--set",
        "ratio=0.5",
        "--set",
        "done=true",
    )
    assert code == 0
    assert out["title"] == "hello"
    assert out["count"] == 42 and isinstance(out["count"], int)
    assert out["ratio"] == 0.5
    assert out["done"] is True
    assert _load(workspace, "Task")["done"] is True


@pytest.mark.parametrize("raw,expected", [("false", False), ("0", False), ("no", False),
                                          ("TRUE", True), ("yes", True), ("on", True)])
def test_write_boolean_words(run, raw, expected):
    code, out, _ = run("write", "Task", "--set", f"done={raw}")
    assert code == 0
    assert out["done"] is expected


def test_write_rejects_non_integer(run, workspace):
    code, out, err = run("write", "Task", "--set", "count=3.5")
    assert code == 2
    assert out is None
    assert "정수가 아니다" in err
    assert not _state(workspace, "Task").exists()


def test_write_rejects_non_boolean(run):
    code, _, err = run("write", "Task", "--set", "done=maybe")
    assert code == 2
    assert "불리언이 아니다" in err


def test_write_unknown_field_lists_available(run):
    code, _, err = run("write", "Task", "--set", "nope=1")
    assert code == 2
    assert "가용 필드" in err and "title" in err


def test_write_requires_an_operation(run):
    code, _, err = run("write", "Task")
    assert code == 2
    assert "--set" in err


def test_write_assignment_needs_equals(run):
    code, _, err = run("write", "Task", "--set", "title")
    assert code == 2
    assert "FIELD=VALUE" in err


def test_write_starts_from_initial_object_when_file_missing(run, workspace):
    code, out, _ = run("write", "Task", "--set", "title=x")
    assert code == 0
    assert out == {"title": "x", "count": 0, "done": False, "tags": []}
    assert _state(workspace, "Task").exists()


def test_write_preserves_untouched_fields(run):
    run("write", "Task", "--set", "title=a", "--set", "count=1")
    code, out, _ = run("write", "Task", "--set", "count=2")
    assert code == 0
    assert out["title"] == "a" and out["count"] == 2


# ─────────────────────────── write: 컬렉션 ───────────────────────────


def test_set_collection_takes_json_array(run):
    code, out, _ = run("write", "Task", "--set", 'tags=["a","b"]')
    assert code == 0
    assert out["tags"] == ["a", "b"]


def test_set_collection_rejects_bare_scalar(run):
    code, _, err = run("write", "Task", "--set", "tags=a")
    assert code == 2
    assert "JSON 배열" in err


def test_append_adds_element(run):
    run("write", "Task", "--append", "tags=a")
    code, out, _ = run("write", "Task", "--append", "tags=b")
    assert code == 0
    assert out["tags"] == ["a", "b"]


def test_append_on_list_keeps_duplicates(run):
    run("write", "Task", "--append", "tags=a")
    code, out, _ = run("write", "Task", "--append", "tags=a")
    assert out["tags"] == ["a", "a"]


def test_append_on_set_dedupes(run):
    run("write", "Task", "--append", "owners=jy")
    code, out, _ = run("write", "Task", "--append", "owners=jy")
    assert code == 0
    assert out["owners"] == ["jy"]


def test_set_on_set_field_dedupes(run):
    code, out, _ = run("write", "Task", "--set", 'owners=["a","b","a"]')
    assert code == 0
    assert out["owners"] == ["a", "b"]


def test_remove_drops_every_occurrence(run):
    run("write", "Task", "--set", 'tags=["a","b","a"]')
    code, out, _ = run("write", "Task", "--remove", "tags=a")
    assert code == 0
    assert out["tags"] == ["b"]


def test_remove_absent_element_is_noop(run):
    run("write", "Task", "--set", 'tags=["a"]')
    code, out, _ = run("write", "Task", "--remove", "tags=zzz")
    assert code == 0
    assert out["tags"] == ["a"]


def test_remove_on_absent_key_does_not_create_it(run, workspace):
    """'제거'가 없던 키를 빈 배열로 만들어내면 안 된다 (owners는 비required)."""
    run("init", "Task")
    code, out, _ = run("write", "Task", "--remove", "owners=jy")
    assert code == 0
    assert "owners" not in out
    assert "owners" not in _load(workspace, "Task")


def test_remove_on_absent_key_still_checks_value_format(run_with_schemas):
    """키가 없어도 값 형식 오류는 그대로 잡힌다 — 상태에 따라 진단이 달라지면 안 된다."""
    _, run = run_with_schemas(
        {
            "Bag": {
                "type": "object",
                "properties": {"nums": {"type": "array", "items": {"type": "integer"}}},
            }
        }
    )
    code, _, err = run("write", "Bag", "--remove", "nums=abc")
    assert code == 2
    assert "정수가 아니다" in err


def test_append_on_scalar_field_is_usage_error(run):
    code, _, err = run("write", "Task", "--append", "title=x")
    assert code == 2
    assert "컬렉션 필드에만" in err


def test_remove_on_scalar_field_is_usage_error(run):
    code, _, err = run("write", "Task", "--remove", "count=1")
    assert code == 2
    assert "컬렉션 필드에만" in err


def test_operations_apply_in_set_append_remove_order(run):
    code, out, _ = run(
        "write",
        "Task",
        "--set",
        'tags=["x"]',
        "--append",
        "tags=y",
        "--remove",
        "tags=x",
    )
    assert code == 0
    assert out["tags"] == ["y"]


# ─────────────────────────── write: 검증 게이트 + 원자성 ───────────────────────────


def test_write_leaves_file_untouched_when_validation_fails(run, workspace):
    """기존 파일에 필수 필드가 빠져 있으면 쓰기가 거부되고 원본이 남는다."""
    broken = {"title": "keep", "count": 1, "tags": []}  # done 누락
    _state(workspace, "Task").write_text(
        json.dumps(broken), encoding="utf-8"
    )
    code, out, err = run("write", "Task", "--set", "title=changed")
    assert code == 1
    assert out is None
    assert "Task.done: 필수 필드가 없다" in err
    assert _load(workspace, "Task") == broken  # 완전히 불변


def test_write_leaves_no_temp_files_behind(run, workspace):
    run("write", "Task", "--set", "title=x")
    leftovers = [p.name for p in (workspace / "state").iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_rejects_corrupt_state_file(run, workspace):
    _state(workspace, "Task").write_text("{ not json", encoding="utf-8")
    code, _, err = run("write", "Task", "--set", "title=x")
    assert code == 2
    assert "파싱 실패" in err
    assert _state(workspace, "Task").read_text(encoding="utf-8") == "{ not json"


def test_write_creates_state_dir_if_absent(workspace, capsys):
    fresh = workspace / "nostate"
    code = main(
        [
            "--state-dir",
            str(fresh),
            "--schemas",
            str(workspace / "schemas" / "schemas.json"),
            "write",
            "Config",
            "--set",
            "level=3",
        ]
    )
    assert code == 0
    capsys.readouterr()
    assert json.loads((fresh / "Config.json").read_text(encoding="utf-8"))["level"] == 3


# ─────────────────────────── validate ───────────────────────────


def test_validate_all_classes_passes_on_clean_state(run):
    run("init", "Task")
    run("init", "Config")
    code, out, _ = run("validate")
    assert code == 0
    assert out["ok"] is True
    assert sorted(out["checked"]) == ["Config", "Task"]
    assert out["violations"] == []


def test_validate_reports_missing_files_without_failing(run):
    run("init", "Task")
    code, out, err = run("validate")
    assert code == 0
    assert out["missing"] == ["Config"]
    assert "Config" in err


def test_validate_detects_type_violation(run, workspace):
    _state(workspace, "Task").write_text(
        json.dumps({"title": 1, "count": 0, "done": False, "tags": []}),
        encoding="utf-8",
    )
    code, out, err = run("validate", "Task")
    assert code == 1
    assert out["ok"] is False
    assert any("Task.title" in v and "string" in v for v in out["violations"])
    assert "Task.title" in err


def test_validate_rejects_bool_for_integer(run, workspace):
    _state(workspace, "Task").write_text(
        json.dumps({"title": "", "count": True, "done": False, "tags": []}),
        encoding="utf-8",
    )
    code, out, _ = run("validate", "Task")
    assert code == 1
    assert any("Task.count" in v for v in out["violations"])


def test_validate_accepts_int_for_number(run, workspace):
    _state(workspace, "Task").write_text(
        json.dumps({"title": "", "count": 0, "done": False, "tags": [], "ratio": 3}),
        encoding="utf-8",
    )
    code, out, _ = run("validate", "Task")
    assert code == 0
    assert out["ok"] is True


def test_validate_detects_array_item_violation(run, workspace):
    _state(workspace, "Task").write_text(
        json.dumps({"title": "", "count": 0, "done": False, "tags": ["a", 2]}),
        encoding="utf-8",
    )
    code, out, _ = run("validate", "Task")
    assert code == 1
    assert any("Task.tags[1]" in v for v in out["violations"])


def test_validate_detects_unique_items_violation(run, workspace):
    _state(workspace, "Task").write_text(
        json.dumps(
            {"title": "", "count": 0, "done": False, "tags": [], "owners": ["a", "a"]}
        ),
        encoding="utf-8",
    )
    code, out, _ = run("validate", "Task")
    assert code == 1
    assert any("uniqueItems" in v for v in out["violations"])


def test_validate_detects_corrupt_file_as_violation(run, workspace):
    _state(workspace, "Task").write_text("{ nope", encoding="utf-8")
    code, out, _ = run("validate", "Task")
    assert code == 1
    assert any("파싱 실패" in v for v in out["violations"])


def test_validate_detects_non_object_root(run, workspace):
    _state(workspace, "Config").write_text("[1, 2]", encoding="utf-8")
    code, out, _ = run("validate", "Config")
    assert code == 1
    assert any("JSON 객체가 아니다" in v for v in out["violations"])


def test_validate_named_missing_file_is_exit_3(run, workspace):
    """이름을 명시했는데 파일이 없으면 exit 3 — exit code만 보고 '정상'으로 읽히면 안 된다."""
    code, out, err = run("validate", "Task")
    assert code == 3
    assert out == {"ok": True, "checked": [], "missing": ["Task"], "violations": []}
    assert "init Task" in err


def test_validate_named_missing_is_still_exit_1_when_another_violates(run, workspace):
    """위반이 우선한다 — 부재(3)보다 고장(1)이 먼저 보고돼야 한다."""
    _state(workspace, "Config").write_text("[1, 2]", encoding="utf-8")
    code, out, _ = run("validate", "Config", "Task")
    assert code == 1
    assert out["missing"] == ["Task"]


def test_validate_all_classes_missing_file_stays_exit_0(run):
    """이름 없는 전 클래스 순회에서 미초기화는 고장이 아니다 (기존 계약 고정)."""
    code, out, _ = run("validate")
    assert code == 0
    assert sorted(out["missing"]) == ["Config", "Task"]


def test_validate_unknown_class_is_usage_error(run):
    code, out, err = run("validate", "Nope")
    assert code == 2
    assert out is None
    assert "Task" in err


def test_validate_skips_progress_convention_file(run, workspace):
    """state/__progress__.json은 스키마 밖 규약 파일 — 순회 대상이 아니다."""
    (workspace / "state" / "__progress__.json").write_text(
        "{ 이건 JSON도 아니다", encoding="utf-8"
    )
    run("init", "Task")
    run("init", "Config")
    code, out, _ = run("validate")
    assert code == 0
    assert "__progress__" not in out["checked"]
    assert "__progress__" not in out["missing"]


def test_validate_named_subset_only(run, workspace):
    run("init", "Config")
    _state(workspace, "Task").write_text("{ broken", encoding="utf-8")
    code, out, _ = run("validate", "Config")
    assert code == 0
    assert out["checked"] == ["Config"]


# ─────────────────────────── 전역 옵션 · 스키마 오류 ───────────────────────────


def test_missing_schemas_file_is_exit_2(tmp_path, capsys):
    code = main(["--schemas", str(tmp_path / "nope.json"), "list"])
    assert code == 2
    assert "스키마 파일이 없다" in capsys.readouterr().err


def test_corrupt_schemas_file_is_exit_2(tmp_path, capsys):
    path = tmp_path / "schemas.json"
    path.write_text("{ broken", encoding="utf-8")
    code = main(["--schemas", str(path), "list"])
    assert code == 2
    assert "스키마 JSON 파싱 실패" in capsys.readouterr().err


def test_non_object_schemas_root_is_exit_2(tmp_path, capsys):
    path = tmp_path / "schemas.json"
    path.write_text("[]", encoding="utf-8")
    code = main(["--schemas", str(path), "list"])
    assert code == 2
    assert "JSON 객체가 아니다" in capsys.readouterr().err


def test_unknown_command_is_exit_2(capsys):
    assert main(["frobnicate"]) == 2


def test_no_command_is_exit_2(capsys):
    assert main([]) == 2


def test_help_is_exit_0(capsys):
    assert main(["--help"]) == 0


def test_defaults_are_relative_state_and_schemas(workspace, monkeypatch, capsys):
    """기본값은 cwd 기준 state/ · schemas/schemas.json — 산출 폴더 구조 그대로."""
    monkeypatch.chdir(workspace)
    assert main(["init", "Config"]) == 0
    capsys.readouterr()
    assert (workspace / "state" / "Config.json").is_file()
