"""``daedalus-bb progress`` — 진행 상태 파일을 CLI가 전담한다 (WP-NS/D13).

왜 CLI인가: `state/__progress__.json`은 지금까지 **산문 지시로 손편집**됐다. 최상위
키가 플러그인 이름이 되면 "다른 최상위 키는 건드리지 말라"는 병합을 LLM이 손으로
해야 하고, 놓치면 파일을 통째 덮어써 남의 진행 상태를 지운다 — 파일시스템 충돌을
파일 안으로 옮기는 셈이다. 그래서 병합을 코드가 보장한다.

배치 규약(D13): 블랙보드는 `state/<플러그인>/`로 갈라지지만 진행 파일은 `state/`
루트에 하나로 남는다. 워크스페이스 전체를 한눈에 보는 것이 그 파일의 목적이고,
`__progress__.json`은 문서에 명시된 **스키마 밖 규약 파일**이라 클래스 순회 대상도
아니다. 그래서 CLI는 진행 파일을 `--state-dir`의 **부모**에 놓는다.
"""
from __future__ import annotations

import json
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


def _make_plugin(root: Path, name: str) -> Path:
    """`schemas/<플러그인>.json`을 깔고 그 경로를 돌려준다 (WP-NS 명명 규약)."""
    path = root / "schemas" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(SCHEMAS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def run(tmp_path: Path, capsys):
    """플러그인 이름을 받아 그 플러그인으로 CLI를 도는 러너를 만든다.

    `--state-dir`을 명시하지 않는다 — 기본값이 스키마 stem에서 유도되는지가
    검증 대상이기 때문이다. 그래서 CWD를 작업 폴더로 옮겨 실행한다.
    """

    def _factory(plugin: str):
        schemas = _make_plugin(tmp_path, plugin)

        def _run(*argv: str):
            import os

            prev = os.getcwd()
            os.chdir(tmp_path)
            try:
                code = main(["--schemas", str(schemas), *argv])
            finally:
                os.chdir(prev)
            captured = capsys.readouterr()
            out = json.loads(captured.out) if captured.out.strip() else None
            return code, out, captured.err

        return _run

    return _factory


def _progress(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "state" / "__progress__.json").read_text("utf-8"))


# ─────────────────────────── 기본 동작 ───────────────────────────


def test_set_creates_entry_under_plugin_key(run, tmp_path: Path):
    """진행 항목이 플러그인 이름을 최상위 키로 하는 객체 밑에 생긴다."""
    code, _, err = run("alpha")("progress", "set", "--current", "collect")
    assert code == 0, err
    data = _progress(tmp_path)
    assert list(data) == ["alpha"]
    assert data["alpha"]["current"] == "collect"


def test_progress_file_sits_beside_state_dir(run, tmp_path: Path):
    """블랙보드는 state/<플러그인>/, 진행 파일은 state/ 루트에 놓인다."""
    run("alpha")("progress", "set", "--current", "collect")
    assert (tmp_path / "state" / "__progress__.json").is_file()
    assert not (tmp_path / "state" / "alpha" / "__progress__.json").exists()


def test_set_accumulates_completed_without_duplicates(run, tmp_path: Path):
    runner = run("alpha")
    runner("progress", "set", "--current", "b", "--completed", "a")
    runner("progress", "set", "--current", "c", "--completed", "b", "--completed", "a")
    assert _progress(tmp_path)["alpha"]["completed"] == ["a", "b"]


def test_set_records_note_and_prev(run, tmp_path: Path):
    run("alpha")(
        "progress", "set", "--current", "c", "--note", "갈래: done", "--prev", "b"
    )
    entry = _progress(tmp_path)["alpha"]
    assert entry["note"] == "갈래: done"
    assert entry["prev"] == "b"


def test_set_stamps_updated(run, tmp_path: Path):
    run("alpha")("progress", "set", "--current", "c")
    assert _progress(tmp_path)["alpha"]["updated"]


def test_read_outputs_own_entry(run):
    runner = run("alpha")
    runner("progress", "set", "--current", "collect")
    code, out, err = runner("progress", "read")
    assert code == 0, err
    assert out["current"] == "collect"


def test_read_missing_exits_3(run):
    code, out, _ = run("alpha")("progress", "read")
    assert code == 3
    assert out is None


# ────────────────── 공존 — 이 WP가 고치려는 버그 ──────────────────


def test_set_preserves_other_plugin_entry(run, tmp_path: Path):
    """다른 플러그인의 진행 항목을 건드리지 않는다.

    이것이 WP-NS가 고치는 실제 버그다. 진행 파일은 고정 파일명이라 두 ddls
    플러그인이 한 작업 폴더에 있으면 나중에 쓴 쪽만 남았다.
    """
    run("alpha")("progress", "set", "--current", "a1", "--completed", "a0")
    run("beta")("progress", "set", "--current", "b1")

    data = _progress(tmp_path)
    assert set(data) == {"alpha", "beta"}
    assert data["alpha"]["current"] == "a1"
    assert data["alpha"]["completed"] == ["a0"]
    assert data["beta"]["current"] == "b1"


def test_read_does_not_see_other_plugin(run):
    run("alpha")("progress", "set", "--current", "a1")
    code, out, _ = run("beta")("progress", "read")
    assert code == 3, "beta는 아직 자기 항목이 없으므로 alpha 것을 보면 안 된다"
    assert out is None


# ─────────────────────────── 손상·구형식 입력 ───────────────────────────


def test_legacy_flat_file_is_rejected(run, tmp_path: Path):
    """구형식(최상위에 current)이면 덮어쓰지 않고 거부한다.

    기존 런타임 데이터는 마이그레이션하지 않기로 했지만(D11), 그것이 조용히
    덮어써도 된다는 뜻은 아니다 — 무엇이 문제인지 말하고 멈춘다.
    """
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "__progress__.json").write_text(
        json.dumps({"plugin": "alpha", "current": "old", "completed": []}),
        encoding="utf-8",
    )
    code, _, err = run("alpha")("progress", "set", "--current", "new")
    assert code == 2
    assert "구형식" in err or "legacy" in err.lower()
    # 파일은 그대로여야 한다.
    assert _progress(tmp_path)["current"] == "old"


def test_broken_json_is_rejected(run, tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "__progress__.json").write_text("{not json", encoding="utf-8")
    code, _, err = run("alpha")("progress", "set", "--current", "new")
    assert code == 2
    assert "__progress__.json" in err
