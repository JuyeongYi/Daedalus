# tests/model/test_wrapped_only_tags.py
"""`# WRAPPED-ONLY` 태그 개수를 설계 문서와 맞물려 고정한다 (WP-2b 리뷰 1).

**왜 개수를 테스트하는가.** WP-2b가 검증 규칙의 술어를 능력 선언으로 바꾸면서
능력으로 표현되지 않는 "랩핑 전용 좁힘"만 태그로 남겼다. `WrappedSkill`
퇴역(WP-10)은 **이 태그를 따라** 전수 삭제하는 것이 계획이므로, 문서가 세는
개수와 소스의 실제 개수가 어긋나면 WP-10이 한 자리를 조용히 빠뜨린다
(실제로 리뷰 1에서 `fork.py`의 게이트가 문서에서 누락된 채 발견됐다).

문서(`docs/design/validation.md`)가 개수의 정본이고, 여기서는 소스를 세어
그 숫자와 같은지만 본다 — 새 태그를 달면 문서도 같은 커밋에서 고쳐야 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "daedalus"
_DOC = _ROOT / "docs" / "design" / "validation.md"

_TAG = "# WRAPPED-ONLY"
# validation.md의 "**랩핑 전용으로 남은 자리는 오늘 N곳**" 문장에서 N을 읽는다.
_DOC_COUNT_RE = re.compile(r"\*\*랩핑 전용으로 남은 자리는 오늘 (\d+)곳\*\*")


def _tagged_lines() -> list[str]:
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _TAG in line:
                hits.append(f"{path.relative_to(_ROOT).as_posix()}:{lineno}")
    return hits


def test_wrapped_only_tag_count_matches_validation_doc():
    """소스의 태그 수 == validation.md가 선언한 수."""
    m = _DOC_COUNT_RE.search(_DOC.read_text(encoding="utf-8"))
    assert m, (
        "validation.md에서 랩핑 전용 자리 개수 문장을 찾지 못했다 — "
        "문장을 고쳤다면 이 테스트의 정규식도 같이 고쳐라."
    )
    declared = int(m.group(1))
    hits = _tagged_lines()
    assert len(hits) == declared, (
        f"`{_TAG}` 태그 {len(hits)}곳 ≠ validation.md 선언 {declared}곳.\n"
        f"WP-10이 태그를 따라 전수 삭제하므로 개수가 어긋나면 한 자리가 남는다.\n"
        + "\n".join(f"  {h}" for h in hits)
    )


def test_wrapped_only_tags_live_in_validation_rules():
    """태그는 검증 규칙 안에만 있다 — 다른 계층으로 번지면 문서가 못 센다."""
    stray = [h for h in _tagged_lines() if "model/validation/project_rules/" not in h]
    assert not stray, (
        "랩핑 전용 좁힘이 검증 규칙 밖으로 번졌다 — "
        "validation.md의 전수 목록이 더는 전수가 아니다:\n"
        + "\n".join(f"  {h}" for h in stray)
    )
