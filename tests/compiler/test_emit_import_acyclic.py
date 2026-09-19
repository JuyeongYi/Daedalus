# tests/compiler/test_emit_import_acyclic.py
"""`daedalus.compiler.emit.*` 모듈 간 임포트 방향 계약 (REFACTOR_SPEC §4-b·R1).

WP-6이 절 적용 표(`section_plan.py`)와 emitter(`emitters.py`)를 이 패키지에
들이면서 가장 크게 부딪히는 것이 **임포트 순환**이다. 오늘의 방향은
`common ← guides ← skill/agent` 단방향이고, 그 위에 새 모듈을 얹을 때 방향이
뒤집히면 "함수 안에서 임포트하면 되잖아"로 미봉된다 — 그 순간 모듈 지도가
거짓이 되고, 다음 사람은 어느 쪽이 위인지 알 수 없다.

그래서 두 가지를 따로 잰다:

① **모듈 레벨 간선** — 항상 비순환이어야 한다.
② **모든 간선**(함수 안 지연 임포트 + `TYPE_CHECKING` 블록 포함) — §4-b의
   최종 계약. WP-6까지는 통과하지 않았다: `sections ↔ wrapped`와
   `agent → sections → wrapped → agent` 두 순환이 지연 임포트로 살아 있어
   `xfail(strict=True)`로 기록해 뒀다. WP-6이 셋을 끊었다 —
   `parse_wrapped_source`/`external_skill_name`은 순수 문자열 파싱이라
   `common`(리프)으로, `_exits_section`은 에이전트와 랩핑 러너가 공유하는
   단락이라 `sections`로 내려갔다. 그래서 이제 ②도 **단언**이다.

**`TYPE_CHECKING` 임포트도 간선으로 센다.** 정적 타입만 쓰는 임포트라도
"이 모듈이 저 모듈을 안다"는 사실은 같고, 그것을 눈감아 주면 모듈 지도가
거짓이 된다 — `section_plan`이 `emitters`의 타입을 주석으로만 쓰던 자리가
실제로 그렇게 걸렸다(그쪽은 타입 주석을 떼어 해소했다).
"""
from __future__ import annotations

import ast
from pathlib import Path

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


def test_all_imports_including_deferred_are_acyclic():
    """§4-b 최종 계약 — 함수 안 지연 임포트·TYPE_CHECKING까지 포함해 비순환."""
    cycle = find_cycle(edges(module_level_only=False))
    assert cycle is None, "  " + " → ".join(cycle or [])


def test_the_former_cycles_are_one_directional_now():
    """WP-6이 끊은 세 간선이 **되돌아오지 않는지** — 순환의 자리를 못 박는다.

    비순환 단언만 남기면 "어디가 위험했는지"가 사라진다. 세 쌍은 실제로 순환을
    이뤘던 자리이므로 방향을 직접 고정한다.
    """
    graph = edges(module_level_only=False)
    # ① sections는 wrapped를 모른다(공용 문자열 파싱은 common으로 내려갔다).
    assert f"{_PKG}.wrapped" not in graph[f"{_PKG}.sections"]
    assert f"{_PKG}.sections" in graph[f"{_PKG}.wrapped"]
    # ② wrapped는 agent를 모른다(_exits_section은 sections가 갖는다).
    assert f"{_PKG}.agent" not in graph[f"{_PKG}.wrapped"]
    # ③ section_plan은 emitters를 모른다(타입 주석으로도).
    assert f"{_PKG}.emitters" not in graph[f"{_PKG}.section_plan"]
    assert f"{_PKG}.section_plan" in graph[f"{_PKG}.emitters"]


def test_pointer_rules_sits_below_guides():
    """포인터 **판정**은 아래, 포인터 **문구**는 위 — §4-b 방향 계약의 실물."""
    graph = edges(module_level_only=False)
    assert f"{_PKG}.pointer_rules" in graph[f"{_PKG}.guides"]
    assert f"{_PKG}.guides" not in graph[f"{_PKG}.pointer_rules"]
