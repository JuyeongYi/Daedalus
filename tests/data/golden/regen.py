# tests/data/golden/regen.py
"""골든 스냅샷 재생성기 — ``python -m tests.data.golden.regen``.

산출이 **의도적으로** 바뀐 커밋에서만 돌린다. 재생성 결과의 diff는 그 커밋의
리뷰 본문에 붙인다 — 골든은 "바뀌었다"를 말해 주는 물건이지 자동으로 따라오는
물건이 아니다(무심코 돌리면 안전망이 사라진다).

같은 일을 pytest 쪽에서 하려면 ``python -m pytest tests/ -q --regen-golden``.
두 경로 모두 :mod:`tests.data.golden.render`의 같은 함수를 부른다.

동결 dogfood 사본(`dogfood.daedalus.json`) 자체를 갱신하려면::

    python -m tests.data.golden.regen --refresh-dogfood

그때만 살아 있는 작업 사본(`project/daedalus_cc_plugin/.daedalus.json`)을
읽어 덮어쓴다. 평소에는 그 파일을 절대 읽지 않는다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from tests.data.golden import render, store
from tests.data.golden.corpus import DOGFOOD_JSON

#: 살아 있는 작업 사본. `--refresh-dogfood`를 줄 때만 읽는다.
LIVE_DOGFOOD = (
    Path(__file__).resolve().parents[3] / "project" / "daedalus_cc_plugin" / ".daedalus.json"
)


def regenerate() -> list[Path]:
    """모든 골든을 다시 쓴다. 쓴 파일 목록을 돌려준다."""
    facades, projects, plans = render.facade_and_project_hashes()
    store.write_hashes(store.FACADES_SHA256, facades)
    store.write_hashes(store.PROJECTS_SHA256, projects)
    store.write_plans(plans)
    store.write_dogfood_project_json(render.dogfood_project_json())
    return [
        store.FACADES_SHA256,
        store.PROJECTS_SHA256,
        *(store.plan_path(case) for case in sorted(plans)),
        store.DOGFOOD_PROJECT_JSON,
    ]


def refresh_dogfood() -> None:
    if not LIVE_DOGFOOD.is_file():
        raise SystemExit(f"살아 있는 작업 사본이 없습니다: {LIVE_DOGFOOD}")
    shutil.copyfile(LIVE_DOGFOOD, DOGFOOD_JSON)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="골든 스냅샷 재생성")
    parser.add_argument(
        "--refresh-dogfood", action="store_true",
        help="동결 dogfood 사본을 살아 있는 작업 사본으로 갱신한 뒤 재생성",
    )
    args = parser.parse_args(argv)
    if args.refresh_dogfood:
        refresh_dogfood()
    for path in regenerate():
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
