# tests/compiler/test_golden_outputs.py
"""산출 골든 — 컴파일러 리팩토링이 **바이트 하나도** 바꾸지 않았음을 고정한다.

REFACTOR_SPEC §8 "golden" 행. 두 벌의 코퍼스를(`tests/data/golden/corpus.py`)
MARKETPLACE·LOCAL 양 타깃으로 ① 공개 파사드 9종 ② `compile_project`가 실제로
쓴 파일 전체 로 렌더해 sha256을 `tests/data/golden/*.sha256`과 비교한다.

왜 해시인가: 산출 텍스트를 통째로 커밋하면 수천 줄이 되고, diff가 "무엇이
바뀌었나"가 아니라 "얼마나 많이 바뀌었나"만 말한다. 키가 정렬된 해시 목록은
**어느 산출이** 바뀌었는지를 한 줄로 짚어 준다. 바뀐 산출의 실물을 보려면
아래 재생성 절차를 밟고 `git diff`를 본다.

─────────────────────────── 골든 재생성 ───────────────────────────
산출이 **의도적으로** 바뀐 커밋에서만::

    python -m tests.data.golden.regen              # 권장 — 스크립트 진입점
    python -m pytest tests/ -q --regen-golden      # 같은 일을 pytest에서

동결 dogfood 사본 자체를 최신 작업 사본으로 갈아끼우려면::

    python -m tests.data.golden.regen --refresh-dogfood

재생성 diff는 그 커밋의 리뷰 본문에 붙인다 — 골든은 "바뀌었다"를 말해 주는
물건이지 자동으로 따라오는 물건이 아니다. **테스트를 통과시키려고 재생성하지
않는다**(안전망이 사라진다).
"""
from __future__ import annotations

import pytest

from tests.data.golden import render, store


@pytest.fixture(scope="module")
def rendered():
    """코퍼스 10건 × 컴파일 1회 — 모듈 안에서 한 번만 돈다."""
    return render.facade_and_project_hashes()


def _compare(label: str, actual: dict[str, str], expected: dict[str, str]) -> None:
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    changed = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
    assert not (missing or added or changed), (
        f"{label} 골든 불일치 — 산출이 바뀌었다.\n"
        f"  사라진 산출: {missing}\n"
        f"  새 산출:     {added}\n"
        f"  내용 변경:   {changed}\n"
        "의도한 변경이면 `python -m tests.data.golden.regen`으로 재생성하고 "
        "diff를 리뷰에 붙여라. 의도하지 않았다면 리팩토링이 바이트를 바꿨다."
    )


def test_golden_snapshots_exist():
    """골든 파일이 실존해야 한다 — 없으면 이 테스트는 아무것도 지키지 않는다."""
    assert store.FACADES_SHA256.is_file(), store.FACADES_SHA256
    assert store.PROJECTS_SHA256.is_file(), store.PROJECTS_SHA256
    assert store.read_hashes(store.FACADES_SHA256), "facades.sha256가 비었다"
    assert store.read_hashes(store.PROJECTS_SHA256), "projects.sha256가 비었다"


def test_facade_outputs_match_golden(rendered, regen_golden):
    """공개 파사드 9종(§8 지명)의 산출 텍스트가 바이트 동일하다."""
    facades, projects, plans = rendered
    if regen_golden:
        store.write_hashes(store.FACADES_SHA256, facades)
        store.write_hashes(store.PROJECTS_SHA256, projects)
        store.write_plans(plans)
        pytest.skip("--regen-golden — 골든을 다시 썼다")
    _compare("파사드", facades, store.read_hashes(store.FACADES_SHA256))


def test_project_outputs_match_golden(rendered, regen_golden):
    """`compile_project`가 쓴 파일 전체가 바이트 동일하다 (복사본 포함)."""
    if regen_golden:
        pytest.skip("--regen-golden — 골든을 다시 썼다")
    _, projects, _ = rendered
    _compare("compile_project 산출", projects, store.read_hashes(store.PROJECTS_SHA256))


def test_every_facade_is_exercised_by_the_corpus(rendered):
    """§8이 지명한 9개 파사드가 **전부** 최소 1건의 산출을 냈는지.

    코퍼스가 어떤 파사드도 태우지 않으면 해시가 아무리 맞아도 그 파사드는
    보호되지 않는다 — 합성 코퍼스가 존재하는 이유가 바로 이것이다(실사용
    프로젝트만으로는 `compile_wrapped_runner`가 0줄이다).
    """
    facades, _, _ = rendered
    facade_names = {key.split("/")[2] for key in facades}
    assert facade_names == {
        "compile_skill", "compile_agent", "compile_wrapped_runner",
        "compile_hooks_json", "compile_hook_scripts", "compile_schemas_json",
        "compile_plugin_manifest", "compile_guide", "render_rule",
    }
    # 해시가 NO_OUTPUT뿐인 파사드는 "돌긴 했지만 아무것도 내지 않았다"이다.
    produced = {
        key.split("/")[2] for key, digest in facades.items()
        if digest != render.NO_OUTPUT
    }
    assert produced == facade_names, sorted(facade_names - produced)


def test_rendering_is_deterministic():
    """같은 모델 → 같은 텍스트 (원칙 6). 두 번 렌더해 해시를 비교한다."""
    first = render.facade_hashes()
    second = render.facade_hashes()
    assert first == second
