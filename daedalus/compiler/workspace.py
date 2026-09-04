# daedalus/compiler/workspace.py
"""`.claude/CLAUDE.md` 구역 병합 (WP-WD/D9) — 순수 stdlib, Qt 무관.

`.claude/CLAUDE.md`는 **사용자·팀의 파일**이다. 통째로 쓰면 남의 내용을 지우고, 한
작업 폴더에 ddls 플러그인이 둘 깔리면 서로를 덮는다. 그래서 플러그인마다 1줄 HTML
주석 두 개로 자기 구역을 만들고 그 안만 갈아끼운다:

    <!-- daedalus:my-plugin open -->
    # my-plugin

    ...본문...
    <!-- daedalus:my-plugin close -->

표식이 HTML 주석인 이유: CC는 CLAUDE.md의 블록 수준 HTML 주석을 **컨텍스트 주입
전에 제거**한다(공식 문서). 즉 표식은 토큰을 한 글자도 쓰지 않는다.

`wiring.wire_workspace`와 같은 결의 모듈이다 — 사용자 파일을 파괴하지 않고 **추가·
갱신만** 하며, 재컴파일이 멱등이다.
"""
from __future__ import annotations

import re

#: 플러그인 이름은 컴파일 게이트가 `^[a-z0-9][a-z0-9-]*$`를 강제하므로 정규식
#: 이스케이프 위험이 없다. 그래도 방어적으로 escape한다 — 게이트를 우회한 호출이
#: 정규식을 깨뜨려 엉뚱한 구역을 지우는 것보다 낫다.
_OPEN = "<!-- daedalus:{plugin} open -->"
_CLOSE = "<!-- daedalus:{plugin} close -->"


def open_marker(plugin: str) -> str:
    return _OPEN.format(plugin=plugin)


def close_marker(plugin: str) -> str:
    return _CLOSE.format(plugin=plugin)


def region_body(title: str, body: str) -> str:
    """구역 안의 내용 — H1으로 시작한다(D9).

    본문이 이미 `# `로 시작하면 제목을 덧붙이지 않는다. 사용자가 스스로 쓴 제목
    위에 하나를 더 얹으면 H1이 둘이 되어 읽는 쪽이 구조를 오해한다.
    """
    text = body.strip("\n")
    if text.lstrip().startswith("# "):
        return text
    return f"# {title}\n\n{text}" if text else f"# {title}"


def merge_claude_md(
    existing: str | None, plugin: str, *, title: str, body: str
) -> tuple[str | None, str | None]:
    """`(새 내용, 경고)`를 돌려준다. 새 내용이 None이면 **파일을 건드리지 않는다**.

    - 파일이 없으면(``existing is None``) 구역 하나만 담아 만든다. 이때도 표식을
      반드시 남긴다 — 없으면 다음 빌드가 그 파일을 남의 것으로 보고 구역을 또
      덧붙인다(사용자 확정).
    - 구역이 있으면 **제자리에서** 갈아끼운다(위치 보존). 없으면 파일 끝에 붙인다.
    - 본문이 비면 구역을 제거한다 — 플러그인 이름이 키라 멱등하게 정리된다.
    - **손상된 구역은 절대 건드리지 않는다.** open만 있고 close가 없을 때 끝을
      추측하면 뒤따르는 사용자 내용을 통째로 날린다. 경고만 내고 물러난다.
    """
    open_tag, close_tag = open_marker(plugin), close_marker(plugin)
    content = region_body(title, body) if body.strip() else ""

    if existing is None:
        if not content:
            return None, None
        return f"{open_tag}\n{content}\n{close_tag}\n", None

    opens = [m.start() for m in re.finditer(re.escape(open_tag), existing)]
    closes = [m.start() for m in re.finditer(re.escape(close_tag), existing)]

    if len(opens) > 1 or len(closes) > 1:
        return None, (
            f"'{plugin}' 구역 표식이 여러 번 나타나 병합하지 않았습니다 "
            f"(open {len(opens)}개 / close {len(closes)}개)."
        )
    if len(opens) != len(closes):
        missing = "close" if opens else "open"
        return None, (
            f"'{plugin}' 구역의 {missing} 표식이 없어 병합하지 않았습니다 — "
            f"구역의 끝을 추측하면 그 뒤의 내용을 지울 수 있습니다."
        )
    if opens and closes and closes[0] < opens[0]:
        return None, (
            f"'{plugin}' 구역의 close 표식이 open보다 앞에 있어 병합하지 "
            f"않았습니다."
        )

    if not opens:  # 구역 없음 — 끝에 덧붙인다(쓸 내용이 있을 때만).
        if not content:
            return None, None
        prefix = existing if existing.endswith("\n") else existing + "\n"
        joiner = "" if prefix.endswith("\n\n") or not prefix.strip() else "\n"
        return f"{prefix}{joiner}{open_tag}\n{content}\n{close_tag}\n", None

    start, end = opens[0], closes[0] + len(close_tag)
    if end < len(existing) and existing[end] == "\n":
        end += 1
    if not content:  # 구역 제거
        return existing[:start] + existing[end:], None
    replacement = f"{open_tag}\n{content}\n{close_tag}\n"
    return existing[:start] + replacement + existing[end:], None
