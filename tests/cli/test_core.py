"""블랙보드 코어 E2E — 임시 폴더 + 코어 함수 직접 호출 (WP-BB1 → WP-BM).

종전에는 같은 시나리오를 `daedalus-bb` CLI의 `main([...])`으로 돌렸다. WP-BM에서
모델이 접하는 표면이 stdio MCP 서버 하나가 되면서 argparse 진입점이 폐기됐고,
시나리오는 **표면이 아니라 코어**를 태우도록 옮겨 왔다 — 여기서 고정하는 것
(스키마 로드·초기 객체·코어션·컬렉션 연산·검증 게이트·원자성)은 어느 표면에서
불리든 같은 계약이기 때문이다.

옮기면서 **사라진 것은 argparse 자체를 보던 시나리오뿐**이다: stdout이 통째로
JSON인가, `--help`가 0인가, 서브커맨드 없이 부르면 2인가, `FIELD=VALUE` 파싱.
그 계층은 더 이상 존재하지 않는다(퇴역 개념은 흔적 없이 — 원칙 7). 표면 쪽
계약(도구 이름·인자·오류 결과)은 `tests/cli/test_mcp_server.py`가 본다.

실제와 같은 모양으로 검증한다: 임시 폴더에 컴파일 산출과 같은
`schemas/schemas.json`과 `state/`를 만들고 코어 함수를 부른다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli import core
from daedalus.cli.core import BlackboardError

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


class _Bench:
    """스키마·상태 폴더를 쥐고 코어를 부르는 얇은 손잡이 (테스트 편의)."""

    def __init__(self, schemas_path: Path, state_dir: Path) -> None:
        self.schemas_path = schemas_path
        self.state_dir = state_dir

    @property
    def schemas(self) -> dict:
        return core.load_schemas(self.schemas_path)

    def list(self):
        return core.list_classes(self.schemas, self.state_dir, self.schemas_path)

    def read(self, cls: str, field: str | None = None):
        return core.read_value(self.schemas, self.state_dir, cls, field)

    def init(self, cls: str, force: bool = False):
        return core.init_class(self.schemas, self.state_dir, cls, force)

    def write(self, cls: str, **ops):
        return core.write_class(self.schemas, self.state_dir, cls, **ops)

    def validate(self, *names):
        return core.validate_classes(self.schemas, self.state_dir, list(names))

    def state(self, cls: str) -> Path:
        return self.state_dir / f"{cls}.json"

    def load(self, cls: str):
        return json.loads(self.state(cls).read_text(encoding="utf-8"))


def _bench_for(root: Path, schemas: dict, *, stem: str = "schemas") -> _Bench:
    path = root / "schemas" / f"{stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(schemas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return _Bench(path, root / "state")


@pytest.fixture
def bench(tmp_path: Path) -> _Bench:
    built = _bench_for(tmp_path, SCHEMAS)
    built.state_dir.mkdir(parents=True, exist_ok=True)
    return built


@pytest.fixture
def bench_with_schemas(tmp_path: Path):
    """SCHEMAS 픽스처가 아닌 임의 스키마로 코어를 도는 손잡이 팩토리."""
    def _factory(schemas: dict) -> tuple[Path, _Bench]:
        root = tmp_path / f"ws{len(list(tmp_path.iterdir()))}"
        return root, _bench_for(root, schemas)

    return _factory


def _kind(excinfo) -> str:
    return excinfo.value.kind


# ─────────────────────────── list ───────────────────────────


def test_list_reports_classes_and_fields(bench: _Bench):
    out = bench.list()
    assert [cls["name"] for cls in out["classes"]] == ["Task", "Config"]
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


def test_list_result_is_json_serializable(bench: _Bench):
    """결과는 그대로 전송된다 — 직렬화할 수 없는 값이 섞이면 조용히 죽는다."""
    json.dumps(bench.list(), ensure_ascii=False)


# ─────────────────────────── init ───────────────────────────


def test_init_creates_zero_valued_required_fields_only(bench: _Bench):
    out = bench.init("Task")
    assert out == {"title": "", "count": 0, "done": False, "tags": []}
    assert bench.load("Task") == out
    assert "note" not in out and "ratio" not in out


def test_init_uses_schema_default_when_type_matches(bench_with_schemas):
    """컴파일러가 배출한 default는 제로값보다 우선한다 (default true → false 금지)."""
    _, built = bench_with_schemas({
        "Flag": {
            "type": "object",
            "properties": {
                "done": {"type": "boolean", "default": True},
                "label": {"type": "string", "default": "n/a"},
                "items": {
                    "type": "array", "items": {"type": "string"}, "default": ["a"],
                },
            },
            "required": ["done", "label", "items"],
        }
    })
    assert built.init("Flag") == {"done": True, "label": "n/a", "items": ["a"]}


def test_init_default_is_copied_not_shared(bench_with_schemas):
    """배열 default를 append로 늘려도 스키마 쪽 객체가 오염되지 않는다."""
    root, built = bench_with_schemas({
        "Flag": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}, "default": ["a"]}
            },
            "required": ["items"],
        }
    })
    built.write("Flag", appends={"items": "b"})
    schemas = json.loads(
        (root / "schemas" / "schemas.json").read_text(encoding="utf-8")
    )
    assert schemas["Flag"]["properties"]["items"]["default"] == ["a"]


def test_init_falls_back_to_zero_when_default_type_mismatches(bench_with_schemas):
    """편집기는 default를 자유 텍스트로 받는다 — 타입이 어긋나면 제로값으로 물러난다."""
    _, built = bench_with_schemas({
        "Flag": {
            "type": "object",
            "properties": {"done": {"type": "boolean", "default": "true"}},
            "required": ["done"],
        }
    })
    assert built.init("Flag") == {"done": False}, (
        "타입이 어긋난 default 때문에 init 자체가 실패하면 안 된다"
    )


def test_init_refuses_existing_file(bench: _Bench):
    bench.init("Task")
    bench.state("Task").write_text('{"title": "keep"}', encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        bench.init("Task")
    assert _kind(excinfo) == "usage"
    assert "--force" in excinfo.value.message
    assert bench.load("Task") == {"title": "keep"}  # 불변


def test_init_force_recreates(bench: _Bench):
    bench.init("Task")
    bench.state("Task").write_text('{"title": "old"}', encoding="utf-8")
    assert bench.init("Task", force=True)["title"] == ""
    assert bench.load("Task")["title"] == ""


def test_init_unknown_class_lists_available(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.init("Nope")
    assert _kind(excinfo) == "usage"
    assert "Task" in excinfo.value.message and "Config" in excinfo.value.message


# ─────────────────────────── read ───────────────────────────


def test_read_missing_file_is_not_found(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.read("Task")
    assert _kind(excinfo) == "not_found"
    assert "상태 파일이 없다" in excinfo.value.message


def test_read_whole_object(bench: _Bench):
    bench.init("Task")
    assert bench.read("Task") == {"title": "", "count": 0, "done": False, "tags": []}


def test_read_field(bench: _Bench):
    bench.init("Task")
    bench.write("Task", sets={"count": "7"})
    assert bench.read("Task", "count") == 7


def test_read_declared_but_absent_field_is_null(bench: _Bench):
    bench.init("Task")
    assert bench.read("Task", "note") is None


def test_read_unknown_field_lists_available(bench: _Bench):
    bench.init("Task")
    with pytest.raises(BlackboardError) as excinfo:
        bench.read("Task", "nope")
    assert _kind(excinfo) == "usage"
    assert "title" in excinfo.value.message and "owners" in excinfo.value.message


def test_read_unknown_field_checked_before_missing_file(bench: _Bench):
    """필드 오타는 파일 유무와 무관하게 사용법 오류로 잡힌다."""
    with pytest.raises(BlackboardError) as excinfo:
        bench.read("Task", "nope")
    assert _kind(excinfo) == "usage"
    assert "가용 필드" in excinfo.value.message


# ─────────────────────────── write: 코어션 ───────────────────────────


def test_write_coerces_scalars_by_schema_type(bench: _Bench):
    out = bench.write("Task", sets={
        "title": "hello", "count": "42", "ratio": "0.5", "done": "true",
    })
    assert out["title"] == "hello"
    assert out["count"] == 42 and isinstance(out["count"], int)
    assert out["ratio"] == 0.5
    assert out["done"] is True
    assert bench.load("Task")["done"] is True


@pytest.mark.parametrize("raw,expected", [
    ("false", False), ("0", False), ("no", False),
    ("TRUE", True), ("yes", True), ("on", True),
])
def test_write_boolean_words(bench: _Bench, raw, expected):
    assert bench.write("Task", sets={"done": raw})["done"] is expected


def test_write_rejects_non_integer(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"count": "3.5"})
    assert _kind(excinfo) == "usage"
    assert "정수가 아니다" in excinfo.value.message
    assert not bench.state("Task").exists()


def test_write_rejects_non_boolean(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"done": "maybe"})
    assert "불리언이 아니다" in excinfo.value.message


def test_write_unknown_field_lists_available(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"nope": "1"})
    assert "가용 필드" in excinfo.value.message
    assert "title" in excinfo.value.message


def test_write_requires_an_operation(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task")
    assert _kind(excinfo) == "usage"
    assert "set" in excinfo.value.message


def test_write_starts_from_initial_object_when_file_missing(bench: _Bench):
    out = bench.write("Task", sets={"title": "x"})
    assert out == {"title": "x", "count": 0, "done": False, "tags": []}
    assert bench.state("Task").exists()


def test_write_preserves_untouched_fields(bench: _Bench):
    bench.write("Task", sets={"title": "a", "count": "1"})
    out = bench.write("Task", sets={"count": "2"})
    assert out["title"] == "a" and out["count"] == 2


# ─────────────────────────── write: 컬렉션 ───────────────────────────


def test_set_collection_takes_json_array(bench: _Bench):
    assert bench.write("Task", sets={"tags": '["a","b"]'})["tags"] == ["a", "b"]


def test_set_collection_rejects_bare_scalar(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"tags": "a"})
    assert "JSON 배열" in excinfo.value.message


def test_append_adds_element(bench: _Bench):
    bench.write("Task", appends={"tags": "a"})
    assert bench.write("Task", appends={"tags": "b"})["tags"] == ["a", "b"]


def test_append_on_list_keeps_duplicates(bench: _Bench):
    bench.write("Task", appends={"tags": "a"})
    assert bench.write("Task", appends={"tags": "a"})["tags"] == ["a", "a"]


def test_append_on_set_dedupes(bench: _Bench):
    bench.write("Task", appends={"owners": "jy"})
    assert bench.write("Task", appends={"owners": "jy"})["owners"] == ["jy"]


def test_set_on_set_field_dedupes(bench: _Bench):
    out = bench.write("Task", sets={"owners": '["a","b","a"]'})
    assert out["owners"] == ["a", "b"]


def test_remove_drops_every_occurrence(bench: _Bench):
    bench.write("Task", sets={"tags": '["a","b","a"]'})
    assert bench.write("Task", removes={"tags": "a"})["tags"] == ["b"]


def test_remove_absent_element_is_noop(bench: _Bench):
    bench.write("Task", sets={"tags": '["a"]'})
    assert bench.write("Task", removes={"tags": "zzz"})["tags"] == ["a"]


def test_remove_on_absent_key_does_not_create_it(bench: _Bench):
    """'제거'가 없던 키를 빈 배열로 만들어내면 안 된다 (owners는 비required)."""
    bench.init("Task")
    out = bench.write("Task", removes={"owners": "jy"})
    assert "owners" not in out
    assert "owners" not in bench.load("Task")


def test_remove_on_absent_key_still_checks_value_format(bench_with_schemas):
    """키가 없어도 값 형식 오류는 그대로 잡힌다 — 상태에 따라 진단이 달라지면 안 된다."""
    _, built = bench_with_schemas({
        "Bag": {
            "type": "object",
            "properties": {"nums": {"type": "array", "items": {"type": "integer"}}},
        }
    })
    with pytest.raises(BlackboardError) as excinfo:
        built.write("Bag", removes={"nums": "abc"})
    assert "정수가 아니다" in excinfo.value.message


def test_append_on_scalar_field_is_usage_error(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", appends={"title": "x"})
    assert _kind(excinfo) == "usage"
    assert "컬렉션 필드에만" in excinfo.value.message


def test_remove_on_scalar_field_is_usage_error(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", removes={"count": "1"})
    assert "컬렉션 필드에만" in excinfo.value.message


def test_operations_apply_in_set_append_remove_order(bench: _Bench):
    out = bench.write(
        "Task",
        sets={"tags": '["x"]'}, appends={"tags": "y"}, removes={"tags": "x"},
    )
    assert out["tags"] == ["y"]


# ─────────────────── write: 검증 게이트 + 원자성 ───────────────────


def test_write_leaves_file_untouched_when_validation_fails(bench: _Bench):
    """기존 파일에 필수 필드가 빠져 있으면 쓰기가 거부되고 원본이 남는다."""
    broken = {"title": "keep", "count": 1, "tags": []}  # done 누락
    bench.state("Task").write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"title": "changed"})
    assert _kind(excinfo) == "rejected"
    assert any("Task.done: 필수 필드가 없다" in d for d in excinfo.value.detail)
    assert bench.load("Task") == broken  # 완전히 불변


def test_write_leaves_no_temp_files_behind(bench: _Bench):
    bench.write("Task", sets={"title": "x"})
    leftovers = [p.name for p in bench.state_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_rejects_corrupt_state_file(bench: _Bench):
    bench.state("Task").write_text("{ not json", encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        bench.write("Task", sets={"title": "x"})
    assert _kind(excinfo) == "usage"
    assert "파싱 실패" in excinfo.value.message
    assert bench.state("Task").read_text(encoding="utf-8") == "{ not json"


def test_write_creates_state_dir_if_absent(tmp_path: Path):
    built = _bench_for(tmp_path, SCHEMAS)
    built.state_dir = tmp_path / "nostate"
    built.write("Config", sets={"level": "3"})
    assert built.load("Config")["level"] == 3


# ─────────────────────────── validate ───────────────────────────


def test_validate_all_classes_passes_on_clean_state(bench: _Bench):
    bench.init("Task")
    bench.init("Config")
    out = bench.validate()
    assert out["ok"] is True
    assert sorted(out["checked"]) == ["Config", "Task"]
    assert out["violations"] == []


def test_validate_reports_missing_files_without_failing(bench: _Bench):
    bench.init("Task")
    out = bench.validate()
    assert out["missing"] == ["Config"]


def test_validate_detects_type_violation(bench: _Bench):
    bench.state("Task").write_text(
        json.dumps({"title": 1, "count": 0, "done": False, "tags": []}),
        encoding="utf-8",
    )
    out = bench.validate("Task")
    assert out["ok"] is False
    assert out["ok"] is False
    assert any("Task.title" in v and "string" in v for v in out["violations"])


def test_validate_rejects_bool_for_integer(bench: _Bench):
    bench.state("Task").write_text(
        json.dumps({"title": "", "count": True, "done": False, "tags": []}),
        encoding="utf-8",
    )
    out = bench.validate("Task")
    assert out["ok"] is False
    assert any("Task.count" in v for v in out["violations"])


def test_validate_accepts_int_for_number(bench: _Bench):
    bench.state("Task").write_text(
        json.dumps({"title": "", "count": 0, "done": False, "tags": [], "ratio": 3}),
        encoding="utf-8",
    )
    out = bench.validate("Task")
    assert out["ok"] is True


def test_validate_detects_array_item_violation(bench: _Bench):
    bench.state("Task").write_text(
        json.dumps({"title": "", "count": 0, "done": False, "tags": ["a", 2]}),
        encoding="utf-8",
    )
    out = bench.validate("Task")
    assert out["ok"] is False
    assert any("Task.tags[1]" in v for v in out["violations"])


def test_validate_detects_unique_items_violation(bench: _Bench):
    bench.state("Task").write_text(
        json.dumps({
            "title": "", "count": 0, "done": False, "tags": [], "owners": ["a", "a"],
        }),
        encoding="utf-8",
    )
    out = bench.validate("Task")
    assert out["ok"] is False
    assert any("uniqueItems" in v for v in out["violations"])


def test_validate_detects_corrupt_file_as_violation(bench: _Bench):
    bench.state("Task").write_text("{ nope", encoding="utf-8")
    out = bench.validate("Task")
    assert out["ok"] is False
    assert any("파싱 실패" in v for v in out["violations"])


def test_validate_detects_non_object_root(bench: _Bench):
    bench.state("Config").write_text("[1, 2]", encoding="utf-8")
    out = bench.validate("Config")
    assert out["ok"] is False
    assert any("JSON 객체가 아니다" in v for v in out["violations"])


def test_validate_named_missing_file_is_not_ok(bench: _Bench):
    """이름을 명시했는데 파일이 없으면 `ok`가 거짓이다 — '검사했고 정상'이 아니다.

    `ok`는 "물어본 것이 전부 있고 전부 유효한가"다. 종전 CLI가 exit 3으로 말하던
    것을 결과 자체가 말한다(표면이 exit code를 갖지 않으므로).
    """
    out = bench.validate("Task")
    assert out == {"ok": False, "checked": [], "missing": ["Task"], "violations": []}


def test_validate_reports_both_a_violation_and_a_missing_name(bench: _Bench):
    """둘 다 있으면 둘 다 보고한다 — 한쪽이 다른 쪽을 가리지 않는다."""
    bench.state("Config").write_text("[1, 2]", encoding="utf-8")
    out = bench.validate("Config", "Task")
    assert out["ok"] is False
    assert out["missing"] == ["Task"]
    assert out["violations"]


def test_validate_all_classes_missing_file_stays_ok(bench: _Bench):
    """이름 없는 전 클래스 순회에서 미초기화는 고장이 아니다 (기존 계약 고정)."""
    out = bench.validate()
    assert sorted(out["missing"]) == ["Config", "Task"]


def test_validate_unknown_class_is_usage_error(bench: _Bench):
    with pytest.raises(BlackboardError) as excinfo:
        bench.validate("Nope")
    assert _kind(excinfo) == "usage"
    assert "Task" in excinfo.value.message


def test_validate_skips_progress_convention_file(bench: _Bench):
    """state/__progress__.json은 스키마 밖 규약 파일 — 순회 대상이 아니다."""
    (bench.state_dir / "__progress__.json").write_text(
        "{ 이건 JSON도 아니다", encoding="utf-8"
    )
    bench.init("Task")
    bench.init("Config")
    out = bench.validate()
    assert "__progress__" not in out["checked"]
    assert "__progress__" not in out["missing"]


def test_validate_named_subset_only(bench: _Bench):
    bench.init("Config")
    bench.state("Task").write_text("{ broken", encoding="utf-8")
    out = bench.validate("Config")
    assert out["ok"] is True
    assert out["checked"] == ["Config"]


# ─────────────────────────── 스키마 파일 오류 ───────────────────────────


def test_missing_schemas_file_is_usage(tmp_path: Path):
    with pytest.raises(BlackboardError) as excinfo:
        core.load_schemas(tmp_path / "nope.json")
    assert _kind(excinfo) == "usage"
    assert "스키마 파일이 없다" in excinfo.value.message


def test_corrupt_schemas_file_is_usage(tmp_path: Path):
    path = tmp_path / "schemas.json"
    path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        core.load_schemas(path)
    assert "스키마 JSON 파싱 실패" in excinfo.value.message


def test_non_object_schemas_root_is_usage(tmp_path: Path):
    path = tmp_path / "schemas.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        core.load_schemas(path)
    assert "JSON 객체가 아니다" in excinfo.value.message


# ─────────────────────────── 경로 유도 (WP-NS/D10) ───────────────────────────


def test_state_dir_is_derived_from_the_schema_stem():
    """상태 폴더 기본값은 cwd 기준 `state/<스키마 stem>`.

    이전에는 `state/`와 `schemas/schemas.json`이 각각 기본값이었다. 두 플러그인이
    한 작업 폴더에 있으면 그 고정 경로가 서로를 덮어써서, 스키마 파일 이름으로
    네임스페이스를 나누고 상태 폴더를 거기서 유도하도록 바뀌었다.
    """
    path = Path("schemas") / "my-plugin.json"
    assert core.plugin_name(path) == "my-plugin"
    assert core.resolve_state_dir(None, path) == Path("state") / "my-plugin"


def test_absolute_schemas_still_yields_a_relative_state_dir(tmp_path: Path):
    """스키마가 절대경로여도(마켓 빌드) 상태는 **작업 폴더 상대**로 남는다.

    상태까지 플러그인 디렉토리로 따라가면 작업 폴더마다 달라야 할 데이터가 섞인다.
    """
    absolute = tmp_path / "elsewhere" / "schemas" / "my-plugin.json"
    assert core.resolve_state_dir(None, absolute) == Path("state") / "my-plugin"


def test_explicit_state_dir_overrides_the_derived_one(tmp_path: Path):
    target = tmp_path / "custom"
    assert core.resolve_state_dir(str(target), Path("schemas/p.json")) == target
