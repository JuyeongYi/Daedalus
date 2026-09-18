# tests/data/golden/store.py
"""골든 스냅샷의 **저장 형식** — 읽기/쓰기가 같은 파일에 산다.

  - ``*.sha256`` — `sha256sum` 형식(``<해시>␠␠<키>``), 키 정렬. 사람이 diff로
    "어느 산출이 바뀌었나"를 바로 읽을 수 있다.
  - ``plan/<코퍼스>-<타깃>.json`` — 계획·쓰기 순서 스냅샷. **목록 순서가 계약**
    이라 정렬하지 않는다.
  - ``dogfood.project.json`` — 동결 사본의 로드→저장 결과.

전부 LF · UTF-8(BOM 없음)로 쓴다 — 산출 결정성 규약(원칙 6)과 같은 규칙이다.
"""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent
FACADES_SHA256 = GOLDEN_DIR / "facades.sha256"
PROJECTS_SHA256 = GOLDEN_DIR / "projects.sha256"
PLAN_DIR = GOLDEN_DIR / "plan"
DOGFOOD_PROJECT_JSON = GOLDEN_DIR / "dogfood.project.json"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def format_hashes(hashes: dict[str, str]) -> str:
    return "".join(f"{hashes[key]}  {key}\n" for key in sorted(hashes))


def parse_hashes(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, key = line.partition("  ")
        out[key] = digest
    return out


def read_hashes(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_hashes(path.read_text(encoding="utf-8"))


def write_hashes(path: Path, hashes: dict[str, str]) -> None:
    _write_text(path, format_hashes(hashes))


def plan_path(case: str) -> Path:
    return PLAN_DIR / f"{case}.json"


def read_plan(case: str) -> dict | None:
    path = plan_path(case)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_plans(plans: dict[str, dict]) -> None:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    keep = set()
    for case, snapshot in plans.items():
        path = plan_path(case)
        keep.add(path.name)
        _write_text(path, json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    for stale in sorted(PLAN_DIR.glob("*.json")):
        if stale.name not in keep:
            stale.unlink()


def read_dogfood_project_json() -> str | None:
    if not DOGFOOD_PROJECT_JSON.is_file():
        return None
    return DOGFOOD_PROJECT_JSON.read_text(encoding="utf-8")


def write_dogfood_project_json(text: str) -> None:
    _write_text(DOGFOOD_PROJECT_JSON, text)
