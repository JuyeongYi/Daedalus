# tests/compiler/test_emit_import_acyclic.py
"""`daedalus.compiler.emit.*` 모듈 간 임포트 방향 계약 (REFACTOR_SPEC §4-b·R1).

WP-6이 절 적용 표(`section_plan.py`)와 emitter(`emitters.py`)를 이 패키지에
들이면서 가장 크게 부딪히는 것이 **임포트 순환**이다. 오늘의 방향은
`common ← guides ← skill/agent` 단방향이고, 그 위에 새 모듈을 얹을 때 방향이
뒤집히면 "함수 안에서 임포트하면 되잖아"로 미봉된다 — 그 순간 모듈 지도가
거짓이 되고, 다음 사람은 어느 쪽이 위인지 알 수 없다.

그래서 두 가지를 따로 잰다:

① **모듈 레벨 간선** — 항상 비순환이어야 한다(오늘 통과).
② **모든 간선**(함수 안 지연 임포트 포함) — §4-b가 요구하는 최종 계약.
   **오늘은 통과하지 않는다**: `sections ↔ wrapped`와
   `agent → sections → wrapped → agent` 두 순환이 지연 임포트로 살아 있다
   (`sections.py:350` → `wrapped.external_skill_name`,
   `wrapped.py:118` → `sections._mcp_servers_from_tools`,
   `wrapped.py:169` → `agent._exits_section`). 실측 결과이므로 단언을
   느슨하게 하지 않고 `xfail(strict=True)`로 **기록**한다 — WP-6이 방향을
   정리해 순환이 사라지면 이 표식이 즉시 실패해 제거를 강제한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_PKG = "daedalus.compiler.emit"
_ROOT = _REPO / "daedalus" / "compiler" / "emit"


def _module_name(path: Path) -> str:
    rel = path.relative_to(_ROOT).with_suffix("").as_posix().replace("/", ".")
    return _PKG if rel == "__init__" else f"{_PKG}.{rel}"


def _modules() -> dict[str, Path]:
    return {_module_name(p): p for p in sorted(_ROOT.rglob("*.py"))}


def _resolve(path: Path, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    rel = path.relative_to(_REPO)
    parts = list(rel.with_suffix("").parts)[:-1]
    if node.level > 1:
        parts = parts[: len(parts) - (node.level - 1)]
    if node.module:
        parts.append(node.module)
    return ".".join(parts)


def _is_module_level(tree: ast.Module, node: ast.AST) -> bool:
    return any(node is stmt for stmt in tree.body)


def edges(*, module_level_only: bool) -> dict[str, set[str]]:
    """모듈 → 임포트 대상 집합 (`emit` 패키지 안쪽 간선만)."""
    modules = _modules()
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if module_level_only and not _is_module_level(tree, node):
                continue
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom):
                targets.append(_resolve(path, node))
            elif isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            for target in targets:
                if target in modules and target != name:
                    graph[name].add(target)
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """순환 하나를 찾아 경로로 돌려준다 (없으면 None). 탐색은 정렬 순서 = 결정적."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)

    def walk(node: str, stack: list[str]) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in sorted(graph[node]):
            if color[nxt] == GRAY:
                return stack[stack.index(nxt):] + [nxt]
            if color[nxt] == WHITE:
                found = walk(nxt, stack)
                if found is not None:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in sorted(graph):
        if color[node] == WHITE:
            found = walk(node, [])
            if found is not None:
                return found
    return None


def test_package_scope_is_nonempty():
    """스캔 대상이 비면 계약이 무의미 — 패키지 이동/개명을 여기서 잡는다."""
    modules = _modules()
    assert _PKG in modules
    assert f"{_PKG}.common" in modules
    assert f"{_PKG}.skill" in modules
    assert len(modules) >= 8, sorted(modules)


def test_module_level_imports_are_acyclic():
    """모듈 레벨 방향은 단방향이다 (오늘의 계약)."""
    cycle = find_cycle(edges(module_level_only=True))
    assert cycle is None, (
        "emit/ 모듈 레벨 임포트에 순환이 생겼다 — 방향은 "
        "common → guides → section_plan → emitters → pointer_rules 단방향이다:\n"
        "  " + " → ".join(cycle or [])
    )


def test_common_is_a_leaf():
    """`common`은 emit 패키지 안쪽을 임포트하지 않는다 (방향의 바닥)."""
    assert edges(module_level_only=False)[f"{_PKG}.common"] == set()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "실측(2026-09-19): 지연 임포트로 sections ↔ wrapped, "
        "agent → sections → wrapped → agent 순환이 살아 있다. "
        "REFACTOR_SPEC §4-b가 WP-6에서 pointer_rules 추출로 정리한다 — "
        "정리되면 이 xfail(strict)이 실패해 제거를 강제한다."
    ),
)
def test_all_imports_including_deferred_are_acyclic():
    """§4-b 최종 계약 — 함수 안 지연 임포트까지 포함해 비순환."""
    cycle = find_cycle(edges(module_level_only=False))
    assert cycle is None, "  " + " → ".join(cycle or [])


def test_known_deferred_cycle_is_recorded():
    """xfail이 가리키는 순환이 **실제로** 있는지 — 사라지면 표식을 지워야 한다.

    xfail(strict)만으로는 "왜 실패하는가"가 남지 않는다. 여기서 순환의 실물을
    짚어 두면 WP-6이 무엇을 끊어야 하는지 바로 읽힌다.
    """
    graph = edges(module_level_only=False)
    assert f"{_PKG}.wrapped" in graph[f"{_PKG}.sections"]
    assert f"{_PKG}.sections" in graph[f"{_PKG}.wrapped"]
    assert f"{_PKG}.agent" in graph[f"{_PKG}.wrapped"]
