# tests/test_kind_literals.py
"""종류 문자열 **디스패치 리터럴** 래칫 (REFACTOR_SPEC §8).

종류 이름이 문자열로 흩어져 있으면 새 종류를 더할 때 "어디를 고쳐야 하는지"를
아무도 말해 주지 않는다 — 빠뜨린 자리는 조용한 no-op가 된다(👻). 리팩토링은
이 리터럴을 선언 참조(`ProceduralSkill.KIND`·`plan_kinds.SKILL`)로 바꿔 나간다.

두 어휘를 따로 센다:

① **컴포넌트 kind** 16종 — 컴포넌트 KIND 9 + config KIND 9에서 겹치는
   `agent`/`fork_agent` 2를 뺀 값. 최종 목표는 `model/serialize/migrate.py`
   한 파일(구버전 파일의 문자열을 해석하는 마이그레이션은 리터럴이 정본이다).

② **plan kind** 14종 — 산출 계획의 kind 문자열. `agent`/`skill`은 컴포넌트
   어휘와 겹치므로 `compiler/**`와 `mcp/tools/query.py`에서만 plan kind로 센다
   (§8 규정). 최종 목표는 신설될 `compiler/plan_kinds.py` 한 파일.

**세는 자리**(§8): `Compare`(`==`/`in`)의 피연산자, `dict` 표시식의 키,
`set`/`tuple`/`list` 리터럴의 원소. **선언**(`KIND = "…"`, `kind` property의
`return "…"`)은 이 자리들이 아니므로 자동으로 빠진다 — 별도 테스트가 선언이
`skill.py`/`agent.py`/`config.py`에만 있는지 본다.

**측정의 정직성.** 짧은 kind 이름은 다른 어휘와 충돌한다 — `"agent"`는 훅
핸들러 종류(`model/plugin/hook.py`)·변수 컨텍스트(`view/editors/
variable_loader.py`)·plan kind이기도 하고, `"reference"`는 랩핑 스킬의
`usage` 값이기도 하다. 그래서 기준선에는 순수한 종류 디스패치가 아닌 자리도
섞여 있다. 래칫은 **내려가기만** 하면 되므로 이 섞임이 계약을 약하게 할 뿐
틀리게 하지는 않는다 — 숫자를 줄이는 WP가 실제 자리를 보고 판단한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "daedalus"

#: 컴포넌트 kind 9 + config kind 9 (겹치는 agent/fork_agent 제외) = 16.
COMPONENT_KIND_LITERALS: frozenset[str] = frozenset({
    "procedural_skill", "sync_fork_skill", "async_fork_skill", "declarative_skill",
    "transfer_skill", "reference_skill", "wrapped_skill", "agent", "fork_agent",
    "procedural", "sync_fork", "async_fork", "declarative", "transfer",
    "reference", "wrapped",
})

#: 산출 계획 kind 14종 (REFACTOR_SPEC §2-f `plan_kinds.py`).
PLAN_KIND_LITERALS: frozenset[str] = frozenset({
    "skill", "wrapped_runner", "agent", "skill_file", "hooks_json", "hook_script",
    "workspace_rule", "guide_workflow", "guide_blackboard", "schemas_json",
    "plugin_manifest", "files_tree", "local_wiring", "claude_md",
})

#: plan kind를 세는 범위 — `agent`/`skill`이 컴포넌트 어휘와 겹치기 때문.
PLAN_KIND_SCOPE: tuple[str, ...] = ("compiler", "mcp.tools.query")

#: 리터럴이 정본인 파일 (여기 든 파일은 세지 않는다).
COMPONENT_KIND_ALLOWED_FILES: frozenset[str] = frozenset({
    # 구버전 저장 파일의 kind 문자열을 해석·치환하는 단방향 마이그레이션.
    # 모델 클래스를 참조할 수 없다(이미 사라진 종류도 해석해야 한다).
    "model.serialize.migrate",
})
#: plan kind의 정본 파일 (WP-5에서 신설). 다른 모듈은 이름으로 참조한다 —
#: `emit/guides.py`의 가이드 kind 둘도 여기서 재-export된 것이다.
PLAN_KIND_ALLOWED_FILES: frozenset[str] = frozenset({
    "compiler.plan_kinds",
})

#: 종류 문자열을 **선언**해도 되는 파일.
KIND_DECLARATION_FILES: frozenset[str] = frozenset({
    "model.plugin.skill", "model.plugin.agent", "model.plugin.config",
})

#: 실측 기준선 (2026-09-19, WP-4 완료 — 직렬화 선언화). **내리기만 한다.**
#: WP-3이 걷어낸 자리: `field_matrix`의 표 키 9(→ `XxxConfig.KIND` 참조) ·
#: `deser_plugin`의 `step_kinds`/종류 해소 사다리/"사용 가능" 문구 2 ·
#: `creation.factories` 람다 9 · `fork_skill.KINDS`/`_KIND_CLASSES` ·
#: `props._SKILL_KINDS`/`_AGENT_KINDS`.
#: WP-4가 걷어낸 자리: `deser_plugin`의 `_CONFIG_KINDS` 튜플과 `_deser_config`
#: 종류 사다리 11 → **0**(패키지 전체에서 모듈 하나가 통째로 빠졌다).
#: 직렬화는 이제 kind 문자열을 **비교하지 않는다** — 레지스트리에 묻고
#: 설정 클래스의 `SERIALIZED_FIELDS`를 읽는다. 남은 자리의 주인은 WP-5~WP-8이다.
#: WP-5가 걷어낸 자리: `project_compiler`의 쓰기 루프 kind 사다리 12
#: (컴포넌트 어휘와 겹치는 `skill`/`agent`/`wrapped_runner` 포함) ·
#: `token_report`의 `CONTEXT_KINDS`/`_GUIDE_KINDS` 사본 2 — 산출 계획의
#: kind 문자열은 이제 `compiler/plan_kinds.py` **한 파일**이 소유하고,
#: 계획 행이 `token_kind`/`expands_root`/`phase`를 **값으로** 들고 다닌다.
#: 남은 plan kind 1건(`mcp/tools/query.py`의 `_workspace_doc_signal` 응답 키
#: `"claude_md"`)은 계획 kind가 아니라 **MCP 응답 형상의 키 이름**이다 —
#: 어휘가 겹치는 오탐이고(모듈 docstring "측정의 정직성"), 고치면 응답 형상이
#: 바뀐다. 0으로 내릴 수 없는 유일한 자리라 여기 적어 둔다.
RATCHET: dict[str, int] = {
    "component_kind_sites": 70,
    "component_kind_files": 16,
    "plan_kind_sites": 1,
    "plan_kind_files": 1,
}


# ─────────────────────────── AST 스캐너 ───────────────────────────

def _module_name(path: Path) -> str:
    return path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")


def _dispatch_literals(tree: ast.AST, vocabulary: frozenset[str]) -> set[tuple[int, int, str]]:
    """(줄, 열, 리터럴) — 같은 상수를 두 문맥에서 세지 않도록 위치로 중복 제거."""
    found: set[tuple[int, int, str]] = set()

    def take(node: ast.expr) -> None:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in vocabulary
        ):
            found.add((node.lineno, node.col_offset, node.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for operand in [node.left, *node.comparators]:
                take(operand)
                if isinstance(operand, (ast.Tuple, ast.List, ast.Set)):
                    for element in operand.elts:
                        take(element)
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    take(key)
        elif isinstance(node, (ast.Set, ast.Tuple, ast.List)):
            for element in node.elts:
                take(element)
    return found


def _scan(vocabulary: frozenset[str], allowed: frozenset[str],
          scope: tuple[str, ...] | None = None) -> list[tuple[str, int, str]]:
    sites: list[tuple[str, int, str]] = []
    for path in sorted(_SRC.rglob("*.py")):
        module = _module_name(path)
        if module in allowed:
            continue
        if scope is not None and not any(
            module == prefix or module.startswith(prefix + ".") for prefix in scope
        ):
            continue
        for line, _col, literal in _dispatch_literals(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path)), vocabulary
        ):
            sites.append((module, line, literal))
    return sorted(sites)


def scan_component_kind_literals() -> list[tuple[str, int, str]]:
    return _scan(COMPONENT_KIND_LITERALS, COMPONENT_KIND_ALLOWED_FILES)


def scan_plan_kind_literals() -> list[tuple[str, int, str]]:
    return _scan(PLAN_KIND_LITERALS, PLAN_KIND_ALLOWED_FILES, PLAN_KIND_SCOPE)


def _report(sites: list[tuple[str, int, str]]) -> str:
    return "\n".join(f"  {module}:{line} → {literal!r}" for module, line, literal in sites[:40])


# ─────────────────────────── ① 컴포넌트 kind ───────────────────────────

def test_component_kind_dispatch_literals_do_not_grow():
    sites = scan_component_kind_literals()
    files = {module for module, _line, _literal in sites}
    assert len(sites) <= RATCHET["component_kind_sites"], (
        f"컴포넌트 kind 디스패치 리터럴이 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['component_kind_sites']}). 문자열 대신 "
        f"클래스 선언(`ProceduralSkill.KIND`)을 참조하라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["component_kind_files"], (
        f"kind 리터럴이 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['component_kind_files']}):\n" + _report(sites)
    )


def test_component_kind_baseline_is_not_stale():
    sites = scan_component_kind_literals()
    files = {module for module, _line, _literal in sites}
    assert RATCHET["component_kind_sites"] == len(sites), (
        f"기준선({RATCHET['component_kind_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['component_kind_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["component_kind_files"] == len(files), (
        f"기준선({RATCHET['component_kind_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['component_kind_files']를 {len(files)}로 내려 잠가라."
    )


# ─────────────────────────── ② plan kind ───────────────────────────

def test_plan_kind_literals_do_not_grow():
    sites = scan_plan_kind_literals()
    files = {module for module, _line, _literal in sites}
    assert len(sites) <= RATCHET["plan_kind_sites"], (
        f"plan kind 리터럴이 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['plan_kind_sites']}). 상수 소유자는 "
        f"`compiler/plan_kinds.py` 하나다:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["plan_kind_files"], (
        f"plan kind 리터럴이 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['plan_kind_files']}):\n" + _report(sites)
    )


def test_plan_kind_baseline_is_not_stale():
    sites = scan_plan_kind_literals()
    files = {module for module, _line, _literal in sites}
    assert RATCHET["plan_kind_sites"] == len(sites), (
        f"기준선({RATCHET['plan_kind_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['plan_kind_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["plan_kind_files"] == len(files), (
        f"기준선({RATCHET['plan_kind_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['plan_kind_files']를 {len(files)}로 내려 잠가라."
    )


# ─────────────────────────── 선언 자리 ───────────────────────────

#: 컴포넌트/설정 계층의 기저 클래스 이름 — `kind` 선언 자리를 가려내는 데 쓴다.
#: `AgentHook.kind → "agent"`처럼 **다른 어휘**의 kind를 오인하지 않기 위함이다
#: (훅 핸들러 종류는 컴포넌트 종류가 아니다).
_COMPONENT_BASES: frozenset[str] = frozenset({
    "PluginComponent", "Skill", "StepSkill", "ForkSkill", "Agent",
    "WorkflowComponent", "ComponentConfig", "SkillConfig", "StepSkillConfig",
    "ForkSkillConfig", "AgentConfigBase",
})


def _kind_declarations(klass: ast.ClassDef) -> list[tuple[int, str, str]]:
    """클래스 한 개의 **종류 선언** 목록 — (줄, 형태, 리터럴).

    선언은 두 형태다(§8): ``KIND = "…"`` 클래스 속성과, `kind` property의
    ``return "…"``. WP-2a에서 정본이 전자로 옮겨 갔고 property는
    ``return self.KIND`` 파사드가 됐다 — 두 형태를 다 봐야 스캐너가 이사
    중에도 조용해지지 않는다.
    """
    found: list[tuple[int, str, str]] = []
    for node in klass.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            target = node.targets[0].id
        if target != "KIND":
            continue
        value = node.value
        if isinstance(value, ast.Constant) and value.value in COMPONENT_KIND_LITERALS:
            found.append((node.lineno, "KIND", value.value))
    for node in ast.walk(klass):
        if not isinstance(node, ast.FunctionDef) or node.name != "kind":
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Return)
                and isinstance(inner.value, ast.Constant)
                and inner.value.value in COMPONENT_KIND_LITERALS
            ):
                found.append((inner.lineno, "kind", inner.value.value))
    return found


def test_kind_strings_are_declared_only_in_the_model_modules():
    """컴포넌트·설정 클래스의 `kind` 선언은 모델 3모듈에만 산다.

    다른 모듈이 같은 문자열을 `return`하면 "종류를 말하는 자리"가 둘이 되고,
    한쪽만 고치는 순간 두 사실이 어긋난다. 판정 대상은 **컴포넌트/설정 계층을
    상속한 클래스**로 좁힌다 — 짧은 종류 이름은 다른 어휘와 겹치기 때문이다.
    """
    offenders: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        module = _module_name(path)
        if module in KIND_DECLARATION_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for klass in ast.walk(tree):
            if not isinstance(klass, ast.ClassDef):
                continue
            bases = {
                base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                for base in klass.bases
            }
            if not bases & _COMPONENT_BASES:
                continue
            for lineno, form, literal in _kind_declarations(klass):
                offenders.append(
                    f"{module}:{lineno} {klass.name}.{form} → {literal!r}"
                )
    assert not offenders, (
        "컴포넌트 종류 문자열 선언은 model/plugin/{skill,agent,config}.py에만 "
        "둔다:\n" + "\n".join(offenders)
    )


def test_declaration_scan_actually_sees_the_model_modules():
    """스캐너가 조용히 0을 세지 않는지 — 허용 3모듈에서는 선언이 실제로 보인다."""
    found: list[str] = []
    for module in sorted(KIND_DECLARATION_FILES):
        path = _SRC / (module.replace(".", "/") + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for klass in ast.walk(tree):
            if not isinstance(klass, ast.ClassDef):
                continue
            bases = {
                base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                for base in klass.bases
            }
            if not bases & _COMPONENT_BASES:
                continue
            for _lineno, _form, literal in _kind_declarations(klass):
                found.append(f"{klass.name}:{literal}")
    # 컴포넌트 9종 + config 9종 = 18개의 선언이 있어야 한다.
    assert len(found) == 18, found


def test_allowed_files_exist():
    """허용 파일이 사라지면 허용이 조용히 무의미해진다."""
    for module in COMPONENT_KIND_ALLOWED_FILES | PLAN_KIND_ALLOWED_FILES:
        path = _SRC / (module.replace(".", "/") + ".py")
        assert path.is_file(), f"허용 파일이 없다: {module}"


def test_vocabulary_sizes_are_as_declared():
    """어휘 크기를 고정 — 종류가 늘면 여기서 먼저 걸려 래칫을 다시 재게 한다."""
    assert len(COMPONENT_KIND_LITERALS) == 16
    assert len(PLAN_KIND_LITERALS) == 14


# ── kind 폴백 금지 (WP-1 D5) ──────────────────────────────────────

def _is_type_name_expr(node: ast.expr) -> bool:
    """`type(<무엇>).__name__` 꼴인가."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "type"
    )


def _kind_type_name_fallbacks() -> list[tuple[str, int]]:
    """`getattr(x, "kind", type(x).__name__)` 전수 — (모듈, 줄)."""
    sites: list[tuple[str, int]] = []
    for path in sorted(_SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) == 3):
                continue
            key, fallback = node.args[1], node.args[2]
            if (isinstance(key, ast.Constant) and key.value == "kind"
                    and _is_type_name_expr(fallback)):
                sites.append((_module_name(path), node.lineno))
    return sites


def test_kind_is_never_read_with_a_class_name_fallback():
    """`kind`는 모든 컴포넌트의 `@abstractmethod` property다 — 폴백은 죽은 코드다.

    D5(카탈로그 F11): `getattr(comp, "kind", type(comp).__name__)`는 **도달할
    수 없는** 분기(스멜 ③)이면서, 컴포넌트가 아닌 것이 흘러들어 왔을 때의
    실패를 클래스 이름으로 **가린다**(원칙 5) — 화면·MCP 응답에 종류 대신
    `"SimpleState"` 같은 문자열이 조용히 실린다. `comp.kind`로 직접 묻는다.

    (config에서 읽는 `getattr(config, "kind", None)` 꼴은 config 자체가
    None일 수 있는 자리라 여기 대상이 아니다 — 그쪽은 종류 리터럴 비교와
    함께 WP-2b/WP-2d가 소유한다.)
    """
    sites = _kind_type_name_fallbacks()
    assert sites == [], (
        "`kind`의 클래스 이름 폴백은 도달 불가 죽은 코드이자 실패 은폐다 — "
        "`x.kind`로 바꿔라:\n"
        + "\n".join(f"  {m}:{ln}" for m, ln in sites)
    )
