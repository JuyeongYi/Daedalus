"""코드 위생 — 파일 크기 상한 고정 (사용자 확정 규칙, WP-RF 재발 방지).

WP-RF 이전에 1,000줄+ 파일 7개가 쌓여 대규모 리팩토링이 필요해졌다 — 경계를
테스트로 고정하지 않으면 반복된다. 규칙:

- 소스 파일은 **1,200줄 상한** (하드 — 이 테스트가 강제).
- ~800줄을 넘으면 분해를 검토한다 (소프트 — CLAUDE.md 지침, 테스트 미강제).
- 기존 초과 파일은 아래 허용 목록에 **현재 크기 스냅샷**으로 등재한다.
  목록은 줄어들기만 해야 한다 — 파일이 상한 아래로 내려가면 테스트가
  목록 제거를 강제한다. 새 파일을 목록에 더하는 것은 규칙 위반이다
  (기능을 더하기 전에 먼저 쪼갠다).
"""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "daedalus"

HARD_LIMIT = 1200

# 경로(POSIX) → 상한. WP-RF 종료 시점(2026-08-17) 실측 스냅샷 + 소폭 여유.
# serialize.py는 RF-1b의 _migrate_v1 집약으로 오히려 커졌다(1,381→1,437) —
# 분해 후보(RF 후속)이며, 그전까지는 이 값을 넘길 수 없다.
ALLOWLIST: dict[str, int] = {
    "daedalus/model/serialize.py": 1500,
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _source_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def test_no_source_file_exceeds_hard_limit():
    """1,200줄 상한 — 허용 목록에 없는 파일이 넘으면 실패."""
    offenders = []
    for path in _source_files():
        rel = path.relative_to(_REPO).as_posix()
        limit = ALLOWLIST.get(rel, HARD_LIMIT)
        count = _line_count(path)
        if count > limit:
            offenders.append(f"{rel}: {count}줄 (상한 {limit})")
    assert not offenders, (
        "파일 크기 상한 초과 — 기능을 더하기 전에 먼저 분해하라 "
        "(허용 목록 추가는 규칙 위반):\n" + "\n".join(offenders)
    )


def test_allowlist_is_ratchet_only():
    """허용 목록은 줄어들기만 한다 — 상한 아래로 내려간 파일은 목록에서 빼라."""
    stale = []
    for rel, limit in ALLOWLIST.items():
        path = _REPO / rel
        if not path.exists():
            stale.append(f"{rel}: 파일이 없다 — 목록에서 제거하라")
            continue
        if _line_count(path) <= HARD_LIMIT:
            stale.append(
                f"{rel}: {_line_count(path)}줄로 상한({HARD_LIMIT}) 이하 — "
                f"목록에서 제거해 재비대를 막아라"
            )
        if limit <= HARD_LIMIT:
            stale.append(f"{rel}: 목록 상한 {limit}이 HARD_LIMIT 이하 — 무의미한 등재")
    assert not stale, "\n".join(stale)
