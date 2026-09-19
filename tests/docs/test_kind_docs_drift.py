# tests/docs/test_kind_docs_drift.py
"""종류 표의 **문서 드리프트** 감시 (REFACTOR_SPEC §8, WP-9).

코드 쪽의 종류 표들은 `tests/test_kind_registry_parity.py`가 집합 등식으로
묶어 두었다 — 새 종류가 한 표에만 생기면 그 자리에서 실패한다. 그런데 사람이
읽는 표(설계 문서의 종류 표, 사용자 안내서의 탭 표)는 그 그물 **밖**이었다:
빠뜨려도 아무도 실패하지 않고, 읽는 사람만 "이 종류는 문서에 없네"를 만난다.
CLAUDE.md의 "기능을 바꾸면 같은 커밋에서 문서를 갱신한다"가 지켜졌는지를
기계가 확인하게 하는 것이 이 파일이다.

**행 수와 `kind` 값만 본다** — 설명 문장까지 고정하면 문구를 다듬는 편집마다
테스트가 깨져, 결국 테스트를 느슨하게 만드는 압력이 된다. 표에 **그 종류가
한 줄로 있는가**가 이 테스트가 묻는 전부다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from daedalus.model.plugin.kinds import KIND_REGISTRY, config_kinds_in
from daedalus.model.plugin.roles import Bucket
from daedalus.view.kind_ui import KIND_UI

_DOCS = Path(__file__).resolve().parent.parent.parent / "docs"


def _table_rows(text: str, heading: str) -> list[str]:
    """`heading` 절 안의 **첫 번째** 마크다운 표의 본문 행 목록."""
    body = text.split(heading, 1)
    assert len(body) == 2, f"'{heading}' 절이 문서에 없다"
    rows: list[str] = []
    started = False
    for line in body[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            started = True
            if set(stripped) <= set("|-: "):
                continue  # 구분선
            rows.append(stripped)
        elif started:
            break
    # 첫 행은 헤더다.
    return rows[1:]


def test_plugin_model_kind_table_lists_every_registered_kind():
    """`plugin-model.md`의 종류 표 = `KIND_REGISTRY` 전수.

    이 표는 설계 정본의 목차다 — 여기 없는 종류는 "왜 있는지"를 아무도 읽을 수
    없다.
    """
    text = (_DOCS / "design" / "plugin-model.md").read_text(encoding="utf-8")
    rows = _table_rows(text, "## 스킬 6종과 에이전트 4종")
    assert len(rows) == len(KIND_REGISTRY), (
        f"종류 표 {len(rows)}행 ↔ 레지스트리 {len(KIND_REGISTRY)}종"
    )
    documented = {
        m.group(1)
        for row in rows
        if (m := re.search(r"\|\s*`([a-z_]+)`\s*\|", row)) is not None
    }
    assert documented == set(KIND_REGISTRY)


def test_concept_guide_kind_table_has_one_row_per_kind():
    """안내서 01의 종류 표도 전수다 — 사용자가 고를 수 있는 것의 목록이다."""
    text = (_DOCS / "guide" / "01-concept.md").read_text(encoding="utf-8")
    rows = _table_rows(text, "### 컴포넌트 종류")
    assert len(rows) == len(KIND_REGISTRY), (
        f"안내서 종류 표 {len(rows)}행 ↔ 레지스트리 {len(KIND_REGISTRY)}종"
    )


def test_registry_guide_tab_table_has_one_row_per_kind():
    """안내서 02의 탭 표 = 레지스트리 탭 수. 탭 아이콘까지 맞춘다."""
    text = (_DOCS / "guide" / "02-registry.md").read_text(encoding="utf-8")
    rows = _table_rows(text, "탭 라벨은 아이콘 하나뿐입니다.")
    assert len(rows) == len(KIND_REGISTRY)
    icons = {row.split("|")[1].strip() for row in rows}
    assert icons == {ui.tab_label for ui in KIND_UI.values()}


@pytest.mark.parametrize(
    "config_kind",
    list(config_kinds_in(Bucket.SKILLS)) + list(config_kinds_in(Bucket.AGENTS)),
)
def test_registry_guide_has_a_section_for_every_kind(config_kind):
    """안내서 02에 그 종류를 설명하는 `##` 절이 있다.

    절 제목은 레지스트리 섹션 라벨(`KindUI.section_label`)을 그대로 쓴다 —
    화면의 탭 이름과 문서의 제목이 갈리면 독자가 같은 것을 가리키는지 알 수 없다.
    """
    from daedalus.model.plugin.kinds import spec_by_config_kind

    text = (_DOCS / "guide" / "02-registry.md").read_text(encoding="utf-8")
    label = KIND_UI[spec_by_config_kind(config_kind).kind].section_label
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    # fork 2종은 한 절이 둘을 함께 설명한다 — 제목에 라벨이 들어 있으면 된다.
    assert any(label in h for h in headings), f"'{label}' 절이 안내서 02에 없다"


# ─────────────────── emitter 절 표 (compiler.md) ───────────────────
#
# 종류 표와 달리 이 표는 **순서가 곧 계약**이다 — 절 하나가 문서에만 남아 있으면
# (WP-10에서 지운 `BACKGROUND_SKILLS`가 실제로 그랬다) 읽는 사람은 코드에 없는
# 절을 기대한다. 행 수만 세는 그물로는 잡히지 않아 **시퀀스 등식**으로 고정한다.

#: fork 2종 행의 축약 표기 — 바로 위 행에서 그 절만 뺀다는 뜻이다.
_FORK_SHORTHAND = "위에서 RESUME 제외"


def _emitter_kind_by_class_name() -> dict[str, str]:
    """emitter 클래스 이름 → 컴포넌트 KIND (`EMITTERS` 등록에서 유도)."""
    from daedalus.compiler.emit.emitters import EMITTERS

    return {type(em).__name__: kind for kind, em in EMITTERS.items()}


def test_compiler_md_section_table_matches_section_plans():
    """`compiler.md`의 emitter 절 표 = `SECTION_PLANS`의 절 순서·양식·포인터 전수.

    문서의 각 행이 **그 종류가 실제로 내는 절을 순서대로** 적고 있는지 본다.
    행 수·절 이름·순서가 전부 계약이고, OUTCOME 양식과 가이드 포인터 열도 같은
    선언에서 나오므로 함께 고정한다.
    """
    from daedalus.compiler.emit.section_plan import SECTION_PLANS

    text = (_DOCS / "design" / "compiler.md").read_text(encoding="utf-8")
    rows = _table_rows(text, "그래서 순서는 전역이 아니라 종류가 갖는다.")
    by_name = _emitter_kind_by_class_name()
    assert len(rows) == len(SECTION_PLANS), (
        f"절 표 {len(rows)}행 ↔ 절 선언 {len(SECTION_PLANS)}종"
    )

    previous: tuple[str, ...] = ()
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        emitter_name = cells[0].strip("`")
        kind = by_name.get(emitter_name)
        assert kind is not None, f"문서에만 있는 emitter: {emitter_name}"
        plan = SECTION_PLANS[kind]

        if cells[1] == _FORK_SHORTHAND:
            documented = tuple(s for s in previous if s != "RESUME")
        else:
            documented = tuple(part.strip() for part in cells[1].split("·"))
        actual = tuple(s.name for s in plan.sections)
        assert documented == actual, (
            f"{emitter_name} 절 순서 문서={documented} 코드={actual}"
        )
        previous = actual

        assert cells[2] in ("–", plan.outcome_style.name), (
            f"{emitter_name} OUTCOME 양식 문서={cells[2]} 코드={plan.outcome_style.name}"
        )
        assert cells[3] == plan.guide_pointer.name, (
            f"{emitter_name} 가이드 포인터 문서={cells[3]} 코드={plan.guide_pointer.name}"
        )
