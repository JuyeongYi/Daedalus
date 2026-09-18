# tests/model/test_golden_project_json.py
"""프로젝트 JSON 골든 — 직렬화 리팩토링이 바이트를 바꾸지 않았음을 고정한다.

REFACTOR_SPEC §8 "JSON 골든" 행 / WP-4(`SERIALIZED_FIELDS` 선언화)의 게이트.

대상은 동결 dogfood 사본(`tests/data/golden/dogfood.daedalus.json`)이다.
살아 있는 작업 사본(`project/daedalus_cc_plugin/.daedalus.json`)은 **읽지
않는다** — 사용자가 편집하면 골든이 무작위로 깨진다.

이 사본은 구버전 포맷(fork 분할 이전 `kind: "fork_skill"`, 에이전트 잔존 FSM)
이라 로드 시 `_migrate_v1`/fork-split 마이그레이션이 돌고, 스냅샷은 그
**마이그레이션 결과**다 — 키 순서·부재 의미론·마이그레이션이 하나라도 바뀌면
여기서 걸린다.

재생성: `python -m tests.data.golden.regen` (자세한 절차는
`tests/compiler/test_golden_outputs.py` docstring).
"""
from __future__ import annotations

import json

import pytest

from tests.data.golden import render, store
from tests.data.golden.corpus import DOGFOOD_JSON


def test_frozen_dogfood_copy_exists():
    """동결 사본이 커밋돼 있어야 한다 — 없으면 이 골든은 아무것도 지키지 않는다."""
    assert DOGFOOD_JSON.is_file(), DOGFOOD_JSON
    data = json.loads(DOGFOOD_JSON.read_text(encoding="utf-8"))
    assert data["skills"] and data["agents"]


def test_dogfood_load_save_matches_golden(regen_golden):
    """로드 → 저장 결과가 스냅샷과 **바이트 동일**."""
    actual = render.dogfood_project_json()
    if regen_golden:
        store.write_dogfood_project_json(actual)
        pytest.skip("--regen-golden — 프로젝트 JSON 골든을 다시 썼다")
    expected = store.read_dogfood_project_json()
    assert expected is not None, (
        f"프로젝트 JSON 골든이 없다: {store.DOGFOOD_PROJECT_JSON} — "
        "`python -m tests.data.golden.regen`으로 생성하라."
    )
    assert actual == expected, (
        "직렬화 결과가 골든과 다르다 — 키 순서·부재 의미론·마이그레이션 중 "
        "하나가 바뀌었다. 의도한 변경이면 재생성하고 diff를 리뷰에 붙여라."
    )


def test_save_is_idempotent():
    """저장 결과를 다시 로드→저장해도 같다 (왕복 안정성).

    골든 한 장만으로는 "한 번의 변환"만 지킨다 — 두 번째 왕복에서 값이 흔들리면
    사용자가 파일을 열었다 닫기만 해도 diff가 생긴다.
    """
    from daedalus.model.serialize import deserialize_project, serialize_project

    once = render.dogfood_project_json()
    again = json.dumps(
        serialize_project(deserialize_project(json.loads(once))),
        ensure_ascii=False, indent=2,
    ) + "\n"
    assert once == again
