"""진행 상태 파일을 코드가 전담한다 (WP-NS/D13 → WP-BM).

왜 산문이 아니라 코드인가: `state/__progress__.json`은 지금까지 **산문 지시로
손편집**됐다. 최상위 키가 플러그인 이름이 되면 "다른 최상위 키는 건드리지 말라"는
병합을 LLM이 손으로 해야 하고, 놓치면 파일을 통째 덮어써 남의 진행 상태를 지운다 —
파일시스템 충돌을 파일 안으로 옮기는 셈이다. 그래서 병합을 코드가 보장한다.

배치 규약(D13): 블랙보드는 `state/<플러그인>/`로 갈라지지만 진행 파일은 `state/`
루트에 하나로 남는다. 워크스페이스 전체를 한눈에 보는 것이 그 파일의 목적이고,
`__progress__.json`은 문서에 명시된 **스키마 밖 규약 파일**이라 클래스 순회 대상도
아니다. 그래서 진행 파일은 상태 폴더의 **부모**에 놓인다.

WP-BM에서 표면이 CLI에서 MCP 도구로 바뀌었고, 이 시나리오들은 표면이 아니라
**코어**(`daedalus.cli.progress`)를 태운다 — 어느 표면에서 불리든 같은 계약이다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli import core, progress
from daedalus.cli.core import BlackboardError


def _state_dir(root: Path, plugin: str) -> Path:
    """그 플러그인의 상태 폴더 — 경로 유도는 코어의 규약 함수가 한다."""
    return root / core.resolve_state_dir(None, Path("schemas") / f"{plugin}.json")


def _progress_file(root: Path) -> dict:
    return json.loads((root / "state" / "__progress__.json").read_text("utf-8"))


# ─────────────────────────── 기본 동작 ───────────────────────────


def test_set_creates_entry_under_plugin_key(tmp_path: Path):
    """진행 항목이 플러그인 이름을 최상위 키로 하는 객체 밑에 생긴다."""
    entry = progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="collect")
    assert entry["current"] == "collect"
    data = _progress_file(tmp_path)
    assert list(data) == ["alpha"]
    assert data["alpha"]["current"] == "collect"


def test_progress_file_sits_beside_state_dir(tmp_path: Path):
    """블랙보드는 state/<플러그인>/, 진행 파일은 state/ 루트에 놓인다."""
    progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="collect")
    assert (tmp_path / "state" / "__progress__.json").is_file()
    assert not (tmp_path / "state" / "alpha" / "__progress__.json").exists()


def test_set_accumulates_completed_without_duplicates(tmp_path: Path):
    state = _state_dir(tmp_path, "alpha")
    progress.set_entry(state, "alpha", current="b", completed=["a"])
    entry = progress.set_entry(state, "alpha", current="c", completed=["b", "a"])
    assert entry["completed"] == ["a", "b"]
    assert _progress_file(tmp_path)["alpha"]["completed"] == ["a", "b"]


def test_set_records_note_and_prev(tmp_path: Path):
    entry = progress.set_entry(
        _state_dir(tmp_path, "alpha"), "alpha",
        current="c", note="갈래: done", prev="b",
    )
    assert entry["note"] == "갈래: done"
    assert entry["prev"] == "b"


def test_set_stamps_updated(tmp_path: Path):
    entry = progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="c")
    assert entry["updated"]


def test_set_leaves_unset_fields_out(tmp_path: Path):
    """없는 필드는 쓰지 않는다 — 빈 값으로 채우면 '설정했다'와 구분이 안 된다."""
    entry = progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="c")
    assert set(entry) == {"current", "updated"}


def test_read_returns_own_entry(tmp_path: Path):
    state = _state_dir(tmp_path, "alpha")
    progress.set_entry(state, "alpha", current="collect")
    assert progress.read_entry(state, "alpha")["current"] == "collect"


def test_read_missing_is_not_found(tmp_path: Path):
    with pytest.raises(BlackboardError) as excinfo:
        progress.read_entry(_state_dir(tmp_path, "alpha"), "alpha")
    assert excinfo.value.kind == "not_found"


# ────────────────── 공존 — 이 규약이 고치는 실제 버그 ──────────────────


def test_set_preserves_other_plugin_entry(tmp_path: Path):
    """다른 플러그인의 진행 항목을 건드리지 않는다.

    진행 파일은 고정 파일명이라 두 ddls 플러그인이 한 작업 폴더에 있으면 나중에
    쓴 쪽만 남았다 — WP-NS가 고치는 실제 버그다.
    """
    progress.set_entry(
        _state_dir(tmp_path, "alpha"), "alpha", current="a1", completed=["a0"],
    )
    progress.set_entry(_state_dir(tmp_path, "beta"), "beta", current="b1")

    data = _progress_file(tmp_path)
    assert set(data) == {"alpha", "beta"}
    assert data["alpha"]["current"] == "a1"
    assert data["alpha"]["completed"] == ["a0"]
    assert data["beta"]["current"] == "b1"


def test_read_does_not_see_other_plugin(tmp_path: Path):
    progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="a1")
    with pytest.raises(BlackboardError) as excinfo:
        progress.read_entry(_state_dir(tmp_path, "beta"), "beta")
    assert excinfo.value.kind == "not_found", (
        "beta는 아직 자기 항목이 없으므로 alpha 것을 보면 안 된다"
    )


# ─────────────────────────── 손상·구형식 입력 ───────────────────────────


def test_legacy_flat_file_is_rejected(tmp_path: Path):
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
    with pytest.raises(BlackboardError) as excinfo:
        progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="new")
    assert excinfo.value.kind == "usage"
    assert "구형식" in excinfo.value.message
    assert _progress_file(tmp_path)["current"] == "old"  # 파일은 그대로


def test_broken_json_is_rejected(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "__progress__.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(BlackboardError) as excinfo:
        progress.set_entry(_state_dir(tmp_path, "alpha"), "alpha", current="new")
    assert excinfo.value.kind == "usage"
    assert "__progress__.json" in excinfo.value.message


# ─────────────────────────── 낙관적 잠금 ───────────────────────────


def test_persistent_conflict_is_rejected_without_losing_the_other_write(
    tmp_path: Path, monkeypatch
):
    """계속 충돌하면 거부한다 — 블랙보드 write의 재시도 소진과 같은 계약이다."""
    state = _state_dir(tmp_path, "alpha")
    progress.set_entry(state, "alpha", current="a1")
    path = progress.progress_path(state)

    real = core.write_state_checked
    calls = {"n": 0}

    def _patched(target, obj, expected_raw):
        calls["n"] += 1
        current = json.loads(target.read_text(encoding="utf-8"))
        current["beta"] = {"current": f"other-{calls['n']}"}
        target.write_text(json.dumps(current), encoding="utf-8")
        return real(target, obj, expected_raw)

    monkeypatch.setattr(core, "write_state_checked", _patched)
    with pytest.raises(BlackboardError) as excinfo:
        progress.set_entry(state, "alpha", current="a2")
    assert excinfo.value.kind == "rejected"
    assert calls["n"] == core._WRITE_MAX_ATTEMPTS
    # 내 갱신은 반영되지 않았고 남의 마지막 쓰기는 그대로 남는다.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["alpha"]["current"] == "a1"
    assert data["beta"]["current"] == f"other-{core._WRITE_MAX_ATTEMPTS}"
