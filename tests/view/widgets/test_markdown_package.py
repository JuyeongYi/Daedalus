"""markdown 패키지 분해(WP-RF-3c) 회귀 고정 — 파사드 완전성 + 상수 단일 진실.

분해는 **이동만**이므로, 기존 임포트 경로가 무수정으로 동작하고 공유 상수가
한 객체를 가리키는 것이 이 WP의 계약이다. 여기서 깨지면 "임포트는 되는데 두
모듈이 서로 다른 정규식을 본다" 류의 조용한 어긋남이 생긴다.
"""
from __future__ import annotations

import daedalus.view.widgets.markdown_editor as facade
from daedalus.view.widgets import markdown as pkg
from daedalus.view.widgets.markdown import (
    editor as editor_mod,
    highlighter as highlighter_mod,
    providers as providers_mod,
    search as search_mod,
    slash as slash_mod,
    syntax as syntax_mod,
    toc as toc_mod,
    toolbar as toolbar_mod,
)

# 소스·테스트가 실제로 기존 경로에서 임포트하는 이름 전부 (grep 전수 조사).
_FACADE_NAMES = (
    # 공개 API
    "MARKDOWN_PALETTE",
    "MarkdownEditor",
    "MarkdownHighlighter",
    "MarkdownToolbar",
    "SearchBar",
    "TocPanel",
    "TocEntry",
    "SlashItem",
    "SLASH_CATALOG",
    "set_files_root_provider",
    "get_files_root",
    "set_skill_files_root_provider",
    "get_skill_files_root",
    # 테스트가 쓰는 언더스코어 이름
    "_file_ref_token",
    "_skill_file_ref_token",
    "_SlashMenu",
    "_detect_line_marker",
    "_make_format",
    "_heading_digit_from_event",
    "_line_marker_from_event",
    "_FENCE_OPEN_RE",
    "_FENCE_CLOSE_RE",
    "_HEADING_RE",
    "_TOC_HEADING_RE",
)


def test_facade_exposes_all_names():
    missing = [n for n in _FACADE_NAMES if not hasattr(facade, n)]
    assert missing == []


def test_facade_and_package_share_objects():
    """파사드는 재-export일 뿐 — 복사본이 아니라 같은 객체여야 한다."""
    assert facade.MarkdownEditor is pkg.MarkdownEditor is editor_mod.MarkdownEditor
    assert facade.MarkdownHighlighter is highlighter_mod.MarkdownHighlighter
    assert facade.MarkdownToolbar is toolbar_mod.MarkdownToolbar
    assert facade.SearchBar is search_mod.SearchBar
    assert facade.TocPanel is toc_mod.TocPanel
    assert facade.SLASH_CATALOG is slash_mod.SLASH_CATALOG
    assert facade.set_files_root_provider is providers_mod.set_files_root_provider


def test_shared_syntax_constants_are_single_source():
    """정규식은 syntax.py 한 곳 — 다른 모듈은 임포트만 한다(복제 금지)."""
    assert facade._FENCE_OPEN_RE is syntax_mod._FENCE_OPEN_RE
    assert facade._FENCE_CLOSE_RE is syntax_mod._FENCE_CLOSE_RE
    assert editor_mod._FENCE_OPEN_RE is syntax_mod._FENCE_OPEN_RE
    assert highlighter_mod._FENCE_OPEN_RE is syntax_mod._FENCE_OPEN_RE
    assert editor_mod._TASK_RE is syntax_mod._TASK_RE
    assert highlighter_mod._TASK_RE is syntax_mod._TASK_RE
    assert editor_mod.MARKDOWN_PALETTE is syntax_mod.MARKDOWN_PALETTE


def test_outline_mirrors_syntax_fence_rules():
    """model/outline.py의 펜스 규칙은 syntax.py의 미러 — 패턴 문자열이 같아야 한다."""
    from daedalus.model import outline

    assert outline._FENCE_OPEN_RE.pattern == syntax_mod._FENCE_OPEN_RE.pattern
    assert outline._FENCE_CLOSE_RE.pattern == syntax_mod._FENCE_CLOSE_RE.pattern


def test_provider_globals_live_in_providers_module():
    """제공자 전역은 providers.py 하나 — 파사드 경유 등록/조회가 같은 상태를 본다."""
    facade.set_files_root_provider(lambda: "X")
    try:
        assert providers_mod.get_files_root() == "X"
        assert pkg.get_files_root() == "X"
    finally:
        facade.set_files_root_provider(None)
    assert providers_mod.get_files_root() is None
