# tests/test_dead_code.py
"""죽은 코드 재발 방지 (DEADCODE.md §5.1 — 규칙 A·B).

`tests/test_code_hygiene.py`(파일 크기 상한)·`tests/test_import_contracts.py`
(경계 계약)와 같은 결의 **AST 기반 소스 스캔**이다. 파일시스템만 읽고 앱을
임포트하지 않는다 — 헤드리스 안전이고, 함수 안 지연 임포트도 놓치지 않는다.

**규칙 A — 소비자 없는 심볼은 없다.**
  `daedalus/` 안 모든 최상위 `def`/`class`/모듈 레벨 상수(언더스코어 포함)와,
  **외부 프레임워크를 상속하지 않는** 클래스의 **dunder를 제외한 모든 메서드
  (`_private` 포함)**는 `daedalus/` 어딘가에서 이름으로 참조되거나 allowlist에
  **사유와 함께** 등재돼야 한다.

**규칙 B — 파사드 핀 목록은 소비자 0인 이름을 새로 담지 않는다.**
  WP-RF 분해 파사드가 재-export하는 이름 중 **분해 시점 스냅샷(핀 목록)에
  없으면서** `daedalus/` 안 소비자도 0인 것이 있으면 실패한다. 스냅샷은 분해
  시점의 기록이지 늘어나는 레지스트리가 아니다 — 분해 이후 추가된 이름은
  실소비자가 생길 때만 파사드에 오른다.

**참조로 치는 것**(정적 트레이스의 알려진 구멍을 메운다):
  `ast.Name` · `ast.Attribute.attr` · import 별칭 · **문자열 디스패치 모듈
  (`STRING_DISPATCH_SOURCES`)의 문자열 상수**.
  마지막 항목이 중요하다 — MCP 도구 76종은 `mcp/service.py`의 `TOOL_NAMES`
  문자열 튜플에서 `getattr`로 디스패치된다. 다만 **그 모듈로 범위를 좁힌다**:
  문자열 상수를 `daedalus/` 전체에서 참조로 세면 이름이 우연히 겹치는 무관한
  리터럴(`add_parser("validate")`·`SimpleState(name="validate")` …)이 진짜
  고아 심볼을 조용히 살려 낸다 — 게이트의 맹점이지 구멍 메우기가 아니다.

**자동 면제**(allowlist를 짧게 유지한다):
  - dunder(`__init__` 등)
  - 외부 기저 클래스를 (간접적으로도) 상속한 클래스의 메서드 — Qt override
    (`paint`/`*Event`/`sizeHint`)가 여기 해당한다. 기저가 같은 이름을
    정의하는지 알려면 PySide6를 임포트해야 하는데, 그건 이 테스트의 헤드리스
    계약을 깬다. 그래서 **기저를 열거할 수 없는 클래스의 메서드는 전부 면제**
    한다(보수적이지만 조용한 오탐보다 낫다).

**면제의 맹점과 그 래칫.** 위 면제는 이름 단위가 아니라 **클래스 단위**다 —
`daedalus/` 클래스 261개 중 92개(35%), 비-dunder 메서드 1040개 중 560개(53%)가
여기 걸린다. 즉 규칙 A는 뷰 계층 대부분에서 잠든다. 그래서 면제되면서 소비자도
없는 메서드를 **버리지 않고 세어**(`scan_external_base_hidden`)
`EXTERNAL_BASE_HIDDEN_BASELINE`에 동결한다. 목록에 없는 새 항목이 생기면
실패하고 이름을 찍는다 — 진짜 Qt override면 목록에 넣고, 아니면 배선하거나
지운다. 목록은 다른 래칫과 같이 **줄어들기만 한다**.

allowlist는 `{심볼: (범주, 사유)}`이고 사유가 비면 실패한다. 범주 5종은
DEADCODE.md §5.1이 정한 것이다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "daedalus"
_TESTS = _REPO / "tests"

#: allowlist 범주 (DEADCODE.md §5.1).
CATEGORIES: frozenset[str] = frozenset({
    "framework-hook",     # 프레임워크가 디스패치한다 (Qt override 등)
    "entry-point",        # 프로세스/CLI 진입점
    "test-seam",          # 선언된 테스트 봉합선
    "contract-registry",  # 테스트가 등가성을 강제하는 선언 레지스트리
    "facade-snapshot",    # WP-RF 분해 스냅샷의 재-export
})

#: 심볼 → (범주, 사유). **줄어들기만 한다** — 지우면 그 심볼이 되살아난다.
ALLOWLIST: dict[str, tuple[str, str]] = {
    "compiler.project_compiler::COMPILER_ERROR_RULES": (
        "contract-registry",
        "컴파일 게이트 rule 등급의 단일 진실. tests/compiler/test_gate.py가 "
        "'발급 rule == 이 집합' + 'WARNING_RULES와 교집합 없음'을 양방향으로 "
        "강제한다 — 새 게이트 규칙이 경고 등급으로 조용히 실리는 것을 막는 "
        "유일한 장치라 프로덕션 소비자가 없어도 살아 있다.",
    ),
    "model.plugin.hook_store::hook_to_json": (
        "test-seam",
        "전역 훅 파일 포맷의 **쓰기 반쪽**. 세 기능의 온디스크 fixture 작성기다"
        "(test_hook_store / test_mcp_gaps / test_hook_panel_global). 지우면 "
        "네 곳이 _ser_hook 모양을 손으로 재현해 포맷 지식이 흩어진다(원칙 1). "
        "전역 훅을 저장하는 GUI·MCP 표면 자체가 없는 것이 진짜 공백이고, "
        "그건 docs/backlog.md 항목이다.",
    ),
    "model.validation.machine_rules::_MachineRules.validate": (
        "test-seam",
        "믹스인을 통한 `Validator.validate(sm)` 공개 진입점(머신 수준 검증) — "
        "`model/validation/__init__.py:68`이 `validate_project`와 나란히 공개 "
        "표면으로 선언한다. 오늘 프로덕션 호출자는 프로젝트 경로 한 갈래뿐이고, "
        "머신 규칙 30여 종을 규칙별로 태우는 쪽은 tests/model/test_validation.py"
        "(+ tests/model/fsm/test_machine.py)다. 지우면 그 테스트들이 private "
        "`_validate_machine`로 내려간다(DEADCODE §3.1).",
    ),
    "view.editors.body_documents::BodyDocumentRegistry.sync_from_model": (
        "test-seam",
        "editor.md:80이 지정한 **유일한 인가 경로** — 모델 body가 에디터 밖에서 "
        "바뀐 경우의 갱신 수단. 오늘은 모든 쓰기가 QTextDocument를 통과해 "
        "staleness가 없어 호출자도 없다. 지우면 첫 외부 변경 경로에서 조용한 "
        "staleness 버그가 난다(DEADCODE §2.7). docs/backlog.md '5. 기능 잔여'에 "
        "배선 조건(component.body를 document_for 없이 쓰는 첫 경로)과 함께 등재.",
    ),
}

#: **자동 면제의 맹점 기준선** — 외부 기저 상속 클래스라서 규칙 A가 건너뛰지만
#: `daedalus/` 안 소비자가 0인 메서드. 2026-09-19 이 저장소에서 실측했다
#: (명세의 숫자를 베끼지 않았다). 대부분은 진짜 Qt override지만 전부는 아니며,
#: 아닌 것들은 귀속 WP를 적어 둔다. **줄어들기만 한다.**
EXTERNAL_BASE_HIDDEN_BASELINE: frozenset[str] = frozenset({
    # ── 프레임워크가 디스패치하는 진짜 override ──
    "view.canvas.canvas_view::FsmCanvasView.wheelEvent",
    "view.canvas.canvas_view::_MiniMap.drawForeground",
    "view.canvas.edge_item::TransitionEdgeItem.paint",
    "view.canvas.edge_item::TransitionEdgeItem.shape",
    "view.canvas.node_item::StateNodeItem.paint",
    "view.canvas.ref_edge_item::ReferenceEdgeItem.paint",
    "view.canvas.ref_edge_item::ReferenceEdgeItem.shape",
    "view.canvas.ref_node_item::ReferenceNodeItem.paint",
    "view.canvas.scene::FsmScene.contextMenuEvent",
    "view.panels.registry_panel::_DraggableList.startDrag",
    "view.widgets.lifecycle_picker::_EventBoxItem.hoverEnterEvent",
    "view.widgets.lifecycle_picker::_EventBoxItem.hoverLeaveEvent",
    "view.widgets.lifecycle_picker::_EventBoxItem.paint",
    "view.widgets.markdown.highlighter::MarkdownHighlighter.highlightBlock",
    # ── override가 아니다 — DEADCODE.md가 분류한 테스트 봉합선 8종(§2.9) ──
    "view.editors.body_editor::SectionContentPanel.current_component",
    "view.editors.frontmatter_panel::_OptionalRow.is_checked",
    "view.editors.workspace_editor::_WorkspaceDocPanelBase.content_panel",
    "view.editors.workspace_settings_panel::WorkspaceSettingsPanel.current_settings",
    "view.launch_actions::McpInfoDialog.selectable_labels",
    "view.launch_actions::McpInfoDialog.snippet_view",
    "view.widgets.lifecycle_picker::HookLifecycleScene.item_for",
    "view.widgets.tag_input::TagInput.get_candidates",
    # ── override가 아니다 — 문자열 `getattr` 동적 호출(디스패치 표 밖) ──
    # surface_commands.py:52 `getattr(window, "rebuild_component_frontmatter")`
    "view.app::MainWindow.rebuild_component_frontmatter",
    # app.py:948 `getattr(editor, "rebuild_frontmatter")`
    "view.editors.component_editor::ComponentEditor.rebuild_frontmatter",
    # ── override도 동적 호출도 아니다 — 귀속 WP가 정해진 잔재 ──
    # (`handle_node_moved`/`handle_waypoint_moved`는 WP-1 D9에서 삭제됐다 —
    #  `editor.md`의 존치 사유였던 "기존 호출부 호환"의 그 호출부가 없어졌다.)
    # REFACTOR_SPEC §11: WP-7 — 삭제가 아니라 context_menus 배선 일관화
    "view.canvas.scene::FsmScene._add_agent_actions_menu",
    "view.canvas.scene::FsmScene._show_component_findings",
})

#: 문자열로 심볼을 디스패치하는 모듈 (`_SRC` 기준 상대 POSIX 경로).
#: 이 파일들의 문자열 상수만 참조로 센다 — 범위를 넓히면 무관한 리터럴이
#: 고아 심볼을 되살린다. 새 디스패치 표가 생기면 여기에 **명시로** 등재한다.
STRING_DISPATCH_SOURCES: frozenset[str] = frozenset({
    "mcp/service.py",   # TOOL_NAMES 튜플 → getattr 디스패치 (MCP 도구 76종)
})

#: 파사드 → 핀 목록이 사는 테스트 파일과 변수 이름 (규칙 B).
FACADE_PINS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("compiler/emit/__init__.py", "compiler/test_emit_facade.py", ("_PRE_SPLIT_ATTRS",)),
    ("model/serialize/__init__.py", "model/test_serialize_facade.py", ("_PRE_SPLIT_ATTRS",)),
    ("model/validation/__init__.py", "model/test_validation_facade.py", ("_PRE_SPLIT_ATTRS",)),
    ("mcp/tools/__init__.py", "mcp/test_tools_facade.py", ("_PRE_SPLIT_MODULE_ATTRS",)),
    ("view/widgets/markdown_editor.py", "view/widgets/test_markdown_package.py",
     ("_FACADE_NAMES",)),
)


# ─────────────────────────── 소스 인덱스 ───────────────────────────

def _module_name(path: Path) -> str:
    return path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")


def _source_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def _module_level_target_ids(tree: ast.Module) -> set[int]:
    """모듈 레벨 대입의 **좌변** Name 노드 — 정의는 참조가 아니다."""
    out: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.add(id(target))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(id(node.target))
    return out


def _referenced_names(
    trees: dict[Path, ast.Module], *, ignore_imports_in: Path | None = None
) -> set[str]:
    """이름 참조 집합.

    ``ignore_imports_in``: 그 파일의 **import 별칭만** 참조로 치지 않는다
    (규칙 B — 파사드의 재-export 줄 자신이 그 이름을 살려 주면 안 된다).
    같은 파일의 다른 사용(예: `DaedalusTools`의 기저 클래스 자리)은 그대로
    참조로 센다.
    """
    names: set[str] = set()
    for path, tree in trees.items():
        skip = _module_level_target_ids(tree)
        skip_imports = ignore_imports_in is not None and path == ignore_imports_in
        dispatches = path.relative_to(_SRC).as_posix() in STRING_DISPATCH_SOURCES
        for node in ast.walk(tree):
            if skip_imports and isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.Name):
                if id(node) not in skip:
                    names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.name)
                    if alias.asname:
                        names.add(alias.asname)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.rsplit(".", 1)[-1])
                    if alias.asname:
                        names.add(alias.asname)
            elif (
                dispatches
                and isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            ):
                names.add(node.value)
    return names


def _class_index(trees: dict[Path, ast.Module]) -> dict[str, list[ast.ClassDef]]:
    index: dict[str, list[ast.ClassDef]] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                index.setdefault(node.name, []).append(node)
    return index


_PURE_BASES = frozenset({"ABC", "object", "Protocol", "Generic"})


def _base_names(klass: ast.ClassDef) -> list[str]:
    out: list[str] = []
    for base in klass.bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            out.append(base.attr)
    return out


def _has_external_base(
    klass: ast.ClassDef, index: dict[str, list[ast.ClassDef]], seen: set[int] | None = None
) -> bool:
    """기저를 소스에서 열거할 수 없으면 True — 그 클래스의 메서드는 면제 대상."""
    seen = seen if seen is not None else set()
    if id(klass) in seen:
        return False
    seen.add(id(klass))
    for name in _base_names(klass):
        if name in _PURE_BASES:
            continue
        if name not in index:
            return True
        for base in index[name]:
            if _has_external_base(base, index, seen):
                return True
    return False


def _parse_all() -> dict[Path, ast.Module]:
    return {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in _source_files()
    }


def _scan(*, hidden: bool) -> list[str]:
    """규칙 A 스캔.

    ``hidden=False``: 규칙 A가 **실제로 강제하는** 소비자 0 심볼 목록.
    ``hidden=True``: 외부 기저 자동 면제에 **가려진** 소비자 0 메서드 목록 —
    같은 한 번의 스캔에서 나오는 두 갈래라 두 결과가 어긋날 수 없다.
    """
    trees = _parse_all()
    referenced = _referenced_names(trees)
    index = _class_index(trees)
    dead: list[str] = []
    for path, tree in trees.items():
        module = _module_name(path)
        for klass in ast.walk(tree):
            if not isinstance(klass, ast.ClassDef):
                continue
            # 자동 면제 — 기저(Qt 등)가 같은 이름을 정의할 수 있다.
            if _has_external_base(klass, index) is not hidden:
                continue
            for member in klass.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if member.name.startswith("__"):
                    continue
                if member.name not in referenced:
                    dead.append(f"{module}::{klass.name}.{member.name}")
        if hidden:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name not in referenced:
                    dead.append(f"{module}::{node.name}")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Name)
                        and not target.id.startswith("__")
                        and target.id not in referenced
                    ):
                        dead.append(f"{module}::{target.id}")
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if not node.target.id.startswith("__") and node.target.id not in referenced:
                    dead.append(f"{module}::{node.target.id}")
    return sorted(dead)


def scan_unreferenced() -> list[str]:
    """`<모듈>::<심볼>` 형식의 소비자 0 심볼 목록 (allowlist 적용 전)."""
    return _scan(hidden=False)


def scan_external_base_hidden() -> list[str]:
    """외부 기저 자동 면제가 **가린** 소비자 0 메서드 목록 (규칙 A 맹점).

    규칙 A가 뷰 계층에서 조용해지는 크기를 눈에 보이게 만든다 — 이 목록이
    늘어나면 `test_external_base_hidden_does_not_grow`가 이름을 찍고 실패한다.
    """
    return _scan(hidden=True)


# ─────────────────────────── 규칙 A ───────────────────────────

def test_rule_a_every_symbol_has_a_consumer():
    offenders = [s for s in scan_unreferenced() if s not in ALLOWLIST]
    assert not offenders, (
        "소비자 없음 — 지우거나 ALLOWLIST에 범주와 사유를 적어 등재하라:\n"
        + "\n".join(f"  {s}" for s in offenders)
    )


def test_allowlist_entries_are_still_dead():
    """살아난 심볼을 allowlist가 붙잡고 있지 않은지 — 목록은 줄어들기만 한다."""
    dead = set(scan_unreferenced())
    stale = sorted(set(ALLOWLIST) - dead)
    assert not stale, (
        "allowlist가 이미 소비자를 가진 심볼을 붙잡고 있다 — 목록에서 빼라:\n"
        + "\n".join(f"  {s}" for s in stale)
    )


def test_allowlist_entries_carry_a_category_and_reason():
    for symbol, entry in ALLOWLIST.items():
        category, reason = entry
        assert category in CATEGORIES, f"{symbol}: 알 수 없는 범주 {category!r}"
        assert reason.strip(), f"{symbol}: 사유가 비었다"
        assert len(reason.strip()) >= 20, f"{symbol}: 사유가 너무 짧다 — 왜 남는지 적어라"


def test_scanner_finds_the_known_survivors():
    """스캐너가 조용히 0을 세지 않는지 — 오늘 알려진 생존자를 실제로 짚는다."""
    dead = set(scan_unreferenced())
    assert "compiler.project_compiler::COMPILER_ERROR_RULES" in dead
    assert "model.plugin.hook_store::hook_to_json" in dead


def test_string_constants_count_as_references():
    """문자열 디스패치를 참조로 세는지 — 안 세면 MCP 도구 76종이 전부 오탐이 된다."""
    dead = set(scan_unreferenced())
    assert "mcp.tools.canvas::CanvasTools.place_component" not in dead
    assert "mcp.tools.query::QueryTools.compile_check" not in dead


def test_string_rescue_is_scoped_to_declared_dispatch_sources():
    """디스패치 표가 아닌 모듈의 문자열은 아무것도 되살리지 않는다.

    범위를 넓히면 이름이 우연히 겹치는 무관한 리터럴이 고아 심볼을 조용히
    살린다 — 실제 사례: `_MachineRules.validate`는 `cli/blackboard.py`의
    `add_parser("validate")`와 `__main__.py`의 `SimpleState(name="validate")`
    때문에 게이트를 통과했었다. 그 심볼이 지금은 **allowlist 사유와 함께**
    잡혀 있어야 한다.
    """
    assert STRING_DISPATCH_SOURCES == frozenset({"mcp/service.py"}), (
        "디스패치 표가 늘었다면 그 모듈이 실제로 문자열 → 심볼 디스패치를 "
        "하는지 확인하고 이 단언을 갱신하라"
    )
    dead = set(scan_unreferenced())
    assert "model.validation.machine_rules::_MachineRules.validate" in dead, (
        "문자열 구제가 다시 전역으로 새고 있다 — 무관한 리터럴이 심볼을 살린다"
    )

    trees = _parse_all()
    outside_literals = {
        node.value
        for path, tree in trees.items()
        if path.relative_to(_SRC).as_posix() not in STRING_DISPATCH_SOURCES
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "validate" in outside_literals, (
        "전제가 깨졌다 — 디스패치 표 밖에 'validate' 리터럴이 있어야 이 테스트가 "
        "범위 제한을 실제로 증명한다"
    )
    assert "validate" not in _referenced_names(trees), (
        "디스패치 표 밖 문자열이 참조로 세어지고 있다"
    )


def test_qt_override_auto_exemption_is_active():
    """외부 기저 상속 클래스의 메서드가 자동 면제되는지 (Qt override)."""
    dead = set(scan_unreferenced())
    assert not [s for s in dead if s.endswith(".paint")], sorted(
        s for s in dead if s.endswith(".paint")
    )
    trees = _parse_all()
    index = _class_index(trees)
    externals = [
        klass.name
        for tree in trees.values()
        for klass in ast.walk(tree)
        if isinstance(klass, ast.ClassDef) and _has_external_base(klass, index)
    ]
    assert externals, "외부 기저 판정이 하나도 걸리지 않는다 — 규칙이 죽었다"


def test_external_base_auto_exemption_is_class_wide_not_name_wide():
    """면제가 **클래스 단위**임을 숫자로 못박는다 (맹점의 크기).

    `paint`/`wheelEvent` 같은 이름만 면제하는 게 아니라 그 클래스의 메서드
    전부를 면제한다. 그 대가가 얼마나 큰지 세어 두지 않으면 아래 래칫의
    존재 이유가 보이지 않는다. 2026-09-19 실측: 클래스 92/261, 메서드 560/1040.
    """
    trees = _parse_all()
    index = _class_index(trees)
    exempt_classes = exempt_methods = 0
    for tree in trees.values():
        for klass in ast.walk(tree):
            if not isinstance(klass, ast.ClassDef) or not _has_external_base(klass, index):
                continue
            exempt_classes += 1
            exempt_methods += sum(
                1
                for member in klass.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not member.name.startswith("__")
            )
    assert exempt_classes > 50 and exempt_methods > 300, (
        f"면제 규모가 실측({exempt_classes} 클래스 / {exempt_methods} 메서드)과 "
        "크게 다르다 — 면제 규칙이 바뀌었으면 기준선 문장도 같이 고쳐라"
    )


def test_external_base_hidden_does_not_grow():
    """자동 면제가 가리는 소비자 0 메서드가 **늘지 않는지**.

    규칙 A는 외부 기저 상속 클래스에서 잠든다. 그 맹점에 새 죽은 메서드가
    조용히 들어앉는 것을 막는 유일한 장치다 — 새 항목이 진짜 Qt override면
    기준선에 적고, 아니면 배선하거나 지운다.
    """
    hidden = set(scan_external_base_hidden())
    fresh = sorted(hidden - EXTERNAL_BASE_HIDDEN_BASELINE)
    assert not fresh, (
        "자동 면제(외부 기저 상속)에 가려진 소비자 0 메서드가 새로 생겼다 — "
        "프레임워크 override면 EXTERNAL_BASE_HIDDEN_BASELINE에 사유 주석과 함께 "
        "등재하고, 아니면 배선하거나 지워라:\n" + "\n".join(f"  {s}" for s in fresh)
    )
    assert len(hidden) <= len(EXTERNAL_BASE_HIDDEN_BASELINE), (
        f"가려진 메서드 {len(hidden)}개 (기준선 "
        f"{len(EXTERNAL_BASE_HIDDEN_BASELINE)}). 래칫은 내려가기만 한다."
    )


def test_external_base_hidden_baseline_is_not_stale():
    """되살아난 심볼을 기준선이 붙잡고 있지 않은지 — 목록은 줄어들기만 한다."""
    hidden = set(scan_external_base_hidden())
    stale = sorted(EXTERNAL_BASE_HIDDEN_BASELINE - hidden)
    assert not stale, (
        "기준선이 이미 소비자를 가졌거나 사라진 메서드를 붙잡고 있다 — 빼라:\n"
        + "\n".join(f"  {s}" for s in stale)
    )


def test_hidden_scan_and_rule_a_scan_are_disjoint():
    """두 갈래가 겹치거나 새지 않는지 — 한 메서드는 한쪽에만 속한다."""
    assert not (set(scan_external_base_hidden()) & set(scan_unreferenced()))
    assert "view.canvas.scene::FsmScene.contextMenuEvent" in scan_external_base_hidden(), (
        "외부 기저(QGraphicsScene) 상속 클래스의 소비자 0 메서드가 맹점 목록에 "
        "없다 — 스캔이 면제 분기를 실제로 태우지 않고 있다"
    )


# ─────────────────────────── 규칙 B ───────────────────────────

def _pin_snapshot(test_rel: str, variables: tuple[str, ...]) -> set[str]:
    path = _TESTS / test_rel
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = set(variables)
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                for element in getattr(node.value, "elts", []):
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        names.add(element.value)
    return names


def _facade_reexports(facade_rel: str) -> set[str]:
    path = _SRC / facade_rel
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name)
    return names


def test_pin_lists_are_readable():
    """핀 목록을 실제로 읽어 오는지 — 못 읽으면 규칙 B가 조용히 통과한다."""
    for _facade, test_rel, variables in FACADE_PINS:
        snapshot = _pin_snapshot(test_rel, variables)
        assert len(snapshot) > 2, f"{test_rel}: 핀 목록을 읽지 못했다 ({variables})"


def test_rule_b_facades_do_not_pin_unconsumed_new_names():
    """분해 스냅샷 밖의 재-export는 실소비자가 있어야 한다.

    분해 이후 파사드에 얹힌 이름은 "누군가 임포트 경로를 지키려고" 올린 것이
    아니라 그냥 남은 줄이다 — 소비자가 없으면 지운다(DEADCODE §3.2 규칙 1·2).
    """
    trees = _parse_all()
    offenders: list[str] = []
    for facade_rel, test_rel, variables in FACADE_PINS:
        snapshot = _pin_snapshot(test_rel, variables)
        exported = _facade_reexports(facade_rel)
        # 파사드의 **재-export 줄 자신**은 참조로 치지 않는다. 같은 파일의
        # 다른 사용(합성 클래스의 기저 자리 등)은 정당한 소비자다.
        referenced = _referenced_names(trees, ignore_imports_in=_SRC / facade_rel)
        for name in sorted(exported - snapshot):
            if name not in referenced:
                offenders.append(f"  {facade_rel}: {name}")
    assert not offenders, (
        "파사드가 스냅샷 밖의 소비자 0 이름을 재-export한다 — 줄을 지워라 "
        "(스냅샷은 늘어나지 않는다):\n" + "\n".join(offenders)
    )
