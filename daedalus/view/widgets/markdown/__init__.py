# daedalus/view/widgets/markdown/
"""마크다운 에디터 위젯 패키지 — 하이브리드(마커 유지 + 스타일) 방식.

WP-RF-3c: 구 단일 모듈 ``view/widgets/markdown_editor.py``를 패키지로 분해했다
(이동만, 동작 불변). 기존 임포트 경로 ``daedalus.view.widgets.markdown_editor``는
**재-export 파사드**로 남아 있어 무수정으로 계속 동작한다.

구획:
  syntax.py      — 팔레트·폰트·정규식·``_make_format``/``_detect_line_marker``
                   (모듈 간 공유 상수의 **단일 진실** — 복제 금지)
  highlighter.py — ``MarkdownHighlighter`` (블록 상태로 코드 펜스 추적)
  providers.py   — files/·skill-files/ 루트 제공자 + 드롭 참조 토큰 계산
  slash.py       — ``SlashItem``/``SLASH_CATALOG``/``_SlashMenu`` (`/` 오버레이)
  editor.py      — ``MarkdownEditor`` (키 입력·리스트 이어쓰기·서식·드롭 치환)
  toolbar.py     — ``MarkdownToolbar`` (서식 버튼 행)
  search.py      — ``SearchBar`` (찾기/바꾸기 바)
  toc.py         — ``TocEntry``/``TocPanel`` (목차 사이드바)

하이라이팅 규칙과 편집 동작은 qmarkdowntextedit
(https://github.com/pbek/qmarkdowntextedit, MIT License,
Copyright (c) 2014-2026 Patrizio Bekerle)의 설계를 PySide6로 포팅했다.
"""
from __future__ import annotations

from daedalus.view.widgets.markdown.editor import MarkdownEditor
from daedalus.view.widgets.markdown.highlighter import MarkdownHighlighter
from daedalus.view.widgets.markdown.providers import (
    get_files_root,
    get_skill_files_root,
    set_files_root_provider,
    set_skill_files_root_provider,
)
from daedalus.view.widgets.markdown.search import SearchBar
from daedalus.view.widgets.markdown.slash import SLASH_CATALOG, SlashItem
from daedalus.view.widgets.markdown.syntax import MARKDOWN_PALETTE
from daedalus.view.widgets.markdown.toc import TocEntry, TocPanel
from daedalus.view.widgets.markdown.toolbar import MarkdownToolbar

__all__ = [
    "MARKDOWN_PALETTE",
    "SLASH_CATALOG",
    "MarkdownEditor",
    "MarkdownHighlighter",
    "MarkdownToolbar",
    "SearchBar",
    "SlashItem",
    "TocEntry",
    "TocPanel",
    "get_files_root",
    "get_skill_files_root",
    "set_files_root_provider",
    "set_skill_files_root_provider",
]
