"""공용 섹션 편집 위젯 — SectionTree, BreadcrumbNav, SectionContentPanel, VariablePopup."""
from __future__ import annotations

from daedalus.model.fsm.section import Section

MAX_DEPTH = 3  # 0-indexed; 4 levels total (H1–H4)


def find_path(target: Section, roots: list[Section]) -> list[Section] | None:
    """루트부터 target까지의 조상 경로를 반환. 못 찾으면 None."""
    for root in roots:
        result = _search(target, root, [])
        if result is not None:
            return result
    return None


def _search(
    target: Section, current: Section, ancestors: list[Section],
) -> list[Section] | None:
    path = ancestors + [current]
    if current is target:
        return path
    for child in current.children:
        result = _search(target, child, path)
        if result is not None:
            return result
    return None


def section_depth(target: Section, roots: list[Section]) -> int:
    """target의 깊이 (루트=0). 못 찾으면 -1."""
    path = find_path(target, roots)
    return len(path) - 1 if path is not None else -1
