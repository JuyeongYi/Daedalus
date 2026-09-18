# tests/test_polymorphism_ratchet.py
"""다형성 래칫 — 종류 분기가 **늘지 않는지** 소스 AST로 감시한다 (WP-0 안전망).

사용자 지시(2026-09-19): *"isinstance 호출이 과도하게 많다면 다형성을 사용하고
있지 않은 것이다."* 리팩토링은 이 수를 단계적으로 내린다. 이 테스트는 그 수가
**올라가지 않는 것**만 보장한다 — 내리는 것은 각 WP의 일이고, 올리는 커밋은
리뷰가 거부한다.

두 래칫(REFACTOR_SPEC §8):

① **컴포넌트 클래스 대상 `isinstance`** — 두 번째 인자(튜플/리스트/집합 포함)에
   컴포넌트·config 클래스 이름이 든 호출. "이 객체가 무슨 종류인가"를 타입으로
   묻는 자리이며, 대부분은 종류가 아니라 **성질**을 묻고 있다.

② **컴포넌트 형상 `getattr`/`hasattr`** — 두 번째 인자가 컴포넌트 형상 속성
   이름 상수인 호출. 타입 대신 문자열로 같은 질문을 하는 우회로다.
   첫 인자가 `project`/`cfg`/`config`/`doc`인 호출은 **제외**한다 — 그쪽은
   컴포넌트 형상이 아니라 프로젝트/설정 dict의 하위 호환 조회다.

두 래칫 모두 **기준선은 이 저장소에서 실측했다**(명세의 숫자를 베끼지 않았다).
면제는 `module::qualname`으로 적는다 — 줄 번호로 적으면 위아래 편집만으로
면제가 엉뚱한 자리로 미끄러진다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "daedalus"

# ── 컴포넌트/설정 클래스 이름 29종 (구체 9 + 추상 5 + 믹스인 1 + config 14) ──
COMPONENT_CLASS_NAMES: frozenset[str] = frozenset({
    # 추상 기저 + 믹스인
    "PluginComponent", "Skill", "StepSkill", "ForkSkill", "Agent", "WorkflowComponent",
    # 구체 컴포넌트 9종
    "ProceduralSkill", "SyncForkSkill", "AsyncForkSkill", "DeclarativeSkill",
    "TransferSkill", "ReferenceSkill", "WrappedSkill", "AgentDefinition", "ForkAgent",
    # config 14종
    "ComponentConfig", "SkillConfig", "StepSkillConfig", "ProceduralSkillConfig",
    "ForkSkillConfig", "SyncForkSkillConfig", "AsyncForkSkillConfig",
    "WrappedSkillConfig", "DeclarativeSkillConfig", "AgentConfigBase", "AgentConfig",
    "ForkAgentConfig", "TransferSkillConfig", "ReferenceSkillConfig",
})

# ── 컴포넌트 형상 속성 (§8 래칫 ② 목록 + output_events/output_event_defs) ──
SHAPE_ATTRS: frozenset[str] = frozenset({
    "config", "body", "fsm", "transfer_on", "call_agents", "when_to_use",
    "usage", "enabled", "reference_placements", "source",
    "output_events", "output_event_defs",
})

#: 첫 인자가 이것들이면 컴포넌트 형상 질문이 아니다(프로젝트/설정/문서 조회).
SHAPE_EXCLUDED_SUBJECTS: frozenset[str] = frozenset({"project", "cfg", "config", "doc"})

#: 실측 기준선 (2026-09-19, WP-2b 완료 — model 소비자 치환 직후). **내리기만 한다.**
RATCHET: dict[str, int] = {
    "isinstance_sites": 84,
    "isinstance_files": 26,
    "shape_attr_sites": 85,
    "shape_attr_files": 32,
}

#: 정당한 잔존 사이트 — `module::qualname`. 면제는 **사유와 철거 주체**를 적는다.
#: 리팩토링 종료 시점의 예정 면제는 `kinds::spec_for`와
#: `deser_plugin::_coerce_config`(역직렬화 안전망) 둘이다.
ISINSTANCE_EXEMPT: dict[str, str] = {
    # WP-1 D4 — 본문 정본이 외부인가. 능력 선언 `BODY_SOURCE`(WP-2a)가 아직
    # 없어 종류로 묻는다. **WP-2c가 이 함수 본문을
    # `BODY_SOURCE is BodySource.EXTERNAL`로 바꾸고 이 면제를 지운다.**
    # 이 커밋 전에는 같은 질문이 `component_editor`의 별칭 `_Wrapped`
    # 뒤에 숨어 스캐너에 잡히지 않았다(판정 2벌 = 원칙 1 위반) — 판정을
    # 모델 한 곳으로 모으면서 드러난 사이트라 실제 분기 수는 늘지 않았다.
    "model.plugin.skill::has_external_body":
        "본문 편집 잠금(GUI)·MCP 본문 쓰기 거절의 공유 판정 — WP-2c가 철거",
}
SHAPE_ATTR_EXEMPT: dict[str, str] = {}


# ─────────────────────────── AST 스캐너 ───────────────────────────

def _module_name(path: Path) -> str:
    return path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")


def _qualname_map(tree: ast.AST) -> dict[int, str]:
    """노드 id → 소속 qualname. 면제 키를 줄 번호가 아니라 이름으로 쓰기 위함."""
    out: dict[int, str] = {}

    def walk(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = scope + (child.name,)
                out[id(child)] = ".".join(inner)
                walk(child, inner)
            else:
                out[id(child)] = ".".join(scope)
                walk(child, scope)

    out[id(tree)] = ""
    walk(tree, ())
    return out


def _enclosing(node: ast.AST, qualnames: dict[int, str]) -> str:
    return qualnames.get(id(node), "")


def _class_names_in(node: ast.expr) -> set[str]:
    """isinstance 두 번째 인자에서 클래스 이름을 모은다 (튜플/리스트/집합 포함)."""
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        found: set[str] = set()
        for element in node.elts:
            found |= _class_names_in(element)
        return found
    return set()


def _subject_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _source_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def scan_isinstance() -> list[tuple[str, int, str, str]]:
    """(모듈, 줄, qualname, 걸린 클래스 이름들) 목록."""
    sites: list[tuple[str, int, str, str]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        qualnames = _qualname_map(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "isinstance" or len(node.args) != 2:
                continue
            hit = _class_names_in(node.args[1]) & COMPONENT_CLASS_NAMES
            if not hit:
                continue
            sites.append((module, node.lineno, _enclosing(node, qualnames),
                          ",".join(sorted(hit))))
    return sites


def scan_shape_attrs() -> list[tuple[str, int, str, str]]:
    """(모듈, 줄, qualname, 속성 이름) 목록."""
    sites: list[tuple[str, int, str, str]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        qualnames = _qualname_map(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in {"getattr", "hasattr"} or len(node.args) < 2:
                continue
            attr = node.args[1]
            if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                continue
            if attr.value not in SHAPE_ATTRS:
                continue
            if _subject_name(node.args[0]) in SHAPE_EXCLUDED_SUBJECTS:
                continue
            sites.append((module, node.lineno, _enclosing(node, qualnames), attr.value))
    return sites


def _apply_exemptions(sites, exempt: dict[str, str]):
    return [s for s in sites if f"{s[0]}::{s[2]}" not in exempt]


def _report(sites) -> str:
    return "\n".join(
        f"  {module}:{line} ({qualname or '<module>'}) → {what}"
        for module, line, qualname, what in sites[:40]
    )


# ─────────────────────────── ① isinstance 래칫 ───────────────────────────

def test_isinstance_on_component_classes_does_not_grow():
    sites = _apply_exemptions(scan_isinstance(), ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert len(sites) <= RATCHET["isinstance_sites"], (
        f"컴포넌트 클래스 대상 isinstance가 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['isinstance_sites']}). 종류를 타입으로 묻지 말고 "
        f"능력 메서드로 물어라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["isinstance_files"], (
        f"isinstance 분기가 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['isinstance_files']}):\n" + _report(sites)
    )


def test_isinstance_ratchet_baseline_is_not_stale():
    """기준선이 실측보다 크게 남아 있으면 내려라 — 래칫은 조여야 의미가 있다."""
    sites = _apply_exemptions(scan_isinstance(), ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert RATCHET["isinstance_sites"] == len(sites), (
        f"기준선({RATCHET['isinstance_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['isinstance_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["isinstance_files"] == len(files), (
        f"기준선({RATCHET['isinstance_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['isinstance_files']를 {len(files)}로 내려 잠가라."
    )


# ─────────────────────────── ② 형상 getattr 래칫 ───────────────────────────

def test_component_shape_getattr_does_not_grow():
    sites = _apply_exemptions(scan_shape_attrs(), SHAPE_ATTR_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert len(sites) <= RATCHET["shape_attr_sites"], (
        f"컴포넌트 형상 getattr/hasattr가 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['shape_attr_sites']}). 문자열로 형상을 더듬는 대신 "
        f"모델이 선언한 능력을 불러라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["shape_attr_files"], (
        f"형상 조회가 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['shape_attr_files']}):\n" + _report(sites)
    )


def test_shape_attr_ratchet_baseline_is_not_stale():
    sites = _apply_exemptions(scan_shape_attrs(), SHAPE_ATTR_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert RATCHET["shape_attr_sites"] == len(sites), (
        f"기준선({RATCHET['shape_attr_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['shape_attr_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["shape_attr_files"] == len(files), (
        f"기준선({RATCHET['shape_attr_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['shape_attr_files']를 {len(files)}로 내려 잠가라."
    )


# ─────────────────────────── 스캐너 자기 검증 ───────────────────────────

def test_exemptions_carry_a_reason():
    """면제는 사유를 강제한다 — 빈 사유는 '왜 남았는지'를 지운다."""
    for table in (ISINSTANCE_EXEMPT, SHAPE_ATTR_EXEMPT):
        for key, reason in table.items():
            assert reason.strip(), f"{key}: 면제 사유가 비었다"


def test_exemptions_point_at_live_sites():
    """존재하지 않는 자리를 면제로 붙잡고 있지 않은지 — 목록은 줄어들기만 한다."""
    live_isinstance = {f"{m}::{q}" for m, _l, q, _w in scan_isinstance()}
    live_shape = {f"{m}::{q}" for m, _l, q, _w in scan_shape_attrs()}
    stale = sorted(set(ISINSTANCE_EXEMPT) - live_isinstance)
    stale += sorted(set(SHAPE_ATTR_EXEMPT) - live_shape)
    assert not stale, f"사라진 자리를 면제가 붙잡고 있다 — 목록에서 빼라: {stale}"


def test_scanner_sees_the_known_hotspots():
    """스캐너가 조용히 0을 세지 않는지 — 알려진 집중 지점을 확인한다."""
    modules = {module for module, _l, _q, _w in scan_isinstance()}
    assert "compiler.emit.skill" in modules
    assert "model.serialize.ser" in modules
    shape_modules = {module for module, _l, _q, _w in scan_shape_attrs()}
    # WP-2b가 `model.project`를 0으로 비웠다 — 남은 집중 지점으로 교체한다
    # (단언 수는 그대로다. 표적을 지우면 스캐너가 조용히 0을 세도 통과한다).
    assert "mcp.tools.query" in shape_modules
    assert "compiler.emit.sections" in shape_modules


def test_shape_exclusion_rule_is_applied():
    """제외 규칙이 실제로 무언가를 걸러내는지 (규칙이 죽으면 기준선이 튄다)."""
    excluded = [
        node
        for path in _source_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "hasattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in SHAPE_ATTRS
        and _subject_name(node.args[0]) in SHAPE_EXCLUDED_SUBJECTS
    ]
    assert excluded, "제외 규칙이 하나도 걸러내지 않는다 — 규칙이 죽었다"
