"""블랙보드 stdio MCP 서버 — 도구 7개와 오류 계약 (WP-BM 단계 1).

세 가지를 고정한다:

1. **1:1 대응** — 도구 이름·인자·결과가 종전 CLI 명령과 같은 시나리오에서
   같은 값을 낸다(파라미터화한 매핑 표).
2. **오류는 결과다** — 실패해도 예외를 던지지 않고
   ``{"ok": false, "error": {"kind": ...}}``를 돌려준다. kind는 셋뿐이고
   (`not_found`/`usage`/`rejected`) 그것이 실패 어휘의 전부다.
3. **stdio 왕복** — 실제 MCP 클라이언트가 서버 프로세스를 띄워 도구를 부를 수
   있다(핸들러를 직접 부르는 나머지 테스트가 못 보는 배선: 도구 등록, 스키마
   생성, 전송).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from daedalus.cli.core import ERROR_KINDS
from daedalus.cli.mcp_server import (
    TOOL_NAMES,
    TOOLS,
    BlackboardTools,
    build_parser,
    server_name,
    tools_from_args,
)

SCHEMAS = {
    "Task": {
        "type": "object",
        "description": "작업 항목",
        "properties": {
            "title": {"type": "string"},
            "count": {"type": "integer"},
            "done": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "owners": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
        },
        "required": ["title"],
    },
    "Config": {
        "type": "object",
        "properties": {"level": {"type": "integer"}},
        "required": ["level"],
    },
}


@pytest.fixture
def tools(tmp_path: Path) -> BlackboardTools:
    """컴파일 산출과 같은 모양 — `schemas/<플러그인>.json` + `state/<플러그인>/`."""
    schemas = tmp_path / "schemas" / "demo.json"
    schemas.parent.mkdir(parents=True)
    schemas.write_text(
        json.dumps(SCHEMAS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return BlackboardTools(schemas, tmp_path / "state" / "demo")


def _error(result) -> dict:
    assert isinstance(result, dict) and result.get("ok") is False, result
    return result["error"]


# ─────────────────────────── 진입 인자 (CLI와 같다) ───────────────────────────


def test_entry_arguments_match_the_old_cli(tmp_path: Path):
    """`--schemas` 필수 + `--state-dir` 유도 — 종전 CLI 계약 그대로 (WP-NS/D10)."""
    args = build_parser().parse_args(["--schemas", "schemas/my-plugin.json"])
    built = tools_from_args(args)
    assert built.plugin == "my-plugin"
    assert built.state_dir == Path("state") / "my-plugin"


def test_explicit_state_dir_still_wins():
    args = build_parser().parse_args(
        ["--schemas", "schemas/p.json", "--state-dir", "elsewhere"]
    )
    assert tools_from_args(args).state_dir == Path("elsewhere")


def test_schemas_is_required(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--state-dir", "x"])
    assert excinfo.value.code == 2
    assert "--schemas" in capsys.readouterr().err


def test_server_name_is_bb_plus_plugin(tools: BlackboardTools):
    """서버 이름 규약 — 컴파일러가 `.mcp.json`에 쓰는 이름과 같아야 한다."""
    assert server_name(tools.plugin) == "bb-demo"


def test_schema_file_is_not_read_at_startup(tmp_path: Path):
    """스키마가 없어도 서버는 뜬다 — 죽으면 모델이 이유를 듣지 못한다(원칙 5)."""
    built = BlackboardTools(tmp_path / "schemas" / "gone.json", tmp_path / "state")
    assert _error(built.tool_list())["kind"] == "usage"


# ─────────────────────────── 1:1 매핑 (CLI 시나리오) ───────────────────────────


def test_list_reports_classes_and_fields(tools: BlackboardTools):
    out = tools.tool_list()
    assert [cls["name"] for cls in out["classes"]] == ["Task", "Config"]
    task = out["classes"][0]
    assert task["description"] == "작업 항목"
    fields = {f["name"]: f for f in task["fields"]}
    assert fields["title"]["required"] is True
    assert fields["tags"]["collection"] == "list"
    assert fields["owners"]["collection"] == "set"


def test_init_creates_the_schema_shaped_object(tools: BlackboardTools):
    assert tools.tool_init("Task") == {"title": ""}
    assert (tools.state_dir / "Task.json").is_file()


def test_init_refuses_an_existing_file_without_force(tools: BlackboardTools):
    tools.tool_init("Task")
    assert _error(tools.tool_init("Task"))["kind"] == "usage"
    assert tools.tool_init("Task", force=True) == {"title": ""}


def test_read_returns_the_whole_object_or_one_field(tools: BlackboardTools):
    tools.tool_write("Task", set={"title": "A"})
    assert tools.tool_read("Task") == {"title": "A"}
    assert tools.tool_read("Task", "title") == {"field": "title", "value": "A"}


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("count", "3", 3),
        ("count", 3, 3),
        ("done", "true", True),
        ("done", True, True),
        ("title", "A", "A"),
    ],
)
def test_write_takes_json_types_and_coerces_strings(
    tools: BlackboardTools, field: str, value, expected
):
    """값은 JSON 타입 그대로 받되 **문자열이면** 종전 코어션 규칙이 돈다."""
    out = tools.tool_write("Task", set={"title": "A", field: value})
    assert out[field] == expected
    assert type(out[field]) is type(expected)


def test_write_append_and_remove_work_on_collections(tools: BlackboardTools):
    tools.tool_write("Task", set={"title": "A"})
    assert tools.tool_write("Task", append={"tags": ["x", "y"]})["tags"] == ["x", "y"]
    assert tools.tool_write("Task", append={"tags": "z"})["tags"] == ["x", "y", "z"]
    assert tools.tool_write("Task", remove={"tags": "y"})["tags"] == ["x", "z"]


def test_set_collection_dedupes_for_unique_items(tools: BlackboardTools):
    out = tools.tool_write("Task", set={"title": "A", "owners": ["a", "b", "a"]})
    assert out["owners"] == ["a", "b"]


def test_validate_reports_missing_and_violations(tools: BlackboardTools):
    assert tools.tool_validate() == {
        "ok": True, "checked": [], "missing": ["Task", "Config"], "violations": [],
    }
    (tools.state_dir).mkdir(parents=True, exist_ok=True)
    (tools.state_dir / "Task.json").write_text('{"count": 1}', encoding="utf-8")
    result = tools.tool_validate()
    assert result["ok"] is False
    assert any("title" in v for v in result["violations"])


def test_progress_read_and_set_round_trip(tools: BlackboardTools):
    assert _error(tools.tool_progress_read())["kind"] == "not_found"
    entry = tools.tool_progress_set(current="collect", completed=["plan"], note="갈래: ok")
    assert entry["current"] == "collect"
    assert entry["completed"] == ["plan"]
    assert tools.tool_progress_read()["current"] == "collect"


def test_progress_file_sits_beside_the_state_dir(tools: BlackboardTools):
    """블랙보드는 `state/<플러그인>/`, 진행 파일은 `state/` 루트 (D13)."""
    tools.tool_progress_set(current="a")
    assert (tools.state_dir.parent / "__progress__.json").is_file()


def test_progress_set_preserves_other_plugin_entries(tmp_path: Path):
    def _make(plugin: str) -> BlackboardTools:
        path = tmp_path / "schemas" / f"{plugin}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(SCHEMAS), encoding="utf-8")
        return BlackboardTools(path, tmp_path / "state" / plugin)

    _make("alpha").tool_progress_set(current="a1")
    _make("beta").tool_progress_set(current="b1")
    data = json.loads(
        (tmp_path / "state" / "__progress__.json").read_text(encoding="utf-8")
    )
    assert set(data) == {"alpha", "beta"}
    assert data["alpha"]["current"] == "a1"


# ─────────────────────────── 오류 kind ───────────────────────────


def test_the_failure_vocabulary_is_exactly_three_kinds():
    """산출 가이드가 설명하는 kind 집합과 코어가 내는 집합이 같아야 한다.

    모델은 이 세 단어로만 분기한다 — 넷째가 생기면 가이드가 침묵한 채 모델이
    모르는 값을 받는다(원칙 5).
    """
    assert ERROR_KINDS == ("not_found", "usage", "rejected")


@pytest.mark.parametrize(
    "scenario,kind",
    [
        ("read_missing_file", "not_found"),
        ("read_unknown_class", "usage"),
        ("read_unknown_field", "usage"),
        ("write_no_operation", "usage"),
        ("write_bad_scalar", "usage"),
        ("append_on_scalar_field", "usage"),
        ("init_existing", "usage"),
        ("write_violates_schema", "rejected"),
        ("progress_read_missing", "not_found"),
    ],
)
def test_failures_come_back_as_results_not_exceptions(
    tools: BlackboardTools, scenario: str, kind: str
):
    """실패는 전부 결과다 — 모델이 읽는 값이므로 예외로 끊지 않는다."""
    if scenario == "read_missing_file":
        result = tools.tool_read("Task")
    elif scenario == "read_unknown_class":
        result = tools.tool_read("Nope")
    elif scenario == "read_unknown_field":
        result = tools.tool_read("Task", "nope")
    elif scenario == "write_no_operation":
        result = tools.tool_write("Task")
    elif scenario == "write_bad_scalar":
        result = tools.tool_write("Task", set={"count": "열"})
    elif scenario == "append_on_scalar_field":
        result = tools.tool_write("Task", append={"title": "x"})
    elif scenario == "init_existing":
        tools.tool_init("Task")
        result = tools.tool_init("Task")
    elif scenario == "write_violates_schema":
        tools.state_dir.mkdir(parents=True, exist_ok=True)
        (tools.state_dir / "Task.json").write_text('{"count": 1}', encoding="utf-8")
        result = tools.tool_write("Task", set={"count": 2})
    else:
        result = tools.tool_progress_read()
    assert _error(result)["kind"] == kind


def test_rejected_write_carries_the_violations_as_detail(tools: BlackboardTools):
    """stderr로 나가던 위반 목록이 결과의 `detail`이 된다 — 채널을 섞지 않는다."""
    tools.state_dir.mkdir(parents=True, exist_ok=True)
    (tools.state_dir / "Task.json").write_text('{"count": 1}', encoding="utf-8")
    error = _error(tools.tool_write("Task", set={"count": 2}))
    assert error["kind"] == "rejected"
    assert any("Task.title" in line for line in error["detail"])
    # 거절은 파일을 건드리지 않는다.
    assert json.loads((tools.state_dir / "Task.json").read_text("utf-8")) == {"count": 1}


def test_every_result_is_json_serializable(tools: BlackboardTools):
    """도구 결과는 그대로 전송된다 — 직렬화할 수 없는 값이 섞이면 조용히 죽는다."""
    tools.tool_init("Task")
    for result in (
        tools.tool_list(), tools.tool_read("Task"), tools.tool_read("Task", "title"),
        tools.tool_write("Task", set={"title": "A"}), tools.tool_validate(),
        tools.tool_progress_set(current="a"), tools.tool_progress_read(),
        tools.tool_read("Nope"),
    ):
        json.dumps(result, ensure_ascii=False)


# ─────────────────────────── stdio 왕복 스모크 ───────────────────────────


def test_tool_names_come_from_the_declared_table(tools: BlackboardTools):
    """노출 이름과 핸들러는 한 표에서 나온다 — 이름만 적고 `getattr`로 찾지 않는다."""
    assert TOOL_NAMES == tuple(name for name, _ in TOOLS)
    assert len(TOOLS) == 7
    for _, func in TOOLS:
        assert callable(func.__get__(tools))


@pytest.mark.parametrize("name,func", TOOLS, ids=[n for n, _ in TOOLS])
def test_every_tool_has_an_english_description(name: str, func):
    """도구 설명은 세션마다 컨텍스트에 실린다 — 영어로, 한 줄로 (원칙 6)."""
    doc = (func.__doc__ or "").strip()
    assert doc and "\n" not in doc
    assert doc.isascii(), doc


def test_stdio_round_trip_lists_and_calls_a_tool(tmp_path: Path):
    """실제 MCP 클라이언트가 서버 프로세스를 띄워 `list`를 부른다.

    핸들러를 직접 부르는 나머지 테스트가 못 보는 배선(도구 등록·입력 스키마
    생성·stdio 전송)을 한 번 훑는다.
    """
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    schemas = tmp_path / "schemas" / "demo.json"
    schemas.parent.mkdir(parents=True)
    schemas.write_text(json.dumps(SCHEMAS), encoding="utf-8")

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from daedalus.cli.mcp_server import main; main()",
            "--schemas",
            str(schemas),
            "--state-dir",
            str(tmp_path / "state" / "demo"),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
    )

    async def _exercise() -> tuple[list[str], str]:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                called = await session.call_tool("list", {})
                return [t.name for t in listed.tools], called.content[0].text

    names, payload = anyio.run(_exercise)
    assert set(names) == set(TOOL_NAMES)
    assert "Task" in payload


def test_an_unregistered_kind_is_refused_loudly():
    """넷째 kind를 조용히 만들 수 없다 — 가이드가 설명하지 못하는 값이 새면 안 된다."""
    from daedalus.cli.core import BlackboardError

    with pytest.raises(ValueError, match="등록되지 않은 오류 kind"):
        BlackboardError("weird", "…")


# ─── 진입점: cp949 콘솔에서도 --help가 죽지 않는다 (2026-09-20 머지 검토) ───


def test_main_help_survives_cp949_console(monkeypatch):
    """Windows 기본 콘솔(cp949)에 한글·em-dash 도움말을 쓰면 옛 CLI는
    스트림을 UTF-8로 재설정해 살았다 — 새 진입점도 같아야 한다."""
    import io

    from daedalus.cli.mcp_server import main

    out = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
    err = io.TextIOWrapper(io.BytesIO(), encoding="cp949")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    assert main(["--help"]) == 0
    out.flush()
    text = out.buffer.getvalue().decode("utf-8")
    assert "--schemas" in text and "stdio MCP" in text
