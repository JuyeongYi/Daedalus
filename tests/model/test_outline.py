"""본문 아웃라인 파서 (WP-BO) — 파생 인덱스, 저장 불변.

핵심 계약: 건드리지 않은 구간은 바이트 그대로다. 왕복 검증 없이 교체만
확인하면 경계 개행이 새는 고장을 놓친다 — 교체 전후 앞뒤 구간을 반드시
문자열로 비교한다.
"""
from __future__ import annotations

import pytest

from daedalus.model.outline import (
    char_span,
    find_section,
    parse_outline,
    replace_section,
    replacement_text,
    section_text,
)

_BODY = """\
프리앰블 — 첫 헤딩 이전 텍스트.

# 제목

도입 문단.

## 배선

배선 내용.

### 세부

세부 내용.

## 검증

검증 내용.

```md
# 펜스 안 헤딩은 무시
## 이것도
```

끝 문단."""


# --- 파싱 ---


def test_parses_headings_with_levels():
    entries = parse_outline(_BODY)
    assert [(e.level, e.title) for e in entries] == [
        (1, "제목"), (2, "배선"), (3, "세부"), (2, "검증"),
    ]


def test_code_fence_headings_are_excluded():
    titles = [e.title for e in parse_outline(_BODY)]
    assert "펜스 안 헤딩은 무시" not in titles
    assert "이것도" not in titles


def test_tilde_fence_and_indented_fence_are_excluded():
    body = "# a\n\n~~~\n# fenced\n~~~\n\n   ```\n## fenced2\n   ```\n\n## b"
    assert [e.title for e in parse_outline(body)] == ["a", "b"]


def test_unclosed_fence_swallows_rest():
    body = "# a\n\n```\n# fenced\n## fenced2"
    assert [e.title for e in parse_outline(body)] == ["a"]


def test_section_span_runs_to_next_same_or_higher_level():
    entries = {e.title: e for e in parse_outline(_BODY)}
    # "배선" 섹션은 하위 "세부"를 포함하고 같은 레벨 "검증" 직전에 끝난다
    assert "### 세부" in section_text(_BODY, entries["배선"])
    assert "검증 내용" not in section_text(_BODY, entries["배선"])
    # 마지막 섹션은 EOF까지 — 펜스와 끝 문단 포함
    assert section_text(_BODY, entries["검증"]).endswith("끝 문단.")


def test_ancestors_and_path():
    entries = {e.title: e for e in parse_outline(_BODY)}
    assert entries["세부"].ancestors == ("제목", "배선")
    assert entries["세부"].path == "제목 > 배선 > 세부"


def test_preamble_is_outside_any_section():
    entries = parse_outline(_BODY)
    assert entries[0].line_start > 0  # 프리앰블 줄들은 어느 섹션에도 안 속한다


# --- find_section ---


def test_find_by_title():
    assert find_section(_BODY, "배선").title == "배선"


def test_find_by_level_qualified():
    body = "# 개요\n\n내용\n\n## 개요\n\n중복 제목"
    assert find_section(body, "## 개요").level == 2
    assert find_section(body, "# 개요").level == 1


def test_find_by_path():
    body = "## 설계\n\n### 규칙\n\nA\n\n## 구현\n\n### 규칙\n\nB"
    assert "B" in section_text(body, find_section(body, "구현 > 규칙"))


def test_ambiguous_match_raises_with_paths():
    body = "## 설계\n\n### 규칙\n\n## 구현\n\n### 규칙"
    with pytest.raises(ValueError, match="여러 섹션과 일치"):
        find_section(body, "규칙")


def test_missing_heading_raises_with_outline():
    with pytest.raises(ValueError, match="아웃라인"):
        find_section(_BODY, "없는 섹션")


def test_empty_heading_raises():
    with pytest.raises(ValueError):
        find_section(_BODY, "  ")


# --- 교체 ---


def test_replace_preserves_untouched_bytes():
    entry = find_section(_BODY, "배선")
    new = replace_section(_BODY, entry, "## 배선\n\n새 내용.\n")
    before = _BODY[:_BODY.index("## 배선")]
    after = _BODY[_BODY.index("## 검증"):]
    assert new.startswith(before)
    assert new.endswith(after)
    assert "배선 내용" not in new
    assert "새 내용." in new


def test_replace_last_section_runs_to_eof():
    entry = find_section(_BODY, "검증")
    new = replace_section(_BODY, entry, "## 검증\n\n교체됨")
    assert new.endswith("## 검증\n\n교체됨")
    assert "끝 문단" not in new


def test_replace_inserts_boundary_blank_line_mid_document():
    """새 텍스트가 본문 줄로 끝나면 다음 헤딩과 빈 줄로 경계를 세운다."""
    entry = find_section(_BODY, "배선")
    new = replace_section(_BODY, entry, "## 배선\n\n개행 없이 끝")
    assert "개행 없이 끝\n\n## 검증" in new


def test_replace_without_heading_merges_into_previous():
    """헤딩 없는 교체 텍스트 — 이전 섹션에 흡수된다 (의도적 병합)."""
    entry = find_section(_BODY, "세부")
    new = replace_section(_BODY, entry, "그냥 문단.")
    titles = [e.title for e in parse_outline(new)]
    assert "세부" not in titles


def test_char_span_matches_section_text():
    for e in parse_outline(_BODY):
        start, end = char_span(_BODY, e)
        assert _BODY[start:end] == section_text(_BODY, e)


def test_char_span_replacement_equals_replace_section():
    """QTextCursor 경로(char_span + replacement_text)와 replace_section이 같다."""
    for heading, new_text in [("배선", "## 배선\n\nX"), ("검증", "## 검증\n\nY\n")]:
        entry = find_section(_BODY, heading)
        start, end = char_span(_BODY, entry)
        via_span = _BODY[:start] + replacement_text(_BODY, entry, new_text) + _BODY[end:]
        assert via_span == replace_section(_BODY, entry, new_text)


def test_split_join_roundtrip_is_identity():
    """연산 기반인 split("\\n") 왕복이 항등임을 고정한다 (CRLF 없는 LF 본문)."""
    assert "\n".join(_BODY.split("\n")) == _BODY


def test_empty_body_has_empty_outline():
    assert parse_outline("") == []
