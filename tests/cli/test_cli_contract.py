"""``daedalus-bb`` 인자 계약 — `--schemas` 필수 + `--state-dir` 유도 (WP-NS/D10).

두 인자가 어긋나면 **조용히 엉뚱한 곳에 쓴다**. `--schemas`를 빠뜨리면 파일이 없어
시끄럽게 실패하지만, `--state-dir`를 빠뜨리면 네임스페이스 밖에 쓰고 검증까지
통과한다 — 아무도 읽지 않는 상태 파일이 생긴다. 그래서 인자 **하나**가 두 경로를
모두 결정하게 만든다: `--state-dir` 기본값을 `--schemas`의 stem에서 유도한다.

positional 고정안을 쓰지 않은 이유도 여기 있다 — 빠뜨렸을 때 argparse가 첫 인자를
경로로 먹고 `invalid choice: 'Task'`라는 엉뚱한 메시지를 낸다. 필수 옵션이면 무엇이
빠졌는지 정확히 짚는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from daedalus.cli.blackboard import main

SCHEMAS = {
    "Task": {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    },
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "schemas" / "my-plugin.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(SCHEMAS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return tmp_path


def _run_in(cwd: Path, argv: list[str]) -> int:
    prev = os.getcwd()
    os.chdir(cwd)
    try:
        return main(argv)
    finally:
        os.chdir(prev)


def test_schemas_is_required(workspace: Path, capsys):
    """`--schemas` 없이 부르면 사용법 오류로 거부한다."""
    code = _run_in(workspace, ["list"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--schemas" in err
    # 사용법 오류여야 한다 — 기본값 경로를 열어 보고 "파일이 없다"고 답하면
    # 무엇이 빠졌는지 말해 주지 않는 것과 같다.
    assert "스키마 파일이 없다" not in err


def test_state_dir_defaults_to_schema_stem(workspace: Path, capsys):
    """`--state-dir` 미지정 시 `state/<스키마 stem>`에 쓴다."""
    code = _run_in(
        workspace,
        ["--schemas", str(workspace / "schemas" / "my-plugin.json"), "init", "Task"],
    )
    capsys.readouterr()
    assert code == 0
    assert (workspace / "state" / "my-plugin" / "Task.json").is_file()
    assert not (workspace / "state" / "Task.json").exists()


def test_absolute_schemas_still_yields_relative_state_dir(tmp_path: Path, capsys):
    """스키마가 절대경로여도 상태는 **작업 폴더 상대**로 남는다.

    마켓플레이스 빌드는 `${CLAUDE_PLUGIN_ROOT}/schemas/<플러그인>.json`을 넘기는데,
    상태까지 플러그인 디렉토리로 따라가면 작업 폴더마다 달라야 할 데이터가 섞인다.
    그래서 stem만 쓴다.
    """
    plugin_dir = tmp_path / "elsewhere" / "schemas"
    plugin_dir.mkdir(parents=True)
    schemas = plugin_dir / "my-plugin.json"
    schemas.write_text(json.dumps(SCHEMAS), encoding="utf-8")

    work = tmp_path / "work"
    work.mkdir()
    code = _run_in(work, ["--schemas", str(schemas), "init", "Task"])
    capsys.readouterr()
    assert code == 0
    assert (work / "state" / "my-plugin" / "Task.json").is_file()
    assert not (plugin_dir.parent / "state").exists()


def test_explicit_state_dir_still_wins(workspace: Path, capsys):
    """명시한 `--state-dir`는 유도값을 덮는다 (기존 호출부 호환)."""
    target = workspace / "custom"
    code = _run_in(
        workspace,
        [
            "--state-dir", str(target),
            "--schemas", str(workspace / "schemas" / "my-plugin.json"),
            "init", "Task",
        ],
    )
    capsys.readouterr()
    assert code == 0
    assert (target / "Task.json").is_file()
