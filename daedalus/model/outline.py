"""본문 아웃라인 (WP-BO) — body 마크다운의 파생 인덱스.

저장의 단일 진실은 ``body: str`` 그대로다(WP-SB). 이 모듈은 그 텍스트에서
헤딩 구조를 **파생**시켜 부분 접근(섹션 단위 읽기/교체)을 제공한다 — 저장
형식을 트리로 바꾸면 마크다운↔트리 무손실 왕복 파서가 필요해지는데, 거기서
새는 버그는 "저장했더니 본문이 미묘하게 달라짐" 류라 최악이다. 구조는 항상
파생으로만 만든다(사용자 확정, A안 — 필요 시 인텍스트 속성(B안)으로 확장).

펜스 규칙은 view의 ``MarkdownHighlighter``와 동일해야 한다(아래 정규식은
``markdown_editor.py``의 ``_FENCE_OPEN_RE``/``_FENCE_CLOSE_RE`` 미러) —
코드 펜스 안의 ``#`` 줄은 헤딩이 아니다. 두 곳이 어긋나면 TOC에 보이는
섹션과 여기서 집는 섹션이 달라진다.

텍스트 연산은 전부 ``body.split("\\n")`` 기반이다 — ``"\\n".join(split("\\n"))``
왕복이 항등이므로, 건드리지 않은 구간은 바이트 그대로 보존된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_FENCE_OPEN_RE = re.compile(r"^\s{0,3}(```|~~~)[^`]*$")
_FENCE_CLOSE_RE = re.compile(r"^\s{0,3}(```|~~~)\s*$")

#: 섹션 경로 구분자 — "부모 > 자식"으로 동명 헤딩을 특정한다.
PATH_SEPARATOR = ">"


@dataclass(frozen=True)
class OutlineEntry:
    """헤딩 하나 — 줄 범위는 0-based, ``line_end``는 배타(파이썬 슬라이스 규약).

    섹션 범위 = 헤딩 줄부터 다음 같은/상위 레벨 헤딩 직전(또는 EOF)까지.
    """

    level: int
    title: str
    line_start: int
    line_end: int
    ancestors: tuple[str, ...]  # 바깥→안쪽 순 조상 헤딩 제목

    @property
    def path(self) -> str:
        return f" {PATH_SEPARATOR} ".join((*self.ancestors, self.title))


def parse_outline(body: str) -> list[OutlineEntry]:
    """body의 ATX 헤딩을 코드 펜스 제외로 추출한다 (순수 함수, 파생 전용)."""
    lines = body.split("\n")
    raw: list[tuple[int, str, int]] = []  # (level, title, line)
    in_fence = False
    for i, line in enumerate(lines):
        if in_fence:
            if _FENCE_CLOSE_RE.match(line):
                in_fence = False
            continue
        if _FENCE_OPEN_RE.match(line):
            in_fence = True
            continue
        m = _HEADING_RE.match(line)
        if m:
            raw.append((len(m.group(1)), m.group(2).strip(), i))

    entries: list[OutlineEntry] = []
    stack: list[tuple[int, str]] = []  # (level, title) — 현재 조상 체인
    for idx, (level, title, line) in enumerate(raw):
        end = len(lines)
        for nlevel, _, nline in raw[idx + 1:]:
            if nlevel <= level:
                end = nline
                break
        while stack and stack[-1][0] >= level:
            stack.pop()
        entries.append(
            OutlineEntry(
                level=level, title=title, line_start=line, line_end=end,
                ancestors=tuple(t for _, t in stack),
            )
        )
        stack.append((level, title))
    return entries


def find_section(body: str, heading: str) -> OutlineEntry:
    """제목(또는 "부모 > 자식" 경로)으로 섹션 하나를 특정한다.

    - 앞의 ``#``들은 레벨 제약으로 해석한다: ``"## 배선"``은 H2인 "배선"만.
    - 경로를 주면 마지막 요소가 제목, 앞 요소들은 조상 체인에 순서대로
      나타나야 한다(연속일 필요 없음).
    - 0개 매칭·2개 이상 매칭은 ``ValueError`` — 조용히 하나를 고르면
      엉뚱한 섹션을 덮어쓴다.
    """
    parts = [p.strip() for p in heading.split(PATH_SEPARATOR) if p.strip()]
    if not parts:
        raise ValueError("heading이 비어 있습니다.")

    level_required = 0
    last = parts[-1]
    m = re.match(r"^(#{1,6})\s+(.+)$", last)
    if m:
        level_required = len(m.group(1))
        last = m.group(2).strip()
    prefix = parts[:-1]

    entries = parse_outline(body)
    matches = []
    for e in entries:
        if e.title != last:
            continue
        if level_required and e.level != level_required:
            continue
        # prefix가 조상 체인의 부분열(순서 유지)인지 검사
        chain = list(e.ancestors)
        pos = 0
        for want in prefix:
            while pos < len(chain) and chain[pos] != want:
                pos += 1
            if pos >= len(chain):
                break
            pos += 1
        else:
            matches.append(e)

    if not matches:
        available = ", ".join(f"'{e.path}'" for e in entries) or "(헤딩 없음)"
        raise ValueError(f"'{heading}' 섹션을 찾을 수 없습니다. 아웃라인: {available}")
    if len(matches) > 1:
        paths = ", ".join(f"'{'#' * e.level} {e.path}'" for e in matches)
        raise ValueError(
            f"'{heading}'이 여러 섹션과 일치합니다: {paths} — "
            f"'부모 {PATH_SEPARATOR} 자식' 경로나 '## 제목' 레벨 지정으로 특정하세요."
        )
    return matches[0]


def section_text(body: str, entry: OutlineEntry) -> str:
    """섹션 텍스트 — 헤딩 줄 포함, 다음 같은/상위 레벨 헤딩 직전까지."""
    return "\n".join(body.split("\n")[entry.line_start:entry.line_end])


def replacement_text(body: str, entry: OutlineEntry, new_text: str) -> str:
    """``char_span`` 범위에 실제로 넣을 텍스트 — 경계 정규화 포함.

    섹션이 문서 끝이 아니고 새 텍스트 마지막 줄이 비어 있지 않으면 빈 줄
    하나를 붙여 다음 헤딩과 경계를 세운다. ``replace_section``과 MCP의
    QTextCursor 교체 경로가 **이 함수를 공유**해야 두 경로 결과가 같다.
    """
    is_last = entry.line_end >= len(body.split("\n"))
    if not is_last and new_text.split("\n")[-1].strip():
        return new_text + "\n"
    return new_text


def replace_section(body: str, entry: OutlineEntry, new_text: str) -> str:
    """섹션(헤딩 줄 포함)을 new_text로 교체한 새 body를 돌려준다.

    교체 텍스트가 자기 헤딩을 포함해야 섹션으로 남는다 — 포함하지 않으면
    이전 섹션에 흡수된다(의도적 병합도 가능하도록 강제하지 않는다).
    건드리지 않은 구간은 바이트 그대로다.
    """
    start, end = char_span(body, entry)
    return body[:start] + replacement_text(body, entry, new_text) + body[end:]


def char_span(body: str, entry: OutlineEntry) -> tuple[int, int]:
    """섹션의 문자 오프셋 [start, end) — QTextCursor 선택 교체용.

    범위는 섹션 첫 줄의 시작부터 마지막 줄의 끝(다음 줄과의 개행 제외)까지 —
    교체 시 경계 개행이 보존된다.
    """
    lines = body.split("\n")
    start = sum(len(l) + 1 for l in lines[:entry.line_start])
    end = start + len("\n".join(lines[entry.line_start:entry.line_end]))
    return start, end
