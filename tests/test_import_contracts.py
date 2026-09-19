# tests/test_import_contracts.py
"""core/GUI 경계 계약 (WP-RF-2) — 소스 AST 기준 임포트 금지 강제.

core 표면(daedalus/model/**, daedalus/compiler/**, daedalus/mcp/endpoint.py,
daedalus/cli/**)은 Qt 바인딩(PySide6/PyQt6/shiboken6)·GUI 레이어(daedalus.view)·
MCP SDK(mcp)·ASGI 서버(uvicorn)를 임포트할 수 없다.

런타임 임포트 차단(tests/compiler/test_purity.py)만으로는 함수 안의 지연 임포트를
놓친다 — 그 코드 경로가 실행되기 전까지는 위반이 드러나지 않는다. 그래서 이
테스트는 파일의 **소스 텍스트를 AST로 파싱**해 모든 import 문(모듈 최상위든
함수 안이든, TYPE_CHECKING 가드 안이든)을 검사한다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

DAEDALUS_ROOT = Path(__file__).resolve().parent.parent / "daedalus"

BANNED = (
    "PySide6",  # Qt 바인딩
    "PyQt6",  # Qt 바인딩
    "shiboken6",  # Qt 바인딩 런타임
    "daedalus.view",  # GUI 레이어
    "mcp",  # MCP SDK (daedalus.mcp 패키지와는 다르다 — 접두 매칭은 점 단위)
    "uvicorn",  # ASGI 서버
)

# core 경계에 속하는 표면. 디렉토리는 재귀(**/*.py), 파일은 그 파일 하나.
CORE_DIRS = ("model", "compiler", "cli")
CORE_FILES = (Path("mcp") / "endpoint.py",)


# CLI(daedalus/cli/**)는 core 금지 목록에 더해 daedalus.model도 임포트할 수 없다
# (WP-BB1). CLI는 **설치 대상 프로젝트**에서 도는 물건이고, 그곳에는 Daedalus
# 모델도 프로젝트 파일도 없다 — 검증의 단일 진실은 컴파일 산출물
# schemas/schemas.json 파일 자체다. 모델을 끌어오는 순간 그 전제가 깨진다.
CLI_EXTRA_BANNED = ("daedalus.model",)


def _is_banned(module_name: str, banned_prefixes: tuple[str, ...] = BANNED) -> str | None:
    """금지 모듈이면 걸린 금지 접두를, 아니면 None을 돌려준다 (점 단위 접두 매칭)."""
    for banned in banned_prefixes:
        if module_name == banned or module_name.startswith(banned + "."):
            return banned
    return None


def _core_source_files() -> list[Path]:
    files: list[Path] = []
    for sub in CORE_DIRS:
        root = DAEDALUS_ROOT / sub
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))
    for rel in CORE_FILES:
        path = DAEDALUS_ROOT / rel
        if path.is_file():
            files.append(path)
    return files


def _resolve_relative(file: Path, node: ast.ImportFrom) -> str:
    """상대 임포트(level>0)를 절대 모듈 경로로 해석한다.

    daedalus/model/fsm/state.py 의 ``from . import x`` → ``daedalus.model.fsm``.
    상대 임포트는 daedalus 패키지 내부를 가리키므로 사실상 금지 대상이 될 수
    없지만(daedalus.view는 core 디렉토리에서 상대로 닿지 않는다), 원칙적으로
    해석해서 같은 규칙으로 검사한다.
    """
    rel = file.relative_to(DAEDALUS_ROOT.parent)
    parts = list(rel.with_suffix("").parts)
    parts = parts[:-1]  # 모듈 파일이면 소속 패키지, __init__이면 그 패키지 자신
    if node.level > 1:
        parts = parts[: len(parts) - (node.level - 1)]
    if node.module:
        parts.append(node.module)
    return ".".join(parts)


def _scan_file(
    file: Path, banned_prefixes: tuple[str, ...] = BANNED
) -> list[str]:
    """파일 하나의 위반 목록 — '경로:줄번호: import 문 (금지: X)' 형식."""
    violations: list[str] = []
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    rel_path = file.relative_to(DAEDALUS_ROOT.parent)

    def _report(lineno: int, statement: str, banned: str) -> None:
        violations.append(f"{rel_path}:{lineno}: {statement} (금지: {banned})")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                banned = _is_banned(alias.name, banned_prefixes)
                if banned:
                    _report(node.lineno, f"import {alias.name}", banned)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                module = _resolve_relative(file, node)
            else:
                module = node.module or ""
            banned = _is_banned(module, banned_prefixes)
            if banned:
                _report(node.lineno, f"from {module} import ...", banned)
                continue
            # ``from daedalus import view`` 처럼 모듈 자체를 이름으로 끌어오는 경우
            for alias in node.names:
                dotted = f"{module}.{alias.name}" if module else alias.name
                banned = _is_banned(dotted, banned_prefixes)
                if banned:
                    _report(node.lineno, f"from {module} import {alias.name}", banned)
    return violations


def test_core_scope_is_nonempty():
    """스캔 대상이 비면 계약이 무의미 — 디렉토리 이동/개명을 여기서 잡는다."""
    files = _core_source_files()
    assert len(files) > 10, f"core 스캔 대상이 비정상적으로 적다: {files}"
    names = {f.relative_to(DAEDALUS_ROOT.parent).as_posix() for f in files}
    assert "daedalus/mcp/endpoint.py" in names
    assert "daedalus/cli/__init__.py" in names


def test_core_has_no_banned_imports():
    """core 표면(model/compiler/mcp.endpoint/cli)은 Qt·view·MCP SDK·uvicorn 무의존."""
    violations: list[str] = []
    for file in _core_source_files():
        violations.extend(_scan_file(file))
    assert not violations, (
        "core 경계 위반 임포트 발견 — core(model/compiler/mcp.endpoint/cli)는 "
        "PySide6·PyQt6·shiboken6·daedalus.view·mcp(SDK)·uvicorn을 임포트할 수 없다:\n"
        + "\n".join(violations)
    )


def test_banned_matching_is_dot_boundary():
    """접두 매칭이 점 단위인지 고정 — daedalus.mcp(우리 패키지)는 mcp(SDK)와 다르다."""
    assert _is_banned("mcp") == "mcp"
    assert _is_banned("mcp.server.fastmcp") == "mcp"
    assert _is_banned("daedalus.mcp.endpoint") is None
    assert _is_banned("mcpx") is None
    assert _is_banned("daedalus.view.app") == "daedalus.view"
    assert _is_banned("daedalus.viewmodelish") is None


# ─────────────────────────── CLI 추가 계약 (WP-BB1) ───────────────────────────


def _cli_source_files() -> list[Path]:
    root = DAEDALUS_ROOT / "cli"
    return sorted(root.rglob("*.py")) if root.is_dir() else []


def test_cli_scope_covers_blackboard_module():
    """CLI 스캔 대상 고정 — 파일이 빠지면 계약이 조용히 무력화된다."""
    names = {f.relative_to(DAEDALUS_ROOT.parent).as_posix() for f in _cli_source_files()}
    assert "daedalus/cli/blackboard.py" in names


def test_cli_does_not_import_daedalus_model():
    """CLI는 순수 stdlib — 검증의 단일 진실은 산출물 schemas.json 파일 자체다.

    CLI는 플러그인이 설치된 **작업 폴더**에서 돌고 그곳에는 Daedalus 모델이
    없다. 모델을 끌어오면 그 전제가 깨질 뿐 아니라, 편집 시점 모델과 산출
    스키마 중 무엇이 정본인지가 흐려진다.
    """
    violations: list[str] = []
    for file in _cli_source_files():
        violations.extend(_scan_file(file, CLI_EXTRA_BANNED))
    assert not violations, (
        "daedalus/cli/**는 daedalus.model을 임포트할 수 없다 "
        "(검증 정본 = 컴파일 산출 schemas.json):\n" + "\n".join(violations)
    )


def test_cli_imports_only_stdlib():
    """CLI 임포트가 서드파티 모듈로 새지 않는지 고정.

    판정은 ``sys.stdlib_module_names``(3.10+, requires-python은 >=3.12)로 한다 —
    손으로 적은 모듈 목록을 쓰면 정당한 stdlib 임포트를 하나 더한 사람이 "stdlib만
    임포트한다"는 이름의 테스트에 걸려 계약을 위반한 줄 안다. 계약은 "이 여덟 개만"이
    아니라 "stdlib(+ 우리 패키지)만"이다.
    """
    allowed_first_parts = set(sys.stdlib_module_names) | {"__future__", "daedalus"}
    offenders: list[str] = []
    for file in _cli_source_files():
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        rel = file.relative_to(DAEDALUS_ROOT.parent).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module.split(".")[0] not in allowed_first_parts:
                    offenders.append(f"{rel}:{node.lineno}: {module}")
    assert not offenders, (
        "daedalus/cli/**는 stdlib만 임포트한다 (순수 stdlib 제약):\n"
        + "\n".join(offenders)
    )


# ───────────────────────── model 추가 계약 (WP-0 안전망) ─────────────────────────

# daedalus/model/**는 컴파일러(daedalus.compiler)와 MCP 어댑터(daedalus.mcp)를
# 임포트할 수 없다. 컴파일러 패턴의 방향이 **model → compiler**이기 때문이다 —
# 모델은 "무엇인가"를 말하고, 컴파일러가 "그것을 어떤 파일로 내는가"를 말한다.
# 역방향 간선이 생기면 모델이 CC 플러그인 레이아웃(`skills/<n>/SKILL.md`)이나
# 산출 절 구조 같은 컴파일러 어휘를 알게 되고, 그 순간 "판정의 실체가 한 곳"
# (원칙 1)이 무너진다.
#
# 오늘 위반은 0건이지만 **테스트가 없었다.** 종류 레지스트리·능력 표면 리팩토링이
# 모델에 선언을 모으는 동안, 컴파일러 어휘가 딸려 들어오는 것을 막는 게이트다.
# (`daedalus.view`는 이미 BANNED에 있으므로 여기서는 추가하지 않는다.)
MODEL_EXTRA_BANNED = ("daedalus.compiler", "daedalus.mcp")


def _model_source_files() -> list[Path]:
    root = DAEDALUS_ROOT / "model"
    return sorted(root.rglob("*.py")) if root.is_dir() else []


def test_model_scope_covers_the_plugin_layer():
    """model 스캔 대상 고정 — 파일이 빠지면 계약이 조용히 무력화된다."""
    names = {f.relative_to(DAEDALUS_ROOT.parent).as_posix() for f in _model_source_files()}
    assert "daedalus/model/project.py" in names
    assert "daedalus/model/plugin/skill.py" in names
    assert "daedalus/model/serialize/ser.py" in names
    assert len(names) > 30, f"model 스캔 대상이 비정상적으로 적다: {len(names)}"


def test_model_does_not_import_compiler_or_mcp():
    """model은 컴파일러·MCP를 임포트하지 않는다 (컴파일러 패턴 방향 고정)."""
    violations: list[str] = []
    for file in _model_source_files():
        violations.extend(_scan_file(file, MODEL_EXTRA_BANNED))
    assert not violations, (
        "daedalus/model/**는 daedalus.compiler·daedalus.mcp를 임포트할 수 없다 "
        "— 방향은 model → compiler 단방향이다:\n" + "\n".join(violations)
    )


def test_model_extra_banned_matching_is_dot_boundary():
    """접두 매칭 경계 — `daedalus.compiler`와 무관한 이름을 잡지 않는다."""
    assert _is_banned("daedalus.compiler", MODEL_EXTRA_BANNED) == "daedalus.compiler"
    assert _is_banned("daedalus.compiler.emit.skill", MODEL_EXTRA_BANNED) == "daedalus.compiler"
    assert _is_banned("daedalus.mcp.tools.props", MODEL_EXTRA_BANNED) == "daedalus.mcp"
    assert _is_banned("daedalus.model.plugin.skill", MODEL_EXTRA_BANNED) is None
    assert _is_banned("daedalus.compilerish", MODEL_EXTRA_BANNED) is None


# ── MCP 도구 ↛ GUI 다이얼로그 (WP-1 D7) ────────────────────────────
#
# MCP 도구는 **GUI 어댑터**라 `daedalus.view`를 임포트할 수 있다 — 편집은
# `view/actions/*`·`view/commands/*` 공유 액션을 거쳐야 undo가 듣고(원칙 3),
# 본문은 `view/editors/body_documents`의 문서 레지스트리를 거쳐야 에디터와
# 같은 undo 스택에 오른다(WP-BU). 그것은 **의도된 공유 실체**다.
#
# 금지는 다이얼로그(`*_dialog`)다: 창 클래스가 든 모듈에서 함수를 빌려 오면
# ① 모델·모델-인접 질문의 실체가 창 파일에 눌러앉고(원칙 1) ② 헤드리스
# MCP 경로가 QDialog 정의를 임포트하게 된다. 실체는 모델(또는 actions)에 두고
# 창이 그것을 부른다.
MCP_TOOLS_BANNED_MODULE_SUFFIX = "_dialog"


def _mcp_tool_source_files() -> list[Path]:
    root = DAEDALUS_ROOT / "mcp"
    return sorted(root.rglob("*.py")) if root.is_dir() else []


def test_mcp_tool_scope_covers_the_tool_modules():
    """스캔 대상 고정 — 파일이 빠지면 계약이 조용히 무력화된다."""
    names = {f.relative_to(DAEDALUS_ROOT.parent).as_posix() for f in _mcp_tool_source_files()}
    assert "daedalus/mcp/tools/external.py" in names
    assert "daedalus/mcp/tools/props.py" in names
    assert len(names) > 10, f"mcp 스캔 대상이 비정상적으로 적다: {len(names)}"


def test_mcp_does_not_import_gui_dialog_modules():
    """MCP 도구는 GUI 다이얼로그 모듈에서 답을 빌려 오지 않는다 (D7)."""
    violations: list[str] = []
    for file in _mcp_tool_source_files():
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        rel_path = file.relative_to(DAEDALUS_ROOT.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_relative(file, node) if node.level > 0 else (node.module or "")
                modules = [base, *(f"{base}.{a.name}" if base else a.name for a in node.names)]
            else:
                continue
            for module in modules:
                if any(part.endswith(MCP_TOOLS_BANNED_MODULE_SUFFIX)
                       for part in module.split(".")):
                    violations.append(f"{rel_path}:{node.lineno}: {module}")
    assert not violations, (
        "MCP 도구가 GUI 다이얼로그 모듈을 임포트한다 — 답의 실체를 모델(또는 "
        "view/actions)로 옮기고 창이 그것을 부르게 하라(원칙 1):\n"
        + "\n".join(violations)
    )
