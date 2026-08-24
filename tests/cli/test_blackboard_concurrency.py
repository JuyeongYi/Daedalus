"""블랙보드 CLI write의 lost update 방지 — 낙관적 잠금 + 재시도 (A6).

병렬 서브에이전트가 같은 클래스를 갱신하면, 읽기-수정-쓰기 사이에 남이 쓴
내용을 통째로 덮어써 **한쪽 갱신이 조용히 사라졌다**.

끼어드는 쓰기는 `write_state_checked`를 감싸 시뮬레이션한다 — 실제 경쟁과
같은 지점(비교 직전)에 파일을 바꿔치기해야 재시도 경로가 실제로 돈다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from daedalus.cli import blackboard
from daedalus.cli.blackboard import main

SCHEMAS = {
    "Task": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "owner": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title"],
    },
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    schemas_path = tmp_path / "schemas" / "schemas.json"
    schemas_path.parent.mkdir(parents=True)
    schemas_path.write_text(json.dumps(SCHEMAS), encoding="utf-8")
    (tmp_path / "state").mkdir()
    return tmp_path


@pytest.fixture
def run(workspace: Path, capsys):
    def _run(*argv: str):
        code = main([
            "--state-dir", str(workspace / "state"),
            "--schemas", str(workspace / "schemas" / "schemas.json"),
            *argv,
        ])
        captured = capsys.readouterr()
        return code, captured.err

    return _run


def _state(workspace: Path) -> dict:
    return json.loads((workspace / "state" / "Task.json").read_text(encoding="utf-8"))


def _interloper(workspace: Path, monkeypatch, times: int):
    """`times`번의 쓰기 시도 직전마다 다른 프로세스가 파일을 고치게 한다."""
    real = blackboard.write_state_checked
    calls = {"n": 0}

    def _patched(path, obj, expected_raw):
        if calls["n"] < times:
            calls["n"] += 1
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            current["owner"] = f"other-{calls['n']}"
            path.write_text(json.dumps(current), encoding="utf-8")
        return real(path, obj, expected_raw)

    monkeypatch.setattr(blackboard, "write_state_checked", _patched)
    return calls


def test_normal_write_still_works(run, workspace):
    """경쟁이 없으면 종전 그대로 — 한 번에 쓰고 exit 0."""
    assert run("write", "Task", "--set", "title=A")[0] == 0
    assert _state(workspace)["title"] == "A"


def test_conflict_retries_and_keeps_both_changes(run, workspace, monkeypatch):
    """충돌하면 다시 읽어 적용한다 — 두 쓰기가 모두 살아남는다."""
    run("write", "Task", "--set", "title=A")
    calls = _interloper(workspace, monkeypatch, times=1)

    code, err = run("write", "Task", "--set", "title=B")
    assert code == 0
    assert calls["n"] == 1
    assert "다시 읽어 적용한다" in err

    state = _state(workspace)
    assert state["title"] == "B"          # 내 갱신
    assert state["owner"] == "other-1"    # 남의 갱신 (덮어쓰지 않았다)


def test_conflict_on_first_write_of_missing_file(run, workspace, monkeypatch):
    """파일이 없던 상태에서 남이 먼저 만들어도 그 내용을 살린다."""
    calls = _interloper(workspace, monkeypatch, times=1)

    assert run("write", "Task", "--set", "title=B")[0] == 0
    assert calls["n"] == 1
    state = _state(workspace)
    assert state["title"] == "B"
    assert state["owner"] == "other-1"


def test_persistent_conflict_fails_without_losing_the_other_write(
    run, workspace, monkeypatch
):
    """계속 충돌하면 exit 1 + 안내. 남의 마지막 쓰기는 그대로 남는다."""
    run("write", "Task", "--set", "title=A")
    calls = _interloper(workspace, monkeypatch, times=99)

    code, err = run("write", "Task", "--set", "title=B")
    assert code == 1
    assert calls["n"] == blackboard._WRITE_MAX_ATTEMPTS
    assert "다른 프로세스가 계속 고쳤다" in err

    state = _state(workspace)
    assert state["title"] == "A"  # 내 갱신은 반영되지 않았다
    assert state["owner"] == f"other-{blackboard._WRITE_MAX_ATTEMPTS}"


def test_append_is_reapplied_on_top_of_the_other_write(run, workspace, monkeypatch):
    """`--append`도 새 내용 위에 다시 적용된다 — 원소가 사라지지 않는다."""
    run("write", "Task", "--set", "title=A", "--append", "tags=x")

    real = blackboard.write_state_checked
    fired = {"done": False}

    def _patched(path, obj, expected_raw):
        if not fired["done"]:
            fired["done"] = True
            current = json.loads(path.read_text(encoding="utf-8"))
            current["tags"] = current.get("tags", []) + ["from-other"]
            path.write_text(json.dumps(current), encoding="utf-8")
        return real(path, obj, expected_raw)

    monkeypatch.setattr(blackboard, "write_state_checked", _patched)

    assert run("write", "Task", "--append", "tags=y")[0] == 0
    assert _state(workspace)["tags"] == ["x", "from-other", "y"]


def test_validation_failure_does_not_retry(run, workspace, monkeypatch):
    """검증 실패는 재시도할 이유가 없다 — 다시 읽어도 같은 값이 같은 위반이다."""
    # title은 required인데 초기 객체가 그것을 빈 문자열로 채운 뒤 지울 수는
    # 없으므로, 스키마 밖 위반을 만들기 위해 required 필드를 지운 파일에서 시작한다.
    (workspace / "state" / "Task.json").write_text('{"owner": "x"}', encoding="utf-8")
    calls = _interloper(workspace, monkeypatch, times=99)

    code, err = run("write", "Task", "--set", "owner=y")
    assert code == 1
    assert calls["n"] == 0  # 쓰기 시도 자체를 하지 않았다
    assert "검증 실패" in err


def test_write_state_checked_detects_change(tmp_path):
    """CAS 원시 연산 단위 — 기대 원문과 다르면 쓰지 않는다."""
    path = tmp_path / "s.json"
    path.write_text('{"a": 1}', encoding="utf-8")

    assert blackboard.write_state_checked(path, {"a": 2}, '{"a": 9}') is False
    assert path.read_text(encoding="utf-8") == '{"a": 1}'

    assert blackboard.write_state_checked(path, {"a": 2}, '{"a": 1}') is True
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2}


def test_write_state_checked_expects_none_for_missing_file(tmp_path):
    """없던 파일은 expected_raw=None — 그 사이에 생겼으면 충돌이다."""
    path = tmp_path / "s.json"
    assert blackboard.write_state_checked(path, {"a": 1}, None) is True

    assert blackboard.write_state_checked(path, {"a": 2}, None) is False
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
