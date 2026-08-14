"""최근 프로젝트 목록 (WP-RP) — 순수 계층.

Qt 없이 파일 하나만 다루는 계층이라 여기서는 목록 규칙만 확인한다. 메뉴 배선은
``test_app_recent.py``에서 검증한다.
"""
from __future__ import annotations

import json
import os

from daedalus.view import recent


def test_load_returns_empty_when_file_absent():
    assert recent.load() == []


def test_push_then_load_roundtrip():
    recent.push("a.daedalus.json")
    assert recent.load() == [os.path.abspath("a.daedalus.json")]


def test_push_stores_absolute_path():
    """상대 경로로 밀어 넣어도 절대 경로로 남아야 한다 — 작업 디렉토리가 바뀌어도
    메뉴 항목이 엉뚱한 파일을 가리키지 않도록."""
    recent.push("rel.daedalus.json")
    stored = recent.load()[0]
    assert os.path.isabs(stored)


def test_most_recent_comes_first():
    recent.push("a.json")
    recent.push("b.json")
    assert [os.path.basename(p) for p in recent.load()] == ["b.json", "a.json"]


def test_repush_moves_to_front_without_duplicating():
    recent.push("a.json")
    recent.push("b.json")
    recent.push("a.json")
    assert [os.path.basename(p) for p in recent.load()] == ["a.json", "b.json"]


def test_equivalent_paths_are_one_entry():
    """같은 파일을 다른 표기로 열어도 항목이 둘로 늘지 않는다."""
    recent.push(os.path.join("x", "..", "a.json"))
    recent.push("a.json")
    assert len(recent.load()) == 1


def test_list_is_capped_at_max():
    for i in range(recent.MAX_RECENT + 5):
        recent.push(f"p{i}.json")
    paths = recent.load()
    assert len(paths) == recent.MAX_RECENT
    # 가장 오래된 것부터 밀려난다
    assert os.path.basename(paths[0]) == f"p{recent.MAX_RECENT + 4}.json"


def test_blank_path_is_ignored():
    recent.push("a.json")
    recent.push("   ")
    assert len(recent.load()) == 1


def test_remove_drops_entry():
    recent.push("a.json")
    recent.push("b.json")
    recent.remove("a.json")
    assert [os.path.basename(p) for p in recent.load()] == ["b.json"]


def test_clear_empties_list():
    recent.push("a.json")
    recent.clear()
    assert recent.load() == []


def test_corrupt_file_reads_as_empty():
    recent.RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    recent.RECENT_PATH.write_text("{ not json", encoding="utf-8")
    assert recent.load() == []


def test_non_list_payload_reads_as_empty():
    recent.RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    recent.RECENT_PATH.write_text('{"paths": []}', encoding="utf-8")
    assert recent.load() == []


def test_non_string_entries_are_skipped():
    recent.RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    recent.RECENT_PATH.write_text(json.dumps(["a.json", 42, None]), encoding="utf-8")
    assert recent.load() == ["a.json"]


def test_write_failure_is_swallowed(monkeypatch, tmp_path):
    """목록 기록 실패가 저장·열기를 실패시키면 안 된다."""
    monkeypatch.setattr(recent, "RECENT_PATH", tmp_path / "nope" / "recent.json")
    monkeypatch.setattr(
        recent.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("denied"))
    )
    recent.push("a.json")  # 예외가 새어 나오지 않아야 한다


def test_load_does_not_stat_paths(monkeypatch):
    """실존 확인은 여기서 하지 않는다 — 메뉴를 열 때마다 stat을 때리면
    네트워크 드라이브에서 UI가 멈춘다."""
    recent.push("gone.json")
    monkeypatch.setattr(
        os.path, "exists", lambda p: (_ for _ in ()).throw(AssertionError("stat 금지"))
    )
    assert len(recent.load()) == 1
