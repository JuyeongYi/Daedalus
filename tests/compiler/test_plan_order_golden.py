# tests/compiler/test_plan_order_golden.py
"""계획·쓰기 **순서** 골든 (REFACTOR_SPEC §8 plan-order 행).

왜 따로 있나: 기존 스위트는 순서를 거의 단언하지 않는다 —
`test_guides.py:121,130`·`test_files.py:58`·`test_dry_run.py:284`는 전부 `set`
비교이고, 정확한 리스트를 보는 곳은 `test_dry_run.py:87` 한 줄뿐이다. 계획
순서를 옮기는 리팩토링(WP-5 `CompileUnit` 이식)이 그 앞에 게이트 없이 들어가면
"파일 내용은 같은데 쓰는 순서가 달라졌다"가 조용히 통과한다.

스냅샷 5종(`tests/data/golden/plan/<코퍼스>-<타깃>.json`):
  plan          — `_plan_outputs`가 세운 [(상대 경로, kind, 라벨)] **그대로**
  written       — `CompileResult.written`의 순서 (out_dir 기준 상대 경로)
  copied_files  — 트리/스킬 파일 복사 순서
  findings      — `errors + warnings`의 (rule, source) 순서
  skipped       — 게이트 실패 시 (이유, 라벨) 목록

재생성은 `test_golden_outputs.py`의 docstring 참조
(`python -m tests.data.golden.regen`).
"""
from __future__ import annotations

import pytest

from tests.data.golden import render, store
from tests.data.golden.corpus import CORPORA, TARGETS

_CASES = [
    f"{corpus}-{target}"
    for corpus, _factory, _kwargs in CORPORA
    for target, _enum in TARGETS
]


@pytest.fixture(scope="module")
def plans():
    _facades, _projects, snapshots = render.facade_and_project_hashes()
    return snapshots


def test_case_list_is_covered(plans):
    """코퍼스 × 타깃 전수가 스냅샷을 갖는지 — 빠지면 그 조합은 무방비다."""
    assert sorted(plans) == sorted(_CASES)


@pytest.mark.parametrize("case", _CASES)
def test_plan_and_write_order_match_golden(case, plans, regen_golden):
    if regen_golden:
        store.write_plans(plans)
        pytest.skip("--regen-golden — 계획 순서 골든을 다시 썼다")
    expected = store.read_plan(case)
    assert expected is not None, (
        f"계획 순서 골든이 없다: {store.plan_path(case)} — "
        "`python -m tests.data.golden.regen`으로 생성하라."
    )
    actual = plans[case]
    for key in ("plan", "written", "copied_files", "findings", "skipped"):
        assert actual[key] == expected[key], (
            f"[{case}] '{key}' 순서/내용이 골든과 다르다.\n"
            f"  골든: {expected[key]}\n"
            f"  현재: {actual[key]}"
        )


def test_gate_failure_reports_every_planned_output_as_skipped(plans):
    """게이트가 막으면 파일을 하나도 쓰지 않고 계획 전체를 skipped로 보고한다.

    `skipped`의 라벨 집합 == 계획의 라벨 목록이라는 계약을 고정한다 —
    WP-5가 계획에 새 행(files_tree/local_wiring/claude_md)을 더할 때
    `exclusive=False` 행이 여기 섞이면 MCP `compile_check` 응답 형상이 바뀐다.
    """
    for case in ("gate-failure-marketplace", "gate-failure-local"):
        snapshot = plans[case]
        assert snapshot["written"] == []
        assert snapshot["copied_files"] == []
        assert [label for _reason, label in snapshot["skipped"]] == [
            label for _rel, _kind, label in snapshot["plan"]
        ]
        assert {reason for reason, _label in snapshot["skipped"]} == {
            "compile_gate_error"
        }
